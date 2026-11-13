/* Acknowledge an issue after you have checked it (unblocks the dbt gate).
   Example: a file that was intentionally deleted from the stage. */
USE ROLE S2C_ADMIN;

-- see what is blocking
SELECT RULE_ID, RECORD_KEY, FILE_NAME, DETAIL, FIRST_SEEN_AT
FROM S2C_DEV.AUDIT.V_DQ_OPEN_FAILURES
WHERE IS_BLOCKING;

-- acknowledge one (edit the WHERE clause)
UPDATE S2C_DEV.AUDIT.DQ_FAILED_RECORDS
   SET ACKNOWLEDGED = TRUE,
       ACKNOWLEDGED_BY = CURRENT_USER(),
       ACKNOWLEDGED_NOTE = 'Checked: <why it is OK>'
 WHERE RULE_ID = 'AUD-F05'
   AND RECORD_KEY = '<file name>';
