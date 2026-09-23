# Final Summary

## Confirmed Runtime Findings

- Current live runtime is `SYSTEM@orcl` in `CDB$ROOT`.
- No dedicated application schema was confirmed for the live website objects.
- `ORCLPDB` was observed as mounted only and is not the active runtime target.
- The two largest live application tables are:
  - `SYSTEM.NSE_NIFTY500_DAILY_RAW_DATA_DEV` at about `2,326,814` rows in `SYSTEM`
  - `SYSTEM.FACT_OHLCV` at about `2,146,116` rows and partitioned in `SYSTEM`

## Safe First Actions

- Create the backup folders under `E:\DB_BACKUP_SAFETY`.
- Create Oracle DIRECTORY objects for Data Pump and report output.
- Run the inventory, tablespace, and validation scripts.
- Extract DDL for all discovered application objects.
- Run the approved object-list Data Pump export with `expdp_used_objects.par`.
- Optionally run the RMAN script for an extra safety backup.

## Review Before Storage Changes

- Confirm the Data Pump export completed successfully.
- Confirm the DDL extract completed successfully.
- Confirm pre-move row counts, object counts, and invalid-object baselines were captured.
- Review the move and rollback scripts together.
- Review materialized view status, especially:
  - `MV_NIFTY50_DAILY_SNAP`
  - `MV_NIFTY_MIDCAP150_DAILY_SNAP`
  - `MV_NIFTY_SMALLCAP250_DAILY_SNAP`
  - `MV_NSE50_DAILY_6M`
  - `MV_NSE_SECTOR_UI_SNAPSHOT`

## What Must Never Auto-Execute

- `SCHEMAS=SYSTEM` Data Pump export
- Any drop statement against app tables, indexes, sequences, views, procedures, packages, triggers, synonyms, or materialized views
- Any direct modification of Oracle internal system objects
- Any non-partition-aware move of `FACT_OHLCV`

## Storage Design Chosen

- New dedicated tablespaces:
  - `CVING_DATA`
  - `CVING_INDEX`
  - `CVING_LOB`
  - `CVING_MV`
- New datafiles under `E:\DB_BACKUP_SAFETY\ORADATA`
- Existing app placement in `CVING_APP` and `USERS` is still considered off-target because the current datafiles live under `E:\SOFTWARES\ORADATA\ORCL`

## Rollback Position

- `rollback_plan.sql` reverses only the application objects covered by the move script.
- Restore-from-backup fallback is the combination of:
  - Data Pump dump files from `expdp_used_objects.par`
  - DDL extract from `ddl_extract_all_objects.sql`
  - Optional RMAN backup under `E:\DB_BACKUP_SAFETY\RMAN`