"""
Upload pushed files to Snowflake (the "landing zone -> stage" step).

Runs in GitHub Actions on every push that touches data/, or locally.

For every new or changed file under data/initial/ or data/incoming/:
  1. profile it (MD5, row counts, header, parse check)        -> file_profiler.py
  2. run pre-load checks (empty, schema, volume, encoding)    -> never block
  3. PUT it to a UNIQUE stage path:
        @RAW.STG_BATCH/<source>/<entity>/<yyyy>/<mm>/<dd>/<commit>/<file>
     so a re-sent file with the same name is never silently skipped
  4. write AUDIT.FILE_REGISTRY + AUDIT.PRELOAD_CHECK_LOG
  5. stream files: ALTER PIPE ... REFRESH PREFIX = '<that folder>'  (Snowpipe loads in ~1 min)
     batch files:  wait for the 10-minute task, or use --load-now

Examples
  python scripts/ingest_files.py --git-range <before_sha> <after_sha>    # what GitHub Actions runs
  python scripts/ingest_files.py --all                                  # every file under data/
  python scripts/ingest_files.py --files data/incoming/sap/po_items/x.csv --load-now
  python scripts/ingest_files.py --all --dry-run                        # no Snowflake, just profile
"""

from __future__ import annotations

import argparse
import os
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from file_profiler import Check, profile_file          # noqa: E402
from source_config import PIPE_NAME, entity_for_path   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ZERO_SHA = "0" * 40
VOLUME_TOLERANCE = float(os.getenv("VOLUME_TOLERANCE", "0.30"))   # +/- 30 %


# ------------------------------------------------------------- git helpers --

def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def files_from_git_range(before: str, after: str) -> list[str]:
    if not before or before == ZERO_SHA:
        out = git("ls-tree", "-r", "--name-only", after, "--", "data")
    else:
        out = git("diff", "--name-only", "--diff-filter=AM", before, after, "--", "data")
    return [l for l in out.splitlines() if l]


def all_data_files() -> list[str]:
    return sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "data").rglob("*") if p.is_file())


def commit_info() -> tuple[str, str]:
    sha = os.getenv("GITHUB_SHA")
    if not sha:
        try:
            sha = git("rev-parse", "HEAD").strip()
        except Exception:
            sha = "local"
    actor = os.getenv("GITHUB_ACTOR")
    if not actor:
        try:
            actor = git("config", "user.name").strip() or "local"
        except Exception:
            actor = "local"
    return sha, actor


# ------------------------------------------------------------------- main ---

def select_files(paths: list[str]) -> list[str]:
    keep = []
    for p in paths:
        if Path(p).name.startswith(".") or Path(p).name.lower() == "readme.md":
            continue
        if entity_for_path(p) is None:
            print(f"  skip (not a known entity folder): {p}")
            continue
        if not (ROOT / p).exists():
            print(f"  skip (deleted): {p}")
            continue
        keep.append(p)
    # initial load first, then incoming; alphabetical inside each
    return sorted(keep, key=lambda p: (0 if p.startswith("data/initial/") else 1, p))


