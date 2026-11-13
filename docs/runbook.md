# Runbook

## Daily use while testing

| I want to... | Do this |
|---|---|
| Start the pipeline | `snowflake/ops/resume_tasks.sql` (or `make resume`) |
| Stop it (save credits) | `snowflake/ops/suspend_tasks.sql` (or `make suspend`) |
| Load right now, without waiting 10 minutes | `snowflake/ops/run_now.sql` (or `make run-now`) |
| See what happened | `snowflake/ops/check_status.sql` (or `make status`) |
| Prove the checks work | `python scripts/check_planted.py` |
| Replay everything from scratch | `snowflake/ops/reset_dev.sql`, then re-run the GitHub workflow manually ("Run workflow" → all) |
| Test something risky | `snowflake/ops/zero_copy_clone.sql` |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| GitHub Action fails at "Upload" with an auth error | Wrong secret, or the public key is not set on `S2C_INGEST_SVC` | `DESC USER S2C_INGEST_SVC;` and check `RSA_PUBLIC_KEY_FP`; re-paste the secret including the BEGIN/END lines |
| Action says "No data files to upload" | The push did not change anything under `data/` | Expected. Git ignores unchanged files. |
| Batch files never reach RAW | Tasks suspended | `SHOW TASKS IN DATABASE S2C_DEV;` → resume |
| Risk files never reach RAW | Pipe not refreshed or paused | `SELECT SYSTEM$PIPE_STATUS('S2C_DEV.RAW.PIPE_RISK_EVENTS');` then `ALTER PIPE ... REFRESH;` |
| `RISK_EVENTS` has rows but `RISK_CURRENT` does not change | Stream task suspended or failing | `TASK_HISTORY` (in `check_status.sql`); AUD-T03 fires after 10 minutes |
| Gate says BLOCKED | AUD-F05/F06/F07 open | `ops/acknowledge_issue.sql` shows the records; fix and reload, or acknowledge with a note |
| AUD-F05 for a file that is in RAW | `COPY_HISTORY` not collected yet | Wait for the next task run or `CALL AUDIT.SP_COLLECT_LOAD_HISTORY();` |
| `RULE_ERROR` in `V_DQ_LATEST_RESULTS` | A rule's SQL fails | `ERROR_MESSAGE` column shows why; fix in `07_dq_rules.sql` and re-run that file |
| Parquet files missing locally | `pyarrow` not installed when generating | `pip install -r requirements.txt`, then `python generator/generate_data.py --clean` |
| Credits rising | Tasks left running | Suspend tasks; the resource monitor stops the warehouse at 20 credits/month |

## Production checklist (what would change)

- Root task schedule: `USING CRON 0 6 * * * Europe/Prague` instead of every 10 minutes
- External stage on Azure ADLS + `AUTO_INGEST = TRUE` + storage integration
- Stage retention: remove files older than 64 days (after load metadata expires)
- Alerts: Snowflake `ALERT` objects or email notifications on task failure and gate = BLOCKED
- Separate `S2C_PROD` database (`python scripts/run_sql.py --db S2C_PROD --setup`) and a prod service user
- Key rotation every 90 days (`RSA_PUBLIC_KEY_2`)
