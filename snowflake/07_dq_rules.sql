/* =============================================================================
   07_dq_rules.sql  - rule catalogue for the pre-dbt audit layer
   -----------------------------------------------------------------------------
   Every rule is one SELECT that returns the FAILING records with exactly these
   columns:  RAW_TABLE, FILE_NAME, FILE_ROW_NUMBER, RECORD_KEY, DETAIL
   (FILE_NAME + FILE_ROW_NUMBER join back to RAW._FILE_NAME / _FILE_ROW_NUMBER,
    so dbt can quarantine exactly the flagged rows.)

   Levels
     FILE    problems with the delivery itself (empty, duplicate, not loaded)
     SCHEMA  header / structure changed
     ROW     technical problems inside a record (types, keys, dates)
     STREAM  speed-layer health
   Business rules (blocked supplier, maverick spend, savings maths ...) live in
   dbt tests, not here. This layer answers: "did the data arrive complete and
   technically usable?"

   IS_BLOCKING = TRUE means data is incomplete, so dbt must not publish Gold
   until it is fixed or acknowledged (see snowflake/ops/acknowledge_issue.sql).
   Everything else is logged and the affected rows are quarantined by dbt.

   Re-runnable: deletes and re-inserts the catalogue.
   ============================================================================= */

USE ROLE S2C_ADMIN;
USE DATABASE S2C_DEV;
USE SCHEMA AUDIT;

DELETE FROM S2C_DEV.AUDIT.DQ_RULES;

INSERT INTO S2C_DEV.AUDIT.DQ_RULES
    (RULE_ID, RULE_NAME, CHECK_LEVEL, TARGET, SEVERITY, IS_BLOCKING, DESCRIPTION, ACTION, CHECK_SQL, IS_ACTIVE)
VALUES
-- ============================================================== FILE LEVEL ===
('AUD-F01', 'Empty or header-only file', 'FILE', 'FILE_REGISTRY', 'WARN', FALSE,
 'File was delivered but contains no data rows.',
 'Logged only. Nothing to load.',
$$
SELECT 'FILE_REGISTRY' AS RAW_TABLE, r.STAGE_PATH AS FILE_NAME, NULL::NUMBER AS FILE_ROW_NUMBER,
       r.FILE_NAME AS RECORD_KEY,
       'File has no data rows (' || r.SIZE_BYTES || ' bytes)' AS DETAIL
FROM S2C_DEV.AUDIT.FILE_REGISTRY r
WHERE r.DATA_ROW_COUNT = 0
$$, TRUE),

('AUD-F02', 'Exact duplicate delivery (same name, same content)', 'FILE', 'FILE_REGISTRY', 'WARN', FALSE,
 'A file with the same name and the same MD5 was delivered before (e.g. an SAP re-extract).',
 'File still lands in RAW. dbt staging keeps one row per business key.',
$$
SELECT 'FILE_REGISTRY' AS RAW_TABLE, r.STAGE_PATH AS FILE_NAME, NULL::NUMBER AS FILE_ROW_NUMBER,
       r.FILE_NAME AS RECORD_KEY,
       'Same name and content already delivered as ' || p.REPO_PATH AS DETAIL
FROM S2C_DEV.AUDIT.FILE_REGISTRY r
JOIN S2C_DEV.AUDIT.FILE_REGISTRY p
  ON p.FILE_NAME = r.FILE_NAME AND p.MD5 = r.MD5
 AND (p.REGISTERED_AT < r.REGISTERED_AT OR (p.REGISTERED_AT = r.REGISTERED_AT AND p.REGISTRY_ID < r.REGISTRY_ID)) AND p.REPO_PATH <> r.REPO_PATH
QUALIFY ROW_NUMBER() OVER (PARTITION BY r.REGISTRY_ID ORDER BY p.REGISTERED_AT, p.REGISTRY_ID) = 1
$$, TRUE),

