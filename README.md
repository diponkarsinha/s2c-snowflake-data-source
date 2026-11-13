# s2c-snowflake-data-source

**Source-to-Contract (S2C) procurement data platform: sources, ingestion and audit layer on Snowflake.**

A fictional *Sample pharmaceutical company* buys from 200+ suppliers. Its procurement data lives in four systems that deliver files in five formats, some daily, some as a live stream, some typed by hand in Excel. This repo is everything up to the point where dbt takes over: realistic source files, a GitHub landing zone, Snowflake ingestion (batch + Snowpipe), and an audit layer that logs every problem before anything is transformed.

The dbt models, KPIs and question banks live in the companion repo **s2c-dbt-analytics** (`https://github.com/<your-user>/s2c-dbt-analytics`).

> All data is synthetic. No real company, supplier or person is represented.

---

## Architecture

```mermaid
flowchart LR
    S["4 source systems<br/>+ reference files"] --> G["GitHub data/<br/>(landing zone)"]
    G -- "GitHub Action<br/>profile + PUT" --> ST["Snowflake stages<br/>unique path per commit"]
    ST -- "COPY INTO<br/>task every 10 min" --> R["RAW (Bronze)<br/>everything lands"]
    ST -- "Snowpipe ~1 min" --> R
    R --> A["AUDIT<br/>27 DQ rules, logs, gate"]
    R -- "stream + task" --> SP["STREAMING<br/>risk alerts"]
    A -- "gate = PASS" --> D["dbt: Silver → Gold<br/>(s2c-dbt-analytics)"]
    R --> D
    SP --> D
```

**Medallion** layers (Bronze here, Silver/Gold in dbt), **Lambda** processing (batch + speed layer), and **land everything, validate after**: nothing is rejected at the door, every issue is traceable to the file, row and Git commit it came from.

Details: [docs/architecture.md](docs/architecture.md)

## Sources

| System | Entities | Formats | Load |
|---|---|---|---|
| SAP ERP | PO lines, invoices, supplier master, cost centres, FX rates | CSV `;` with decimal comma, Parquet, XML IDoc, CSV, XML | Batch |
| Ariba Sourcing | Sourcing requests, events, bids, awards | Paginated JSON, nested JSON | Batch |
| Ariba Contracts | Contracts, amendments, approvals | Nested JSON, CSV | Batch |
| Supplier Risk | Weekly risk + ESG, risk score events | JSON, **NDJSON stream** | Batch + **Stream** |
| Reference | Category taxonomy, savings tracker | CSV, **Excel** | Batch |

[Data catalog](docs/data_catalog.md) · [Data dictionary](docs/data_dictionary/README.md) · [ER diagram](docs/source_er_diagram.md) · [Source-to-target mapping](docs/source_to_target.md)

## What makes it realistic

- **214 planted issues** with an answer key ([answer_key/planted_issues.csv](answer_key/planted_issues.csv)): duplicate suppliers under new IDs, blocked suppliers still receiving POs, closed cost centres, orphan invoices, credit memos, reversals, overlapping contracts, mixed boolean types, a TOTAL row in Excel, dd/mm dates, missing FX rates...
- **12 drop waves** pushed one at a time to test the pipeline: duplicates (three kinds), bad rows, late data, SCD2 changes, schema drift, empty and huge files, out-of-order / duplicate / invalid stream events ([drop plan](docs/drop_plan.md))
- **A self-checking audit layer**: `scripts/check_planted.py` compares what was planted with what Snowflake caught

## Repository layout

```text
.github/workflows/ingest.yml   push to data/ -> upload to Snowflake
data/initial/                  first load (Jan-Oct 2026), all sources
data/incoming/                 waves land here when dropped
pending/                       12 waves waiting to be dropped (git-ignored, re-generated)
answer_key/                    planted_issues.csv, waves.json
generator/                     generate_data.py (seeded), build_docs.py
scripts/                       ingest_files.py, file_profiler.py, drop_wave.py, run_sql.py, check_planted.py
snowflake/                     01-11 setup scripts in run order + ops/ (resume, suspend, status, reset)
docs/                          architecture, catalog, dictionary, DQ rules, decisions, runbook, setup
```

## Quick start

```bash
pip install -r requirements.txt
python generator/generate_data.py --clean      # build all data (needs pyarrow for Parquet)
# Snowflake: run snowflake/01 as ACCOUNTADMIN, then 02-11 as S2C_ADMIN
# GitHub: add 3 secrets, push -> the Action uploads data/initial
python scripts/drop_wave.py 1 --push           # drop the first wave
```

Full step-by-step guide: **[docs/github_setup.md](docs/github_setup.md)**

## Snowflake objects

| Schema | Highlights |
|---|---|
| `RAW` | 13 Bronze tables (VARCHAR / VARIANT + `_FILE_NAME`, `_FILE_ROW_NUMBER`, `_FILE_CONTENT_KEY`, `_LOADED_AT`), 5 file formats, 2 stages, Snowpipe, stream |
| `AUDIT` | File registry, pre-load checks, load log (from `COPY_HISTORY`), 27 DQ rules, failing records, pipeline gate, lineage views, task graph |
| `STREAMING` | `RISK_CURRENT` (event-time MERGE), `RISK_ALERTS`, `RISK_DEAD_LETTER`, `RISK_EVENT_LOG` |
| `GOVERNANCE` | Email masking policy, PII tag |

Roles: `S2C_ADMIN`, `S2C_LOADER` (GitHub service user, key-pair auth), `S2C_TRANSFORMER` (dbt), `S2C_ANALYST`, `S2C_PII_READER`. Cost: XS warehouse, 60 s auto-suspend, 20-credit resource monitor.

## Documentation

| Doc | What's in it |
|---|---|
| [architecture.md](docs/architecture.md) | Flow diagrams, layers, batch and stream sequences, data-loss defences, cost |
| [data_catalog.md](docs/data_catalog.md) | Source inventory, formats, Snowflake object catalog |
| [data_dictionary/](docs/data_dictionary/README.md) | Every column of every source, with samples and known issues |
| [source_er_diagram.md](docs/source_er_diagram.md) | Source ER model and the S2C chain |
| [source_to_target.md](docs/source_to_target.md) | RAW → dbt staging mapping |
| [dq_rules.md](docs/dq_rules.md) | All 27 audit rules + pre-load and stream checks |
| [drop_plan.md](docs/drop_plan.md) | The 12 waves and planted issues |
| [scenario_matrix.md](docs/scenario_matrix.md) | Waves → practice topics; interview questions → where to look |
| [decision_log.md](docs/decision_log.md) | 16 design decisions with trade-offs |
| [runbook.md](docs/runbook.md) | Operating, troubleshooting, production checklist |
| [github_setup.md](docs/github_setup.md) | Zip → running pipeline, step by step |

## Roadmap

- **Phase 2:** CI checks on pull requests (sqlfluff, pytest), Streamlit-in-Snowflake DQ dashboard
- **Phase 3:** Azure ADLS Gen2 landing + Snowpipe auto-ingest (Event Grid); Airflow DAG orchestrating upload → load → DQ → dbt
