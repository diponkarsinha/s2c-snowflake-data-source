/* =============================================================================
   06_stream_risk.sql  (speed layer)
   -----------------------------------------------------------------------------
   File pushed -> uploader PUTs it to @STG_STREAM/risk_events/<date>/<sha>/
              -> uploader runs ALTER PIPE ... REFRESH PREFIX = '<that folder>'
              -> PIPE_RISK_EVENTS loads RAW.RISK_EVENTS (serverless)
              -> RISK_EVENTS_STREAM records the new rows (CDC)
              -> TASK_PROCESS_RISK_EVENTS (every minute, only if the stream has
                 data) calls SP_PROCESS_RISK_EVENTS, which:
                    * parses and validates each event
                    * sends bad events to RISK_DEAD_LETTER (nothing is lost)
                    * skips duplicate event_ids
                    * MERGEs the newest score per supplier into RISK_CURRENT,
                      ignoring older events that arrive late (out of order)
                    * writes alerts into RISK_ALERTS

   Note: AUTO_INGEST (event notifications) only works with cloud storage
   (Azure / S3 / GCS). With an internal stage, the uploader tells the pipe
   about new files with ALTER PIPE ... REFRESH. Moving to Azure later only
   changes the stage and sets AUTO_INGEST = TRUE.
   ============================================================================= */

USE ROLE S2C_ADMIN;
USE DATABASE S2C_DEV;

-- -----------------------------------------------------------------------------
-- 1. Snowpipe
-- -----------------------------------------------------------------------------
CREATE OR REPLACE PIPE S2C_DEV.RAW.PIPE_RISK_EVENTS
  COMMENT = 'Loads risk event files (NDJSON) as soon as they are staged'
AS
COPY INTO S2C_DEV.RAW.RISK_EVENTS (RAW, _FILE_NAME, _FILE_ROW_NUMBER, _FILE_CONTENT_KEY, _FILE_LAST_MODIFIED, _LOADED_AT)
FROM (
    SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_CONTENT_KEY,
           METADATA$FILE_LAST_MODIFIED, METADATA$START_SCAN_TIME
    FROM @S2C_DEV.RAW.STG_STREAM/risk_events/
)
FILE_FORMAT = (FORMAT_NAME = 'S2C_DEV.RAW.FF_JSON')
ON_ERROR = CONTINUE;

-- the uploader refreshes the pipe after each upload
-- (ALTER PIPE ... REFRESH needs OPERATE on the pipe, READ on the internal stage,
--  USAGE on the file format and SELECT + INSERT on the target table)
GRANT OPERATE, MONITOR ON PIPE S2C_DEV.RAW.PIPE_RISK_EVENTS TO ROLE S2C_LOADER;
GRANT SELECT, INSERT ON TABLE S2C_DEV.RAW.RISK_EVENTS TO ROLE S2C_LOADER;

-- -----------------------------------------------------------------------------
-- 2. Stream (change tracking) on the RAW table
-- -----------------------------------------------------------------------------
CREATE STREAM IF NOT EXISTS S2C_DEV.RAW.RISK_EVENTS_STREAM
  ON TABLE S2C_DEV.RAW.RISK_EVENTS
  APPEND_ONLY = TRUE
  COMMENT = 'New risk events not yet processed by the speed layer';

-- -----------------------------------------------------------------------------
-- 3. Speed-layer tables
-- -----------------------------------------------------------------------------
USE SCHEMA STREAMING;

CREATE TRANSIENT TABLE IF NOT EXISTS S2C_DEV.STREAMING.RISK_WORK (
    EVENT_ID VARCHAR, PAYLOAD_VERSION NUMBER, SUPPLIER_VAT VARCHAR, RISK_SCORE NUMBER,
    PREVIOUS_SCORE NUMBER, REASON VARCHAR, SANCTIONS_HIT BOOLEAN, EVENT_TIME TIMESTAMP_NTZ,
    RAW VARIANT, FILE_NAME VARCHAR, FILE_ROW_NUMBER NUMBER, LOADED_AT TIMESTAMP_LTZ,
    REJECT_REASON VARCHAR
) COMMENT = 'Scratch table for one processing run';

