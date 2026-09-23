from fastapi import Depends, FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from uuid import uuid4
import logging
import time

from .config import get_settings
from .db import close_pool, init_pool
from .routes import annotations, bars, indicators, overlays, symbols
from .security import verify_api_key
from .utils.logging import configure_logging
from backend.automation.nse_market_data_scheduler import start_nse_marketdata_auto_scheduler

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get('X-Request-Id') or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers['X-Request-Id'] = request_id
        return response


app = FastAPI(
    title=settings.app_name,
    version='1.0.0',
    default_response_class=ORJSONResponse,
    dependencies=[Depends(verify_api_key)],
)

if settings.enable_gzip:
    app.add_middleware(GZipMiddleware, minimum_size=settings.gzip_min_size)
app.add_middleware(RequestIdMiddleware)


@app.middleware('http')
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    logger.info(
        'request.completed',
        extra={
            'method': request.method,
            'path': request.url.path,
            'status_code': response.status_code,
            'duration_ms': duration_ms,
            'request_id': getattr(request.state, 'request_id', None),
        },
    )
    return response


@app.on_event('startup')
async def startup_event():
    init_pool()
    start_nse_marketdata_auto_scheduler(initial_delay_seconds=10)


@app.on_event('shutdown')
async def shutdown_event():
    close_pool()


@app.get('/health')
async def health():
    return {'status': 'ok'}


app.include_router(symbols.router, prefix='/api')
app.include_router(bars.router, prefix='/api')
app.include_router(indicators.router, prefix='/api')
app.include_router(overlays.router, prefix='/api')
app.include_router(annotations.router, prefix='/api')
