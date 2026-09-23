import logging
import json
import os
import uuid
import re
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, g, make_response
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from cache import TTLCache
from register_service import (
  init_registration_db,
  register_user,
  authenticate_user,
  record_login_activity,
  reset_credentials,
  validate_session,
  logout_session,
)
from db import _acquire_connection, build_dsn
from routes.trend import bp as trend_bp
from routes.momentum import bp as momentum_bp
from routes.sr import bp as sr_bp
from routes.rsi50 import bp as rsi50_bp
from routes.volume import bp as volume_bp
from routes.delivery import bp as delivery_bp
from routes.adx import bp as adx_bp
from routes.atr14 import bp as atr14_bp
from routes.dashboard import bp as dashboard_bp
from routes.levels import bp as levels_bp
from routes.price_action import bp as price_action_bp
from routes.trendline import bp as trendline_bp
from routes.breakout import bp as breakout_bp
from routes.chart_patterns import bp as chart_patterns_bp
from routes.chart import bp as chart_bp
from routes.chart_compat import bp as chart_compat_bp
from routes.strong_technicals import bp as strong_technicals_bp
from routes.strong_uptrend_reversal import bp as strong_uptrend_reversal_bp
from routes.marketdata import bp as marketdata_bp, start_marketdata_auto_merge, _status_payload_snapshot as marketdata_merge_status_snapshot
from routes.fyers_holdings_debug import bp as fyers_holdings_debug_bp
from routes.historical_data import bp as historical_data_bp
from routes.ema import bp as ema_bp
from routes.asura import bp as asura_bp, start_asura_auto_insert
from routes.asura_v3 import bp as asura_v3_bp
from routes.bhramhaputra import bp as bhramhaputra_bp, start_bhramhaputra_auto_insert
from routes.bhramhastra import bp as bhramhastra_bp, start_bhramhastra_auto_insert
from routes.yamuna import bp as yamuna_bp, start_yamuna_auto_ingest
from routes.prudvi_strategy import bp as prudvi_strategy_bp
from routes.strategy_sync import bp as strategy_sync_bp
from routes.strategy_agent import bp as strategy_agent_bp
from routes.server_control import bp as server_control_bp
from routes.automation_status import bp as automation_status_bp
from routes.sector_rotation import bp as sector_rotation_bp, warm_sector_rotation_cache
from routes.sector_hierarchy import bp as sector_hierarchy_bp
from routes.corporate_actions import bp as corporate_actions_bp
from routes.database import bp as database_bp
from routes.react_spa import register_frontend_routes, serve_frontend_root
from services.strategy_agent_runtime_service import start_strategy_agent_scheduler
from services.marketdata_service import start_fyers_data_cleanup_scheduler
try:
  from automation.nse_market_data_scheduler import start_nse_marketdata_auto_scheduler
except Exception:  # pragma: no cover
  from backend.automation.nse_market_data_scheduler import start_nse_marketdata_auto_scheduler  # type: ignore
try:
  from automation.manual_sr_image_auto_ingest import start_manual_sr_image_auto_ingest_scheduler
except Exception:  # pragma: no cover
  from backend.automation.manual_sr_image_auto_ingest import start_manual_sr_image_auto_ingest_scheduler  # type: ignore
from warmup import warm_in_background
from error_log_service import capture_api_error
try:
  from services import nse_mcap_service as nse_mcap_svc
  from services import nse_ffmc_service as nse_ffmc_svc
  from services import nse_delivery_service as nse_delivery_svc
  from services import nse_existing_csv_symbol_service as nse_existing_csv_symbol_svc
except Exception:  # pragma: no cover
  from backend.services import nse_mcap_service as nse_mcap_svc  # type: ignore
  from backend.services import nse_ffmc_service as nse_ffmc_svc  # type: ignore
  from backend.services import nse_delivery_service as nse_delivery_svc  # type: ignore
  from backend.services import nse_existing_csv_symbol_service as nse_existing_csv_symbol_svc  # type: ignore

try:  # pragma: no cover
  import oracledb
except Exception:  # pragma: no cover
  oracledb = None


logger = logging.getLogger(__name__)


def _generate_request_id() -> str:
  return f"CVT25X-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


def _env_flag(name: str, default: bool = False) -> bool:
  raw = os.getenv(name)
  if raw is None:
    return bool(default)
  return str(raw).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _parse_allowed_origins() -> set[str]:
  raw = str(os.getenv('CORS_ALLOW_ORIGINS', 'http://localhost,http://127.0.0.1,null')).strip()
  origins = {item.strip() for item in raw.split(',') if item.strip()}
  return origins or {'http://localhost', 'http://127.0.0.1', 'null'}


