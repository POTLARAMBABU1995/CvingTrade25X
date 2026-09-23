# FastAPI SR Levels Service

## Prerequisites
- Oracle database with `sr_levels_mv` materialized view
- Python 3.11+
- Redis (optional) for distributed caching

## Environment
```
ORACLE_USER=...
ORACLE_PASSWORD=...
ORACLE_DSN=127.0.0.1:1521/cvingpdb.local
ORACLE_MIN_POOL=2
ORACLE_MAX_POOL=10
ORACLE_POOL_INCREMENT=1
ORACLE_STMT_CACHE=40
REDIS_URL=redis://localhost:6379/0  # optional
CACHE_TTL_SECONDS=30
SR_DEFAULT_PAGE_SIZE=25
SR_MAX_PAGE_SIZE=200
```

## Install
```
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

## Run
```
uvicorn backend.api:app --host 0.0.0.0 --port 5055 --reload
```

## API
`GET /api/sr-levels`
- `timeframe`: daily | weekly | monthly | yearly
- `tolerance`: 0.05 (5%) etc
- `page` & `page_size`
- `search`: prefix filter

Response sample:
```
{
  "rows": [...],
  "meta": {
    "page": 1,
    "page_size": 25,
    "total_rows": 2000,
    "total_pages": 80,
    "timeframe": "daily",
    "tolerance": 0.05
  }
}
```
