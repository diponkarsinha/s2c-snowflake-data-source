# Data catalog

Four source systems plus reference files. All data is synthetic, for a fictional "Sample pharmaceutical company".

## Source inventory

| # | Source system | Entity | Format in GitHub | Frequency (real life) | Load | Load type | Change tracking | RAW table | Initial rows | Sensitivity |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | SAP ERP | Purchase order lines | CSV `;`, decimal comma | Daily 02:00 | Batch | Incremental + deletion flag | `AEDAT` | `SAP_PO_ITEMS` | 3,244 | Confidential |
| 2 | SAP ERP | Invoice lines | Parquet | Daily 02:00 | Batch | Incremental | `CPUDT` | `SAP_INVOICES` | 2,451 | Confidential |
| 3 | SAP ERP | Supplier master | XML (IDoc CREMAS05) | Daily 02:00 | Batch | **Full reload** → SCD2 | `UPDAT` | `SAP_SUPPLIERS` | 208 | Confidential (tax, bank) |
| 4 | SAP ERP | Cost centres | CSV `,` | Daily | Batch | Full reload | `updated_at` | `SAP_COST_CENTERS` | 20 | Internal |
| 5 | SAP ERP | FX rates | XML (ECB style) | Monthly | Batch | Full reload | month | `SAP_FX_RATES` | 22 months × 5 | Internal |
| 6 | Ariba Sourcing | Sourcing requests | JSON, paginated API | Hourly | Batch | Incremental | `updated_at` | `ARIBA_SOURCING_REQUESTS` | 300 (3 pages) | Internal (emails) |
| 7 | Ariba Sourcing | Sourcing events + bids + awards | JSON, nested | Hourly | Batch | Incremental | `updatedAt` | `ARIBA_SOURCING_EVENTS` | 180 events | Confidential |
| 8 | Ariba Contracts | Contracts | JSON, nested | Hourly | Batch | Incremental + soft deletes | `lastStatusChangeAt` | `ARIBA_CONTRACTS` | 268 | Confidential |
| 9 | Ariba Contracts | Contract approvals | CSV `,` | Hourly | Batch | Incremental | `decided_at` | `ARIBA_CONTRACT_APPROVALS` | 578 | Internal (names) |
| 10 | Supplier Risk | Risk + ESG scores | JSON | Weekly (Mon) | Batch | Full reload | `generatedAt` | `RISK_ESG` | 170 | Licensed |
| 11 | Supplier Risk | Risk score events | NDJSON | Continuous | **Stream** | Append | `event_time` | `RISK_EVENTS` | via waves | Licensed |
| 12 | Reference | Category taxonomy | CSV `,` | On change | Batch | Full reload | `updated_at` | `REF_CATEGORIES` | 25 | Internal |
| 13 | Reference (manual) | Savings tracker | Excel (.xlsx) | Weekly (Fri) | Batch | Full reload | file date | `MANUAL_SAVINGS` | 60 + junk rows | Confidential |

Why only four systems? A real S2C landscape has more (ServiceNow intake, Icertis CLM, D&B, EcoVadis, SharePoint). Here intake lives inside Ariba Sourcing and both risk feeds come from one provider, so the project stays small but keeps every hard problem: cross-system IDs, five file formats, batch and stream, a manual Excel file.

## Formats and why each one is here

| Format | Entity | What it teaches | Snowflake file format |
|---|---|---|---|
| CSV `;` + decimal comma | PO lines | Delimiters, `1234,50` numbers, SAP headers, leading zeros | `FF_CSV_SEMICOLON` |
| CSV `,` | Cost centres, approvals, taxonomy | The normal case | `FF_CSV_COMMA` |
| Parquet | Invoices | Self-describing typed columns, `USE_LOGICAL_TYPE` | `FF_PARQUET` |
| XML IDoc | Supplier master | `STRIP_OUTER_ELEMENT`, `XMLGET`, empty tags, nested segments | `FF_XML` |
| XML attributes | FX rates | `GET(xml, '@rate')`, one row per month | `FF_XML` |
| Paginated JSON | Requests | Many files = one dataset, `FLATTEN(result)`, numbers as text | `FF_JSON` |
| Nested JSON | Events, contracts, risk | Multi-level `FLATTEN`, arrays inside arrays, mixed types | `FF_JSON` |
| NDJSON | Risk events | One event per line, streaming | `FF_JSON` |
| Excel | Savings tracker | Snowflake cannot read it: Python converts; header not on row 1 | `FF_CSV_COMMA` after conversion |

## Object catalog (Snowflake)

| Schema | Object | Type | Purpose |
|---|---|---|---|
| RAW | `STG_BATCH`, `STG_STREAM` | Internal stage | Landing for uploaded files |
| RAW | `FF_*` | File format | One per real-world format |
| RAW | 13 tables | Table | Bronze layer |
| RAW | `PIPE_RISK_EVENTS` | Pipe | Snowpipe for risk events |
| RAW | `RISK_EVENTS_STREAM` | Stream | CDC on `RISK_EVENTS` |
| AUDIT | `INGEST_CONFIG` | Table | Entity → stage → RAW table |
| AUDIT | `FILE_REGISTRY` | Table | Every pushed file, with MD5 and commit |
| AUDIT | `PRELOAD_CHECK_LOG` | Table | Checks before upload |
| AUDIT | `LOAD_RUN_LOG`, `FILE_LOAD_LOG` | Table | What ran / what loaded |
| AUDIT | `DQ_RULES`, `DQ_RUN_LOG`, `DQ_RESULTS_LOG`, `DQ_FAILED_RECORDS` | Table | Rule engine |
| AUDIT | `SP_LOAD_BATCH`, `SP_COLLECT_LOAD_HISTORY`, `SP_RUN_DQ` | Procedure | Load, log, check |
| AUDIT | `TASK_LOAD_BATCH` → `TASK_COLLECT_LOAD_HISTORY` → `TASK_RUN_DQ` | Task graph | Every 10 minutes |
| AUDIT | `V_PIPELINE_GATE`, `V_ROW_DQ_STATUS`, `V_FILE_LINEAGE`, `V_PIPELINE_HEALTH`, ... | View | Monitoring + dbt inputs |
| STREAMING | `RISK_CURRENT`, `RISK_EVENT_LOG`, `RISK_ALERTS`, `RISK_DEAD_LETTER` | Table | Speed layer |
| STREAMING | `SP_PROCESS_RISK_EVENTS`, `TASK_PROCESS_RISK_EVENTS` | Procedure, task | Every minute when the stream has data |
| GOVERNANCE | `MP_EMAIL`, tag `PII` | Masking policy, tag | GDPR |

Column-level details: [data_dictionary/](data_dictionary/README.md).
