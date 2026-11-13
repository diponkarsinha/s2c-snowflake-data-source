# Data quality rules (pre-dbt audit layer)

Rules live in `AUDIT.DQ_RULES` (source: `snowflake/07_dq_rules.sql`). `SP_RUN_DQ` runs them after every batch load. Each rule is one SQL query that returns the failing records, keyed by file and row, so dbt can quarantine exactly those rows.

**Severity:** ERROR = row is quarantined by dbt · WARN = kept and reported · INFO = for awareness.  
**Blocking:** data is incomplete, so dbt must not publish Gold until it is fixed or acknowledged.

Business rules (blocked supplier, maverick spend, savings maths, contract dates, ...) are dbt tests in `s2c-dbt-analytics`. This layer answers one question: *did the data arrive complete and technically usable?*

| Rule | Level | Name | Severity | Blocking | What it checks | What happens |
|---|---|---|---|---|---|---|
| `AUD-F01` | FILE | Empty or header-only file | WARN | No | File was delivered but contains no data rows. | Logged only. Nothing to load. |
| `AUD-F02` | FILE | Exact duplicate delivery (same name, same content) | WARN | No | A file with the same name and the same MD5 was delivered before (e.g. an SAP re-extract). | File still lands in RAW. dbt staging keeps one row per business key. |
| `AUD-F03` | FILE | Same file name, different content | WARN | No | A file with a name seen before arrived with different content (a correction, or an overwrite). | Both versions land. dbt keeps the latest version of each record (by change date / load time). |
| `AUD-F04` | FILE | Same content, different file name | WARN | No | The same content (MD5) arrived again under a new name. Snowflake load history cannot catch this. | File lands. RAW holds duplicates; dbt staging de-duplicates on the business key. |
| `AUD-F05` | FILE | Uploaded but not loaded | ERROR | **Yes** | File was uploaded to a stage more than 30 minutes ago but no load is recorded (silent skip, failed pipe, suspended task). | BLOCKS Gold. Investigate, reload, then acknowledge. |
| `AUD-F06` | FILE | Row count mismatch (file vs RAW) | ERROR | **Yes** | Rows loaded into RAW differ from rows counted in the file before upload. | BLOCKS Gold. Data is incomplete. |
| `AUD-F07` | FILE | Load errors reported by Snowflake | ERROR | **Yes** | COPY / Snowpipe reported rejected rows or a failed file. | BLOCKS Gold. Fix the file or the file format, reload. |
| `AUD-F08` | FILE | Unusual file volume | WARN | No | Row count is more than 30% away from the average of the last 5 deliveries of the same entity. | Logged. Someone checks whether it is a real spike or a broken extract. |
| `AUD-S01` | SCHEMA | Schema drift (header changed) | ERROR | No | CSV/Excel header differs from the expected header (renamed, added or missing columns). | Data still lands (positional columns + _EXTRA_n). Update the mapping in dbt staging, then acknowledge. |
| `AUD-S02` | SCHEMA | PO header in RAW differs from expected | ERROR | No | Same check as AUD-S01 but done inside Snowflake on row 1 of every PO file. | Shows drift can be detected without the uploader. |
| `AUD-R01` | ROW | PO line delivered more than once | WARN | No | The same EBELN + EBELP appears in more than one row (re-extracts, corrections, changes). | Expected for changes. dbt keeps the latest version (AEDAT, then load time). |
| `AUD-R02` | ROW | PO quantity / price / value not numeric | ERROR | No | MENGE, NETPR or NETWR cannot be read as a number (text, shifted columns). | Row is quarantined by dbt. |
| `AUD-R03` | ROW | PO line missing a key field | ERROR | No | EBELN, EBELP or LIFNR is empty. | Row is quarantined by dbt. |
| `AUD-R04` | ROW | PO date invalid | ERROR | No | BEDAT or AEDAT is not a valid YYYYMMDD date. | Row is quarantined by dbt. |
| `AUD-R05` | ROW | PO value <> quantity x price | WARN | No | NETWR differs from MENGE x NETPR / PEINH by more than 1%. | Logged; row kept. Finance checks the line. |
| `AUD-R06` | ROW | Invalid characters (encoding) | WARN | No | Text contains U+FFFD: the file had bytes that are not valid UTF-8 (e.g. Latin-1). | Row kept; text is cleaned in dbt. Ask the source to send UTF-8. |
| `AUD-R07` | ROW | Invoice line delivered more than once | WARN | No | The same BELNR + GJAHR + BUZEI appears more than once. | dbt keeps one row per invoice line. |
| `AUD-R08` | ROW | Late-arriving invoice | INFO | No | Posting date is more than 30 days older than the newest posting date loaded before this file. | Row kept. dbt incremental models must use a lookback window to pick it up. |
| `AUD-R09` | ROW | Request updated before it was created | WARN | No | updated_at is earlier than created_at (clock / timezone problem in the source). | Row kept. dbt uses GREATEST(created_at, updated_at) for change tracking. |
| `AUD-R10` | ROW | Contract without contractId | ERROR | No | A contract record has no ID, so it cannot be tracked. | Record is quarantined by dbt. |
| `AUD-R11` | ROW | Risk score out of range | WARN | No | financialRisk must be between 1 and 9. | Row kept; dbt sets the score to NULL and the supplier counts as "not assessed". |
| `AUD-R12` | ROW | Non-data row in the savings sheet | WARN | No | Hand-made TOTAL row or blank row in the Excel tracker. | Row kept in RAW; dbt filters it out. |
| `AUD-R13` | ROW | Mixed boolean types (autoRenew) | INFO | No | autoRenew arrives as true/false, "Y"/"N" or "true" (text). | dbt normalises it with a macro. |
| `AUD-R14` | ROW | Savings date not ISO (typed by hand) | INFO | No | Savings Date is text like 03/10/2026 instead of a real date. | dbt parses DD/MM/YYYY explicitly (never MM/DD). |
| `AUD-T01` | STREAM | Risk events sent to dead letter | WARN | No | Events the speed layer could not process (invalid, duplicate, unsupported version). | Kept in RISK_DEAD_LETTER; fix and replay if needed. |
| `AUD-T02` | STREAM | Snowpipe not running | WARN | No | The pipe is paused or stalled, so streaming files will not load. | Resume the pipe: ALTER PIPE ... SET PIPE_EXECUTION_PAUSED = FALSE. |
| `AUD-T03` | STREAM | Stream backlog not processed | WARN | No | Events loaded more than 10 minutes ago are neither in RISK_EVENT_LOG nor in the dead letter (task suspended or failing). | Check TASK_PROCESS_RISK_EVENTS history. (We compare tables instead of reading the stream, so this check never consumes it.) |

