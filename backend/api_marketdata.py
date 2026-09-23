# backend/api_marketdata.py
from fastapi import APIRouter, Body, HTTPException, Query
from typing import Optional, Literal

from backend.services import marketdata_service as svc
from backend.services.marketdata_service import SymbolNotFoundError

router = APIRouter(prefix="/api/marketdata", tags=["marketdata"])

@router.get("/symbols")
def list_symbols(q: Optional[str] = Query(None, description="search prefix"),
                 limit: int = Query(200, ge=1, le=5000),
                 source: Optional[str] = Query(None, description="Optional source selector")):
    return svc.list_symbols(q, limit, source=source)

@router.get("/stock/summary")
def stock_summary(symbol: str, source: Optional[str] = Query(None, description="Optional source selector")):
    try:
        return svc.stock_summary(symbol, source=source)
    except SymbolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.get("/summary/table")
def summary_table(
    timeframe: Literal["daily","weekly","monthly","yearly"],
    symbol: Optional[str] = Query(None, description="Optional stock filter"),
    source: Optional[str] = Query(None, description="Optional source selector"),
):
    try:
        return svc.summary_table(timeframe, symbol, source=source)
    except SymbolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/stats")
def market_stats(source: Optional[str] = Query(None, description="Optional source selector")):
    return svc.market_stats(source=source)


@router.get("/stock/ohlcv")
def stock_ohlcv(symbol: str,
                granularity: Literal["daily","weekly","monthly","yearly"] = "daily",
                date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
                date_to:   Optional[str] = Query(None, description="YYYY-MM-DD")):
    return svc.stock_ohlcv(symbol, granularity, date_from, date_to)


@router.post("/merge-latest")
def merge_latest():
    try:
        return svc.merge_latest()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/stock-eod/clear")
@router.post("/stock-eod/clear/")
def clear_stock_eod_rows(payload: dict = Body(default_factory=dict)):
    try:
        return svc.clear_stock_eod_history(payload.get("confirm_text"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
