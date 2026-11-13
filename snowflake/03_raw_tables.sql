/* =============================================================================
   03_raw_tables.sql  (Bronze layer)
   -----------------------------------------------------------------------------
   One RAW table per entity. Two shapes:

   1) CSV files  -> every column VARCHAR, named after the source header,
                    plus _EXTRA_1.._EXTRA_3 to catch appended columns.
                    Row 1 of every file is the header row (kept on purpose).
   2) JSON / XML / Parquet -> one VARIANT column called RAW.

   Every table also has the same file-lineage columns:
     _FILE_NAME           path inside the stage (includes the commit SHA)
     _FILE_ROW_NUMBER     line / record number inside the file
     _FILE_CONTENT_KEY    checksum of the file content
     _FILE_LAST_MODIFIED  when the file was uploaded to the stage
     _LOADED_AT           when Snowflake started loading the file
   ============================================================================= */

USE ROLE S2C_ADMIN;
USE DATABASE S2C_DEV;
USE SCHEMA RAW;

-- ----------------------------------------------------------------- SAP ERP --

CREATE TABLE IF NOT EXISTS S2C_DEV.RAW.SAP_PO_ITEMS (
    EBELN VARCHAR,  -- purchase order number
    EBELP VARCHAR,  -- PO line (item) number, leading zeros
    BUKRS VARCHAR,  -- company code
    LIFNR VARCHAR,  -- SAP supplier number, leading zeros
    BEDAT VARCHAR,  -- PO date, YYYYMMDD
    MATKL VARCHAR,  -- material group (maps to category)
    TXZ01 VARCHAR,  -- short text
    MENGE VARCHAR,  -- quantity, decimal comma
    MEINS VARCHAR,  -- unit of measure
    NETPR VARCHAR,  -- net price, decimal comma
    PEINH VARCHAR,  -- price unit
    NETWR VARCHAR,  -- net value, decimal comma
    WAERS VARCHAR,  -- currency
    KOSTL VARCHAR,  -- cost centre
    KONNR VARCHAR,  -- contract reference (empty = no contract)
    LOEKZ VARCHAR,  -- deletion flag ('L' = deleted in SAP)
    AEDAT VARCHAR,  -- last changed date, YYYYMMDD
    _EXTRA_1 VARCHAR, _EXTRA_2 VARCHAR, _EXTRA_3 VARCHAR,
    _FILE_NAME VARCHAR, _FILE_ROW_NUMBER NUMBER, _FILE_CONTENT_KEY VARCHAR,
    _FILE_LAST_MODIFIED TIMESTAMP_NTZ, _LOADED_AT TIMESTAMP_LTZ
) COMMENT = 'SAP EKKO/EKPO purchase order lines (semicolon CSV). Row 1 per file = header.';

CREATE TABLE IF NOT EXISTS S2C_DEV.RAW.SAP_INVOICES (
    RAW VARIANT,
    _FILE_NAME VARCHAR, _FILE_ROW_NUMBER NUMBER, _FILE_CONTENT_KEY VARCHAR,
    _FILE_LAST_MODIFIED TIMESTAMP_NTZ, _LOADED_AT TIMESTAMP_LTZ
) COMMENT = 'SAP RBKP/RSEG invoice lines (Parquet), one row per invoice line';

CREATE TABLE IF NOT EXISTS S2C_DEV.RAW.SAP_SUPPLIERS (
    RAW VARIANT,
    _FILE_NAME VARCHAR, _FILE_ROW_NUMBER NUMBER, _FILE_CONTENT_KEY VARCHAR,
    _FILE_LAST_MODIFIED TIMESTAMP_NTZ, _LOADED_AT TIMESTAMP_LTZ
) COMMENT = 'SAP vendor master (IDoc CREMAS05 XML), one row per <IDOC>. Full reload.';

CREATE TABLE IF NOT EXISTS S2C_DEV.RAW.SAP_COST_CENTERS (
    KOSTL VARCHAR, KOKRS VARCHAR, BUKRS VARCHAR, COST_CENTER_NAME VARCHAR,
    BUSINESS_UNIT VARCHAR, RESPONSIBLE VARCHAR, VALID_FROM VARCHAR, VALID_TO VARCHAR,
    UPDATED_AT VARCHAR,
    _EXTRA_1 VARCHAR, _EXTRA_2 VARCHAR, _EXTRA_3 VARCHAR,
    _FILE_NAME VARCHAR, _FILE_ROW_NUMBER NUMBER, _FILE_CONTENT_KEY VARCHAR,
    _FILE_LAST_MODIFIED TIMESTAMP_NTZ, _LOADED_AT TIMESTAMP_LTZ
) COMMENT = 'SAP CSKS cost centres (CSV). Row 1 per file = header.';

CREATE TABLE IF NOT EXISTS S2C_DEV.RAW.SAP_FX_RATES (
    RAW VARIANT,
    _FILE_NAME VARCHAR, _FILE_ROW_NUMBER NUMBER, _FILE_CONTENT_KEY VARCHAR,
    _FILE_LAST_MODIFIED TIMESTAMP_NTZ, _LOADED_AT TIMESTAMP_LTZ
) COMMENT = 'SAP TCURR monthly FX rates (XML), one row per month <Cube time=...>';

-- ---------------------------------------------------------- Ariba Sourcing --

CREATE TABLE IF NOT EXISTS S2C_DEV.RAW.ARIBA_SOURCING_REQUESTS (
    RAW VARIANT,
    _FILE_NAME VARCHAR, _FILE_ROW_NUMBER NUMBER, _FILE_CONTENT_KEY VARCHAR,
    _FILE_LAST_MODIFIED TIMESTAMP_NTZ, _LOADED_AT TIMESTAMP_LTZ
) COMMENT = 'Sourcing requests (intake), paginated API JSON: one row per page {result:[...], meta:{...}}';