def volume_check(cur, entity_key: str, rows: int, repo_path: str) -> Check:
    if not repo_path.startswith("data/incoming/"):
        return Check("VOLUME", "PASS", "initial load: no volume baseline")
    if rows <= 0:
        return Check("VOLUME", "PASS", "no data rows (see NOT_EMPTY)")
    cur.execute(
        """SELECT DATA_ROW_COUNT FROM AUDIT.FILE_REGISTRY
           WHERE ENTITY = %s AND REPO_PATH LIKE 'data/incoming/%%' AND DATA_ROW_COUNT > 0
           ORDER BY REGISTRY_ID DESC LIMIT 5""", (entity_key,))
    hist = [r[0] for r in cur.fetchall()]
    if not hist:
        return Check("VOLUME", "PASS", "first incoming file for this entity")
    avg = statistics.mean(hist)
    low, high = avg * (1 - VOLUME_TOLERANCE), avg * (1 + VOLUME_TOLERANCE)
    if low <= rows <= high:
        return Check("VOLUME", "PASS", f"{rows} rows vs avg {avg:.0f} of last {len(hist)}")
    return Check("VOLUME", "WARN",
                 f"{rows} rows is outside +/-{VOLUME_TOLERANCE:.0%} of avg {avg:.0f} (last {len(hist)} files)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--git-range", nargs=2, metavar=("BEFORE", "AFTER"))
    g.add_argument("--files", nargs="+")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="profile only, no Snowflake connection")
    ap.add_argument("--load-now", action="store_true",
                    help="after upload, run the batch load + DQ immediately instead of waiting for the task")
    args = ap.parse_args()

    if args.git_range:
        candidates = files_from_git_range(*args.git_range)
    elif args.files:
        candidates = [Path(f).as_posix() for f in args.files]
    else:
        candidates = all_data_files()
    files = select_files(candidates)
    if not files:
        print("No data files to upload.")
        return 0

    sha, actor = commit_info()
    short = sha[:10]
    today = datetime.now(timezone.utc)
    date_path = today.strftime("%Y/%m/%d")
    print(f"Commit {short} by {actor}: {len(files)} file(s)")

    conn = cur = None
    db = os.getenv("SNOWFLAKE_DATABASE", "S2C_DEV")
    if not args.dry_run:
        from sf_connect import connect, database
        conn = connect()
        db = database()
        cur = conn.cursor()
        cur.execute(f"USE DATABASE {db}")

    stream_prefixes: set[str] = set()
    uploaded = 0
    with tempfile.TemporaryDirectory() as tmp:
        for repo_path in files:
            ent = entity_for_path(repo_path)
            local = ROOT / repo_path
            prof = profile_file(local, ent, Path(tmp))
            # sub folders under the entity (e.g. redelivery_20261103/) are kept, so two files with
            # the same name in one push never collide
            sub = "/".join(repo_path.split("/")[4:-1])
            folder = f"{ent.stage_prefix}/{date_path}/{short}" + (f"/{sub}" if sub else "")
            stage_path = f"{folder}/{prof.upload_path.name}"
            if cur is not None:
                prof.checks.append(volume_check(cur, ent.key, prof.data_row_count, repo_path))

            flag = " ".join(f"{c.name}={c.status}" for c in prof.checks if c.status != "PASS") or "all checks PASS"
            print(f"- {repo_path}\n    -> @{ent.stage}/{stage_path}  rows={prof.data_row_count}  {flag}")
            if args.dry_run:
                continue

            # idempotent: the same commit + file is never registered twice (e.g. a re-run job)
            cur.execute("SELECT COUNT(*) FROM AUDIT.FILE_REGISTRY WHERE STAGE_NAME = %s AND STAGE_PATH = %s",
                        (ent.stage, stage_path))
            if cur.fetchone()[0] > 0:
                print("    already uploaded for this commit - skipped")
                continue

            put_target = f"@{db}.RAW.{ent.stage}/{folder}/"
            cur.execute(f"PUT 'file://{prof.upload_path.resolve().as_posix()}' '{put_target}' "
                        f"AUTO_COMPRESS = FALSE OVERWRITE = FALSE PARALLEL = 4")
            cur.execute(
                """INSERT INTO AUDIT.FILE_REGISTRY
                     (ENTITY, REPO_PATH, FILE_NAME, STAGE_NAME, STAGE_PATH, FILE_TYPE, MD5, SIZE_BYTES,
                      DATA_ROW_COUNT, EXPECTED_RAW_ROWS, HEADER_TEXT, COMMIT_SHA, PUSHED_BY)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (ent.key, repo_path, local.name, ent.stage, stage_path, ent.file_type, prof.md5, prof.size_bytes,
                 prof.data_row_count, prof.expected_raw_rows,
                 (ent.csv_delimiter or ",").join(prof.header) if prof.header else None, sha, actor))
            cur.executemany(
                """INSERT INTO AUDIT.PRELOAD_CHECK_LOG (STAGE_PATH, FILE_NAME, ENTITY, CHECK_NAME, STATUS, DETAIL)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [(stage_path, local.name, ent.key, c.name, c.status, c.detail[:2000]) for c in prof.checks])
            uploaded += 1
            if ent.load_mode == "STREAM":
                # PREFIX is relative to the pipe's stage path (@STG_STREAM/risk_events/)
                stream_prefixes.add(f"{date_path}/{short}/")

    if args.dry_run:
        print("Dry run: nothing uploaded.")
        return 0

    for prefix in sorted(stream_prefixes):
        cur.execute(f"ALTER PIPE {db}.{PIPE_NAME} REFRESH PREFIX = '{prefix}'")
        print(f"Snowpipe notified for risk_events/{prefix}: {len(cur.fetchall())} file(s) queued")

    if args.load_now:
        for call in ("CALL AUDIT.SP_LOAD_BATCH()", "CALL AUDIT.SP_COLLECT_LOAD_HISTORY()", "CALL AUDIT.SP_RUN_DQ(TRUE)"):
            cur.execute(call)
            print(f"{call}: {cur.fetchone()[0]}")

    print(f"Uploaded {uploaded} file(s). Batch files load on the next 10-minute task run "
          f"(or run with --load-now); stream files load via Snowpipe in about a minute.")
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