CREATE TABLE IF NOT EXISTS S2C_DEV.STREAMING.RISK_EVENT_LOG (
    EVENT_ID        VARCHAR,
    PAYLOAD_VERSION NUMBER,
    SUPPLIER_VAT    VARCHAR,
    RISK_SCORE      NUMBER,
    PREVIOUS_SCORE  NUMBER,
    RISK_BAND       VARCHAR,
    REASON          VARCHAR,
    SANCTIONS_HIT   BOOLEAN,
    EVENT_TIME      TIMESTAMP_NTZ,      -- when it happened (UTC)
    LOADED_AT       TIMESTAMP_LTZ,      -- when Snowflake loaded it
    PROCESSED_AT    TIMESTAMP_LTZ,
    IS_LATE         BOOLEAN,            -- event_time more than 1 hour behind the event-time watermark
    FILE_NAME       VARCHAR,
    FILE_ROW_NUMBER NUMBER
) COMMENT = 'Every valid, de-duplicated risk event (full history)';

CREATE TABLE IF NOT EXISTS S2C_DEV.STREAMING.RISK_CURRENT (
    SUPPLIER_VAT    VARCHAR,
    RISK_SCORE      NUMBER,
    RISK_BAND       VARCHAR,
    SANCTIONS_HIT   BOOLEAN,
    LAST_EVENT_ID   VARCHAR,
    LAST_EVENT_TIME TIMESTAMP_NTZ,
    UPDATED_AT      TIMESTAMP_LTZ
) COMMENT = 'Latest risk score per supplier (by event_time, not arrival time)';

CREATE TABLE IF NOT EXISTS S2C_DEV.STREAMING.RISK_ALERTS (
    ALERT_ID        VARCHAR DEFAULT UUID_STRING(),
    EVENT_ID        VARCHAR,
    SUPPLIER_VAT    VARCHAR,
    ALERT_TYPE      VARCHAR,            -- HIGH_RISK | SCORE_JUMP | SANCTIONS_HIT
    RISK_SCORE      NUMBER,
    PREVIOUS_SCORE  NUMBER,
    EVENT_TIME      TIMESTAMP_NTZ,
    IS_LATE         BOOLEAN,
    CREATED_AT      TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    STATUS          VARCHAR DEFAULT 'OPEN'
) COMMENT = 'Near-real-time supplier risk alerts';

CREATE TABLE IF NOT EXISTS S2C_DEV.STREAMING.RISK_DEAD_LETTER (
    EVENT_ID        VARCHAR,
    REJECT_REASON   VARCHAR,
    RAW             VARIANT,
    FILE_NAME       VARCHAR,
    FILE_ROW_NUMBER NUMBER,
    LOADED_AT       TIMESTAMP_LTZ,
    REJECTED_AT     TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
) COMMENT = 'Events that could not be processed; kept so they can be fixed and replayed';

GRANT SELECT ON ALL TABLES IN SCHEMA S2C_DEV.STREAMING TO ROLE S2C_TRANSFORMER;

-- -----------------------------------------------------------------------------
-- 4. Processing procedure
-- -----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE S2C_DEV.STREAMING.SP_PROCESS_RISK_EVENTS()
RETURNS VARCHAR
LANGUAGE SQL
COMMENT = 'Validates, de-duplicates and merges new risk events; raises alerts'
EXECUTE AS OWNER
AS
$$
DECLARE
    n_in INTEGER DEFAULT 0;
    n_bad INTEGER DEFAULT 0;
    n_ok INTEGER DEFAULT 0;
    n_alerts INTEGER DEFAULT 0;
    watermark TIMESTAMP_NTZ;
