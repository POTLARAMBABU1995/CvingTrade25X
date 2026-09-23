from __future__ import annotations

import asyncio
import logging
import os
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api_marketdata import router as marketdata_router
from .config import settings
from .oracle_pool import oracle_pool
from .services.levels_service import load_levels_payload
from .services.sr_async_service import sr_levels_service

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title='CvingTrade25X API', version='1.0.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in os.getenv('CORS_ALLOW_ORIGINS', 'http://localhost,http://127.0.0.1').split(',') if item.strip()],
    allow_credentials=False,
    allow_methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allow_headers=['Authorization', 'Content-Type', 'X-Requested-With', 'X-Request-ID'],
)

app.include_router(marketdata_router)


async def ensure_pool():
    await oracle_pool.init()


@app.on_event('startup')
async def startup_event():
    await ensure_pool()
    logger.info('Startup complete')


@app.on_event('shutdown')
async def shutdown_event():
    await oracle_pool.close()


@app.get('/health')
async def health():
    return {
        'status': 'ok',
        'pool': oracle_pool.stats(),
    }


@app.get('/api/sr-levels')
async def api_sr_levels(
    timeframe: Annotated[str, Query(description='daily/weekly/monthly/yearly')] = 'daily',
    tolerance: Annotated[float, Query(ge=0.005, le=0.25)] = 0.05,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=settings.max_page_size)] = settings.default_page_size,
    search: str | None = Query(default=None, min_length=1),
    refresh: bool = Query(default=False, description='Bypass cache and fetch latest data'),
):
    timeframe = timeframe.lower()
    if timeframe not in {'daily', 'weekly', 'monthly', 'yearly'}:
        raise HTTPException(status_code=400, detail='Invalid timeframe')

    try:
        payload = await sr_levels_service.fetch_page(
            timeframe=timeframe,
            tolerance=tolerance,
            page=page,
            page_size=page_size,
            search=search,
            force_refresh=refresh,
        )
        return JSONResponse(payload)
    except Exception as exc:
        logger.exception('Failed to serve sr-levels request')
        raise HTTPException(status_code=500, detail='Internal server error.') from exc


@app.get('/api/highs-lows')
async def api_highs_lows():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    try:
        if loop and loop.is_running():
            payload = await loop.run_in_executor(None, load_levels_payload)
        else:
            payload = load_levels_payload()
        return JSONResponse(payload)
    except Exception as exc:
        logger.exception('Failed to compute highs-lows payload')
        raise HTTPException(status_code=500, detail='Internal server error.') from exc



