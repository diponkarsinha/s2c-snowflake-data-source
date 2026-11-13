/* =============================================================================
   05_load_procedures.sql
   -----------------------------------------------------------------------------
   SP_LOAD_BATCH            COPY INTO every batch RAW table from STG_BATCH.
                            Snowflake load metadata skips files already loaded,
                            so running it every 10 minutes is safe (idempotent).
   SP_COLLECT_LOAD_HISTORY  copies COPY_HISTORY (batch AND Snowpipe loads) into
                            AUDIT.FILE_LOAD_LOG so every load is auditable.

   Why COPY_HISTORY and not VALIDATE()? VALIDATE does not support COPY
   statements that transform data, and we transform (we add file metadata).
   Because RAW is all VARCHAR / VARIANT, row rejects should be ~0 anyway;
   any errors still show up in COPY_HISTORY (ERROR_COUNT, FIRST_ERROR).
   ============================================================================= */

USE ROLE S2C_ADMIN;
USE DATABASE S2C_DEV;
USE SCHEMA AUDIT;

CREATE OR REPLACE PROCEDURE S2C_DEV.AUDIT.SP_LOAD_BATCH()
RETURNS VARCHAR
LANGUAGE SQL
COMMENT = 'Loads every batch entity from STG_BATCH into RAW (COPY INTO, ON_ERROR = CONTINUE)'
EXECUTE AS OWNER
AS
$$
DECLARE
    run_id     VARCHAR DEFAULT UUID_STRING();
    ok_count   INTEGER DEFAULT 0;
    fail_count INTEGER DEFAULT 0;
    msg        VARCHAR DEFAULT '';
