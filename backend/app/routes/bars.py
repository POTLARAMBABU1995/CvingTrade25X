from fastapi import APIRouter, HTTPException, Query, Request

from ..config import get_settings
from ..models import BarsResponse
from ..services.bars_service import fetch_bars
from ..utils.time import normalize_tf, resolve_history_window

router = APIRouter()
settings = get_settings()


@router.get('/bars', response_model=BarsResponse)
async def get_bars(
    request: Request,
    symbol: str = Query(...),
    tf: str = Query('1D'),
    from_: str = Query(None, alias='from'),
    to: str = Query(None),
    range_: str = Query(None, alias='range'),
    limit: int = Query(None),
    cursor: str = Query(None),
):
    if not symbol:
        raise HTTPException(status_code=400, detail='symbol is required')
    tf_norm = normalize_tf(tf)
    resolved_from, resolved_to = resolve_history_window(from_, to, range_)
    effective_limit = limit or settings.default_limit
    bars, next_cursor = fetch_bars(symbol, tf_norm, resolved_from, resolved_to, effective_limit, cursor)
    return BarsResponse(symbol=symbol, tf=tf_norm, nextCursor=next_cursor, bars=bars)
