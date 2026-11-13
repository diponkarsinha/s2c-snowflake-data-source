/* =============================================================================
   09_tasks.sql  - orchestration inside Snowflake
   -----------------------------------------------------------------------------
   Batch task graph (every 10 minutes while testing):

       TASK_LOAD_BATCH  (root, SCHEDULE = 10 MINUTE)   -> CALL SP_LOAD_BATCH()
            └── TASK_COLLECT_LOAD_HISTORY  (AFTER)     -> CALL SP_COLLECT_LOAD_HISTORY()
                    └── TASK_RUN_DQ        (AFTER)     -> CALL SP_RUN_DQ(FALSE)

   Stream task (speed layer):

       TASK_PROCESS_RISK_EVENTS (every minute, WHEN SYSTEM$STREAM_HAS_DATA)
            -> CALL SP_PROCESS_RISK_EVENTS()
       The WHEN condition is checked without a warehouse, so an idle minute
       costs nothing.

   Tasks are created SUSPENDED. Start them with snowflake/ops/resume_tasks.sql
   and STOP them with snowflake/ops/suspend_tasks.sql when you finish testing.
   For production, change the root schedule to a CRON, e.g.
       SCHEDULE = 'USING CRON 0 6 * * * Europe/Prague'
   ============================================================================= */

USE ROLE S2C_ADMIN;
USE DATABASE S2C_DEV;
USE SCHEMA AUDIT;

-- suspend the root first so the graph can be replaced
ALTER TASK IF EXISTS S2C_DEV.AUDIT.TASK_LOAD_BATCH SUSPEND;

CREATE OR REPLACE TASK S2C_DEV.AUDIT.TASK_LOAD_BATCH
  WAREHOUSE = S2C_WH
  SCHEDULE = '10 MINUTE'
  ALLOW_OVERLAPPING_EXECUTION = FALSE
  SUSPEND_TASK_AFTER_NUM_FAILURES = 3
  COMMENT = 'Root: COPY INTO all batch RAW tables'
AS
  CALL S2C_DEV.AUDIT.SP_LOAD_BATCH();

CREATE OR REPLACE TASK S2C_DEV.AUDIT.TASK_COLLECT_LOAD_HISTORY
  WAREHOUSE = S2C_WH
  COMMENT = 'Copies COPY_HISTORY (batch + Snowpipe) into FILE_LOAD_LOG'
  AFTER S2C_DEV.AUDIT.TASK_LOAD_BATCH
AS
  CALL S2C_DEV.AUDIT.SP_COLLECT_LOAD_HISTORY();

CREATE OR REPLACE TASK S2C_DEV.AUDIT.TASK_RUN_DQ
  WAREHOUSE = S2C_WH
  COMMENT = 'Runs the DQ rule catalogue (skips if nothing new arrived)'
  AFTER S2C_DEV.AUDIT.TASK_COLLECT_LOAD_HISTORY
AS
  CALL S2C_DEV.AUDIT.SP_RUN_DQ(FALSE);

-- speed layer
ALTER TASK IF EXISTS S2C_DEV.STREAMING.TASK_PROCESS_RISK_EVENTS SUSPEND;

CREATE OR REPLACE TASK S2C_DEV.STREAMING.TASK_PROCESS_RISK_EVENTS
  WAREHOUSE = S2C_WH
  SCHEDULE = '1 MINUTE'
  ALLOW_OVERLAPPING_EXECUTION = FALSE
  SUSPEND_TASK_AFTER_NUM_FAILURES = 5
  COMMENT = 'Processes new risk events when the stream has data'
WHEN
  SYSTEM$STREAM_HAS_DATA('S2C_DEV.RAW.RISK_EVENTS_STREAM')
AS
  CALL S2C_DEV.STREAMING.SP_PROCESS_RISK_EVENTS();

-- (all four tasks are now suspended; see ops/resume_tasks.sql)
SHOW TASKS IN DATABASE S2C_DEV;
