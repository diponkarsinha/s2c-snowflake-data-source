# Drop plan: initial load + 12 waves

Push the initial load first, then drop one wave at a time and watch what happens.

```bash
python scripts/drop_wave.py --list      # status of every wave
python scripts/drop_wave.py 1 --push    # copy wave 1 into data/incoming/, commit, push
```

Each wave's files and expected behaviour are also in `pending/wave_NN/WAVE.md`.

| Wave | Path | What arrives | What should happen | Planted issues |
|---|---|---|---|---|
| initial | Batch | Full history for every source (Jan-Oct 2026) | Everything lands; business issues are left for dbt | 144 |
| 01 | Batch | New PO lines (CSV) and invoices (Parquet) for 2026-11-02 | Loaded on the next 10-minute batch run. No DQ errors. Incremental models pick up only new rows. | 0 |
| 02 | Stream | 5 NDJSON files of risk score events; one supplier jumps to score 8 | Each file lands within about a minute (Snowpipe). RISK_CURRENT updates; the spike raises HIGH_RISK and SCORE_JUMP alerts. | 1 |
| 03 | Batch | The wave-1 PO file delivered again in a 'redelivery' folder: same name, same content | It lands in RAW (unique stage path), AUD-F02 flags it, dbt dedup keeps one row per PO line. | 1 |
| 04 | Batch | The wave-1 PO file resent as *_resend.csv | Snowflake load history cannot catch this. AUD-F04 (same MD5) flags it; RAW has duplicates; staging dedups. | 1 |
| 05 | Both | Corrected PO file and a risk file re-sent with the SAME file names as before, new content | With unique stage paths both land (no silent skip). AUD-F03 flags them; staging keeps the latest AEDAT/load. | 7 |
| 06 | Batch | PO file with an extra delimiter, text in an amount, a missing supplier, an invalid date, bad encoding | Whole file still lands (all VARCHAR, ON_ERROR=CONTINUE). Row rules flag the 5 rows; dbt quarantines them. | 5 |
| 07 | Batch | Invoices posted in September arriving now; PO lines changed or deleted (new AEDAT) | Incremental models must use a lookback window or late rows are missed; staging keeps latest AEDAT. | 18 |
| 08 | Batch | Full reload of the vendor master: names, addresses, bank accounts changed, 2 newly blocked, 1 new duplicate | dbt snapshot creates new SCD2 versions; golden record merges the new duplicate by VAT. | 9 |
| 09 | Both | PO file with a renamed column and a new column; risk events with payload_version 2 | Data still lands (header row kept, extra column in _EXTRA_1). AUD-S01 flags drift; stream handles v2. | 2 |
| 10 | Batch | Contract deltas (amendments, terminations, soft delete), events completed, 12 new requests in 3 pages | Snapshots capture status history; soft deletes excluded; new pages flattened. | 12 |
| 11 | Batch | A 0-byte file, a header-only file, and a bulk file with 19354 PO lines | Empty files are logged, not errors. Volume check warns on the bulk file. Python reads it in chunks. | 3 |
| 12 | Both | Out-of-order, duplicate, late and invalid risk events; a 500-event burst; new savings Excel; November FX | Dead letter gets 4 invalid events + 1 duplicate; the out-of-order event does not overwrite the newer score; the late event is flagged. | 11 |

## Planted issues by type

| Issue type | Count | Caught by | Expected check |
|---|---|---|---|
| empty_file | 1 | audit | AUD-F01 |
| exact_duplicate_file | 1 | audit | AUD-F02 |
| excel_total_row | 2 | audit | AUD-R12 |
| extra_delimiter | 1 | audit | AUD-R02 |
| header_only_file | 1 | audit | AUD-F01 |
| invalid_date | 1 | audit | AUD-R04 |
| invalid_encoding | 1 | audit | AUD-R06 |
| missing_key | 1 | audit | AUD-R03 |
| netwr_mismatch | 4 | audit | AUD-R05 |
| risk_score_out_of_range | 3 | audit | AUD-R11 |
| same_content_new_name | 1 | audit | AUD-F04 |
| same_name_new_content | 2 | audit | AUD-F03 |
| schema_drift | 1 | audit | AUD-S01 |
| text_in_amount | 1 | audit | AUD-R02 |
| updated_before_created | 5 | audit | AUD-R09 |
| volume_spike | 1 | audit | AUD-F08 |
| changed_record | 10 | dbt | DBT: keep latest AEDAT per PO line |
| closed_cost_center | 6 | dbt | DBT: PO not charged to a closed cost centre |
| completed_no_award_date | 6 | dbt | DBT: completed event has award date |
| contract_amended | 6 | dbt | DBT: snapshot contract status (SCD2) |
| corrected_line | 5 | dbt | DBT: keep latest version per PO line |
| credit_memo | 15 | dbt | DBT: credit memos reduce spend |
| deleted_record | 5 | dbt | DBT: keep and flag deleted PO lines |
| deletion_flag | 1 | dbt | DBT: keep and flag deleted PO lines |
| duplicate_bid | 4 | dbt | SQL: dedup bids after FLATTEN |
| duplicate_supplier | 9 | dbt | DBT: one golden ID per VAT number |
| end_before_start | 3 | dbt | DBT: fct_contract end_date after start_date |
| inactive_category | 3 | dbt | DBT: category active for material group |
| invoice_on_deleted_po | 3 | dbt | DBT: no invoice on a deleted PO line |
| late_arriving | 3 | dbt | DBT: incremental lookback window |
| missing_fx_rate | 1 | dbt | DBT: no null amount_eur (FX found) |
| orphan_invoice | 5 | dbt | DBT: every invoice line has a PO line |
| overlapping_contract | 5 | dbt | SQL: overlapping contracts per supplier + category |
| pasted_duplicate_row | 5 | dbt | DBT: unique savings_id |
| po_to_blocked_supplier | 5 | dbt | DBT: no PO to a blocked supplier |
| price_variance | 20 | dbt | KPI: invoice price variance |
| qty_above_po | 6 | dbt | DBT: invoiced quantity <= ordered quantity |
| reversal | 5 | dbt | DBT: reversed invoices net to zero |
| risk_review_overdue | 10 | dbt | DBT: risk review not overdue |
| savings_mismatch | 5 | dbt | DBT: savings = baseline - negotiated |
| scd2_change | 8 | dbt | DBT: snapshot (SCD2) on supplier |
| signed_after_start | 4 | dbt | DBT: signed_date on or before start_date |
| soft_delete | 6 | dbt | DBT: exclude soft-deleted contracts |
| status_change | 3 | dbt | DBT: dim_contract_status one current row |
| supplier_not_in_sap | 4 | dbt | DBT: every contract maps to a SAP supplier |
| unknown_category | 3 | dbt | DBT: relationships category_id |
| unknown_material_group | 3 | dbt | DBT: relationships material group -> category |
| burst | 1 | stream | STREAM: throughput |
| duplicate_event | 1 | stream | STREAM: dedup on event_id |
| invalid_event | 4 | stream | STREAM: dead letter |
| late_event | 1 | stream | STREAM: is_late flag |
| out_of_order | 1 | stream | STREAM: MERGE only if event_time is newer |
| payload_v2_sanctions | 1 | stream | STREAM: v2 payload handled + sanctions alert |
| risk_spike | 1 | stream | STREAM: alert when score >= 7 or jump >= 3 |

Total planted issues: **214**. Full list: `answer_key/planted_issues.csv`.
Check them against Snowflake with `python scripts/check_planted.py`.
