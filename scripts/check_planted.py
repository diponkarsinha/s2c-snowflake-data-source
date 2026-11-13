"""
Prove the audit layer works: compare what we planted (answer_key/planted_issues.csv)
with what Snowflake actually caught.

  caught      the expected rule / stream behaviour found the record
  MISSED      the file was delivered but the check did not find it  -> investigate
  not yet     the file has not been pushed yet
  dbt         caught later by dbt tests in s2c-dbt-analytics (not checked here)

Usage
  python scripts/check_planted.py            # summary + every MISSED item
  python scripts/check_planted.py --all      # list every item
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sf_connect import connect  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    planted = list(csv.DictReader(open(ROOT / "answer_key" / "planted_issues.csv", encoding="utf-8")))
    conn = connect()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT FILE_NAME FROM AUDIT.FILE_REGISTRY")
    delivered = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT RULE_ID, RECORD_KEY FROM AUDIT.DQ_FAILED_RECORDS")
    failed = {(r[0], r[1]) for r in cur.fetchall()}
    cur.execute("SELECT EVENT_ID, REJECT_REASON FROM STREAMING.RISK_DEAD_LETTER")
    dead = {}
    for eid, why in cur.fetchall():
        dead.setdefault(eid, set()).add(why)
    cur.execute("SELECT EVENT_ID, ALERT_TYPE FROM STREAMING.RISK_ALERTS")
    alerts = {}
    for eid, t in cur.fetchall():
        alerts.setdefault(eid, set()).add(t)
    cur.execute("SELECT EVENT_ID, IS_LATE FROM STREAMING.RISK_EVENT_LOG")
    logged = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT LAST_EVENT_ID FROM STREAMING.RISK_CURRENT")
    current_ids = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT COUNT(*) FROM RAW.RISK_EVENTS WHERE _FILE_NAME LIKE '%risk_events_20261112_02_burst%'")
    burst_rows = cur.fetchone()[0]
    conn.close()

    results = []
    for p in planted:
        f = p["file_name"]
        was_delivered = any(fnmatch.fnmatch(d, f) for d in delivered)
        if p["caught_by"] == "dbt":
            status = "dbt"
        elif not was_delivered:
            status = "not yet"
        elif p["caught_by"] == "audit":
            key = f if p["record_key"] == "(file)" else p["record_key"]
            status = "caught" if (p["expected_check"], key) in failed else "MISSED"
        else:  # stream behaviour
            k, t = p["record_key"], p["issue_type"]
            ok = {
                "risk_spike": "HIGH_RISK" in alerts.get(k, set()) or "SCORE_JUMP" in alerts.get(k, set()),
                "payload_v2_sanctions": "SANCTIONS_HIT" in alerts.get(k, set()),
                "duplicate_event": "DUPLICATE_EVENT" in dead.get(k, set()) and k in logged,
                "invalid_event": k in dead and k not in logged,
                "out_of_order": k in logged and k not in current_ids and k not in alerts,
                "late_event": bool(logged.get(k)),
                "burst": burst_rows == 500,
            }.get(t, False)
            status = "caught" if ok else "MISSED"
        results.append((status, p))

    counts = Counter(s for s, _ in results)
    print("Planted issues vs. what Snowflake caught")
    for s in ("caught", "MISSED", "not yet", "dbt"):
        print(f"  {s:8} {counts.get(s, 0)}")
    show = results if args.all else [r for r in results if r[0] == "MISSED"]
    if show:
        print()
        for s, p in show:
            print(f"  [{s:7}] {p['issue_id']} {p['wave']:8} {p['issue_type']:24} {p['record_key']:28} "
                  f"{p['expected_check']}")
    return 1 if counts.get("MISSED") else 0


if __name__ == "__main__":
    sys.exit(main())
