# Corporate Actions - Split / Bonus Detector

## Overview
- Feature page: `/app/database/corporate-actions`
- Purpose: detect probable split/bonus candidates from historical price corrections
- Source of truth: `NSE_NIFTY500_DAILY_RAW_DATA_DEV` (read-only)
- Derived view: `V_CORP_ACTION_CANDIDATES`

## Detection Logic
- `prev_price = LAG(price) OVER (PARTITION BY symbol ORDER BY trading_date)`
- `actual_factor = price / prev_price`
- `drop_pct = ((prev_price - price) / prev_price) * 100`
- Expected factors are matched with tolerance `ABS(actual_factor - expected_factor) <= 0.05`
- UI default filter is `drop_pct >= 50`
- Results are probabilistic (`possible_actions`), not official confirmation

## Price Column Auto-Detection
View creation script auto-detects close-price source with priority:
1. `PREVIOUS_CLOSE`
2. `CLOSE_PRICE`
3. `CLOSE`
4. `LTP`
5. `PRICE`
6. `LAST_PRICE`
7. `ADJ_CLOSE`
8. `CLOSING_PRICE`

If none exists, script fails fast with a clear Oracle error.

## Files Added
- `backend/routes/corporate_actions.py`
- `frontend/src/pages/ops/CorporateActionsPage.tsx`
- `frontend/src/services/api/databaseApi.ts`
- `sql/001_create_v_corp_action_candidates.sql`
- `sql/002_validate_corp_action_candidates.sql`
- `docs/CORPORATE_ACTIONS_README.md`

## Files Updated
- `backend/app.py` (blueprint registration + API catalog entry)
- `frontend/src/App.tsx` (React route registration)
- `frontend/src/data/databaseNav.ts` (Database menu item)

## API
`GET /api/corporate-actions/split-bonus-candidates`

### Query Params
- `q` (optional symbol search)
- `min_drop_pct` (default `50`)
- `from_date` (optional `YYYY-MM-DD`)
- `to_date` (optional `YYYY-MM-DD`)
- `limit` (default `500`, max `5000`)

### Response Shape
```json
{
  "success": true,
  "count": 10,
  "data": [],
  "filters": {
    "q": "",
    "min_drop_pct": 50,
    "from_date": "",
    "to_date": "",
    "limit": 500
  }
}
```

## Runbook (PowerShell)
```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X

# In Oracle client:
# @sql/001_create_v_corp_action_candidates.sql
# @sql/002_validate_corp_action_candidates.sql

python -m compileall backend\routes\corporate_actions.py
python backend\app.py

Invoke-RestMethod "http://127.0.0.1:5055/api/corporate-actions/split-bonus-candidates?min_drop_pct=50&limit=20"
```

## Rollback
1. Remove corporate-actions blueprint import/registration from `backend/app.py`
2. Remove the React route/menu entry from `frontend/src/App.tsx` and `frontend/src/data/databaseNav.ts`
3. Delete added files listed above
4. Optional DB rollback:
```sql
DROP VIEW V_CORP_ACTION_CANDIDATES;
```