('AUD-F03', 'Same file name, different content', 'FILE', 'FILE_REGISTRY', 'WARN', FALSE,
 'A file with a name seen before arrived with different content (a correction, or an overwrite).',
 'Both versions land. dbt keeps the latest version of each record (by change date / load time).',
$$
SELECT 'FILE_REGISTRY' AS RAW_TABLE, r.STAGE_PATH AS FILE_NAME, NULL::NUMBER AS FILE_ROW_NUMBER,
       r.FILE_NAME AS RECORD_KEY,
       'Name already used by ' || p.REPO_PATH || ' with different content' AS DETAIL
FROM S2C_DEV.AUDIT.FILE_REGISTRY r
JOIN S2C_DEV.AUDIT.FILE_REGISTRY p
  ON p.FILE_NAME = r.FILE_NAME AND p.MD5 <> r.MD5 AND (p.REGISTERED_AT < r.REGISTERED_AT OR (p.REGISTERED_AT = r.REGISTERED_AT AND p.REGISTRY_ID < r.REGISTRY_ID))
QUALIFY ROW_NUMBER() OVER (PARTITION BY r.REGISTRY_ID ORDER BY p.REGISTERED_AT DESC, p.REGISTRY_ID DESC) = 1
$$, TRUE),

('AUD-F04', 'Same content, different file name', 'FILE', 'FILE_REGISTRY', 'WARN', FALSE,
 'The same content (MD5) arrived again under a new name. Snowflake load history cannot catch this.',
 'File lands. RAW holds duplicates; dbt staging de-duplicates on the business key.',
$$
SELECT 'FILE_REGISTRY' AS RAW_TABLE, r.STAGE_PATH AS FILE_NAME, NULL::NUMBER AS FILE_ROW_NUMBER,
       r.FILE_NAME AS RECORD_KEY,
       'Identical content to ' || p.REPO_PATH AS DETAIL
FROM S2C_DEV.AUDIT.FILE_REGISTRY r
JOIN S2C_DEV.AUDIT.FILE_REGISTRY p
  ON p.MD5 = r.MD5 AND p.FILE_NAME <> r.FILE_NAME AND (p.REGISTERED_AT < r.REGISTERED_AT OR (p.REGISTERED_AT = r.REGISTERED_AT AND p.REGISTRY_ID < r.REGISTRY_ID))
WHERE r.DATA_ROW_COUNT > 0
QUALIFY ROW_NUMBER() OVER (PARTITION BY r.REGISTRY_ID ORDER BY p.REGISTERED_AT, p.REGISTRY_ID) = 1
$$, TRUE),

('AUD-F05', 'Uploaded but not loaded', 'FILE', 'FILE_REGISTRY', 'ERROR', TRUE,
 'File was uploaded to a stage more than 30 minutes ago but no load is recorded (silent skip, failed pipe, suspended task).',
 'BLOCKS Gold. Investigate, reload, then acknowledge.',
$$
SELECT 'FILE_REGISTRY' AS RAW_TABLE, r.STAGE_PATH AS FILE_NAME, NULL::NUMBER AS FILE_ROW_NUMBER,
       r.FILE_NAME AS RECORD_KEY,
       'Uploaded at ' || TO_VARCHAR(r.REGISTERED_AT, 'YYYY-MM-DD HH24:MI') || ' but not loaded' AS DETAIL
FROM S2C_DEV.AUDIT.FILE_REGISTRY r
WHERE r.EXPECTED_RAW_ROWS > 0
  AND r.REGISTERED_AT < DATEADD(MINUTE, -30, CURRENT_TIMESTAMP())
  AND NOT EXISTS (
        SELECT 1 FROM S2C_DEV.AUDIT.FILE_LOAD_LOG l
        WHERE (ENDSWITH(l.FILE_NAME, r.STAGE_PATH) OR l.FILE_NAME = r.STAGE_PATH)
          AND UPPER(REPLACE(l.STATUS, ' ', '_')) IN ('LOADED', 'PARTIALLY_LOADED'))
$$, TRUE),

