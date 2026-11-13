/* =============================================================================
   08_dq_procedure.sql
   -----------------------------------------------------------------------------
   SP_RUN_DQ(FORCE_RUN)
     1. Skips quietly if nothing new arrived since the last run (saves credits),
        unless FORCE_RUN = TRUE.
     2. Runs every active rule in AUDIT.DQ_RULES.
     3. MERGEs failing records into DQ_FAILED_RECORDS (first seen / last seen),
        so a record is logged once, not every 10 minutes.
     4. Writes one row per rule into DQ_RESULTS_LOG and one row into DQ_RUN_LOG.
   A broken rule never stops the others: it is logged as RULE_ERROR.
   ============================================================================= */

USE ROLE S2C_ADMIN;
USE DATABASE S2C_DEV;
USE SCHEMA AUDIT;

CREATE OR REPLACE PROCEDURE S2C_DEV.AUDIT.SP_RUN_DQ(FORCE_RUN BOOLEAN)
RETURNS VARCHAR
LANGUAGE SQL
COMMENT = 'Runs every active DQ rule and logs results and failing records'
EXECUTE AS OWNER
AS
$$
DECLARE
    run_id        VARCHAR DEFAULT UUID_STRING();
    last_run      TIMESTAMP_LTZ;
    new_activity  INTEGER DEFAULT 0;
    rules_run     INTEGER DEFAULT 0;
    rules_failed  INTEGER DEFAULT 0;
    rule_errors   INTEGER DEFAULT 0;
    cnt           INTEGER DEFAULT 0;
    new_cnt       INTEGER DEFAULT 0;
    samples       VARCHAR;
    stmt          VARCHAR;
    rid           VARCHAR;
    sev           VARCHAR;
    blk           BOOLEAN;
    errmsg        VARCHAR;
    c1 CURSOR FOR
        SELECT RULE_ID, SEVERITY, IS_BLOCKING, CHECK_SQL
        FROM S2C_DEV.AUDIT.DQ_RULES
        WHERE IS_ACTIVE
        ORDER BY RULE_ID;
