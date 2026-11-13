# Decision log (ADRs)

Short records of the important design choices: what we decided, why, and what we gave up. Interviewers often ask "why did you do it this way?", and the answers are here.

| ID | Decision | Why | Trade-off / alternative |
|---|---|---|---|
| DEC-01 | **Land everything, validate after.** RAW accepts any file; checks only log. | A rejected file is lost data, and someone has to notice and re-send it. Logged problems can be fixed later. | RAW contains junk; every consumer must go through staging. |
| DEC-02 | **CSV columns are VARCHAR in RAW**; JSON / XML / Parquet go into one VARIANT column. | Text in a number column, shifted columns and new fields never fail the load. Casting happens once, in dbt. | Types are enforced later, not at load. |
| DEC-03 | **Unique stage path per commit** (`.../<yyyy>/<mm>/<dd>/<sha>/`). | Snowpipe skips a file name it has seen (even with new content), and COPY reloads a changed file in full. A unique path makes behaviour predictable; duplicates are detected by MD5 and handled in dbt. | More files in the stage; needs a cleanup / retention policy. |
| DEC-04 | **Stream only supplier risk; everything else is batch.** | Risk drives a compliance decision (stop an award or PO) that cannot wait for tomorrow. Spend, contracts and savings are reviewed weekly or monthly, so batch is cheaper and simpler. | Two code paths, so the speed layer is reconciled into Gold by the batch run. |
| DEC-05 | **Snowpipe + stream + task** for the speed layer, not Kafka. | Events arrive as files at modest volume; Snowpipe is serverless and needs no extra infrastructure. | Latency is about a minute, not milliseconds. Kafka / Snowpipe Streaming would be the next step. |
| DEC-06 | **ALTER PIPE REFRESH** instead of auto-ingest. | Internal stages have no cloud event notifications. | Moving to Azure ADLS switches to `AUTO_INGEST = TRUE` with Event Grid. |
| DEC-07 | **SAP is the system of record for suppliers**; Ariba IDs are mapped to SAP by VAT number. | One supplier list in reports; VAT is the only identifier both systems share. | Suppliers without VAT, or with a typo, cannot be matched, so they are reported as unmatched. |
| DEC-08 | **Technical checks in Snowflake, business rules in dbt.** | Ingestion problems are caught even if dbt never runs; business logic stays version-controlled and tested next to the models. | Two places to look, which is why both write to the same kind of log. |
| DEC-09 | **Blocking vs non-blocking rules.** Only "incomplete data" (not loaded, row count mismatch, load errors) blocks Gold. | Bad rows can be quarantined, but missing data makes every total wrong. | A blocked gate needs a human: fix, or acknowledge with a note. |
| DEC-10 | **Late = event time behind the watermark**, not wall-clock time. | Test files carry historical timestamps; event-time logic behaves the same when you replay them, as it does in production. | Needs a watermark (max event time seen). |
| DEC-11 | **Keep deleted / soft-deleted records and flag them.** | Invoices still reference deleted PO lines; audit needs history. | Every model must filter `is_deleted`. |
| DEC-12 | **Convert all spend to EUR at the monthly average rate.** | Matches finance month-end reporting. | A missing month gives NULL `amount_eur`, which a dbt test catches. |
| DEC-13 | **Key-pair service user for automation**, roles per job (loader, transformer, analyst). | No passwords in GitHub; least privilege. | Key rotation is a manual step. |
| DEC-14 | **Mask emails** with a masking policy, not by deleting them. | GDPR: analysts do not need names; procurement admins do. | Policy must be attached to every new email column (done by a dbt post-hook). |
| DEC-15 | **Kimball star schema in Gold** (not Data Vault). | Four sources and one clear domain: a star schema is simpler and faster for BI. | Data Vault would make sense with many more changing sources and strict audit needs. |
| DEC-16 | **Four source systems**, not ten. | Every hard problem (cross-system IDs, five formats, batch + stream, manual Excel) is covered without extra plumbing. | Less realistic breadth; easy to add a source later because ingestion is config-driven. |
