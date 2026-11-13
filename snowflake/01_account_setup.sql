/* =============================================================================
   01_account_setup.sql
   -----------------------------------------------------------------------------
   One-time account setup: roles, warehouse, database, schemas, cost control,
   and the service user that GitHub Actions uses to upload files.

   Run as ACCOUNTADMIN (needed for the resource monitor and EXECUTE TASK).
   Everything after this file runs as S2C_ADMIN.

   To build a second environment, run scripts/run_sql.py with --db S2C_PROD
   (it replaces S2C_DEV in every script), or find/replace by hand.
   ============================================================================= */

USE ROLE ACCOUNTADMIN;

-- -----------------------------------------------------------------------------
-- 1. Roles (functional roles, least privilege)
--    S2C_ADMIN        owns every object in the project
--    S2C_LOADER       service role: upload files, register them, refresh the pipe
--    S2C_TRANSFORMER  dbt: reads RAW/AUDIT/STREAMING, builds STAGING..MARTS
--    S2C_ANALYST      reads the Gold layer (MARTS) only
--    S2C_PII_READER   may see unmasked emails (added on top of another role)
-- -----------------------------------------------------------------------------
CREATE ROLE IF NOT EXISTS S2C_ADMIN;
CREATE ROLE IF NOT EXISTS S2C_LOADER;
CREATE ROLE IF NOT EXISTS S2C_TRANSFORMER;
CREATE ROLE IF NOT EXISTS S2C_ANALYST;
CREATE ROLE IF NOT EXISTS S2C_PII_READER;

-- role hierarchy: SYSADMIN sees everything the project owns
GRANT ROLE S2C_LOADER      TO ROLE S2C_ADMIN;
GRANT ROLE S2C_TRANSFORMER TO ROLE S2C_ADMIN;
GRANT ROLE S2C_ANALYST     TO ROLE S2C_TRANSFORMER;
GRANT ROLE S2C_PII_READER  TO ROLE S2C_ADMIN;
GRANT ROLE S2C_ADMIN       TO ROLE SYSADMIN;

-- give yourself the admin role
SET my_user = CURRENT_USER();
GRANT ROLE S2C_ADMIN TO USER IDENTIFIER($my_user);

-- tasks need this account-level privilege
GRANT EXECUTE TASK ON ACCOUNT TO ROLE S2C_ADMIN;

-- -----------------------------------------------------------------------------
-- 2. Warehouse: extra-small, suspends after 60 s of idle time
-- -----------------------------------------------------------------------------
CREATE WAREHOUSE IF NOT EXISTS S2C_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'S2C project: loading, audit, dbt';

GRANT USAGE, OPERATE ON WAREHOUSE S2C_WH TO ROLE S2C_ADMIN;
GRANT USAGE ON WAREHOUSE S2C_WH TO ROLE S2C_LOADER;
GRANT USAGE ON WAREHOUSE S2C_WH TO ROLE S2C_TRANSFORMER;
GRANT USAGE ON WAREHOUSE S2C_WH TO ROLE S2C_ANALYST;

-- -----------------------------------------------------------------------------
-- 3. Cost control: stop the warehouse if it burns more than 20 credits a month
-- -----------------------------------------------------------------------------
CREATE RESOURCE MONITOR IF NOT EXISTS S2C_MONTHLY_RM
  WITH CREDIT_QUOTA = 20
  FREQUENCY = MONTHLY
  START_TIMESTAMP = IMMEDIATELY
  TRIGGERS
    ON 75 PERCENT DO NOTIFY
    ON 90 PERCENT DO NOTIFY
    ON 100 PERCENT DO SUSPEND;

ALTER WAREHOUSE S2C_WH SET RESOURCE_MONITOR = S2C_MONTHLY_RM;

-- -----------------------------------------------------------------------------
-- 4. Database and schemas (Medallion layers)
--    RAW          Bronze: every file lands here as-is (strings / VARIANT)
--    AUDIT        file registry, load log, data quality rules and results
--    STREAMING    near-real-time risk path (speed layer)
--    GOVERNANCE   masking policies and tags
--    STAGING, INTERMEDIATE, SNAPSHOTS, MARTS  built by dbt (Silver / Gold)
-- -----------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS S2C_DEV COMMENT = 'Source-to-Contract data platform (dev)';
GRANT OWNERSHIP ON DATABASE S2C_DEV TO ROLE S2C_ADMIN COPY CURRENT GRANTS;

USE ROLE S2C_ADMIN;
USE DATABASE S2C_DEV;

