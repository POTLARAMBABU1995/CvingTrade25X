-- CvingTrade25X Sector Rotation V3 - destructive database rollback.
--
-- Normal application rollback is configuration-only:
--   SECTOR_ROTATION_ENGINE_VERSION=v2
--   VITE_SECTOR_ROTATION_VERSION=v2
-- Keep the V3 tables for audit/review whenever possible.
--
-- This script drops only the four additive V3 tables. It does not reference or
-- modify any V1/V2 object. Run it only after all of the following are true:
--   1. Explicit human approval to discard V3 snapshot/audit data was recorded.
--   2. The V3 refresh job and route selection were disabled.
--   3. Required V3 data was exported/backed up.
--   4. The confirmation value below was deliberately changed.
--
-- Safety gate: leave this value as NO for a guaranteed no-op failure.
DEFINE CONFIRM_V3_DROP = 'NO'

SET SERVEROUTPUT ON;
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK;

BEGIN
  IF UPPER('&&CONFIRM_V3_DROP') <> 'DROP_SECTOR_ROTATION_V3' THEN
    RAISE_APPLICATION_ERROR(
      -20051,
      'V3 objects were preserved. Set CONFIRM_V3_DROP to DROP_SECTOR_ROTATION_V3 only after explicit approval.'
    );
  END IF;
END;
/

SET DEFINE OFF;

DECLARE
  PROCEDURE drop_table_if_exists(p_table_name IN VARCHAR2) IS
    v_count PLS_INTEGER;
  BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM user_tables
     WHERE table_name = UPPER(p_table_name);

    IF v_count = 1 THEN
      EXECUTE IMMEDIATE 'DROP TABLE ' || UPPER(p_table_name) || ' CASCADE CONSTRAINTS';
      DBMS_OUTPUT.PUT_LINE('Dropped table ' || UPPER(p_table_name));
    ELSE
      DBMS_OUTPUT.PUT_LINE('Table already absent: ' || UPPER(p_table_name));
    END IF;
  END;
BEGIN
  -- Child-to-parent order preserves referential-integrity safety.
  drop_table_if_exists('NSE_SECTOR_ROT_COMP_V3');
  drop_table_if_exists('NSE_SECTOR_ROTATION_SNAP_V3');
  drop_table_if_exists('NSE_SECTOR_ROT_RUN_V3');
  drop_table_if_exists('NSE_SECTOR_ROT_CONFIG_V3');
END;
/

PROMPT Sector Rotation V3 database objects were dropped.
PROMPT V1 and V2 objects were not modified.
