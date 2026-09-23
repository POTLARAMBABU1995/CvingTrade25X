from fastapi import APIRouter, HTTPException, Query

from ..models import OverlaysResponse
from ..services.overlay_service import fetch_pivots, fetch_sr_levels
from ..services.pattern_service import fetch_patterns
from ..services.zone_service import fetch_zones
from ..utils.time import normalize_tf, resolve_history_window

router = APIRouter()


@router.get('/overlays', response_model=OverlaysResponse)
async def get_overlays(
    symbol: str = Query(...),
    tf: str = Query('1D'),
    from_: str = Query(None, alias='from'),
    to: str = Query(None),
    range_: str = Query(None, alias='range'),
):
    if not symbol:
        raise HTTPException(status_code=400, detail='symbol is required')
    tf_norm = normalize_tf(tf)
    resolved_from, resolved_to = resolve_history_window(from_, to, range_)
    annotations = []
    annotations.extend(fetch_sr_levels(symbol, tf_norm, resolved_from, resolved_to))
    annotations.extend(fetch_pivots(symbol, tf_norm, resolved_from, resolved_to))
    annotations.extend(fetch_patterns(symbol, tf_norm, resolved_from, resolved_to))
    annotations.extend(fetch_zones(symbol, tf_norm, resolved_from, resolved_to))
    return OverlaysResponse(symbol=symbol, tf=tf_norm, annotations=annotations)