('AUD-F06', 'Row count mismatch (file vs RAW)', 'FILE', 'FILE_LOAD_LOG', 'ERROR', TRUE,
 'Rows loaded into RAW differ from rows counted in the file before upload.',
 'BLOCKS Gold. Data is incomplete.',
$$
SELECT l.RAW_TABLE AS RAW_TABLE, r.STAGE_PATH AS FILE_NAME, NULL::NUMBER AS FILE_ROW_NUMBER,
       r.FILE_NAME AS RECORD_KEY,
       'Expected ' || r.EXPECTED_RAW_ROWS || ' rows in RAW, loaded ' || l.ROW_COUNT AS DETAIL
FROM S2C_DEV.AUDIT.FILE_REGISTRY r
JOIN S2C_DEV.AUDIT.FILE_LOAD_LOG l
  ON (ENDSWITH(l.FILE_NAME, r.STAGE_PATH) OR l.FILE_NAME = r.STAGE_PATH)
WHERE l.ROW_COUNT <> r.EXPECTED_RAW_ROWS
$$, TRUE),

('AUD-F07', 'Load errors reported by Snowflake', 'FILE', 'FILE_LOAD_LOG', 'ERROR', TRUE,
 'COPY / Snowpipe reported rejected rows or a failed file.',
 'BLOCKS Gold. Fix the file or the file format, reload.',
$$
SELECT l.RAW_TABLE AS RAW_TABLE, l.FILE_NAME AS FILE_NAME, l.FIRST_ERROR_LINE AS FILE_ROW_NUMBER,
       SPLIT_PART(l.FILE_NAME, '/', -1) AS RECORD_KEY,
       l.STATUS || ': ' || COALESCE(l.ERROR_COUNT, 0) || ' errors, first: ' || COALESCE(l.FIRST_ERROR, '-') AS DETAIL
FROM S2C_DEV.AUDIT.FILE_LOAD_LOG l
WHERE COALESCE(l.ERROR_COUNT, 0) > 0 OR UPPER(l.STATUS) LIKE '%FAIL%'
$$, TRUE),

('AUD-F08', 'Unusual file volume', 'FILE', 'PRELOAD_CHECK_LOG', 'WARN', FALSE,
 'Row count is more than 30% away from the average of the last 5 deliveries of the same entity.',
 'Logged. Someone checks whether it is a real spike or a broken extract.',
$$
SELECT 'PRELOAD_CHECK_LOG' AS RAW_TABLE, p.STAGE_PATH AS FILE_NAME, NULL::NUMBER AS FILE_ROW_NUMBER,
       p.FILE_NAME AS RECORD_KEY, p.DETAIL AS DETAIL
FROM S2C_DEV.AUDIT.PRELOAD_CHECK_LOG p
WHERE p.CHECK_NAME = 'VOLUME' AND p.STATUS <> 'PASS'
$$, TRUE),

-- ============================================================ SCHEMA LEVEL ===
('AUD-S01', 'Schema drift (header changed)', 'SCHEMA', 'PRELOAD_CHECK_LOG', 'ERROR', FALSE,
 'CSV/Excel header differs from the expected header (renamed, added or missing columns).',
 'Data still lands (positional columns + _EXTRA_n). Update the mapping in dbt staging, then acknowledge.',
$$
SELECT 'PRELOAD_CHECK_LOG' AS RAW_TABLE, p.STAGE_PATH AS FILE_NAME, NULL::NUMBER AS FILE_ROW_NUMBER,
       p.FILE_NAME AS RECORD_KEY, p.DETAIL AS DETAIL
FROM S2C_DEV.AUDIT.PRELOAD_CHECK_LOG p
WHERE p.CHECK_NAME = 'SCHEMA' AND p.STATUS <> 'PASS'
$$, TRUE),

