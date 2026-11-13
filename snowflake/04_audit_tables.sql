/* =============================================================================
   04_audit_tables.sql
   -----------------------------------------------------------------------------
   The audit layer sits between Bronze (RAW) and dbt. It records:

     INGEST_CONFIG       which entity loads from where, into which RAW table
     FILE_REGISTRY       every file pushed from GitHub (written by the uploader)
     PRELOAD_CHECK_LOG   checks the uploader ran before PUT (never blocks)
     LOAD_RUN_LOG        every run of the batch load procedure
     FILE_LOAD_LOG       what Snowflake actually loaded (from COPY_HISTORY)
     DQ_RULES            rule catalogue: one SQL check per rule
     DQ_RUN_LOG          one row per DQ run
     DQ_RESULTS_LOG      one row per rule per run (counts + sample keys)
     DQ_FAILED_RECORDS   every failing record, keyed to file + row, for dbt
   ============================================================================= */

USE ROLE S2C_ADMIN;
USE DATABASE S2C_DEV;
USE SCHEMA AUDIT;

CREATE TABLE IF NOT EXISTS S2C_DEV.AUDIT.INGEST_CONFIG (
    ENTITY            VARCHAR NOT NULL,   -- folder under data/: <source>/<entity>
    SOURCE_SYSTEM     VARCHAR,
    LOAD_MODE         VARCHAR,            -- BATCH | STREAM
    FILE_TYPE         VARCHAR,            -- CSV | JSON | NDJSON | XML | PARQUET | XLSX
    STAGE_NAME        VARCHAR,
    RAW_TABLE         VARCHAR,
    EXPECTED_HEADER   VARCHAR,            -- CSV only, exact header line
    BUSINESS_KEY      VARCHAR,
    IS_ACTIVE         BOOLEAN DEFAULT TRUE,
    CONSTRAINT PK_INGEST_CONFIG PRIMARY KEY (ENTITY)
);