BEGIN
    TRUNCATE TABLE S2C_DEV.STREAMING.RISK_WORK;

    -- (a) read the stream ONCE. This INSERT consumes the stream (offset moves on commit).
    INSERT INTO S2C_DEV.STREAMING.RISK_WORK
    SELECT
        e.event_id, e.payload_version, e.supplier_vat, e.risk_score, e.previous_score,
        e.reason, e.sanctions_hit, e.event_time, e.raw, e.file_name, e.file_row_number, e.loaded_at,
        CASE
            WHEN e.event_id IS NULL                       THEN 'MISSING_EVENT_ID'
            WHEN e.payload_version IS NULL
              OR e.payload_version NOT IN (1, 2)          THEN 'UNSUPPORTED_PAYLOAD_VERSION'
            WHEN e.supplier_vat IS NULL                   THEN 'MISSING_SUPPLIER_VAT'
            WHEN e.risk_score IS NULL                     THEN 'RISK_SCORE_NOT_NUMERIC'
            WHEN e.risk_score NOT BETWEEN 1 AND 9         THEN 'RISK_SCORE_OUT_OF_RANGE'
            WHEN e.event_time IS NULL                     THEN 'INVALID_EVENT_TIME'
        END AS reject_reason
    FROM (
        SELECT
            NULLIF(TRIM(s.RAW:event_id::STRING), '')                      AS event_id,
            TRY_TO_NUMBER(s.RAW:payload_version::STRING)                   AS payload_version,
            NULLIF(TRIM(s.RAW:supplier_vat::STRING), '')                  AS supplier_vat,
            TRY_TO_NUMBER(s.RAW:risk_score::STRING)                        AS risk_score,
            TRY_TO_NUMBER(s.RAW:previous_score::STRING)                    AS previous_score,
            s.RAW:reason::STRING                                           AS reason,
            TRY_TO_BOOLEAN(s.RAW:sanctions_hit::STRING)                    AS sanctions_hit,
            TRY_TO_TIMESTAMP_NTZ(s.RAW:event_time::STRING)                 AS event_time,
            s.RAW                                                          AS raw,
            s._FILE_NAME AS file_name, s._FILE_ROW_NUMBER AS file_row_number, s._LOADED_AT AS loaded_at
        FROM S2C_DEV.RAW.RISK_EVENTS_STREAM s
        WHERE s.METADATA$ACTION = 'INSERT'
    ) e;
    n_in := SQLROWCOUNT;

    -- (b) duplicates: already processed earlier, or repeated inside this batch
    UPDATE S2C_DEV.STREAMING.RISK_WORK w
       SET REJECT_REASON = 'DUPLICATE_EVENT'
      FROM (SELECT DISTINCT EVENT_ID FROM S2C_DEV.STREAMING.RISK_EVENT_LOG) l
     WHERE l.EVENT_ID = w.EVENT_ID
       AND w.REJECT_REASON IS NULL;

    UPDATE S2C_DEV.STREAMING.RISK_WORK w
       SET REJECT_REASON = 'DUPLICATE_EVENT'
      FROM (
            SELECT FILE_NAME, FILE_ROW_NUMBER,
                   ROW_NUMBER() OVER (PARTITION BY EVENT_ID ORDER BY LOADED_AT, FILE_NAME, FILE_ROW_NUMBER) AS rn
            FROM S2C_DEV.STREAMING.RISK_WORK
            WHERE REJECT_REASON IS NULL
           ) d
     WHERE w.FILE_NAME = d.FILE_NAME
       AND w.FILE_ROW_NUMBER = d.FILE_ROW_NUMBER
       AND d.rn > 1;

    -- event-time watermark: newest event time seen so far (history + this batch).
    -- An event is LATE if it happened more than 1 hour before the watermark.
    -- (We use event time, not the wall clock, so replaying old test files still works.)
    SELECT COALESCE(MAX(EVENT_TIME), '1900-01-01'::TIMESTAMP_NTZ) INTO :watermark
    FROM (
        SELECT EVENT_TIME FROM S2C_DEV.STREAMING.RISK_EVENT_LOG
        UNION ALL
        SELECT EVENT_TIME FROM S2C_DEV.STREAMING.RISK_WORK WHERE REJECT_REASON IS NULL
    );

    -- (c) dead letter: keep everything we did not process
    INSERT INTO S2C_DEV.STREAMING.RISK_DEAD_LETTER (EVENT_ID, REJECT_REASON, RAW, FILE_NAME, FILE_ROW_NUMBER, LOADED_AT)
    SELECT EVENT_ID, REJECT_REASON, RAW, FILE_NAME, FILE_ROW_NUMBER, LOADED_AT
    FROM S2C_DEV.STREAMING.RISK_WORK
    WHERE REJECT_REASON IS NOT NULL;
    n_bad := SQLROWCOUNT;

    -- (d) alerts: only for the newest event per supplier in this batch, and only
    --     if it is newer than what we already have (old, out-of-order events never alert)
    INSERT INTO S2C_DEV.STREAMING.RISK_ALERTS (EVENT_ID, SUPPLIER_VAT, ALERT_TYPE, RISK_SCORE, PREVIOUS_SCORE, EVENT_TIME, IS_LATE)
    SELECT x.EVENT_ID, x.SUPPLIER_VAT, a.alert_type, x.RISK_SCORE, x.prior_score, x.EVENT_TIME, x.is_late
    FROM (
        -- candidates: newest valid event per supplier that is newer than RISK_CURRENT
        SELECT l.EVENT_ID, l.SUPPLIER_VAT, l.RISK_SCORE, l.SANCTIONS_HIT, l.EVENT_TIME,
               COALESCE(c.RISK_SCORE, l.PREVIOUS_SCORE) AS prior_score,
               l.EVENT_TIME < DATEADD(HOUR, -1, :watermark) AS is_late
        FROM (
            SELECT *
            FROM S2C_DEV.STREAMING.RISK_WORK
            WHERE REJECT_REASON IS NULL
            QUALIFY ROW_NUMBER() OVER (PARTITION BY SUPPLIER_VAT ORDER BY EVENT_TIME DESC, FILE_ROW_NUMBER DESC) = 1
        ) l
        LEFT JOIN S2C_DEV.STREAMING.RISK_CURRENT c ON c.SUPPLIER_VAT = l.SUPPLIER_VAT
        WHERE c.LAST_EVENT_TIME IS NULL OR l.EVENT_TIME > c.LAST_EVENT_TIME
    ) x
    JOIN (SELECT column1 AS alert_type FROM VALUES ('SANCTIONS_HIT'), ('HIGH_RISK'), ('SCORE_JUMP')) a
      ON (a.alert_type = 'SANCTIONS_HIT' AND COALESCE(x.SANCTIONS_HIT, FALSE))
      OR (a.alert_type = 'HIGH_RISK'     AND x.RISK_SCORE >= 7 AND COALESCE(x.prior_score, 0) < 7)
      OR (a.alert_type = 'SCORE_JUMP'    AND x.RISK_SCORE - COALESCE(x.prior_score, x.RISK_SCORE) >= 3);
    n_alerts := SQLROWCOUNT;

    -- (e) full history of valid events
    INSERT INTO S2C_DEV.STREAMING.RISK_EVENT_LOG
    SELECT EVENT_ID, PAYLOAD_VERSION, SUPPLIER_VAT, RISK_SCORE, PREVIOUS_SCORE,
           CASE WHEN RISK_SCORE <= 3 THEN 'Low' WHEN RISK_SCORE <= 6 THEN 'Medium' ELSE 'High' END,
           REASON, COALESCE(SANCTIONS_HIT, FALSE), EVENT_TIME, LOADED_AT, CURRENT_TIMESTAMP(),
           EVENT_TIME < DATEADD(HOUR, -1, :watermark),
           FILE_NAME, FILE_ROW_NUMBER
    FROM S2C_DEV.STREAMING.RISK_WORK
    WHERE REJECT_REASON IS NULL;
    n_ok := SQLROWCOUNT;

    -- (f) current state: newest event wins, by EVENT_TIME (protects against out-of-order arrival)
    MERGE INTO S2C_DEV.STREAMING.RISK_CURRENT t
    USING (
        SELECT *
        FROM S2C_DEV.STREAMING.RISK_WORK
        WHERE REJECT_REASON IS NULL
        QUALIFY ROW_NUMBER() OVER (PARTITION BY SUPPLIER_VAT ORDER BY EVENT_TIME DESC, FILE_ROW_NUMBER DESC) = 1
    ) s
    ON t.SUPPLIER_VAT = s.SUPPLIER_VAT
    WHEN MATCHED AND s.EVENT_TIME > t.LAST_EVENT_TIME THEN UPDATE SET
        RISK_SCORE = s.RISK_SCORE,
        RISK_BAND = CASE WHEN s.RISK_SCORE <= 3 THEN 'Low' WHEN s.RISK_SCORE <= 6 THEN 'Medium' ELSE 'High' END,
        SANCTIONS_HIT = COALESCE(s.SANCTIONS_HIT, FALSE),
        LAST_EVENT_ID = s.EVENT_ID,
        LAST_EVENT_TIME = s.EVENT_TIME,
        UPDATED_AT = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT
        (SUPPLIER_VAT, RISK_SCORE, RISK_BAND, SANCTIONS_HIT, LAST_EVENT_ID, LAST_EVENT_TIME, UPDATED_AT)
        VALUES (s.SUPPLIER_VAT, s.RISK_SCORE,
                CASE WHEN s.RISK_SCORE <= 3 THEN 'Low' WHEN s.RISK_SCORE <= 6 THEN 'Medium' ELSE 'High' END,
                COALESCE(s.SANCTIONS_HIT, FALSE), s.EVENT_ID, s.EVENT_TIME, CURRENT_TIMESTAMP());

    RETURN 'Risk events: ' || n_in || ' read, ' || n_ok || ' processed, ' || n_bad || ' dead-lettered, '
           || n_alerts || ' alerts';
END;
$$;