## Checks that run before upload (Python, `scripts/file_profiler.py`)

| Check | Status if it fails | Logged to |
|---|---|---|
| `NOT_EMPTY` file has data rows | WARN | `PRELOAD_CHECK_LOG` → AUD-F01 |
| `ENCODING` file is valid UTF-8 | WARN | `PRELOAD_CHECK_LOG` |
| `SCHEMA` header equals the expected header | FAIL | `PRELOAD_CHECK_LOG` → AUD-S01 |
| `PARSE` JSON / XML / Parquet / Excel can be read | FAIL | `PRELOAD_CHECK_LOG` |
| `VOLUME` rows within ±30% of the last 5 deliveries | WARN | `PRELOAD_CHECK_LOG` → AUD-F08 |

None of these block the upload. The file always lands; the result is logged.

## Stream checks (inside `SP_PROCESS_RISK_EVENTS`)

| Check | Result |
|---|---|
| `event_id` missing | dead letter `MISSING_EVENT_ID` |
| `payload_version` not 1 or 2 | dead letter `UNSUPPORTED_PAYLOAD_VERSION` |
| `supplier_vat` missing | dead letter `MISSING_SUPPLIER_VAT` |
| `risk_score` not a number / outside 1-9 | dead letter `RISK_SCORE_NOT_NUMERIC` / `RISK_SCORE_OUT_OF_RANGE` |
| `event_time` not a timestamp | dead letter `INVALID_EVENT_TIME` |
| `event_id` already processed or repeated in the batch | dead letter `DUPLICATE_EVENT` (first copy is processed) |
| older `event_time` than the current score | logged, but does not overwrite `RISK_CURRENT` and raises no alert |
| `event_time` > 1 hour behind the event-time watermark | `IS_LATE = TRUE` |

## Useful queries

```sql
-- latest result per rule
SELECT * FROM S2C_DEV.AUDIT.V_DQ_LATEST_RESULTS ORDER BY STATUS, SEVERITY;

-- is dbt allowed to publish Gold?
SELECT * FROM S2C_DEV.AUDIT.V_PIPELINE_GATE;

-- which RAW rows are flagged (dbt joins this)
SELECT * FROM S2C_DEV.AUDIT.V_ROW_DQ_STATUS WHERE DQ_STATUS = 'ERROR';
```