CREATE TABLE IF NOT EXISTS S2C_DEV.AUDIT.FILE_REGISTRY (
    REGISTRY_ID        NUMBER AUTOINCREMENT START 1 INCREMENT 1,
    ENTITY             VARCHAR,
    REPO_PATH          VARCHAR,           -- path in GitHub, e.g. data/incoming/sap/po_items/x.csv
    FILE_NAME          VARCHAR,           -- base name
    STAGE_NAME         VARCHAR,
    STAGE_PATH         VARCHAR,           -- unique path inside the stage
    FILE_TYPE          VARCHAR,
    MD5                VARCHAR,           -- of the original file in Git
    SIZE_BYTES         NUMBER,
    DATA_ROW_COUNT     NUMBER,            -- business records in the file (no header)
    EXPECTED_RAW_ROWS  NUMBER,            -- rows that should appear in RAW (CSV incl. header)
    HEADER_TEXT        VARCHAR,
    COMMIT_SHA         VARCHAR,
    PUSHED_BY          VARCHAR,
    REGISTERED_AT      TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS S2C_DEV.AUDIT.PRELOAD_CHECK_LOG (
    STAGE_PATH   VARCHAR,
    FILE_NAME    VARCHAR,
    ENTITY       VARCHAR,
    CHECK_NAME   VARCHAR,                 -- NOT_EMPTY | SCHEMA | VOLUME | PARSE
    STATUS       VARCHAR,                 -- PASS | WARN | FAIL
    DETAIL       VARCHAR,
    CHECKED_AT   TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS S2C_DEV.AUDIT.LOAD_RUN_LOG (
    RUN_ID        VARCHAR,
    RUN_TYPE      VARCHAR,
    STARTED_AT    TIMESTAMP_LTZ,
    FINISHED_AT   TIMESTAMP_LTZ,
    STATUS        VARCHAR,
    ENTITIES_OK   NUMBER,
    ENTITIES_FAILED NUMBER,
    MESSAGE       VARCHAR
);

CREATE TABLE IF NOT EXISTS S2C_DEV.AUDIT.FILE_LOAD_LOG (
    RAW_TABLE        VARCHAR,
    FILE_NAME        VARCHAR,             -- as reported by COPY_HISTORY
    STAGE_LOCATION   VARCHAR,
    STATUS           VARCHAR,             -- Loaded | Partially loaded | Load failed
    ROW_COUNT        NUMBER,
    ROW_PARSED       NUMBER,
    FILE_SIZE        NUMBER,
    ERROR_COUNT      NUMBER,
    FIRST_ERROR      VARCHAR,
    FIRST_ERROR_LINE NUMBER,
    PIPE_NAME        VARCHAR,             -- set when Snowpipe loaded the file
    LAST_LOAD_TIME   TIMESTAMP_LTZ,
    LOGGED_AT        TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS S2C_DEV.AUDIT.DQ_RULES (
    RULE_ID      VARCHAR NOT NULL,
    RULE_NAME    VARCHAR,
    CHECK_LEVEL  VARCHAR,                 -- FILE | SCHEMA | ROW | STREAM
    TARGET       VARCHAR,
    SEVERITY     VARCHAR,                 -- INFO | WARN | ERROR
    IS_BLOCKING  BOOLEAN DEFAULT FALSE,   -- TRUE = dbt must not publish Gold
    DESCRIPTION  VARCHAR,
    ACTION       VARCHAR,                 -- what happens to the data
    CHECK_SQL    VARCHAR,                 -- returns RAW_TABLE, FILE_NAME, FILE_ROW_NUMBER, RECORD_KEY, DETAIL
    IS_ACTIVE    BOOLEAN DEFAULT TRUE,
    CONSTRAINT PK_DQ_RULES PRIMARY KEY (RULE_ID)
);

CREATE TABLE IF NOT EXISTS S2C_DEV.AUDIT.DQ_RUN_LOG (
    RUN_ID         VARCHAR,
    STARTED_AT     TIMESTAMP_LTZ,
    FINISHED_AT    TIMESTAMP_LTZ,
    STATUS         VARCHAR,
    RULES_RUN      NUMBER,
    RULES_FAILED   NUMBER,
    RULE_ERRORS    NUMBER,
    MESSAGE        VARCHAR
);

CREATE TABLE IF NOT EXISTS S2C_DEV.AUDIT.DQ_RESULTS_LOG (
    RUN_ID        VARCHAR,
    RULE_ID       VARCHAR,
    SEVERITY      VARCHAR,
    IS_BLOCKING   BOOLEAN,
    STATUS        VARCHAR,                -- PASS | FAIL | RULE_ERROR
    FAILED_COUNT  NUMBER,                 -- all currently failing records
    NEW_COUNT     NUMBER,                 -- first seen in this run
    SAMPLE_KEYS   VARCHAR,
    ERROR_MESSAGE VARCHAR,
    CHECKED_AT    TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS S2C_DEV.AUDIT.DQ_FAILED_RECORDS (
    RULE_ID            VARCHAR,
    SEVERITY           VARCHAR,
    IS_BLOCKING        BOOLEAN,
    RAW_TABLE          VARCHAR,
    FILE_NAME          VARCHAR,           -- stage path, joins to RAW._FILE_NAME
    FILE_ROW_NUMBER    NUMBER,            -- joins to RAW._FILE_ROW_NUMBER
    RECORD_KEY         VARCHAR,
    DETAIL             VARCHAR,
    FIRST_SEEN_RUN_ID  VARCHAR,
    LAST_SEEN_RUN_ID   VARCHAR,
    FIRST_SEEN_AT      TIMESTAMP_LTZ,
    LAST_SEEN_AT       TIMESTAMP_LTZ,
    ACKNOWLEDGED       BOOLEAN DEFAULT FALSE,
    ACKNOWLEDGED_BY    VARCHAR,
    ACKNOWLEDGED_NOTE  VARCHAR
);

-- the uploader (GitHub Actions) writes the registry and pre-load results
GRANT INSERT, SELECT ON TABLE S2C_DEV.AUDIT.FILE_REGISTRY     TO ROLE S2C_LOADER;
GRANT INSERT, SELECT ON TABLE S2C_DEV.AUDIT.PRELOAD_CHECK_LOG TO ROLE S2C_LOADER;
GRANT SELECT ON TABLE S2C_DEV.AUDIT.INGEST_CONFIG             TO ROLE S2C_LOADER;
GRANT SELECT ON ALL TABLES IN SCHEMA S2C_DEV.AUDIT            TO ROLE S2C_TRANSFORMER;

-- -----------------------------------------------------------------------------
-- Ingest configuration: one row per entity (folder under data/)
-- -----------------------------------------------------------------------------
MERGE INTO S2C_DEV.AUDIT.INGEST_CONFIG t
USING (
    SELECT * FROM VALUES
    ('sap/po_items',              'SAP ERP',         'BATCH',  'CSV',     'STG_BATCH',  'SAP_PO_ITEMS',
       'EBELN;EBELP;BUKRS;LIFNR;BEDAT;MATKL;TXZ01;MENGE;MEINS;NETPR;PEINH;NETWR;WAERS;KOSTL;KONNR;LOEKZ;AEDAT', 'EBELN + EBELP'),
    ('sap/invoices',              'SAP ERP',         'BATCH',  'PARQUET', 'STG_BATCH',  'SAP_INVOICES',          NULL, 'BELNR + GJAHR + BUZEI'),
    ('sap/suppliers',             'SAP ERP',         'BATCH',  'XML',     'STG_BATCH',  'SAP_SUPPLIERS',         NULL, 'LIFNR'),
    ('sap/cost_centers',          'SAP ERP',         'BATCH',  'CSV',     'STG_BATCH',  'SAP_COST_CENTERS',
       'kostl,kokrs,bukrs,cost_center_name,business_unit,responsible,valid_from,valid_to,updated_at', 'KOSTL'),
    ('sap/fx_rates',              'SAP ERP',         'BATCH',  'XML',     'STG_BATCH',  'SAP_FX_RATES',          NULL, 'currency + month'),
    ('ariba_sourcing/requests',   'Ariba Sourcing',  'BATCH',  'JSON',    'STG_BATCH',  'ARIBA_SOURCING_REQUESTS', NULL, 'request_id'),
    ('ariba_sourcing/events',     'Ariba Sourcing',  'BATCH',  'JSON',    'STG_BATCH',  'ARIBA_SOURCING_EVENTS', NULL, 'eventId'),
    ('ariba_contracts/contracts', 'Ariba Contracts', 'BATCH',  'JSON',    'STG_BATCH',  'ARIBA_CONTRACTS',       NULL, 'contractId'),
    ('ariba_contracts/approvals', 'Ariba Contracts', 'BATCH',  'CSV',     'STG_BATCH',  'ARIBA_CONTRACT_APPROVALS',
       'approval_id,contract_id,step,approver_id,approver_name,approver_email,approver_manager_id,approver_title,decision,decided_at', 'approval_id'),
    ('supplier_risk/risk_esg',    'Supplier Risk',   'BATCH',  'JSON',    'STG_BATCH',  'RISK_ESG',              NULL, 'vatNumber + generatedAt'),
    ('supplier_risk/risk_events', 'Supplier Risk',   'STREAM', 'NDJSON',  'STG_STREAM', 'RISK_EVENTS',           NULL, 'event_id'),
    ('reference/categories',      'Reference',       'BATCH',  'CSV',     'STG_BATCH',  'REF_CATEGORIES',
       'category_id,category_name,parent_category_id,level,unspsc_code,sap_material_group,is_active,valid_from,valid_to,updated_at', 'category_id'),
    ('reference/savings_tracker', 'Reference',       'BATCH',  'XLSX',    'STG_BATCH',  'MANUAL_SAVINGS',
       '_sheet_row,Savings ID,Event ID,Category,Supplier,Baseline (EUR),Negotiated (EUR),Savings (EUR),Savings Date,Validated by Finance,Owner,Comments', 'Savings ID')
    AS v(ENTITY, SOURCE_SYSTEM, LOAD_MODE, FILE_TYPE, STAGE_NAME, RAW_TABLE, EXPECTED_HEADER, BUSINESS_KEY)
) s
ON t.ENTITY = s.ENTITY
WHEN MATCHED THEN UPDATE SET
    SOURCE_SYSTEM = s.SOURCE_SYSTEM, LOAD_MODE = s.LOAD_MODE, FILE_TYPE = s.FILE_TYPE,
    STAGE_NAME = s.STAGE_NAME, RAW_TABLE = s.RAW_TABLE, EXPECTED_HEADER = s.EXPECTED_HEADER,
    BUSINESS_KEY = s.BUSINESS_KEY, IS_ACTIVE = TRUE
WHEN NOT MATCHED THEN INSERT
    (ENTITY, SOURCE_SYSTEM, LOAD_MODE, FILE_TYPE, STAGE_NAME, RAW_TABLE, EXPECTED_HEADER, BUSINESS_KEY, IS_ACTIVE)
    VALUES (s.ENTITY, s.SOURCE_SYSTEM, s.LOAD_MODE, s.FILE_TYPE, s.STAGE_NAME, s.RAW_TABLE, s.EXPECTED_HEADER, s.BUSINESS_KEY, TRUE);