('AUD-S02', 'PO header in RAW differs from expected', 'SCHEMA', 'RAW.SAP_PO_ITEMS', 'ERROR', FALSE,
 'Same check as AUD-S01 but done inside Snowflake on row 1 of every PO file.',
 'Shows drift can be detected without the uploader.',
$$
SELECT 'SAP_PO_ITEMS' AS RAW_TABLE, h._FILE_NAME AS FILE_NAME, h._FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       SPLIT_PART(h._FILE_NAME, '/', -1) AS RECORD_KEY,
       'Header: ' || h.hdr || ' | expected: ' || c.EXPECTED_HEADER AS DETAIL
FROM (
    SELECT _FILE_NAME, _FILE_ROW_NUMBER,
           ARRAY_TO_STRING(ARRAY_CONSTRUCT_COMPACT(EBELN, EBELP, BUKRS, LIFNR, BEDAT, MATKL, TXZ01, MENGE, MEINS,
               NETPR, PEINH, NETWR, WAERS, KOSTL, KONNR, LOEKZ, AEDAT, _EXTRA_1, _EXTRA_2, _EXTRA_3), ';') AS hdr
    FROM S2C_DEV.RAW.SAP_PO_ITEMS
    WHERE _FILE_ROW_NUMBER = 1
) h
JOIN S2C_DEV.AUDIT.INGEST_CONFIG c ON c.ENTITY = 'sap/po_items'
WHERE h.hdr <> c.EXPECTED_HEADER
$$, TRUE),

-- =============================================================== ROW LEVEL ===
('AUD-R01', 'PO line delivered more than once', 'ROW', 'RAW.SAP_PO_ITEMS', 'WARN', FALSE,
 'The same EBELN + EBELP appears in more than one row (re-extracts, corrections, changes).',
 'Expected for changes. dbt keeps the latest version (AEDAT, then load time).',
$$
SELECT 'SAP_PO_ITEMS' AS RAW_TABLE, d._FILE_NAME AS FILE_NAME, d._FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       d.k AS RECORD_KEY, 'PO line delivered ' || d.cnt || ' times' AS DETAIL
FROM (
    SELECT _FILE_NAME, _FILE_ROW_NUMBER, EBELN || '-' || EBELP AS k,
           COUNT(*) OVER (PARTITION BY EBELN, EBELP) AS cnt
    FROM S2C_DEV.RAW.SAP_PO_ITEMS
    WHERE _FILE_ROW_NUMBER > 1 AND EBELN IS NOT NULL AND EBELP IS NOT NULL
) d
WHERE d.cnt > 1
$$, TRUE),

('AUD-R02', 'PO quantity / price / value not numeric', 'ROW', 'RAW.SAP_PO_ITEMS', 'ERROR', FALSE,
 'MENGE, NETPR or NETWR cannot be read as a number (text, shifted columns).',
 'Row is quarantined by dbt.',
$$
SELECT 'SAP_PO_ITEMS' AS RAW_TABLE, _FILE_NAME AS FILE_NAME, _FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       COALESCE(EBELN, '?') || '-' || COALESCE(EBELP, '?') AS RECORD_KEY,
       'MENGE=' || COALESCE(MENGE, 'null') || ' NETPR=' || COALESCE(NETPR, 'null') || ' NETWR=' || COALESCE(NETWR, 'null') AS DETAIL
FROM S2C_DEV.RAW.SAP_PO_ITEMS
WHERE _FILE_ROW_NUMBER > 1
  AND (   (MENGE IS NOT NULL AND TRY_TO_NUMBER(REPLACE(MENGE, ',', '.'), 18, 3) IS NULL)
       OR (NETPR IS NOT NULL AND TRY_TO_NUMBER(REPLACE(NETPR, ',', '.'), 18, 2) IS NULL)
       OR (NETWR IS NOT NULL AND TRY_TO_NUMBER(REPLACE(NETWR, ',', '.'), 18, 2) IS NULL))
$$, TRUE),

