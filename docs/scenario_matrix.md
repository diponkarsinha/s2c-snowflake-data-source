# Scenario matrix: waves → scenarios → what each one tests

Each delivery wave plants a specific problem. This shows what to look at in Snowflake and which skill it tests.

## By wave

| Wave | Scenario | Look at in Snowflake | SQL | Python | Snowflake / files | dbt |
|---|---|---|---|---|---|---|
| initial | Full history, 144 planted business issues | `V_FILE_LINEAGE`, RAW row counts, `V_DQ_LATEST_RESULTS` | Basics, joins, aggregation, windows, recursive (taxonomy, approvals) | pandas on every format, Excel conversion | Stages, file formats, COPY, XMLGET, FLATTEN, Parquet | Sources, staging, golden supplier, star schema |
| 01 | Normal daily batch | Task history, `FILE_LOAD_LOG` | Incremental "new since" queries | Volume baseline | Task graph, load metadata | Incremental models |
| 02 | Risk stream + spike | `RISK_EVENTS`, `RISK_CURRENT`, `RISK_ALERTS` | LAG for score jumps | NDJSON parsing | Snowpipe, streams, tasks, `SYSTEM$STREAM_HAS_DATA` | Source freshness, reconcile speed → batch |
| 03 | Exact duplicate file | AUD-F02, RAW duplicates | Dedup with QUALIFY | MD5 of a file | Load history vs unique paths | Staging dedup |
| 04 | Same content, new name | AUD-F04 | Find duplicate rows across files | Hash-based duplicate detection | Why load metadata cannot catch it | `unique` tests |
| 05 | Same name, new content | AUD-F03, both versions in RAW | Latest version per key | Compare two file versions | Snowpipe silent skip vs COPY reload | Keep latest by `AEDAT` / `_LOADED_AT` |
| 06 | Bad rows | AUD-R02/R03/R04/R06, `V_ROW_DQ_STATUS` | `TRY_TO_NUMBER`, `TRY_TO_DATE` | Validate rows before load, encodings | `ON_ERROR`, column-count mismatch, `REPLACE_INVALID_CHARACTERS` | Quarantine models |
| 07 | Late, changed, deleted | AUD-R08, AUD-R01 | Watermarks, latest change | Late-data detection | Change tracking | Incremental lookback, soft deletes |
| 08 | Supplier master changes | New IDoc file, duplicate VAT | SCD2 queries, valid_from / valid_to | Diff two snapshots | Full reload pattern | `dbt snapshot` (check strategy) |
| 09 | Schema drift | AUD-S01/S02, `_EXTRA_1`, v2 events | Header comparison | Schema check | Positional loads, `MATCH_BY_COLUMN_NAME` trade-offs | Contracts, `on_schema_change` |
| 10 | Contract + sourcing updates | New JSON deltas, AUD-R09 | Overlapping contracts, cycle time, FLATTEN pages | Pagination | Multi-level FLATTEN | Snapshot contract status |
| 11 | Empty, header-only, bulk | AUD-F01, AUD-F08 | - | Chunked reading, memory | File sizing, PARALLEL in PUT | - |
| 12 | Stream chaos, Excel, FX | `RISK_DEAD_LETTER`, `RISK_CURRENT`, AUD-R12/R14 | Out-of-order handling, gaps | Excel quirks, dd/mm dates | MERGE with event time, dead letter | Savings validation tests |

## Design questions: where to look in this repo

| Question | Where to look |
|---|---|
| "How do you make sure no data is lost?" | Unique stage paths, all-VARCHAR RAW, AUD-F05/F06, dead letter (`docs/architecture.md`) |
| "Batch or streaming, and why?" | Risk = stream (compliance needs minutes), everything else = batch (`docs/decision_log.md` DEC-04) |
| "How do you handle duplicates?" | Waves 3, 4, 5: three different duplicate types and three different defences |
| "How do you know your DQ checks work?" | `answer_key/planted_issues.csv` + `scripts/check_planted.py` |
| "Schema change in a source?" | Wave 9: data still lands, drift is flagged, mapping is updated in dbt |
| "Late or out-of-order data?" | Wave 7 (batch watermark) and wave 12 (event-time MERGE) |
| "How do you control cost?" | XS warehouse, resource monitor, skip-if-nothing-new, `WHEN SYSTEM$STREAM_HAS_DATA` |
| "Secrets and security?" | Key-pair service user, GitHub secrets, RBAC roles, masking policy |
