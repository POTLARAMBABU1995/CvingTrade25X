# Manual Price Action SR Levels Loader

This loader inserts manually curated support/resistance points into the `PRICE_ACTION_SR_LEVELS_MANUALLY` Oracle table as one numeric `SR_LEVEL` value per row. It does not touch the dynamic `SR_LEVELS.html` technical page or its `SR_LEVELS` table flow.

## File format
Use a JSON file shaped like:

```json
{
  "records": [
    {
      "symbol": "ADANIPOWER",
      "tf": "1D",
      "as_of_date": "2026-03-13",
      "source": "manual_image",
      "level_type": "MANUAL",
      "sr_levels": [180.01, 150.67, 137.18, 124.05, 113.34]
    }
  ]
}
```

## Run
PowerShell:

```powershell
$env:DB_USER = 'your_user'
$env:DB_PASSWORD = 'your_password'
$env:DB_DSN = '127.0.0.1:1521/cvingpdb.local'
python -m batch.jobs.load_manual_sr_levels --file batch\config\manual_sr_levels_adanipower_2026-03-13.json
```

Check DB presence without inserting:

```powershell
python -m batch.jobs.load_manual_sr_levels --file batch\config\manual_sr_levels_adanipower_2026-03-13.json --check-only
```

Insert only rows that are currently missing in Oracle:

```powershell
python -m batch.jobs.load_manual_sr_levels --dir batch\manual_sr_image_queue\04_payloads --only-missing
```

The loader is idempotent. It uses a stable hash per symbol, timeframe, level type, and numeric level, then `MERGE`s into `PRICE_ACTION_SR_LEVELS_MANUALLY`.

## Query for automation
```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD-MON-RR HH.MI.SS AM';

SELECT LEVEL_ID,
       SYMBOL,
       TF,
       LEVEL_TYPE,
       SR_LEVEL,
       CREATED_AT,
       UPDATED_AT
FROM PRICE_ACTION_SR_LEVELS_MANUALLY
WHERE SYMBOL = 'ADANIPOWER'
ORDER BY SR_LEVEL DESC;
```

## Date display in Oracle tools
The `CREATED_AT` and `UPDATED_AT` columns should be plain Oracle `DATE` values. To display them as `13-MAR-26 10.02.04 PM`, use:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD-MON-RR HH.MI.SS AM';
```