BEGIN
    INSERT INTO S2C_DEV.AUDIT.LOAD_RUN_LOG (RUN_ID, RUN_TYPE, STARTED_AT, STATUS)
    VALUES (:run_id, 'BATCH', CURRENT_TIMESTAMP(), 'RUNNING');

    -- 1. SAP purchase order lines (semicolon CSV, 17 columns + 3 spare) ------------
    BEGIN
        COPY INTO S2C_DEV.RAW.SAP_PO_ITEMS (
            EBELN, EBELP, BUKRS, LIFNR, BEDAT, MATKL, TXZ01, MENGE, MEINS, NETPR, PEINH, NETWR,
            WAERS, KOSTL, KONNR, LOEKZ, AEDAT, _EXTRA_1, _EXTRA_2, _EXTRA_3,
            _FILE_NAME, _FILE_ROW_NUMBER, _FILE_CONTENT_KEY, _FILE_LAST_MODIFIED, _LOADED_AT)
        FROM (
            SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17,
                   $18, $19, $20,
                   METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_CONTENT_KEY,
                   METADATA$FILE_LAST_MODIFIED, METADATA$START_SCAN_TIME
            FROM @S2C_DEV.RAW.STG_BATCH/sap/po_items/
        )
        FILE_FORMAT = (FORMAT_NAME = 'S2C_DEV.RAW.FF_CSV_SEMICOLON')
        ON_ERROR = CONTINUE;
        ok_count := ok_count + 1;
    EXCEPTION WHEN OTHER THEN
        fail_count := fail_count + 1;
        msg := msg || 'SAP_PO_ITEMS: ' || SQLERRM || ' | ';
    END;

    -- 2. SAP invoices (Parquet -> VARIANT) ------------------------------------------
    BEGIN
        COPY INTO S2C_DEV.RAW.SAP_INVOICES (RAW, _FILE_NAME, _FILE_ROW_NUMBER, _FILE_CONTENT_KEY, _FILE_LAST_MODIFIED, _LOADED_AT)
        FROM (
            SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_CONTENT_KEY,
                   METADATA$FILE_LAST_MODIFIED, METADATA$START_SCAN_TIME
            FROM @S2C_DEV.RAW.STG_BATCH/sap/invoices/
        )
        FILE_FORMAT = (FORMAT_NAME = 'S2C_DEV.RAW.FF_PARQUET')
        ON_ERROR = CONTINUE;
        ok_count := ok_count + 1;
    EXCEPTION WHEN OTHER THEN
        fail_count := fail_count + 1;
        msg := msg || 'SAP_INVOICES: ' || SQLERRM || ' | ';
    END;

    -- 3. SAP supplier master (XML IDoc -> one row per <IDOC>) -----------------------
    BEGIN
        COPY INTO S2C_DEV.RAW.SAP_SUPPLIERS (RAW, _FILE_NAME, _FILE_ROW_NUMBER, _FILE_CONTENT_KEY, _FILE_LAST_MODIFIED, _LOADED_AT)
        FROM (
            SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_CONTENT_KEY,
                   METADATA$FILE_LAST_MODIFIED, METADATA$START_SCAN_TIME
            FROM @S2C_DEV.RAW.STG_BATCH/sap/suppliers/
        )
        FILE_FORMAT = (FORMAT_NAME = 'S2C_DEV.RAW.FF_XML')
        ON_ERROR = CONTINUE;
        ok_count := ok_count + 1;
    EXCEPTION WHEN OTHER THEN
        fail_count := fail_count + 1;
        msg := msg || 'SAP_SUPPLIERS: ' || SQLERRM || ' | ';
    END;

    -- 4. SAP cost centres (CSV) -----------------------------------------------------
    BEGIN
        COPY INTO S2C_DEV.RAW.SAP_COST_CENTERS (
            KOSTL, KOKRS, BUKRS, COST_CENTER_NAME, BUSINESS_UNIT, RESPONSIBLE, VALID_FROM, VALID_TO,
            UPDATED_AT, _EXTRA_1, _EXTRA_2, _EXTRA_3,
            _FILE_NAME, _FILE_ROW_NUMBER, _FILE_CONTENT_KEY, _FILE_LAST_MODIFIED, _LOADED_AT)
        FROM (
            SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                   METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_CONTENT_KEY,
                   METADATA$FILE_LAST_MODIFIED, METADATA$START_SCAN_TIME
            FROM @S2C_DEV.RAW.STG_BATCH/sap/cost_centers/
        )
        FILE_FORMAT = (FORMAT_NAME = 'S2C_DEV.RAW.FF_CSV_COMMA')
        ON_ERROR = CONTINUE;
        ok_count := ok_count + 1;
    EXCEPTION WHEN OTHER THEN
        fail_count := fail_count + 1;
        msg := msg || 'SAP_COST_CENTERS: ' || SQLERRM || ' | ';
    END;

    -- 5. SAP FX rates (XML -> one row per month) ------------------------------------
    BEGIN
        COPY INTO S2C_DEV.RAW.SAP_FX_RATES (RAW, _FILE_NAME, _FILE_ROW_NUMBER, _FILE_CONTENT_KEY, _FILE_LAST_MODIFIED, _LOADED_AT)
        FROM (
            SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_CONTENT_KEY,
                   METADATA$FILE_LAST_MODIFIED, METADATA$START_SCAN_TIME
            FROM @S2C_DEV.RAW.STG_BATCH/sap/fx_rates/
        )
        FILE_FORMAT = (FORMAT_NAME = 'S2C_DEV.RAW.FF_XML')
        ON_ERROR = CONTINUE;
        ok_count := ok_count + 1;
    EXCEPTION WHEN OTHER THEN
        fail_count := fail_count + 1;
        msg := msg || 'SAP_FX_RATES: ' || SQLERRM || ' | ';
    END;

    -- 6. Ariba sourcing requests (paginated JSON, one row per page) -----------------
    BEGIN
        COPY INTO S2C_DEV.RAW.ARIBA_SOURCING_REQUESTS (RAW, _FILE_NAME, _FILE_ROW_NUMBER, _FILE_CONTENT_KEY, _FILE_LAST_MODIFIED, _LOADED_AT)
        FROM (
            SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_CONTENT_KEY,
                   METADATA$FILE_LAST_MODIFIED, METADATA$START_SCAN_TIME
            FROM @S2C_DEV.RAW.STG_BATCH/ariba_sourcing/requests/
        )
        FILE_FORMAT = (FORMAT_NAME = 'S2C_DEV.RAW.FF_JSON')
        ON_ERROR = CONTINUE;
        ok_count := ok_count + 1;
    EXCEPTION WHEN OTHER THEN
        fail_count := fail_count + 1;
        msg := msg || 'ARIBA_SOURCING_REQUESTS: ' || SQLERRM || ' | ';
    END;

    -- 7. Ariba sourcing events (JSON with nested bids) ------------------------------
    BEGIN
        COPY INTO S2C_DEV.RAW.ARIBA_SOURCING_EVENTS (RAW, _FILE_NAME, _FILE_ROW_NUMBER, _FILE_CONTENT_KEY, _FILE_LAST_MODIFIED, _LOADED_AT)
        FROM (
            SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_CONTENT_KEY,
                   METADATA$FILE_LAST_MODIFIED, METADATA$START_SCAN_TIME
            FROM @S2C_DEV.RAW.STG_BATCH/ariba_sourcing/events/
        )
        FILE_FORMAT = (FORMAT_NAME = 'S2C_DEV.RAW.FF_JSON')
        ON_ERROR = CONTINUE;
        ok_count := ok_count + 1;
    EXCEPTION WHEN OTHER THEN
        fail_count := fail_count + 1;
        msg := msg || 'ARIBA_SOURCING_EVENTS: ' || SQLERRM || ' | ';
    END;

    -- 8. Ariba contracts (nested JSON) ----------------------------------------------
    BEGIN
        COPY INTO S2C_DEV.RAW.ARIBA_CONTRACTS (RAW, _FILE_NAME, _FILE_ROW_NUMBER, _FILE_CONTENT_KEY, _FILE_LAST_MODIFIED, _LOADED_AT)
        FROM (
            SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_CONTENT_KEY,
                   METADATA$FILE_LAST_MODIFIED, METADATA$START_SCAN_TIME
            FROM @S2C_DEV.RAW.STG_BATCH/ariba_contracts/contracts/
        )
        FILE_FORMAT = (FORMAT_NAME = 'S2C_DEV.RAW.FF_JSON')
        ON_ERROR = CONTINUE;
        ok_count := ok_count + 1;
    EXCEPTION WHEN OTHER THEN
        fail_count := fail_count + 1;
        msg := msg || 'ARIBA_CONTRACTS: ' || SQLERRM || ' | ';
    END;

    -- 9. Ariba contract approvals (CSV) ---------------------------------------------
    BEGIN
        COPY INTO S2C_DEV.RAW.ARIBA_CONTRACT_APPROVALS (
            APPROVAL_ID, CONTRACT_ID, STEP, APPROVER_ID, APPROVER_NAME, APPROVER_EMAIL,
            APPROVER_MANAGER_ID, APPROVER_TITLE, DECISION, DECIDED_AT, _EXTRA_1, _EXTRA_2, _EXTRA_3,
            _FILE_NAME, _FILE_ROW_NUMBER, _FILE_CONTENT_KEY, _FILE_LAST_MODIFIED, _LOADED_AT)
        FROM (
            SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                   METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_CONTENT_KEY,
                   METADATA$FILE_LAST_MODIFIED, METADATA$START_SCAN_TIME
            FROM @S2C_DEV.RAW.STG_BATCH/ariba_contracts/approvals/
        )
        FILE_FORMAT = (FORMAT_NAME = 'S2C_DEV.RAW.FF_CSV_COMMA')
        ON_ERROR = CONTINUE;
        ok_count := ok_count + 1;
    EXCEPTION WHEN OTHER THEN
        fail_count := fail_count + 1;
        msg := msg || 'ARIBA_CONTRACT_APPROVALS: ' || SQLERRM || ' | ';
    END;

    -- 10. Weekly risk + ESG file (JSON) ----------------------------------------------
    BEGIN
        COPY INTO S2C_DEV.RAW.RISK_ESG (RAW, _FILE_NAME, _FILE_ROW_NUMBER, _FILE_CONTENT_KEY, _FILE_LAST_MODIFIED, _LOADED_AT)
        FROM (
            SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_CONTENT_KEY,
                   METADATA$FILE_LAST_MODIFIED, METADATA$START_SCAN_TIME
            FROM @S2C_DEV.RAW.STG_BATCH/supplier_risk/risk_esg/
        )
        FILE_FORMAT = (FORMAT_NAME = 'S2C_DEV.RAW.FF_JSON')
        ON_ERROR = CONTINUE;
        ok_count := ok_count + 1;
    EXCEPTION WHEN OTHER THEN
        fail_count := fail_count + 1;
        msg := msg || 'RISK_ESG: ' || SQLERRM || ' | ';
    END;

    -- 11. Category taxonomy (CSV) ----------------------------------------------------
    BEGIN
        COPY INTO S2C_DEV.RAW.REF_CATEGORIES (
            CATEGORY_ID, CATEGORY_NAME, PARENT_CATEGORY_ID, CATEGORY_LEVEL, UNSPSC_CODE, SAP_MATERIAL_GROUP,
            IS_ACTIVE, VALID_FROM, VALID_TO, UPDATED_AT, _EXTRA_1, _EXTRA_2, _EXTRA_3,
            _FILE_NAME, _FILE_ROW_NUMBER, _FILE_CONTENT_KEY, _FILE_LAST_MODIFIED, _LOADED_AT)
        FROM (
            SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                   METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_CONTENT_KEY,
                   METADATA$FILE_LAST_MODIFIED, METADATA$START_SCAN_TIME
            FROM @S2C_DEV.RAW.STG_BATCH/reference/categories/
        )
        FILE_FORMAT = (FORMAT_NAME = 'S2C_DEV.RAW.FF_CSV_COMMA')
        ON_ERROR = CONTINUE;
        ok_count := ok_count + 1;
    EXCEPTION WHEN OTHER THEN
        fail_count := fail_count + 1;
        msg := msg || 'REF_CATEGORIES: ' || SQLERRM || ' | ';
    END;

    -- 12. Savings tracker (Excel converted to CSV by the uploader) ------------------
    BEGIN
        COPY INTO S2C_DEV.RAW.MANUAL_SAVINGS (
            SHEET_ROW, SAVINGS_ID, EVENT_ID, CATEGORY, SUPPLIER, BASELINE_EUR, NEGOTIATED_EUR,
            SAVINGS_EUR, SAVINGS_DATE, VALIDATED_BY_FINANCE, OWNER, COMMENTS, _EXTRA_1, _EXTRA_2, _EXTRA_3,
            _FILE_NAME, _FILE_ROW_NUMBER, _FILE_CONTENT_KEY, _FILE_LAST_MODIFIED, _LOADED_AT)
        FROM (
            SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                   METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_CONTENT_KEY,
                   METADATA$FILE_LAST_MODIFIED, METADATA$START_SCAN_TIME
            FROM @S2C_DEV.RAW.STG_BATCH/reference/savings_tracker/
        )
        FILE_FORMAT = (FORMAT_NAME = 'S2C_DEV.RAW.FF_CSV_COMMA')
        ON_ERROR = CONTINUE;
        ok_count := ok_count + 1;
    EXCEPTION WHEN OTHER THEN
        fail_count := fail_count + 1;
        msg := msg || 'MANUAL_SAVINGS: ' || SQLERRM || ' | ';
    END;

    UPDATE S2C_DEV.AUDIT.LOAD_RUN_LOG
       SET FINISHED_AT = CURRENT_TIMESTAMP(),
           STATUS = IFF(:fail_count = 0, 'SUCCESS', 'PARTIAL'),
           ENTITIES_OK = :ok_count,
           ENTITIES_FAILED = :fail_count,
           MESSAGE = NULLIF(:msg, '')
     WHERE RUN_ID = :run_id;

    RETURN 'Batch load ' || run_id || ': ' || ok_count || ' entities ok, ' || fail_count || ' failed. ' || msg;
