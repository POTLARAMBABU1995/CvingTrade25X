# Database Change Standard

Oracle 19c is the database source of truth for this application. Every database change must be explicit, reversible, and validated.

Required for every Oracle DB change:

- Forward migration under `database/migrations`.
- Rollback script under `database/rollback`.
- Validation script under `database/validation`.
- Table or object purpose.
- Key columns and constraints.
- Index assumptions and performance impact note.
- Data impact note.
- Backward compatibility note.

Rules:

- No destructive DDL without explicit approval.
- No `DROP`, `TRUNCATE`, broad `DELETE`, destructive `ALTER`, or production table rename without explicit approval.
- No change to `STOCK_EOD_HISTORY` -> `NSE_NIFTY500_DAILY_RAW_DATA_DEV` flow without explicit approval.
- Use bind variables in application SQL.
- Prefer set-based SQL and `MERGE` for approved upserts.