def _origin_allowed(origin: str | None, allowed_origins: set[str]) -> bool:
  token = str(origin or '').strip()
  if not token:
    return False
  if token in allowed_origins:
    return True
  if token == 'null':
    return True
  if re.match(r'^https?://192\.168\.\d{1,3}\.\d{1,3}(:\d+)?$', token):
    return True
  if re.match(r'^https?://10\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?$', token):
    return True
  if re.match(r'^https?://172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}(:\d+)?$', token):
    return True
  if re.match(r'^https?://\[::1\](:\d+)?$', token):
    return True
  if re.match(r'^https?://0\.0\.0\.0(:\d+)?$', token):
    return True
  return token.startswith('http://localhost:') or token.startswith('http://127.0.0.1:')


_DEFAULT_ALLOWED_SYMBOL_DIRS = (
  Path(__file__).resolve().parents[1] / 'batch',
  Path(__file__).resolve().parents[1] / 'data',
)


def _resolve_symbol_file_path_safe(raw_path: str | None) -> str | None:
  text = str(raw_path or '').strip()
  if not text:
    return None
  candidate = Path(text).expanduser()
  try:
    resolved = candidate.resolve(strict=False)
  except Exception:
    return None
  if resolved.suffix.lower() != '.csv':
    return None
  configured = str(os.getenv('ALLOWED_SYMBOL_FILE_DIRS', '')).strip()
  allowed_roots: list[Path] = []
  if configured:
    for item in configured.split(','):
      token = item.strip()
      if not token:
        continue
      allowed_roots.append(Path(token).expanduser().resolve(strict=False))
  else:
    for root in _DEFAULT_ALLOWED_SYMBOL_DIRS:
      allowed_roots.append(root.resolve(strict=False))
  for root in allowed_roots:
    try:
      resolved.relative_to(root)
      return str(resolved)
    except Exception:
      continue
  return None


def _run_startup_step(app: Flask, step_name: str, action) -> None:
  try:
    action()
  except Exception as exc:  # pragma: no cover
    warnings = app.config.setdefault('STARTUP_WARNINGS', [])
    warnings.append({
      'step': step_name,
      'error': str(exc),
    })
    logger.exception('Startup step failed: %s', step_name)


def _json_api_error(message: str, status: int = 400):
  safe_message = 'Internal server error.' if int(status) >= 500 else str(message or 'Invalid request parameter')
  payload = {
    'status': 'error',
    'message': safe_message,
    'request_id': getattr(g, 'request_id', ''),
  }
  return jsonify(payload), int(status)


_verification_cache = TTLCache(ttl_seconds=30, max_items=128)