BEGIN
    -- 1. anything new since the last run?
    SELECT MAX(STARTED_AT) INTO :last_run FROM S2C_DEV.AUDIT.DQ_RUN_LOG;
    IF (NOT FORCE_RUN AND last_run IS NOT NULL) THEN
        SELECT COUNT(*) INTO :new_activity
        FROM (
            SELECT LOGGED_AT AS ts FROM S2C_DEV.AUDIT.FILE_LOAD_LOG WHERE LOGGED_AT > :last_run
            UNION ALL
            SELECT REGISTERED_AT FROM S2C_DEV.AUDIT.FILE_REGISTRY WHERE REGISTERED_AT > :last_run
            UNION ALL
            SELECT REJECTED_AT FROM S2C_DEV.STREAMING.RISK_DEAD_LETTER WHERE REJECTED_AT > :last_run
        );
        IF (new_activity = 0) THEN
            RETURN 'DQ skipped: nothing new since ' || TO_VARCHAR(last_run);
        END IF;
    END IF;

    INSERT INTO S2C_DEV.AUDIT.DQ_RUN_LOG (RUN_ID, STARTED_AT, STATUS)
    VALUES (:run_id, CURRENT_TIMESTAMP(), 'RUNNING');

    -- 2. run every rule
    FOR r IN c1 DO
        rid := r.RULE_ID;
        sev := r.SEVERITY;
        blk := r.IS_BLOCKING;
        BEGIN
            stmt := 'CREATE OR REPLACE TEMPORARY TABLE S2C_DEV.AUDIT.DQ_WORK AS
                     SELECT RAW_TABLE::VARCHAR AS RAW_TABLE, FILE_NAME::VARCHAR AS FILE_NAME,
                            FILE_ROW_NUMBER::NUMBER AS FILE_ROW_NUMBER, RECORD_KEY::VARCHAR AS RECORD_KEY,
                            LEFT(DETAIL::VARCHAR, 2000) AS DETAIL
                     FROM (' || r.CHECK_SQL || ')';
            EXECUTE IMMEDIATE :stmt;

            SELECT COUNT(*) INTO :cnt FROM S2C_DEV.AUDIT.DQ_WORK;

            -- 3. failing records: insert new ones, refresh "last seen" on old ones
            MERGE INTO S2C_DEV.AUDIT.DQ_FAILED_RECORDS t
            USING (
                SELECT RAW_TABLE, FILE_NAME, FILE_ROW_NUMBER, RECORD_KEY, DETAIL
                FROM S2C_DEV.AUDIT.DQ_WORK
                QUALIFY ROW_NUMBER() OVER (PARTITION BY FILE_NAME, FILE_ROW_NUMBER, RECORD_KEY ORDER BY DETAIL) = 1
            ) s
            ON  t.RULE_ID = :rid
            AND EQUAL_NULL(t.FILE_NAME, s.FILE_NAME)
            AND EQUAL_NULL(t.FILE_ROW_NUMBER, s.FILE_ROW_NUMBER)
            AND EQUAL_NULL(t.RECORD_KEY, s.RECORD_KEY)
            WHEN MATCHED THEN UPDATE SET
                LAST_SEEN_RUN_ID = :run_id, LAST_SEEN_AT = CURRENT_TIMESTAMP(), DETAIL = s.DETAIL
            WHEN NOT MATCHED THEN INSERT
                (RULE_ID, SEVERITY, IS_BLOCKING, RAW_TABLE, FILE_NAME, FILE_ROW_NUMBER, RECORD_KEY, DETAIL,
                 FIRST_SEEN_RUN_ID, LAST_SEEN_RUN_ID, FIRST_SEEN_AT, LAST_SEEN_AT, ACKNOWLEDGED)
            VALUES
                (:rid, :sev, :blk, s.RAW_TABLE, s.FILE_NAME, s.FILE_ROW_NUMBER, s.RECORD_KEY, s.DETAIL,
                 :run_id, :run_id, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), FALSE);

            SELECT COUNT(*) INTO :new_cnt
            FROM S2C_DEV.AUDIT.DQ_FAILED_RECORDS
            WHERE RULE_ID = :rid AND FIRST_SEEN_RUN_ID = :run_id;

            SELECT LISTAGG(RECORD_KEY, ', ') WITHIN GROUP (ORDER BY RECORD_KEY) INTO :samples
            FROM (SELECT DISTINCT RECORD_KEY FROM S2C_DEV.AUDIT.DQ_WORK ORDER BY RECORD_KEY LIMIT 10);

            -- 4. one result row per rule
            INSERT INTO S2C_DEV.AUDIT.DQ_RESULTS_LOG
                (RUN_ID, RULE_ID, SEVERITY, IS_BLOCKING, STATUS, FAILED_COUNT, NEW_COUNT, SAMPLE_KEYS)
            VALUES
                (:run_id, :rid, :sev, :blk, IFF(:cnt = 0, 'PASS', 'FAIL'), :cnt, :new_cnt, :samples);

            rules_run := rules_run + 1;
            IF (cnt > 0) THEN
                rules_failed := rules_failed + 1;
            END IF;
        EXCEPTION WHEN OTHER THEN
            rule_errors := rule_errors + 1;
            errmsg := LEFT(SQLERRM, 2000);
            INSERT INTO S2C_DEV.AUDIT.DQ_RESULTS_LOG (RUN_ID, RULE_ID, SEVERITY, IS_BLOCKING, STATUS, ERROR_MESSAGE)
            VALUES (:run_id, :rid, :sev, :blk, 'RULE_ERROR', :errmsg);
        END;
    END FOR;

    UPDATE S2C_DEV.AUDIT.DQ_RUN_LOG
       SET FINISHED_AT = CURRENT_TIMESTAMP(),
           STATUS = IFF(:rule_errors = 0, 'SUCCESS', 'PARTIAL'),
           RULES_RUN = :rules_run,
           RULES_FAILED = :rules_failed,
           RULE_ERRORS = :rule_errors
     WHERE RUN_ID = :run_id;

    RETURN 'DQ run ' || run_id || ': ' || rules_run || ' rules run, ' || rules_failed
           || ' with failures, ' || rule_errors || ' rule errors';
END;
$$;

GRANT USAGE ON PROCEDURE S2C_DEV.AUDIT.SP_RUN_DQ(BOOLEAN) TO ROLE S2C_LOADER;
