"""
Run one or more .sql files against Snowflake (an alternative to pasting them into Snowsight).

Examples
  python scripts/run_sql.py snowflake/02_file_formats_stages.sql
  python scripts/run_sql.py --setup                         # runs 02..11 in order as S2C_ADMIN
  python scripts/run_sql.py snowflake/ops/check_status.sql
  python scripts/run_sql.py --db S2C_PROD --setup           # build a second environment

01_account_setup.sql needs ACCOUNTADMIN: run it once in Snowsight (or with --role ACCOUNTADMIN).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sf_connect import connect  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SETUP_FILES = [
    "02_file_formats_stages.sql", "03_raw_tables.sql", "04_audit_tables.sql", "05_load_procedures.sql",
    "06_stream_risk.sql", "07_dq_rules.sql", "08_dq_procedure.sql", "09_tasks.sql",
    "10_monitoring_views.sql", "11_governance.sql",
]


def run_file(conn, path: Path, db: str) -> None:
    sql = path.read_text(encoding="utf-8")
    if db != "S2C_DEV":
        sql = sql.replace("S2C_DEV", db)
    print(f"\n=== {path.relative_to(ROOT)} ===")
    for cur in conn.execute_string(sql, remove_comments=True):
        first = (cur.query or "").strip().split()[0].upper() if cur.query else ""
        if first in ("SELECT", "SHOW", "CALL", "WITH", "DESCRIBE", "DESC", "LIST"):
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            print("  " + " | ".join(cols))
            for r in rows[:25]:
                print("  " + " | ".join("" if v is None else str(v) for v in r))
            if len(rows) > 25:
                print(f"  ... {len(rows) - 25} more rows")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--setup", action="store_true", help="run snowflake/02..11 in order")
    ap.add_argument("--db", default="S2C_DEV")
    ap.add_argument("--role", default="S2C_ADMIN")
    args = ap.parse_args()

    files = [ROOT / "snowflake" / f for f in SETUP_FILES] if args.setup else [Path(f).resolve() for f in args.files]
    if not files:
        ap.print_help()
        return 1
    conn = connect(role=args.role)
    try:
        for f in files:
            run_file(conn, f, args.db)
    finally:
        conn.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