CREATE SCHEMA IF NOT EXISTS S2C_DEV.RAW          COMMENT = 'Bronze: files as delivered, plus file metadata';
CREATE SCHEMA IF NOT EXISTS S2C_DEV.AUDIT        COMMENT = 'File registry, load log, DQ rules and results';
CREATE SCHEMA IF NOT EXISTS S2C_DEV.STREAMING    COMMENT = 'Speed layer: supplier risk events';
CREATE SCHEMA IF NOT EXISTS S2C_DEV.GOVERNANCE   COMMENT = 'Masking policies and tags';
CREATE SCHEMA IF NOT EXISTS S2C_DEV.STAGING      COMMENT = 'Silver: built by dbt';
CREATE SCHEMA IF NOT EXISTS S2C_DEV.INTERMEDIATE COMMENT = 'Silver: built by dbt';
CREATE SCHEMA IF NOT EXISTS S2C_DEV.SNAPSHOTS    COMMENT = 'SCD2 history: built by dbt';
CREATE SCHEMA IF NOT EXISTS S2C_DEV.MARTS        COMMENT = 'Gold: star schema and KPIs, built by dbt';

-- -----------------------------------------------------------------------------
-- 5. Grants (run as ACCOUNTADMIN so future grants always work)
-- -----------------------------------------------------------------------------
USE ROLE ACCOUNTADMIN;
GRANT USAGE ON DATABASE S2C_DEV TO ROLE S2C_LOADER;
GRANT USAGE ON DATABASE S2C_DEV TO ROLE S2C_TRANSFORMER;
GRANT USAGE ON DATABASE S2C_DEV TO ROLE S2C_ANALYST;

-- loader: RAW + AUDIT (stage + registry objects get their own grants later)
GRANT USAGE ON SCHEMA S2C_DEV.RAW   TO ROLE S2C_LOADER;
GRANT USAGE ON SCHEMA S2C_DEV.AUDIT TO ROLE S2C_LOADER;

-- transformer (dbt): read the landing layers, own the dbt layers
GRANT USAGE ON SCHEMA S2C_DEV.RAW        TO ROLE S2C_TRANSFORMER;
GRANT USAGE ON SCHEMA S2C_DEV.AUDIT      TO ROLE S2C_TRANSFORMER;
GRANT USAGE ON SCHEMA S2C_DEV.STREAMING  TO ROLE S2C_TRANSFORMER;
GRANT USAGE ON SCHEMA S2C_DEV.GOVERNANCE TO ROLE S2C_TRANSFORMER;
GRANT SELECT ON ALL TABLES    IN SCHEMA S2C_DEV.RAW       TO ROLE S2C_TRANSFORMER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA S2C_DEV.RAW       TO ROLE S2C_TRANSFORMER;
GRANT SELECT ON ALL TABLES    IN SCHEMA S2C_DEV.AUDIT     TO ROLE S2C_TRANSFORMER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA S2C_DEV.AUDIT     TO ROLE S2C_TRANSFORMER;
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA S2C_DEV.AUDIT     TO ROLE S2C_TRANSFORMER;
GRANT SELECT ON ALL TABLES    IN SCHEMA S2C_DEV.STREAMING TO ROLE S2C_TRANSFORMER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA S2C_DEV.STREAMING TO ROLE S2C_TRANSFORMER;
GRANT ALL ON SCHEMA S2C_DEV.STAGING      TO ROLE S2C_TRANSFORMER;
GRANT ALL ON SCHEMA S2C_DEV.INTERMEDIATE TO ROLE S2C_TRANSFORMER;
GRANT ALL ON SCHEMA S2C_DEV.SNAPSHOTS    TO ROLE S2C_TRANSFORMER;
GRANT ALL ON SCHEMA S2C_DEV.MARTS        TO ROLE S2C_TRANSFORMER;

-- analyst: Gold only
GRANT USAGE ON SCHEMA S2C_DEV.MARTS TO ROLE S2C_ANALYST;
GRANT SELECT ON FUTURE TABLES IN SCHEMA S2C_DEV.MARTS TO ROLE S2C_ANALYST;
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA S2C_DEV.MARTS TO ROLE S2C_ANALYST;

-- -----------------------------------------------------------------------------
-- 6. Service user for GitHub Actions (key-pair auth, no password)
--    1) create a key pair on your laptop (see docs/github_setup.md)
--    2) paste the PUBLIC key below (without the BEGIN/END lines) and run
-- -----------------------------------------------------------------------------
USE ROLE ACCOUNTADMIN;
CREATE USER IF NOT EXISTS S2C_INGEST_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = S2C_LOADER
  DEFAULT_WAREHOUSE = S2C_WH
  DEFAULT_NAMESPACE = 'S2C_DEV.RAW'
  COMMENT = 'GitHub Actions: uploads pushed files to Snowflake stages';
-- ALTER USER S2C_INGEST_SVC SET RSA_PUBLIC_KEY = 'MIIBIjANBgkqh...';
GRANT ROLE S2C_LOADER TO USER S2C_INGEST_SVC;

USE ROLE S2C_ADMIN;
