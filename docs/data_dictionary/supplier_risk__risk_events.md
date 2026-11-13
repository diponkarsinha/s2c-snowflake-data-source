# Supplier risk events (stream)

Score changes pushed as they happen. Feeds STREAMING.RISK_CURRENT and RISK_ALERTS.

| | |
|---|---|
| **Entity folder** | `data/*/supplier_risk/risk_events/` |
| **Source system** | Third-party risk provider (fictional 'RiskCo') |
| **File name** | `risk_events_YYYYMMDD_NN.ndjson` |
| **Format** | NDJSON (one JSON event per line) |
| **Grain** | One row per event |
| **Business key** | `event_id` |
| **Load pattern** | STREAM: Snowpipe -> stream -> task (about 1 minute) |
| **RAW table** | `RAW.RISK_EVENTS (VARIANT)` |

## Columns

| Column | Source type | Nullable | Description | Sensitivity | Known / planted issues |
|---|---|---|---|---|---|
| `event_id` | text | No | Unique event ID | Internal | Wave 12: duplicates |
| `event_type` | text | No | RISK_SCORE_CHANGED | Internal |  |
| `payload_version` | int | No | 1 or 2 (v2 adds sanctions_hit, data_provider_ref) | Internal | Wave 12: version 3 -> dead letter |
| `supplier_vat` | text | No | Supplier VAT | Confidential | Wave 12: empty |
| `risk_score` | int | No | 1-9 | Licensed | Wave 12: 15 and 'high' |
| `previous_score` | int | Yes | Score before | Licensed |  |
| `reason` | text | Yes | Why it changed | Internal |  |
| `event_time` | ISO timestamp | No | When it happened (UTC) | Internal | Wave 12: out of order and 6 hours late |
| `sanctions_hit` | boolean | v2 only | Supplier on a sanctions list | Confidential |  |

## RAW lineage columns (every table)

`_FILE_NAME` (stage path incl. commit), `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY` (checksum), `_FILE_LAST_MODIFIED`, `_LOADED_AT`.

## Sample

_(no sample in data/initial)_