def create_app(
  *,
  enable_background_jobs: bool = True,
  enable_warmup: bool = True,
  enable_nse_marketdata_automation: bool | None = None,
  enable_manual_sr_image_auto_ingest: bool | None = None,
  enable_marketdata_auto_merge: bool = True,
):
  app = Flask(__name__)
  app.config['STARTUP_WARNINGS'] = []
  start_nse_marketdata_automation = (
    bool(enable_background_jobs)
    if enable_nse_marketdata_automation is None
    else bool(enable_nse_marketdata_automation)
  )
  start_manual_sr_image_auto_ingest = (
    bool(enable_background_jobs)
    if enable_manual_sr_image_auto_ingest is None
    else bool(enable_manual_sr_image_auto_ingest)
  )
  # Broad, API-scoped CORS with explicit allowlist.
  allowed_origins = _parse_allowed_origins()
  CORS(
    app,
    resources={r"/api/*": {"origins": [r"^https?://localhost(:\d+)?$", r"^https?://127\.0\.0\.1(:\d+)?$", *list(allowed_origins)]}},
    supports_credentials=True,
    send_wildcard=False,
  )

  _run_startup_step(app, 'registration-db-init', init_registration_db)

  app.register_blueprint(trend_bp)
  app.register_blueprint(momentum_bp)
  app.register_blueprint(sr_bp)
  app.register_blueprint(dashboard_bp)
  app.register_blueprint(volume_bp)
  app.register_blueprint(delivery_bp)
  app.register_blueprint(adx_bp)
  app.register_blueprint(atr14_bp)
  app.register_blueprint(rsi50_bp)
  app.register_blueprint(levels_bp)
  app.register_blueprint(price_action_bp)
  app.register_blueprint(trendline_bp)
  app.register_blueprint(breakout_bp)
  app.register_blueprint(chart_patterns_bp)
  app.register_blueprint(chart_bp)
  app.register_blueprint(chart_compat_bp)
  app.register_blueprint(strong_technicals_bp)
  app.register_blueprint(strong_uptrend_reversal_bp)
  app.register_blueprint(marketdata_bp)
  app.register_blueprint(fyers_holdings_debug_bp)
  app.register_blueprint(historical_data_bp)
  app.register_blueprint(ema_bp)
  app.register_blueprint(asura_bp)
  app.register_blueprint(asura_v3_bp)
  app.register_blueprint(bhramhaputra_bp)
  app.register_blueprint(bhramhastra_bp)
  app.register_blueprint(yamuna_bp)
  app.register_blueprint(prudvi_strategy_bp)

  if enable_marketdata_auto_merge:
    _run_startup_step(app, 'marketdata-auto-merge', start_marketdata_auto_merge)
  if enable_background_jobs:
    _run_startup_step(app, 'asura-auto-insert', start_asura_auto_insert)
    _run_startup_step(app, 'bhramhaputra-auto-insert', start_bhramhaputra_auto_insert)
    _run_startup_step(app, 'bhramhastra-auto-insert', start_bhramhastra_auto_insert)
    _run_startup_step(app, 'yamuna-auto-ingest', start_yamuna_auto_ingest)
    _run_startup_step(app, 'strategy-agent-scheduler', start_strategy_agent_scheduler)
    _run_startup_step(app, 'fyers-data-cleanup-scheduler', start_fyers_data_cleanup_scheduler)
  if start_manual_sr_image_auto_ingest:
    _run_startup_step(app, 'manual-sr-image-auto-ingest', start_manual_sr_image_auto_ingest_scheduler)
  if start_nse_marketdata_automation:
    _run_startup_step(app, 'nse-marketdata-automation', start_nse_marketdata_auto_scheduler)
  app.register_blueprint(strategy_sync_bp)
  app.register_blueprint(strategy_agent_bp)
  app.register_blueprint(server_control_bp)
  app.register_blueprint(automation_status_bp)
  app.register_blueprint(sector_rotation_bp)
  app.register_blueprint(sector_hierarchy_bp)
  app.register_blueprint(corporate_actions_bp)
  app.register_blueprint(database_bp)
  if enable_background_jobs:
    _run_startup_step(app, 'sector-rotation-cache-warm', warm_sector_rotation_cache)

  api_catalog = [
    "/api/health",
    "/api/config",
    "/api/trend",
    "/api/trend/latestDate",
    "/api/trend/ping",
    "/api/trend/metrics",
    "/api/momentum/macd",
    "/api/rsi50",
    "/api/volume",
    "/api/technicals/delivery",
    "/api/adx",
    "/api/atr14",
    "/api/sr-levels",
    "/api/price-action-sr-levels-manually",
    "/api/technicals/price-action",
    "/api/technicals/trendline",
    "/api/technicals/breakout",
    "/api/technicals/chart-patterns",
    "/api/chart/ohlcv",
    "/api/strategy/strong-uptrend-reversal",
    "/api/strategy/prudvi",
    "/api/chart/watchlist",
    "/api/symbols",
    "/api/bars",
    "/api/indicators",
    "/api/overlays",
    "/api/user-annotations",
    "/api/technicals/strong",
    "/api/asura",
    "/api/strategy/asura-v3/dashboard-summary",
    "/api/strategy/asura-v3/latest-signals",
    "/api/strategy/asura-v3/yearly-summary",
    "/api/strategy/asura-v3/cost-summary",
    "/api/strategy/asura-v3/risk-summary",
    "/api/strategy/asura-v3/symbol-ratings",
    "/api/strategy/asura-v3/health",
    "/api/yamuna/last-ltc-date",
    "/api/yamuna/ingest",
    "/api/bhramhaputra",
    "/api/bhramhaputra/last-ltc-date",
    "/api/bhramhaputra/insert",
    "/api/bhramhastra",
    "/api/bhramhastra/last-ltc-date",
    "/api/bhramhastra/insert",
    "/api/strategy/sync",
    "/api/strategy-agent/status",
    "/api/strategy-agent/backtests",
    "/api/strategy-agent/run",
    "/api/strategy-agent/cancel",
    "/api/server-control/status",
    "/api/server-control/notifications",
    "/api/automation/nse-marketdata/status",
    "/api/automation/nse-marketdata/latest-result",
    "/api/server-control/start",
    "/api/server-control/stop",
    "/api/server-control/restart",
    "/api/highs-lows",
    "/api/ema",
    "/api/marketdata/fyers/nifty500-sync",
    "/api/marketdata/fyers/nifty500-sync/compare",
    "/api/marketdata/fyers/nifty500-sync/merge",
    "/api/marketdata/fyers/nifty500-sync/rows",
    "/api/marketdata/fyers/authorize",
    "/api/marketdata/fyers/auth-status",
    "/api/marketdata/fyers/single",
    "/api/marketdata/fyers/single/start",
    "/api/marketdata/fyers/batch",
    "/api/marketdata/fyers/batch/start",
    "/api/marketdata/fyers/jobs/{jobId}",
    "/api/marketdata/fyers/holdings",
    "/api/fyers/holdings/reconcile",
    "/api/marketdata/fyers/holdings/reconcile",
    "/api/corporate-actions/split-bonus-candidates",
    "/api/corporate-actions/split-bonus-candidates/delete-symbols",
    "/api/marketdata/fyers/holdings/import",
    "/api/marketdata/fyers/holdings/summary",
    "/api/marketdata/fyers/holdings/imports",
    "/api/marketdata/fyers/holdings/{holdingId}",
    "/api/marketdata/stock-eod/clear",
    "/api/marketdata/merge/status/latest",
    "/api/merge/status/latest",
    "/api/marketdata/nse-mcap/process-existing-csv-symbols",
    "/api/marketdata/nse-ffmc/process-existing-csv-symbols",
    "/api/marketdata/nse-delivery/process-existing-csv-symbols",
    "/api/market-calendar/trading-day-verification",
    "/api/nse-symbols",
    "/api/nse-ffmc/process-existing-csv-symbols",
    "/api/nse-delivery/process-existing-csv-symbols",
    "/api/nse-market-cap/process-existing-csv-symbols",
    "/api/nse-marketcap-index/latest",
    "/api/historical-data/tables",
    "/api/historical-data/summary",
    "/api/historical-data/symbol/{symbol}",
    "/api/historical-data/delete-symbols",
    "/api/historical-data/delete-rows",
    "/api/dashboard/movers",
    "/api/sectors",
    "/api/sectors/breadth",
    "/api/sector-rotation/sectors",
    "/api/sector-rotation/stocks",
    "/api/sectors/{sectorCode}/stocks",
    "/api/sector/{sectorName}/stocks",
    "/api/sector/{sectorName}/stocks/sector-wise",
    "/api/sector-hierarchy/parents",
    "/api/sector-hierarchy/industries",
    "/api/sector-hierarchy/sub-sectors",
    "/api/sector-hierarchy/stocks",
    "/api/sector-hierarchy/summary",
    "/api/sector-hierarchy/tree",
    "/api/sectors/refresh",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/session",
    "/api/auth/logout",
    "/api/auth/activity",
    "/api/auth/reset",
  ]

  auth_exempt = {
    '/api',
    '/api/health',
    '/api/server-control/notifications',
    '/api/merge/status/latest',
    '/api/marketdata/merge/status/latest',
    '/api/automation/nse-marketdata/status',
    '/api/auth/login',
    '/api/auth/register',
    '/api/auth/reset',
    '/api/nse-marketcap-index/latest',
    '/api/marketdata/nse-mcap-index/latest',
    '/api/dashboard/movers',
    '/api/volume',
    '/api/symbols',
    '/api/bars',
    '/api/indicators',
    '/api/overlays',
    '/api/user-annotations',
    '/api/corporate-actions/split-bonus-candidates',
    '/api/corporate-actions/split-bonus-candidates/delete-symbols',
    '/api/market-calendar/trading-day-verification',
    '/api/marketdata/nse-mcap/init',
    '/api/marketdata/nse-mcap/summary',
    '/api/marketdata/nse-mcap/download',
    '/api/marketdata/nse-mcap/validate',
    '/api/marketdata/nse-mcap/process',
    '/api/marketdata/nse-mcap/process-existing-csv-symbols',
    '/api/marketdata/nse-mcap/pipeline/start',
    '/api/marketdata/nse-mcap/jobs/latest',
    '/api/marketdata/nse-ffmc/init',
    '/api/marketdata/nse-ffmc/summary',
    '/api/marketdata/nse-ffmc/download',
    '/api/marketdata/nse-ffmc/validate',
    '/api/marketdata/nse-ffmc/process',
    '/api/marketdata/nse-ffmc/process-existing-csv-symbols',
    '/api/marketdata/nse-ffmc/pipeline/start',
    '/api/marketdata/nse-ffmc/jobs/latest',
    '/api/marketdata/nse-delivery/init',
    '/api/marketdata/nse-delivery/summary',
    '/api/marketdata/nse-delivery/download',
    '/api/marketdata/nse-delivery/validate',
    '/api/marketdata/nse-delivery/process',
    '/api/marketdata/nse-delivery/process-existing-csv-symbols',
    '/api/marketdata/nse-delivery/pipeline/start',
    '/api/marketdata/nse-delivery/jobs/latest',
  }
  nse_database_public_prefixes = (
    '/api/marketdata/nse-mcap/jobs/',
    '/api/marketdata/nse-ffmc/jobs/',
    '/api/marketdata/nse-delivery/jobs/',
  )
  sector_api_public_exempt = str(os.getenv('SECTOR_API_PUBLIC_EXEMPT', '1')).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
  server_control_local_exempt = {
    '/api/server-control/status',
    '/api/server-control/start',
    '/api/server-control/stop',
    '/api/server-control/restart',
  }
  auth_cache_ttl_raw = str(os.getenv('AUTH_SESSION_CACHE_TTL_SECONDS', '15')).strip()
  try:
    auth_cache_ttl = max(1, int(auth_cache_ttl_raw))
  except Exception:
    auth_cache_ttl = 15
  auth_session_cache = TTLCache(ttl_seconds=auth_cache_ttl, max_items=8192)

  def _auth_cache_key(token: str) -> str:
    return f"session:{token}"

  def _extract_session_token():
    auth = request.headers.get('Authorization', '')
    if auth.lower().startswith('bearer '):
      return auth.split(' ', 1)[1].strip()
    token = request.headers.get('X-Session-Token', '')
    if token:
      return token.strip()
    cookie_token = request.cookies.get('ct_refresh') or request.cookies.get('ct_session') or ''
    return cookie_token.strip() if cookie_token else ''

  def _is_loopback_request() -> bool:
    remote_ip = (request.remote_addr or '').strip()
    if remote_ip in {'127.0.0.1', '::1'}:
      return True
    forwarded_for = (request.headers.get('X-Forwarded-For') or '').split(',', 1)[0].strip()
    return forwarded_for in {'127.0.0.1', '::1'}

  @app.before_request
  def bind_request_context():
    incoming_request_id = (
      request.headers.get('X-Request-ID')
      or request.headers.get('X-Request-Id')
      or ''
    ).strip()
    g.request_id = incoming_request_id or _generate_request_id()
    g.request_started_at = time.perf_counter()
    g.request_client_page = str(request.headers.get('X-Client-Page', '')).strip()[:256]
    g.request_client_action = str(request.headers.get('X-Client-Action', '')).strip()[:128]
    g.request_client_component = str(request.headers.get('X-Client-Component', '')).strip()[:128]
    try:
      request.request_id = g.request_id
    except Exception:
      pass
    return None

  @app.before_request
  def enforce_auth():
    if request.method == 'OPTIONS':
      return None
    path = request.path or ''
    if not path.startswith('/api'):
      return None
    if path in auth_exempt:
      return None
    if any(path.startswith(prefix) for prefix in nse_database_public_prefixes):
      return None
    if path in server_control_local_exempt and _is_loopback_request():
      return None
    if sector_api_public_exempt and (
      path.startswith('/api/sectors')
      or path.startswith('/api/sector/')
      or path.startswith('/api/sector-rotation/')
      or path.startswith('/api/sector-hierarchy/')
    ):
      return None
    token = _extract_session_token()
    if not token:
      return jsonify({'status': 'error', 'message': 'Unauthorized', 'request_id': getattr(g, 'request_id', '')}), 401
    cache_key = _auth_cache_key(token)
    cached_session = auth_session_cache.get(cache_key)
    if cached_session:
      g.auth_session = cached_session
      return None
    meta = {
      'source_ip': request.headers.get('X-Forwarded-For', request.remote_addr),
      'user_agent': request.headers.get('User-Agent'),
      'referrer': request.headers.get('Referer'),
    }
    session = validate_session(token, meta)
    if not session:
      auth_session_cache.delete(cache_key)
      return jsonify({'status': 'error', 'message': 'Session expired. Please login again.', 'request_id': getattr(g, 'request_id', '')}), 401
    auth_session_cache.set(cache_key, session)
    g.auth_session = session
    return None

  @app.after_request
  def add_cors_headers(resp):
    # Reflect only allow-listed origins.
    origin = request.headers.get('Origin')
    if origin in (None, ''):
      resp.headers['Access-Control-Allow-Origin'] = 'null'
      resp.headers['Access-Control-Allow-Credentials'] = 'false'
    else:
      is_allowed_origin = _origin_allowed(origin, allowed_origins)
      resp.headers['Access-Control-Allow-Origin'] = origin if is_allowed_origin else 'null'
      resp.headers['Access-Control-Allow-Credentials'] = 'true' if is_allowed_origin else 'false'

    # Ensure caches vary by Origin when reflecting.
    resp.headers['Vary'] = 'Origin'

    # Explicitly advertise allowed methods and headers. Echo requested headers
    # to satisfy strict browsers and extensions.
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    requested_headers = request.headers.get('Access-Control-Request-Headers')
    resp.headers['Access-Control-Allow-Headers'] = requested_headers or (
      'Content-Type, Authorization, X-Requested-With, X-Request-ID, X-Session-Token, '
      'X-Client-Page, X-Client-Action, X-Client-Component'
    )
    resp.headers['Access-Control-Expose-Headers'] = 'X-Request-ID'

    # Private Network Access (Chrome): honor preflight header when present.
    # See https://developer.chrome.com/blog/private-network-access-update
    if request.method == 'OPTIONS' and request.headers.get('Access-Control-Request-Private-Network') == 'true':
      resp.headers['Access-Control-Allow-Private-Network'] = 'true'

    # Cache preflight for a day to reduce OPTIONS noise.
    if request.method == 'OPTIONS':
      resp.headers['Access-Control-Max-Age'] = '86400'
    resp.headers['X-Request-ID'] = getattr(g, 'request_id', '') or _generate_request_id()
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    resp.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    resp.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    resp.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    if request.is_secure:
      resp.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    if request.method != 'OPTIONS' and resp.status_code >= 400 and resp.is_json:
      payload = resp.get_json(silent=True)
      if isinstance(payload, dict) and not payload.get('errorId'):
        message = payload.get('message') or 'Request failed.'
        payload.update(capture_api_error(
          request=request,
          status=resp.status_code,
          message=str(message),
          extra={
            'client_action': getattr(g, 'request_client_action', ''),
            'client_component': getattr(g, 'request_client_component', ''),
            'client_page': getattr(g, 'request_client_page', ''),
            'handler': 'after_request',
            'request_id': getattr(g, 'request_id', ''),
          },
        ))
        payload['status'] = payload.get('status') or 'error'
        payload['message'] = str(message)
        payload['request_id'] = getattr(g, 'request_id', '')
        payload.pop('detail', None)
        resp.set_data(json.dumps(payload, ensure_ascii=True))
        resp.headers['Content-Type'] = 'application/json'
        resp.headers['Content-Length'] = str(len(resp.get_data()))

    if request.method != 'OPTIONS' and (request.path or '').startswith('/api'):
      started = getattr(g, 'request_started_at', None)
      duration_ms = int((time.perf_counter() - started) * 1000) if isinstance(started, (int, float)) else -1
      logger.info(
        'api_request method=%s path=%s status=%s duration_ms=%s request_id=%s client_page=%s client_action=%s client_component=%s',
        request.method,
        request.path,
        resp.status_code,
        duration_ms,
        getattr(g, 'request_id', ''),
        getattr(g, 'request_client_page', '') or '-',
        getattr(g, 'request_client_action', '') or '-',
        getattr(g, 'request_client_component', '') or '-',
      )

    return resp

  @app.errorhandler(Exception)
  def handle_unexpected_error(exc):
    if isinstance(exc, HTTPException):
      status = int(exc.code or 500)
      message = str(exc.description or exc) or 'Request failed.'
    else:
      status = 500
      message = 'Internal server error.'
      logger.exception(
        'Unhandled exception request_id=%s method=%s path=%s',
        getattr(g, 'request_id', ''),
        request.method,
        request.path,
      )
    payload = {'status': 'error', 'message': message, 'request_id': getattr(g, 'request_id', '')}
    payload.update(capture_api_error(
      request=request,
      status=status,
      message=message,
      extra={
        'client_action': getattr(g, 'request_client_action', ''),
        'client_component': getattr(g, 'request_client_component', ''),
        'client_page': getattr(g, 'request_client_page', ''),
        'handler': 'errorhandler',
        'request_id': getattr(g, 'request_id', ''),
      },
      exc=None if isinstance(exc, HTTPException) else exc,
    ))
    return jsonify(payload), status

  @app.route('/api/<path:_any>', methods=['OPTIONS'])
  def api_options(_any):
    return ('', 204)

  def _register_user_handler():
    payload = request.get_json(silent=True) or {}
    meta = {
      'source_ip': request.headers.get('X-Forwarded-For', request.remote_addr),
      'user_agent': request.headers.get('User-Agent'),
      'referrer': request.headers.get('Referer'),
    }
    body, status = register_user(payload, meta)
    return jsonify(body), status

  @app.post('/api/auth/register')
  def api_auth_register():
    return _register_user_handler()

  @app.post('/auth/register')
  def legacy_auth_register():
    return _register_user_handler()

  @app.post('/api/auth/login')
  def api_auth_login():
    payload = request.get_json(silent=True) or {}
    meta = {
      'source_ip': request.headers.get('X-Forwarded-For', request.remote_addr),
      'user_agent': request.headers.get('User-Agent'),
      'referrer': request.headers.get('Referer'),
    }
    body, status = authenticate_user(payload, meta)
    resp = make_response(jsonify(body), status)
    if status == 200:
      token = body.get('session_token') or (body.get('session') or {}).get('token')
      if token:
        try:
          ttl_minutes = int(str(os.getenv('SESSION_TTL_MINUTES', '1440')).strip())
        except Exception:
          ttl_minutes = 1440
        cookie_secure = request.is_secure or str(os.getenv('COOKIE_SECURE', '')).lower() in ('1', 'true', 'yes')
        cookie_samesite = os.getenv('COOKIE_SAMESITE', 'Lax')
        resp.set_cookie(
          'ct_refresh',
          token,
          httponly=True,
          secure=cookie_secure,
          samesite=cookie_samesite,
          max_age=max(1, ttl_minutes) * 60,
          path='/'
        )
    return resp

  @app.get('/api/auth/session')
  def api_auth_session():
    session = getattr(g, 'auth_session', None)
    if not session:
      return jsonify({'status': 'error', 'message': 'Unauthorized', 'request_id': getattr(g, 'request_id', '')}), 401
    return jsonify({'ok': True, 'session': session})

  @app.post('/api/auth/logout')
  def api_auth_logout():
    token = _extract_session_token()
    if not token:
      return jsonify({'status': 'error', 'message': 'Session token is required.', 'request_id': getattr(g, 'request_id', '')}), 400
    auth_session_cache.delete(_auth_cache_key(token))
    if not logout_session(token):
      return jsonify({'status': 'error', 'message': 'Session not found.', 'request_id': getattr(g, 'request_id', '')}), 404
    resp = make_response(jsonify({'ok': True}))
    resp.set_cookie('ct_refresh', '', httponly=True, max_age=0, path='/')
    return resp

  @app.post('/api/auth/activity')
  def api_auth_activity():
    payload = request.get_json(silent=True) or {}
    meta = {
      'source_ip': request.headers.get('X-Forwarded-For', request.remote_addr),
      'user_agent': request.headers.get('User-Agent'),
      'referrer': request.headers.get('Referer'),
    }
    body, status = record_login_activity(payload, meta)
    return jsonify(body), status

  @app.post('/api/auth/reset')
  def api_auth_reset():
    payload = request.get_json(silent=True) or {}
    meta = {
      'source_ip': request.headers.get('X-Forwarded-For', request.remote_addr),
      'user_agent': request.headers.get('User-Agent'),
      'referrer': request.headers.get('Referer'),
    }
    body, status = reset_credentials(payload, meta)
    return jsonify(body), status

  @app.get('/')
  def root():
    return serve_frontend_root(api_catalog)

  @app.get('/api')
  def api_index():
    return jsonify({'ok': True, 'endpoints': api_catalog})

  @app.get('/api/health')
  def health():
    db_ok = False
    err = None
    if oracledb is not None:
      try:
        with _acquire_connection() as conn:
          with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM DUAL')
            cur.fetchone()
            db_ok = True
      except Exception as exc:  # pragma: no cover
        err = 'Database connectivity check failed.'
        db_ok = False
    info = {
      'ok': True,
      'driver': ('python-oracledb' if oracledb is not None else 'unavailable'),
      'db': 'up' if db_ok else 'down',
      'error': err,
      'startupWarnings': list(app.config.get('STARTUP_WARNINGS', [])),
      'request_id': getattr(g, 'request_id', ''),
    }
    return jsonify(info)

  @app.get('/api/config')
  def api_config():
    expose_details = str(os.getenv('EXPOSE_RUNTIME_CONFIG', '0')).strip().lower() in {'1', 'true', 'yes', 'on'}
    if not expose_details:
      return jsonify({'ok': True, 'message': 'Runtime config exposure disabled.', 'request_id': getattr(g, 'request_id', '')})
    schema = os.getenv('ORACLE_SCHEMA', '')
    table = os.getenv('ORACLE_TABLE', 'NSE_NIFTY500_DAILY_RAW_DATA_DEV')
    qualified = f"{schema}.{table}" if schema else table
    return jsonify({
      'host': os.getenv('ORACLE_HOST', 'localhost'),
      'port': int(os.getenv('ORACLE_PORT', '1521')),
      'sid': os.getenv('ORACLE_SID'),
      'service_name': os.getenv('ORACLE_SERVICE_NAME'),
      'user_set': bool(os.getenv('ORACLE_USER')),
      'schema': schema,
      'table': table,
      'qualified_table': qualified,
      'request_id': getattr(g, 'request_id', ''),
    })

  def _nse_symbols_payload():
    payload = request.get_json(silent=True) if request.method == 'POST' else {}
    if not isinstance(payload, dict):
      payload = {}
    symbol_file_path = (
      request.args.get('symbolFilePath')
      or request.args.get('symbol_file_path')
      or payload.get('symbolFilePath')
      or payload.get('symbol_file_path')
    )
    safe_symbol_file_path = _resolve_symbol_file_path_safe(symbol_file_path)
    if symbol_file_path and not safe_symbol_file_path:
      return _json_api_error('Invalid symbol file path.', 400)
    try:
      symbols = sorted(nse_existing_csv_symbol_svc.load_valid_symbols(safe_symbol_file_path))
      resolved = nse_existing_csv_symbol_svc.resolve_symbol_file_path(safe_symbol_file_path)
      return jsonify({
        'ok': True,
        'status': 'success',
        'count': len(symbols),
        'symbols': symbols,
        'symbol_file_path': str(resolved),
        'request_id': getattr(g, 'request_id', ''),
      })
    except FileNotFoundError as exc:
      return _json_api_error(str(exc), 404)
    except Exception as exc:
      return _json_api_error(str(exc), 500)

  @app.get('/api/nse-symbols')
  def api_nse_symbols():
    return _nse_symbols_payload()

  @app.post('/api/nse-symbols')
  def api_nse_symbols_post():
    return _nse_symbols_payload()

  @app.post('/api/nse-delivery/process-existing-csv-symbols')
  def api_nse_delivery_process_existing_csv_symbols():
    payload = request.get_json(silent=True) or {}
    try:
      return jsonify(nse_delivery_svc.process_existing_csv_for_symbols_api(payload))
    except ValueError as exc:
      return _json_api_error(str(exc), 400)
    except Exception as exc:
      return _json_api_error(str(exc), 500)

  @app.post('/api/nse-ffmc/process-existing-csv-symbols')
  def api_nse_ffmc_process_existing_csv_symbols():
    payload = request.get_json(silent=True) or {}
    try:
      return jsonify(nse_ffmc_svc.process_existing_csv_for_symbols_api(payload))
    except ValueError as exc:
      return _json_api_error(str(exc), 400)
    except Exception as exc:
      return _json_api_error(str(exc), 500)

  @app.post('/api/nse-market-cap/process-existing-csv-symbols')
  def api_nse_market_cap_process_existing_csv_symbols():
    payload = request.get_json(silent=True) or {}
    try:
      return jsonify(nse_mcap_svc.process_existing_csv_for_symbols_api(payload))
    except ValueError as exc:
      return _json_api_error(str(exc), 400)
    except Exception as exc:
      return _json_api_error(str(exc), 500)
  @app.get('/api/market-calendar/trading-day-verification')
  def api_market_calendar_trading_day_verification():
    page = request.args.get('page', '', type=str)
    raw_year = request.args.get('year', '', type=str).strip()
    refresh = request.args.get('refresh', '0-0', type=str).strip()
    token = str(page or '').strip().upper().replace('-', '_').replace(' ', '_')
    
    cache_key = f"{token}:{raw_year}"
    use_cache = (refresh == '0-0')
    if use_cache:
      cached = _verification_cache.get(cache_key)
      if cached is not None:
        return jsonify(cached)

    try:
      year = int(raw_year) if raw_year else None
      if year is not None and (year < 1900 or year > 2100):
        raise ValueError('year must be between 1900 and 2100.')
      if token in {'FFMC', 'NSE_FFMC'}:
        res = nse_ffmc_svc.get_trading_day_verification(year=year)
      elif token in {'DELIVERY', 'NSE_DELIVERY', 'NSE_DELIVERY_DATA', 'DELIVERY_DATA'}:
        res = nse_delivery_svc.get_trading_day_verification(year=year)
      elif token in {'MARKET_CAP', 'MARKETCAP', 'MCAP', 'NSE_MCAP', 'NSE_MARKET_CAP'}:
        res = nse_mcap_svc.get_trading_day_verification(year=year)
      else:
        raise ValueError('page must be one of FFMC, DELIVERY, or MARKET_CAP.')
      
      _verification_cache.set(cache_key, res)
      return jsonify(res)
    except ValueError as exc:
      return _json_api_error(str(exc), 400)
    except Exception as exc:
      return _json_api_error(str(exc), 500)

  @app.get('/api/nse-marketcap-index/latest')
  def api_nse_marketcap_index_latest():
    try:
      return jsonify(nse_mcap_svc.get_marketcap_index_latest())
    except ValueError as exc:
      return _json_api_error(str(exc), 400)
    except Exception as exc:
      return _json_api_error(str(exc), 500)

  @app.get('/api/merge/status/latest')
  def api_marketdata_merge_status_latest():
    return jsonify(marketdata_merge_status_snapshot())

  if enable_warmup:
    try:
      warm_in_background()
    except Exception:  # pragma: no cover
      pass

  register_frontend_routes(app, api_catalog)
  return app


