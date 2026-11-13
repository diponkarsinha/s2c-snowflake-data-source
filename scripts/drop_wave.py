"""
Drop a wave: copy pending/wave_NN/ into the repo, then (optionally) commit and push.

The push triggers GitHub Actions, which uploads the new files to Snowflake.
This simulates source systems delivering new files over time.

Examples
  python scripts/drop_wave.py --list          # show all waves and which are already dropped
  python scripts/drop_wave.py 1               # copy wave 1 into data/incoming/ (no git)
  python scripts/drop_wave.py 1 --push        # copy, git add, commit and push
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "pending"


def waves() -> list[dict]:
    p = ROOT / "answer_key" / "waves.json"
    return json.loads(p.read_text()) if p.exists() else []


def wave_files(n: int) -> list[Path]:
    d = PENDING / f"wave_{n:02d}"
    return sorted(p for p in d.rglob("*") if p.is_file() and p.name != "WAVE.md")


def is_dropped(n: int) -> bool:
    files = wave_files(n)
    return bool(files) and all((ROOT / f.relative_to(PENDING / f"wave_{n:02d}")).exists() for f in files)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wave", nargs="?", type=int)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--push", action="store_true", help="git add + commit + push after copying")
    args = ap.parse_args()

    if not PENDING.exists():
        print("pending/ not found. Run: python generator/generate_data.py")
        return 1

    if args.list or args.wave is None:
        for w in waves():
            mark = "dropped" if is_dropped(w["wave"]) else "pending"
            print(f"  wave {w['wave']:>2}  [{mark:7}]  {w['path']:6}  {w['title']}")
        return 0

    n = args.wave
    files = wave_files(n)
    if not files:
        print(f"wave {n} has no files")
        return 1
    meta = next((w for w in waves() if w["wave"] == n), {"title": f"wave {n}"})
    print(f"Wave {n}: {meta['title']}")
    for f in files:
        rel = f.relative_to(PENDING / f"wave_{n:02d}")
        dst = ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        print(f"  + {rel.as_posix()}")
    print(f"\nWhat should happen: {meta.get('expect', '')}")
    print(f"Details: pending/wave_{n:02d}/WAVE.md")

    if args.push:
        rels = [f.relative_to(PENDING / f"wave_{n:02d}").as_posix() for f in files]
        subprocess.run(["git", "add", *rels], cwd=ROOT, check=True)
        subprocess.run(["git", "commit", "-m", f"data: drop wave {n:02d} - {meta['title']}"], cwd=ROOT, check=True)
        subprocess.run(["git", "push"], cwd=ROOT, check=True)
        print("\nPushed. Watch the 'Ingest to Snowflake' workflow in the GitHub Actions tab.")
    else:
        print("\nNext: git add data && git commit -m \"data: drop wave %02d\" && git push" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