CREATE TABLE IF NOT EXISTS S2C_DEV.RAW.ARIBA_SOURCING_EVENTS (
    RAW VARIANT,
    _FILE_NAME VARCHAR, _FILE_ROW_NUMBER NUMBER, _FILE_CONTENT_KEY VARCHAR,
    _FILE_LAST_MODIFIED TIMESTAMP_NTZ, _LOADED_AT TIMESTAMP_LTZ
) COMMENT = 'Sourcing events with nested bids and award, one row per export {records:[...]}';

-- --------------------------------------------------------- Ariba Contracts --

CREATE TABLE IF NOT EXISTS S2C_DEV.RAW.ARIBA_CONTRACTS (
    RAW VARIANT,
    _FILE_NAME VARCHAR, _FILE_ROW_NUMBER NUMBER, _FILE_CONTENT_KEY VARCHAR,
    _FILE_LAST_MODIFIED TIMESTAMP_NTZ, _LOADED_AT TIMESTAMP_LTZ
) COMMENT = 'Contract workspaces, nested JSON, one row per export {contracts:[...]}';

CREATE TABLE IF NOT EXISTS S2C_DEV.RAW.ARIBA_CONTRACT_APPROVALS (
    APPROVAL_ID VARCHAR, CONTRACT_ID VARCHAR, STEP VARCHAR, APPROVER_ID VARCHAR,
    APPROVER_NAME VARCHAR, APPROVER_EMAIL VARCHAR, APPROVER_MANAGER_ID VARCHAR,
    APPROVER_TITLE VARCHAR, DECISION VARCHAR, DECIDED_AT VARCHAR,
    _EXTRA_1 VARCHAR, _EXTRA_2 VARCHAR, _EXTRA_3 VARCHAR,
    _FILE_NAME VARCHAR, _FILE_ROW_NUMBER NUMBER, _FILE_CONTENT_KEY VARCHAR,
    _FILE_LAST_MODIFIED TIMESTAMP_NTZ, _LOADED_AT TIMESTAMP_LTZ
) COMMENT = 'Contract approval steps (CSV); approver -> manager forms a hierarchy';

-- ----------------------------------------------------------- Supplier risk --

CREATE TABLE IF NOT EXISTS S2C_DEV.RAW.RISK_ESG (
    RAW VARIANT,
    _FILE_NAME VARCHAR, _FILE_ROW_NUMBER NUMBER, _FILE_CONTENT_KEY VARCHAR,
    _FILE_LAST_MODIFIED TIMESTAMP_NTZ, _LOADED_AT TIMESTAMP_LTZ
) COMMENT = 'Weekly risk + ESG file, one row per file {provider, generatedAt, suppliers:[...]}';

CREATE TABLE IF NOT EXISTS S2C_DEV.RAW.RISK_EVENTS (
    RAW VARIANT,
    _FILE_NAME VARCHAR, _FILE_ROW_NUMBER NUMBER, _FILE_CONTENT_KEY VARCHAR,
    _FILE_LAST_MODIFIED TIMESTAMP_NTZ, _LOADED_AT TIMESTAMP_LTZ
) COMMENT = 'Risk score events (NDJSON), loaded by Snowpipe, one row per event';

-- ------------------------------------------------------- Reference / manual --

CREATE TABLE IF NOT EXISTS S2C_DEV.RAW.REF_CATEGORIES (
    CATEGORY_ID VARCHAR, CATEGORY_NAME VARCHAR, PARENT_CATEGORY_ID VARCHAR, CATEGORY_LEVEL VARCHAR,  -- source header: level
    UNSPSC_CODE VARCHAR, SAP_MATERIAL_GROUP VARCHAR, IS_ACTIVE VARCHAR,
    VALID_FROM VARCHAR, VALID_TO VARCHAR, UPDATED_AT VARCHAR,
    _EXTRA_1 VARCHAR, _EXTRA_2 VARCHAR, _EXTRA_3 VARCHAR,
    _FILE_NAME VARCHAR, _FILE_ROW_NUMBER NUMBER, _FILE_CONTENT_KEY VARCHAR,
    _FILE_LAST_MODIFIED TIMESTAMP_NTZ, _LOADED_AT TIMESTAMP_LTZ
) COMMENT = 'Category taxonomy (3 levels, UNSPSC + SAP material group). Row 1 per file = header.';

CREATE TABLE IF NOT EXISTS S2C_DEV.RAW.MANUAL_SAVINGS (
    SHEET_ROW VARCHAR,             -- row number in the Excel sheet (added by the converter)
    SAVINGS_ID VARCHAR, EVENT_ID VARCHAR, CATEGORY VARCHAR, SUPPLIER VARCHAR,
    BASELINE_EUR VARCHAR, NEGOTIATED_EUR VARCHAR, SAVINGS_EUR VARCHAR, SAVINGS_DATE VARCHAR,
    VALIDATED_BY_FINANCE VARCHAR, OWNER VARCHAR, COMMENTS VARCHAR,
    _EXTRA_1 VARCHAR, _EXTRA_2 VARCHAR, _EXTRA_3 VARCHAR,
    _FILE_NAME VARCHAR, _FILE_ROW_NUMBER NUMBER, _FILE_CONTENT_KEY VARCHAR,
    _FILE_LAST_MODIFIED TIMESTAMP_NTZ, _LOADED_AT TIMESTAMP_LTZ
) COMMENT = 'Savings tracker kept in Excel; converted to CSV on upload. Includes blank and TOTAL rows.';

-- dbt (transformer) reads every RAW table
GRANT SELECT ON ALL TABLES IN SCHEMA S2C_DEV.RAW TO ROLE S2C_TRANSFORMER;
