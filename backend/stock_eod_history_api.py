# backend/api.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import oracledb

from backend.db_pool import pool
from backend.api_marketdata import router as marketdata_router

app = FastAPI(title="CvingTrade25X Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost,http://127.0.0.1").split(",") if item.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Request-ID"],
)

@app.post("/api/merge-latest")
def merge_latest():
    try:
        with pool.acquire() as con:
            with con.cursor() as cur:
                o_dev = cur.var(oracledb.NUMBER)
                o_orc = cur.var(oracledb.NUMBER)
                # Uses your incremental proc with watermark
                cur.callproc("merge_from_history_to_raw_inc", [None, None, o_dev, o_orc])
                con.commit()
                return {
                    "status": "ok",
                    "inserted_dev": int(o_dev.getvalue() or 0),
                    "inserted_oracle": int(o_orc.getvalue() or 0),
                }
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error.")

# Mount market-data endpoints under /api/marketdata/*
app.include_router(marketdata_router)
