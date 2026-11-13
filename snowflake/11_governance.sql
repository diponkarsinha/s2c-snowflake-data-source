/* =============================================================================
   11_governance.sql  - PII protection
   -----------------------------------------------------------------------------
   Emails of employees (requesters, owners, approvers) are personal data (GDPR).
   RAW keeps them as delivered (only the admin and dbt roles can read RAW).
   dbt applies this masking policy to the email columns in STAGING and MARTS,
   so analysts see "*****@samplepharma.example" unless they hold S2C_PII_READER.

   In dbt (s2c-dbt-analytics) the policy is attached with a post-hook:
     ALTER TABLE ... MODIFY COLUMN requested_by_email
       SET MASKING POLICY S2C_DEV.GOVERNANCE.MP_EMAIL;
   ============================================================================= */

USE ROLE S2C_ADMIN;
USE DATABASE S2C_DEV;
USE SCHEMA GOVERNANCE;

CREATE MASKING POLICY IF NOT EXISTS S2C_DEV.GOVERNANCE.MP_EMAIL
  AS (val STRING) RETURNS STRING ->
  CASE
      WHEN val IS NULL THEN NULL
      WHEN IS_ROLE_IN_SESSION('S2C_PII_READER') THEN val
      ELSE REGEXP_REPLACE(val, '^[^@]+', '*****')
  END
  COMMENT = 'Masks the local part of an email unless the session has S2C_PII_READER';

CREATE TAG IF NOT EXISTS S2C_DEV.GOVERNANCE.PII
  ALLOWED_VALUES 'email', 'name', 'bank_account', 'tax_id'
  COMMENT = 'Marks columns that contain personal or sensitive data';

-- dbt (transformer) needs to attach the policy and tag to the tables it builds
GRANT APPLY ON MASKING POLICY S2C_DEV.GOVERNANCE.MP_EMAIL TO ROLE S2C_TRANSFORMER;
GRANT APPLY ON TAG S2C_DEV.GOVERNANCE.PII TO ROLE S2C_TRANSFORMER;

-- How to test: after dbt has built a model with a masked email column,
-- query it as S2C_ANALYST (masked) and then as S2C_ADMIN (clear text).