if __name__ == '__main__':
  debug_mode = str(os.getenv('FLASK_DEBUG', '0')).strip().lower() in {'1', 'true', 'yes', 'on'}
  port = int(os.getenv('PORT', '5055'))
  run_background_jobs = _env_flag('CVING_ENABLE_BACKGROUND_JOBS', True)
  run_marketdata_auto_merge = _env_flag('CVING_ENABLE_MARKETDATA_AUTO_MERGE', True)
  run_warmup = _env_flag('CVING_ENABLE_WARMUP', run_background_jobs)
  run_nse_marketdata_automation = _env_flag('CVING_ENABLE_NSE_MARKETDATA_AUTOMATION', run_background_jobs)
  run_manual_sr_image_auto_ingest = _env_flag(
    'CVING_ENABLE_MANUAL_SR_IMAGE_AUTO_INGEST',
    _env_flag('MANUAL_SR_IMAGE_AUTO_INGEST_ENABLED', True),
  )
  if debug_mode:
    # Flask's debug reloader starts a parent watchdog and a serving child process.
    # Only the child should launch background schedulers and cache warmers.
    reloader_child = os.getenv('WERKZEUG_RUN_MAIN') == 'true'
    run_background_jobs = run_background_jobs and reloader_child
    run_marketdata_auto_merge = run_marketdata_auto_merge and reloader_child
    run_warmup = run_warmup and reloader_child
    run_nse_marketdata_automation = run_nse_marketdata_automation and reloader_child
    run_manual_sr_image_auto_ingest = run_manual_sr_image_auto_ingest and reloader_child
  app = create_app(
    enable_background_jobs=run_background_jobs,
    enable_warmup=run_warmup,
    enable_nse_marketdata_automation=run_nse_marketdata_automation,
    enable_manual_sr_image_auto_ingest=run_manual_sr_image_auto_ingest,
    enable_marketdata_auto_merge=run_marketdata_auto_merge,
  )
  app.run(host='0.0.0.0', port=port, debug=debug_mode, use_reloader=debug_mode, threaded=True)






