('AUD-R03', 'PO line missing a key field', 'ROW', 'RAW.SAP_PO_ITEMS', 'ERROR', FALSE,
 'EBELN, EBELP or LIFNR is empty.',
 'Row is quarantined by dbt.',
$$
SELECT 'SAP_PO_ITEMS' AS RAW_TABLE, _FILE_NAME AS FILE_NAME, _FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       COALESCE(EBELN, '?') || '-' || COALESCE(EBELP, '?') AS RECORD_KEY,
       'Missing: ' || ARRAY_TO_STRING(ARRAY_CONSTRUCT_COMPACT(
            IFF(EBELN IS NULL, 'EBELN', NULL), IFF(EBELP IS NULL, 'EBELP', NULL), IFF(LIFNR IS NULL, 'LIFNR', NULL)), ', ') AS DETAIL
FROM S2C_DEV.RAW.SAP_PO_ITEMS
WHERE _FILE_ROW_NUMBER > 1 AND (EBELN IS NULL OR EBELP IS NULL OR LIFNR IS NULL)
$$, TRUE),

('AUD-R04', 'PO date invalid', 'ROW', 'RAW.SAP_PO_ITEMS', 'ERROR', FALSE,
 'BEDAT or AEDAT is not a valid YYYYMMDD date.',
 'Row is quarantined by dbt.',
$$
SELECT 'SAP_PO_ITEMS' AS RAW_TABLE, _FILE_NAME AS FILE_NAME, _FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       COALESCE(EBELN, '?') || '-' || COALESCE(EBELP, '?') AS RECORD_KEY,
       'BEDAT=' || COALESCE(BEDAT, 'null') || ' AEDAT=' || COALESCE(AEDAT, 'null') AS DETAIL
FROM S2C_DEV.RAW.SAP_PO_ITEMS
WHERE _FILE_ROW_NUMBER > 1
  AND (TRY_TO_DATE(BEDAT, 'YYYYMMDD') IS NULL OR (AEDAT IS NOT NULL AND TRY_TO_DATE(AEDAT, 'YYYYMMDD') IS NULL))
$$, TRUE),

('AUD-R05', 'PO value <> quantity x price', 'ROW', 'RAW.SAP_PO_ITEMS', 'WARN', FALSE,
 'NETWR differs from MENGE x NETPR / PEINH by more than 1%.',
 'Logged; row kept. Finance checks the line.',
$$
SELECT 'SAP_PO_ITEMS' AS RAW_TABLE, _FILE_NAME AS FILE_NAME, _FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       EBELN || '-' || EBELP AS RECORD_KEY,
       'NETWR=' || netwr || ' but MENGE x NETPR = ' || ROUND(menge * netpr / NULLIF(peinh, 0), 2) AS DETAIL
FROM (
    SELECT _FILE_NAME, _FILE_ROW_NUMBER, EBELN, EBELP,
           TRY_TO_NUMBER(REPLACE(MENGE, ',', '.'), 18, 3) AS menge,
           TRY_TO_NUMBER(REPLACE(NETPR, ',', '.'), 18, 2) AS netpr,
           TRY_TO_NUMBER(REPLACE(NETWR, ',', '.'), 18, 2) AS netwr,
           COALESCE(TRY_TO_NUMBER(PEINH), 1) AS peinh
    FROM S2C_DEV.RAW.SAP_PO_ITEMS
    WHERE _FILE_ROW_NUMBER > 1
)
WHERE menge IS NOT NULL AND netpr IS NOT NULL AND netwr IS NOT NULL
  AND ABS(netwr - menge * netpr / NULLIF(peinh, 0)) > 0.01 * ABS(netwr) + 0.01
$$, TRUE),

('AUD-R06', 'Invalid characters (encoding)', 'ROW', 'RAW.SAP_PO_ITEMS', 'WARN', FALSE,
 'Text contains U+FFFD: the file had bytes that are not valid UTF-8 (e.g. Latin-1).',
 'Row kept; text is cleaned in dbt. Ask the source to send UTF-8.',
$$
SELECT 'SAP_PO_ITEMS' AS RAW_TABLE, _FILE_NAME AS FILE_NAME, _FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       COALESCE(EBELN, '?') || '-' || COALESCE(EBELP, '?') AS RECORD_KEY,
       'TXZ01=' || TXZ01 AS DETAIL
FROM S2C_DEV.RAW.SAP_PO_ITEMS
WHERE _FILE_ROW_NUMBER > 1 AND CONTAINS(TXZ01, CHR(65533))
$$, TRUE),

