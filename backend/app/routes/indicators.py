from fastapi import APIRouter, HTTPException, Query

from ..models import IndicatorsResponse
from ..services.indicator_service import fetch_indicators
from ..utils.time import normalize_tf, resolve_history_window

router = APIRouter()


@router.get('/indicators', response_model=IndicatorsResponse)
async def get_indicators(
    symbol: str = Query(...),
    tf: str = Query('1D'),
    names: str = Query(None),
    from_: str = Query(None, alias='from'),
    to: str = Query(None),
    range_: str = Query(None, alias='range'),
):
    if not symbol:
        raise HTTPException(status_code=400, detail='symbol is required')
    name_list = [n for n in (names or '').split(',') if n.strip()]
    tf_norm = normalize_tf(tf)
    resolved_from, resolved_to = resolve_history_window(from_, to, range_)
    series = fetch_indicators(symbol, tf_norm, name_list, resolved_from, resolved_to)
    return IndicatorsResponse(symbol=symbol, tf=tf_norm, series=series)