END;
$$;


CREATE OR REPLACE PROCEDURE S2C_DEV.AUDIT.SP_COLLECT_LOAD_HISTORY()
RETURNS VARCHAR
LANGUAGE SQL
COMMENT = 'Copies COPY_HISTORY (batch + Snowpipe) for every RAW table into AUDIT.FILE_LOAD_LOG'
EXECUTE AS OWNER
AS
$$
DECLARE
    tables_done INTEGER DEFAULT 0;
    stmt VARCHAR;
    c1 CURSOR FOR SELECT DISTINCT RAW_TABLE FROM S2C_DEV.AUDIT.INGEST_CONFIG WHERE IS_ACTIVE;
BEGIN
    FOR rec IN c1 DO
        stmt := 'INSERT INTO S2C_DEV.AUDIT.FILE_LOAD_LOG
                   (RAW_TABLE, FILE_NAME, STAGE_LOCATION, STATUS, ROW_COUNT, ROW_PARSED, FILE_SIZE,
                    ERROR_COUNT, FIRST_ERROR, FIRST_ERROR_LINE, PIPE_NAME, LAST_LOAD_TIME)
                 SELECT ''' || rec.RAW_TABLE || ''', h.FILE_NAME, h.STAGE_LOCATION, h.STATUS, h.ROW_COUNT,
                        h.ROW_PARSED, h.FILE_SIZE, h.ERROR_COUNT, h.FIRST_ERROR_MESSAGE,
                        h.FIRST_ERROR_LINE_NUMBER, h.PIPE_NAME, h.LAST_LOAD_TIME
                 FROM TABLE(S2C_DEV.INFORMATION_SCHEMA.COPY_HISTORY(
                          TABLE_NAME => ''S2C_DEV.RAW.' || rec.RAW_TABLE || ''',
                          START_TIME => DATEADD(DAY, -7, CURRENT_TIMESTAMP()))) h
                 WHERE NOT EXISTS (
                     SELECT 1 FROM S2C_DEV.AUDIT.FILE_LOAD_LOG l
                     WHERE l.RAW_TABLE = ''' || rec.RAW_TABLE || '''
                       AND l.FILE_NAME = h.FILE_NAME
                       AND l.LAST_LOAD_TIME = h.LAST_LOAD_TIME)';
        EXECUTE IMMEDIATE :stmt;
        tables_done := tables_done + 1;
    END FOR;
    RETURN 'Collected load history for ' || tables_done || ' RAW tables';
END;
$$;

-- the uploader may trigger a load right after a push (scripts/ingest_files.py --load-now)
GRANT USAGE ON PROCEDURE S2C_DEV.AUDIT.SP_LOAD_BATCH() TO ROLE S2C_LOADER;
GRANT USAGE ON PROCEDURE S2C_DEV.AUDIT.SP_COLLECT_LOAD_HISTORY() TO ROLE S2C_LOADER;
