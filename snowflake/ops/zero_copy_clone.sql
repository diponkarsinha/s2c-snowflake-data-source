/* Make a full copy of DEV in seconds for a risky test (no extra storage until data changes). */
USE ROLE S2C_ADMIN;
CREATE OR REPLACE DATABASE S2C_DEV_CLONE CLONE S2C_DEV;
-- ... test something destructive in S2C_DEV_CLONE ...
-- DROP DATABASE S2C_DEV_CLONE;

/* Time Travel: see a table as it was 30 minutes ago, or undo a mistake */
-- SELECT COUNT(*) FROM S2C_DEV.RAW.SAP_PO_ITEMS AT(OFFSET => -60*30);
-- CREATE TABLE S2C_DEV.RAW.SAP_PO_ITEMS_RESTORED CLONE S2C_DEV.RAW.SAP_PO_ITEMS AT(OFFSET => -60*30);
