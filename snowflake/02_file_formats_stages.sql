/* =============================================================================
   02_file_formats_stages.sql
   -----------------------------------------------------------------------------
   One file format per real-world format, and two internal stages.

   Design rule: "land everything". File formats are tolerant on purpose:
     - SKIP_HEADER = 0          the header row is loaded too (row 1), so schema
                                drift can be detected inside Snowflake
     - ERROR_ON_COLUMN_COUNT_MISMATCH = FALSE
                                extra columns go to _EXTRA_n, missing ones are NULL
     - REPLACE_INVALID_CHARACTERS = TRUE
                                bad bytes become U+FFFD instead of failing the file
     - all CSV columns are VARCHAR in RAW, so text in a number never fails
   Quality is checked AFTER loading by the audit layer (07/08) and dbt.
   ============================================================================= */

USE ROLE S2C_ADMIN;
USE DATABASE S2C_DEV;
USE SCHEMA RAW;

-- SAP extracts: semicolon separated, decimal comma kept as text
CREATE OR REPLACE FILE FORMAT S2C_DEV.RAW.FF_CSV_SEMICOLON
  TYPE = CSV
  FIELD_DELIMITER = ';'
  SKIP_HEADER = 0
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  EMPTY_FIELD_AS_NULL = TRUE
  TRIM_SPACE = FALSE                      -- keep trailing spaces so we can see them
  ERROR_ON_COLUMN_COUNT_MISMATCH = FALSE
  ENCODING = 'UTF8'
  REPLACE_INVALID_CHARACTERS = TRUE
  COMMENT = 'SAP table extracts (EKPO): ; separated, decimal comma';

-- normal comma separated files (cost centres, approvals, taxonomy, converted Excel)
CREATE OR REPLACE FILE FORMAT S2C_DEV.RAW.FF_CSV_COMMA
  TYPE = CSV
  FIELD_DELIMITER = ','
  SKIP_HEADER = 0
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  EMPTY_FIELD_AS_NULL = TRUE
  TRIM_SPACE = FALSE
  ERROR_ON_COLUMN_COUNT_MISMATCH = FALSE
  ENCODING = 'UTF8'
  REPLACE_INVALID_CHARACTERS = TRUE
  COMMENT = 'Comma separated files with a header row';

-- JSON documents (API exports) and NDJSON (one event per line)
CREATE OR REPLACE FILE FORMAT S2C_DEV.RAW.FF_JSON
  TYPE = JSON
  STRIP_OUTER_ARRAY = FALSE
  REPLACE_INVALID_CHARACTERS = TRUE
  COMMENT = 'API JSON documents and NDJSON event files';

-- XML: SAP IDoc and FX rates. STRIP_OUTER_ELEMENT gives one row per child element
CREATE OR REPLACE FILE FORMAT S2C_DEV.RAW.FF_XML
  TYPE = XML
  STRIP_OUTER_ELEMENT = TRUE
  DISABLE_AUTO_CONVERT = TRUE             -- keep '0000100001' as text (no leading-zero loss)
  REPLACE_INVALID_CHARACTERS = TRUE
  COMMENT = 'XML files: one row per element under the root';

-- Parquet: typed columns; USE_LOGICAL_TYPE keeps dates as dates
CREATE OR REPLACE FILE FORMAT S2C_DEV.RAW.FF_PARQUET
  TYPE = PARQUET
  USE_LOGICAL_TYPE = TRUE
  COMMENT = 'Parquet files (SAP invoice extract)';

-- -----------------------------------------------------------------------------
-- Stages
--   STG_BATCH   files loaded by the 10-minute batch task (COPY INTO)
--   STG_STREAM  files loaded by Snowpipe (risk events)
-- Every push lands in a UNIQUE path:
--   <source>/<entity>/<yyyy>/<mm>/<dd>/<commit_sha>/<file name>
-- so a re-sent file with the same name is never silently skipped.
-- -----------------------------------------------------------------------------
CREATE STAGE IF NOT EXISTS S2C_DEV.RAW.STG_BATCH
  DIRECTORY = (ENABLE = TRUE)
  COMMENT = 'Landing for batch files (pushed from GitHub)';

CREATE STAGE IF NOT EXISTS S2C_DEV.RAW.STG_STREAM
  DIRECTORY = (ENABLE = TRUE)
  COMMENT = 'Landing for streaming files (Snowpipe)';

-- loader may upload; transformer may list (useful for audits)
GRANT READ, WRITE ON STAGE S2C_DEV.RAW.STG_BATCH  TO ROLE S2C_LOADER;
GRANT READ, WRITE ON STAGE S2C_DEV.RAW.STG_STREAM TO ROLE S2C_LOADER;
GRANT READ ON STAGE S2C_DEV.RAW.STG_BATCH  TO ROLE S2C_TRANSFORMER;
GRANT READ ON STAGE S2C_DEV.RAW.STG_STREAM TO ROLE S2C_TRANSFORMER;
GRANT USAGE ON FILE FORMAT S2C_DEV.RAW.FF_CSV_SEMICOLON TO ROLE S2C_LOADER;
GRANT USAGE ON FILE FORMAT S2C_DEV.RAW.FF_CSV_COMMA     TO ROLE S2C_LOADER;
GRANT USAGE ON FILE FORMAT S2C_DEV.RAW.FF_JSON          TO ROLE S2C_LOADER;
GRANT USAGE ON FILE FORMAT S2C_DEV.RAW.FF_XML           TO ROLE S2C_LOADER;
GRANT USAGE ON FILE FORMAT S2C_DEV.RAW.FF_PARQUET       TO ROLE S2C_LOADER;