('AUD-R07', 'Invoice line delivered more than once', 'ROW', 'RAW.SAP_INVOICES', 'WARN', FALSE,
 'The same BELNR + GJAHR + BUZEI appears more than once.',
 'dbt keeps one row per invoice line.',
$$
SELECT 'SAP_INVOICES' AS RAW_TABLE, d._FILE_NAME AS FILE_NAME, d._FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       d.k AS RECORD_KEY, 'Invoice line delivered ' || d.cnt || ' times' AS DETAIL
FROM (
    SELECT _FILE_NAME, _FILE_ROW_NUMBER, k, COUNT(*) OVER (PARTITION BY k) AS cnt
    FROM (
        SELECT _FILE_NAME, _FILE_ROW_NUMBER,
               RAW:"BELNR"::STRING || '-' || RAW:"GJAHR"::STRING || '-' || RAW:"BUZEI"::STRING AS k
        FROM S2C_DEV.RAW.SAP_INVOICES
    )
) d
WHERE d.cnt > 1
$$, TRUE),

('AUD-R08', 'Late-arriving invoice', 'ROW', 'RAW.SAP_INVOICES', 'INFO', FALSE,
 'Posting date is more than 30 days older than the newest posting date loaded before this file.',
 'Row kept. dbt incremental models must use a lookback window to pick it up.',
$$
WITH f AS (
    SELECT _FILE_NAME, MIN(_LOADED_AT) AS loaded_at, MAX(TRY_TO_DATE(RAW:"BUDAT"::STRING)) AS max_budat
    FROM S2C_DEV.RAW.SAP_INVOICES
    GROUP BY _FILE_NAME
),
w AS (
    SELECT _FILE_NAME,
           MAX(max_budat) OVER (ORDER BY loaded_at ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS watermark
    FROM f
)
SELECT 'SAP_INVOICES' AS RAW_TABLE, i._FILE_NAME AS FILE_NAME, i._FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       i.RAW:"BELNR"::STRING || '-' || i.RAW:"GJAHR"::STRING || '-' || i.RAW:"BUZEI"::STRING AS RECORD_KEY,
       'BUDAT ' || i.RAW:"BUDAT"::STRING || ' is older than watermark ' || w.watermark AS DETAIL
FROM S2C_DEV.RAW.SAP_INVOICES i
JOIN w ON w._FILE_NAME = i._FILE_NAME
WHERE TRY_TO_DATE(i.RAW:"BUDAT"::STRING) < DATEADD(DAY, -30, w.watermark)
$$, TRUE),

('AUD-R09', 'Request updated before it was created', 'ROW', 'RAW.ARIBA_SOURCING_REQUESTS', 'WARN', FALSE,
 'updated_at is earlier than created_at (clock / timezone problem in the source).',
 'Row kept. dbt uses GREATEST(created_at, updated_at) for change tracking.',
$$
SELECT 'ARIBA_SOURCING_REQUESTS' AS RAW_TABLE, r._FILE_NAME AS FILE_NAME, r._FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       f.value:request_id::STRING AS RECORD_KEY,
       'updated_at ' || f.value:updated_at::STRING || ' < created_at ' || f.value:created_at::STRING AS DETAIL
FROM S2C_DEV.RAW.ARIBA_SOURCING_REQUESTS r,
     LATERAL FLATTEN(input => r.RAW:result) f
WHERE TRY_TO_TIMESTAMP_NTZ(f.value:updated_at::STRING) < TRY_TO_TIMESTAMP_NTZ(f.value:created_at::STRING)
$$, TRUE),

('AUD-R10', 'Contract without contractId', 'ROW', 'RAW.ARIBA_CONTRACTS', 'ERROR', FALSE,
 'A contract record has no ID, so it cannot be tracked.',
 'Record is quarantined by dbt.',
$$
SELECT 'ARIBA_CONTRACTS' AS RAW_TABLE, c._FILE_NAME AS FILE_NAME, c._FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       '(index ' || f.index || ')' AS RECORD_KEY, 'contractId is missing' AS DETAIL
FROM S2C_DEV.RAW.ARIBA_CONTRACTS c,
     LATERAL FLATTEN(input => c.RAW:contracts) f
WHERE f.value:contractId IS NULL OR f.value:contractId::STRING = ''
$$, TRUE),

('AUD-R11', 'Risk score out of range', 'ROW', 'RAW.RISK_ESG', 'WARN', FALSE,
 'financialRisk must be between 1 and 9.',
 'Row kept; dbt sets the score to NULL and the supplier counts as "not assessed".',
$$
SELECT 'RISK_ESG' AS RAW_TABLE, r._FILE_NAME AS FILE_NAME, r._FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       f.value:supplier:vatNumber::STRING AS RECORD_KEY,
       'financialRisk = ' || COALESCE(f.value:scores:financialRisk::STRING, 'null') AS DETAIL
FROM S2C_DEV.RAW.RISK_ESG r,
     LATERAL FLATTEN(input => r.RAW:suppliers) f
WHERE TRY_TO_NUMBER(f.value:scores:financialRisk::STRING) IS NULL
   OR TRY_TO_NUMBER(f.value:scores:financialRisk::STRING) NOT BETWEEN 1 AND 9
$$, TRUE),

('AUD-R12', 'Non-data row in the savings sheet', 'ROW', 'RAW.MANUAL_SAVINGS', 'WARN', FALSE,
 'Hand-made TOTAL row or blank row in the Excel tracker.',
 'Row kept in RAW; dbt filters it out.',
$$
SELECT 'MANUAL_SAVINGS' AS RAW_TABLE, _FILE_NAME AS FILE_NAME, _FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       COALESCE(SAVINGS_ID, '(blank row ' || COALESCE(SHEET_ROW, '?') || ')') AS RECORD_KEY,
       IFF(UPPER(TRIM(SAVINGS_ID)) = 'TOTAL', 'Hand-made TOTAL row', 'Blank row in the sheet') AS DETAIL
FROM S2C_DEV.RAW.MANUAL_SAVINGS
WHERE _FILE_ROW_NUMBER > 1
  AND (UPPER(TRIM(SAVINGS_ID)) = 'TOTAL'
       OR (SAVINGS_ID IS NULL AND EVENT_ID IS NULL AND SAVINGS_EUR IS NULL))
$$, TRUE),

('AUD-R13', 'Mixed boolean types (autoRenew)', 'ROW', 'RAW.ARIBA_CONTRACTS', 'INFO', FALSE,
 'autoRenew arrives as true/false, "Y"/"N" or "true" (text).',
 'dbt normalises it with a macro.',
$$
SELECT 'ARIBA_CONTRACTS' AS RAW_TABLE, c._FILE_NAME AS FILE_NAME, c._FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       f.value:contractId::STRING AS RECORD_KEY,
       'autoRenew = ' || f.value:term:autoRenew::STRING || ' (' || TYPEOF(f.value:term:autoRenew) || ')' AS DETAIL
FROM S2C_DEV.RAW.ARIBA_CONTRACTS c,
     LATERAL FLATTEN(input => c.RAW:contracts) f
WHERE TYPEOF(f.value:term:autoRenew) <> 'BOOLEAN'
$$, TRUE),

('AUD-R14', 'Savings date not ISO (typed by hand)', 'ROW', 'RAW.MANUAL_SAVINGS', 'INFO', FALSE,
 'Savings Date is text like 03/10/2026 instead of a real date.',
 'dbt parses DD/MM/YYYY explicitly (never MM/DD).',
$$
SELECT 'MANUAL_SAVINGS' AS RAW_TABLE, _FILE_NAME AS FILE_NAME, _FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       SAVINGS_ID AS RECORD_KEY, 'Savings Date = ' || SAVINGS_DATE AS DETAIL
FROM S2C_DEV.RAW.MANUAL_SAVINGS
WHERE _FILE_ROW_NUMBER > 1 AND SAVINGS_DATE IS NOT NULL
  AND TRY_TO_DATE(SAVINGS_DATE, 'YYYY-MM-DD') IS NULL
$$, TRUE),

-- ============================================================ STREAM LEVEL ===
('AUD-T01', 'Risk events sent to dead letter', 'STREAM', 'STREAMING.RISK_DEAD_LETTER', 'WARN', FALSE,
 'Events the speed layer could not process (invalid, duplicate, unsupported version).',
 'Kept in RISK_DEAD_LETTER; fix and replay if needed.',
$$
SELECT 'RISK_EVENTS' AS RAW_TABLE, FILE_NAME AS FILE_NAME, FILE_ROW_NUMBER AS FILE_ROW_NUMBER,
       COALESCE(EVENT_ID, '(no event_id)') AS RECORD_KEY, REJECT_REASON AS DETAIL
FROM S2C_DEV.STREAMING.RISK_DEAD_LETTER
$$, TRUE),

('AUD-T02', 'Snowpipe not running', 'STREAM', 'RAW.PIPE_RISK_EVENTS', 'WARN', FALSE,
 'The pipe is paused or stalled, so streaming files will not load.',
 'Resume the pipe: ALTER PIPE ... SET PIPE_EXECUTION_PAUSED = FALSE.',
$$
SELECT 'RISK_EVENTS' AS RAW_TABLE, NULL::VARCHAR AS FILE_NAME, NULL::NUMBER AS FILE_ROW_NUMBER,
       'PIPE_RISK_EVENTS' AS RECORD_KEY, 'Pipe state: ' || s.state AS DETAIL
FROM (SELECT PARSE_JSON(SYSTEM$PIPE_STATUS('S2C_DEV.RAW.PIPE_RISK_EVENTS')):executionState::STRING AS state) s
WHERE s.state <> 'RUNNING'
$$, TRUE),

('AUD-T03', 'Stream backlog not processed', 'STREAM', 'RAW.RISK_EVENTS', 'WARN', FALSE,
 'Events loaded more than 10 minutes ago are neither in RISK_EVENT_LOG nor in the dead letter (task suspended or failing).',
 'Check TASK_PROCESS_RISK_EVENTS history. (We compare tables instead of reading the stream, so this check never consumes it.)',
$$
SELECT 'RISK_EVENTS' AS RAW_TABLE, MIN(r._FILE_NAME) AS FILE_NAME, NULL::NUMBER AS FILE_ROW_NUMBER,
       'RISK_EVENTS_BACKLOG' AS RECORD_KEY,
       COUNT(*) || ' events waiting since ' || TO_VARCHAR(MIN(r._LOADED_AT), 'YYYY-MM-DD HH24:MI') AS DETAIL
FROM S2C_DEV.RAW.RISK_EVENTS r
WHERE r._LOADED_AT < DATEADD(MINUTE, -10, CURRENT_TIMESTAMP())
  AND NOT EXISTS (SELECT 1 FROM S2C_DEV.STREAMING.RISK_EVENT_LOG l
                  WHERE l.FILE_NAME = r._FILE_NAME AND l.FILE_ROW_NUMBER = r._FILE_ROW_NUMBER)
  AND NOT EXISTS (SELECT 1 FROM S2C_DEV.STREAMING.RISK_DEAD_LETTER d
                  WHERE d.FILE_NAME = r._FILE_NAME AND d.FILE_ROW_NUMBER = r._FILE_ROW_NUMBER)
HAVING COUNT(*) > 0
$$, TRUE);

SELECT RULE_ID, CHECK_LEVEL, SEVERITY, IS_BLOCKING, RULE_NAME FROM S2C_DEV.AUDIT.DQ_RULES ORDER BY RULE_ID;
