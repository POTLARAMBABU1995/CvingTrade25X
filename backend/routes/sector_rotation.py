from __future__ import annotations



import json

import logging

import math

import os

import re

import time

from functools import cmp_to_key

from datetime import date, datetime, timedelta

import threading

from decimal import Decimal

from pathlib import Path

from typing import Any, Mapping



from flask import Blueprint, jsonify, request



from cache import TTLCache

from db import get_oracle_connection

from services.ath_service import get_all_time_high_for_symbols, log_stale_snapshot_warning

from services.sector_cache_service import sector_cache_service

from services.sector_stock_cache_service import sector_stock_cache_service
from services.nse_symbol_normalization import (
    NSE_CASH_SERIES,
    NSE_SYMBOL_SERIES,
    canonical_nse_symbol,
    canonical_nse_symbol_key,
)

from services.sector_rotation_service import ensure_sector_reference_data_synced, fetch_sector_rotation_rows
from utils.sector_hierarchy import canonical_sector_code, hierarchy_fields, normalize_sector_alias
from services.sector_snapshot_service import (
    get_latest_ltc_date_fast,
    read_sector_rotation_snapshot,
    write_sector_rotation_snapshot,
    read_sector_wise_snapshot,
    write_sector_wise_snapshot
)

try:

    from services.technical_score_engine import enrich_row_with_master_score_fields

except Exception:  # pragma: no cover

    enrich_row_with_master_score_fields = None  # type: ignore

try:

    from routes.sr import _compute_base_payload as _sr_compute_base_payload  # type: ignore

    from routes.sr import _get_cached_trading_window as _sr_get_cached_trading_window  # type: ignore

    from routes.sr import normalize_symbol as _sr_normalize_symbol  # type: ignore

except Exception:  # pragma: no cover

    _sr_compute_base_payload = None  # type: ignore

    _sr_get_cached_trading_window = None  # type: ignore

    _sr_normalize_symbol = None  # type: ignore





bp = Blueprint('sector_rotation', __name__)

logger = logging.getLogger(__name__)



_CACHE_TTL = int(os.getenv('SECTOR_ROTATION_CACHE_TTL', '45'))

_POPUP_CACHE_TTL = int(os.getenv('SECTOR_POPUP_CACHE_TTL', '60'))

_SECTOR_WISE_TREND_CACHE_TTL = int(os.getenv('SECTOR_WISE_TREND_CACHE_TTL', '900'))

_SECTOR_STOCK_CACHE_TTL_SECONDS = max(60, int(os.getenv('SECTOR_STOCK_CACHE_TTL_SECONDS', '900')))

_SECTOR_TABLES_SNAPSHOT_PATH = Path('runtime/snapshots/sector_rotation_tables.json')
_SECTOR_OVERVIEW_SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / 'runtime' / 'snapshots' / 'sector_overview_latest.json'
_SECTOR_V3_STOCK_SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / 'runtime' / 'snapshots' / 'sector_rotation_v3_stocks_latest.json'

_SECTOR_WISE_USE_AUTHORITATIVE_ATH = str(os.getenv('SECTOR_WISE_USE_AUTHORITATIVE_ATH', '')).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

_SECTOR_WISE_FAST_FIRST_RESPONSE_ENABLED = str(os.getenv('SECTOR_WISE_FAST_FIRST_RESPONSE_ENABLED', '0')).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

_SECTOR_WISE_BACKGROUND_ENRICH_ENABLED = str(os.getenv('SECTOR_WISE_BACKGROUND_ENRICH_ENABLED', '0')).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

_SECTOR_STALE_SNAPSHOT_CACHE_TTL_SECONDS = max(30, int(os.getenv('SECTOR_STALE_SNAPSHOT_CACHE_TTL_SECONDS', '300')))

_SECTOR_CACHE_VERSION = str(os.getenv('SECTOR_CACHE_VERSION', 'v7')).strip() or 'v7'

_SECTOR_STOCK_CACHE_VERSION = str(os.getenv('SECTOR_STOCK_CACHE_VERSION', 'v7')).strip() or 'v7'

_SECTOR_ROTATION_CANONICAL_GROUPING_VERSION = 'v7'



_cache = TTLCache(ttl_seconds=_CACHE_TTL, max_items=128)

_popup_cache = TTLCache(ttl_seconds=_POPUP_CACHE_TTL, max_items=512)

_sector_wise_trend_cache = TTLCache(ttl_seconds=_SECTOR_WISE_TREND_CACHE_TTL, max_items=8)

_SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / 'cache' / 'sector_rotation_latest.json'

_SECTOR_FAST_ENRICH_LOCK = threading.Lock()

_SECTOR_FAST_ENRICH_INFLIGHT: set[str] = set()

_SECTOR_ORACLE_SNAPSHOT_LOCK = threading.Lock()

_SECTOR_ORACLE_SNAPSHOT_INFLIGHT: set[str] = set()





def _apply_latest_raw_trade_date(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:

    raw_latest_date = _latest_raw_trading_date()

    if raw_latest_date is None:

        return rows

    for row in rows:

        if not isinstance(row, dict):

            continue

        current_as_of = _coerce_date(row.get('asOfDate'))

        if current_as_of is None or raw_latest_date > current_as_of:

            row['asOfDate'] = raw_latest_date.isoformat()

    return rows





def _apply_sector_master_score(row: dict[str, Any], sr_context: dict[str, Any] | None = None) -> dict[str, Any]:

    if not SECTOR_WISE_MASTER_SCORE_ENABLED or enrich_row_with_master_score_fields is None:

        return row

    try:

        return enrich_row_with_master_score_fields(

            row,

            sr_context=sr_context,

            replace_existing=True,

        )

    except Exception:

        logger.exception('sector_master_score_enrich_failed symbol=%s', row.get('stock') or row.get('symbol'))

        return row





def _load_breadth_snapshot() -> list[dict[str, Any]] | None:

    try:

        if not _SNAPSHOT_PATH.exists():

            return None

        payload = json.loads(_SNAPSHOT_PATH.read_text(encoding='utf-8'))

        if isinstance(payload, list):

            return _apply_latest_raw_trade_date(payload)

    except Exception:

        logger.exception('Failed to load sector rotation snapshot cache')

    return None





def _save_breadth_snapshot(rows: list[dict[str, Any]]) -> None:

    try:

        _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)

        _SNAPSHOT_PATH.write_text(json.dumps(rows, ensure_ascii=True), encoding='utf-8')

    except Exception:

        logger.exception('Failed to save sector rotation snapshot cache')





def _apply_breadth_engine_version(rows: list[dict[str, Any]], engine_version: str) -> list[dict[str, Any]]:

    rows = _apply_sector_hierarchy(rows)

    if engine_version == 'v3':

        from services.sector_rotation_v3_service import enrich_sector_rotation_v3_rows

        return enrich_sector_rotation_v3_rows(rows, engine_version='v3')

    if engine_version != 'v2':

        return rows

    from services.sector_rotation_v2_service import enrich_breadth_with_v2_signals

    return [enrich_breadth_with_v2_signals(row) for row in rows]


_V3_STAGING_OVERRIDE_FIELDS = {
    'availableSymbols',
    'breadthComposite',
    'confirmedStocks',
    'countBreadth',
    'rsi50Pct',
    'rsi55Pct',
    'screenedStocks',
    'sma100Pct',
    'sma20Pct',
    'sma50Pct',
    'stockConfirmationLabel',
    'stockConfirmationScoreAvg',
    'stockConfirmationScreening',
    'tableName',
    'totalStocks',
    'totalSymbols',
}


def _prepare_breadth_engine_rows(
    rows: list[dict[str, Any]],
    engine_version: str,
) -> list[dict[str, Any]]:
    """Prepare one response version without changing the V1/V2 execution path."""

    if engine_version != 'v3':
        return _apply_breadth_engine_version(
            _supplement_breadth_rows_with_sector_tables(rows),
            engine_version,
        )

    source_rows = [dict(row) for row in rows if isinstance(row, dict)]
    supplemented_rows = _supplement_breadth_rows_with_sector_tables(source_rows)
    source_by_code = {
        str(row.get('sectorCode') or '').strip().upper(): row
        for row in source_rows
        if str(row.get('sectorCode') or '').strip()
    }
    merged_rows: list[dict[str, Any]] = []
    for supplemented in supplemented_rows:
        code = str(supplemented.get('sectorCode') or '').strip().upper()
        source = source_by_code.get(code)
        if source is None:
            merged_rows.append(dict(supplemented))
            continue
        merged = dict(source)
        for field in _V3_STAGING_OVERRIDE_FIELDS:
            if field in supplemented:
                merged[field] = supplemented[field]
        merged['totalStocks'] = max(
            _coerce_int(source.get('totalStocks') or source.get('totalSymbols'), default=0),
            _coerce_int(supplemented.get('totalStocks') or supplemented.get('totalSymbols'), default=0),
        )
        merged['totalSymbols'] = max(
            _coerce_int(source.get('totalSymbols') or source.get('totalStocks'), default=0),
            _coerce_int(supplemented.get('totalSymbols') or supplemented.get('totalStocks'), default=0),
        )
        merged_rows.append(merged)

    return _apply_breadth_engine_version(merged_rows, engine_version)


def _supplement_v3_breadth_membership_counts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep V3's visible universe aligned with the persisted staging discovery."""
    snapshot = _read_snapshot_from_disk()
    entries = _collapse_sector_entries_for_unique_ui(
        _normalize_sector_table_entries((snapshot or {}).get('tables'))
    )
    staging_counts = {
        str(entry.get('sectorCode') or '').strip().upper(): _coerce_int(entry.get('stockCount'), default=0)
        for entry in entries
        if str(entry.get('sectorCode') or '').strip()
    }
    if not staging_counts:
        return [dict(row) for row in rows if isinstance(row, dict)]

    supplemented: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        code = _canonical_unique_sector_selector_code(row.get('sectorCode')) or str(row.get('sectorCode') or '').strip().upper()
        staging_count = _coerce_int(staging_counts.get(code), default=0)
        if staging_count > _coerce_int(row.get('totalStocks') or row.get('totalSymbols'), default=0):
            row['totalStocks'] = staging_count
            row['totalSymbols'] = max(_coerce_int(row.get('totalSymbols'), default=0), staging_count)
        supplemented.append(row)
    return supplemented


def _breadth_response(
    rows: list[dict[str, Any]],
    *,
    engine_version: str,
    cache_status: str,
    source: str,
    started_at: float,
    as_of_date: date,
    is_stale: bool = False,
    cache_key: str | None = None,
    prebuilt_payload: Mapping[str, Any] | None = None,
):
    duration_ms = max((time.perf_counter() - started_at) * 1000, 0.0)
    payload: Any = rows
    if engine_version == 'v3':
        if prebuilt_payload is not None:
            payload = dict(prebuilt_payload)
            payload['rows'] = [dict(row) for row in rows if isinstance(row, dict)]
            payload['cacheStatus'] = cache_status
            payload['isStale'] = bool(payload.get('isStale')) or is_stale
        else:
            from services.sector_rotation_v3_service import build_sector_rotation_v3_envelope

            payload = build_sector_rotation_v3_envelope(
                rows,
                engine_version='v3',
                as_of_date=as_of_date,
                cache_status=cache_status,
                is_stale=is_stale,
                calculation_duration_ms=duration_ms,
            )
        if cache_key:
            _cache.set(cache_key, payload)
    response = jsonify(payload)
    response.headers['X-Cache-Status'] = cache_status
    response.headers['X-Source'] = source
    response.headers['X-Response-Time-Ms'] = str(int(duration_ms))
    if engine_version == 'v3':
        response.headers['X-Sector-Rotation-Version'] = engine_version
    return response


def _warm_sector_breadth_cache_once() -> None:

    cache_key = f'breadth:{_SECTOR_ROTATION_CANONICAL_GROUPING_VERSION}:latest:history:0'

    if _cache.get(cache_key) is not None:

        return

    try:

        ensure_sector_reference_data_synced()

        rows = fetch_sector_rotation_rows(None, include_history=False)

        rows = _apply_latest_raw_trade_date(rows)

        rows = _supplement_breadth_rows_with_sector_tables(rows)

        _cache.set(cache_key, rows)

        _save_breadth_snapshot(rows)

    except Exception:

        logger.exception('Failed warm sector breadth cache')





def _warm_sector_wise_trend_cache_once() -> None:

    try:

        _load_sector_wise_trend_map(force_refresh=False)

    except Exception:

        logger.exception('Failed warm sector-wise trend cache')





def warm_sector_rotation_cache() -> None:

    threading.Thread(

        target=_warm_sector_breadth_cache_once,

        daemon=True,

        name='warm:sector-rotation',

    ).start()

    threading.Thread(

        target=_warm_sector_wise_trend_cache_once,

        daemon=True,

        name='warm:sector-wise-trend',

    ).start()



_MAP_SECTOR_CACHE_KEY = 'map-sector-codes'

_CAP_VIEW_EXISTS_CACHE_KEY = 'has-vw-symbol-cap-bucket'

_MCAP_INDEX_VIEW_EXISTS_CACHE_KEY = 'has-v-nse-market-cap-index'

_SNAPSHOT_COLUMNS_CACHE_KEY = 'snapshot-ui-cols'

_BREADTH_VIEW_EXISTS_CACHE_KEY = 'has-vw-sector-breadth'

_RAW_SMA_SOURCE_CACHE_KEY = 'raw-sma-source'

_RAW_EXTREMA_SOURCE_CACHE_KEY = 'raw-extrema-source'

_RAW_LATEST_DATE_CACHE_KEY = 'raw-latest-trading-date'

_SNAPSHOT_MAX_DATE_CACHE_KEY = 'snapshot-ui-max-ltc-date'

_SR_LEVELS_VIEW_EXISTS_CACHE_KEY = 'has-sr-levels-mv'

_SECTOR_WISE_TREND_CACHE_KEY = 'sector-wise-trend-map'

_SECTOR_STOCK_CACHE_PREFIX = 'sector_stocks::'

_SECTOR_TABLES_CACHE_KEY = 'sector-rotation:db-sector-tables'

_SECTOR_TABLE_COLUMNS_CACHE_PREFIX = 'sector-rotation:table-cols:'

_ATH_SOURCE_TABLE = 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'

_NSE_MCAP_HIST_TABLE = (os.getenv('NSE_MCAP_TABLE') or 'CVING_NSE_MARKET_CAP_HIST').strip().upper()

_NSE_MCAP_INDEX_VIEW = (os.getenv('NSE_MCAP_INDEX_VIEW') or 'V_NSE_MARKET_CAP_INDEX').strip().upper()





def _env_float(name: str, default: float) -> float:

    try:

        return float(str(os.getenv(name, str(default))).strip())

    except Exception:

        return default





SECTOR_TREND_NEAR_HIGH_PERCENT = max(0.1, _env_float('SECTOR_TREND_NEAR_HIGH_PERCENT', 5.0))

SECTOR_TREND_NEAR_LOW_PERCENT = max(0.1, _env_float('SECTOR_TREND_NEAR_LOW_PERCENT', 5.0))

SECTOR_TREND_FAR_BELOW_HIGH_PERCENT = max(0.1, _env_float('SECTOR_TREND_FAR_BELOW_HIGH_PERCENT', 18.0))

SECTOR_TREND_NEAR_LEVEL_PERCENT = max(0.1, _env_float('SECTOR_TREND_NEAR_LEVEL_PERCENT', 2.0))

SECTOR_TREND_BREAKOUT_BUFFER_PERCENT = max(0.0, _env_float('SECTOR_TREND_BREAKOUT_BUFFER_PERCENT', 0.0))

SECTOR_TREND_BREAKDOWN_BUFFER_PERCENT = max(0.0, _env_float('SECTOR_TREND_BREAKDOWN_BUFFER_PERCENT', 0.0))

SECTOR_TREND_EMA_BULLISH_THRESHOLD = max(1, int(_env_float('SECTOR_TREND_EMA_BULLISH_THRESHOLD', 3)))

SECTOR_TREND_EMA_BEARISH_THRESHOLD = max(1, int(_env_float('SECTOR_TREND_EMA_BEARISH_THRESHOLD', 3)))

SECTOR_WISE_TREND_DEBUG = str(os.getenv('SECTOR_WISE_TREND_DEBUG', '')).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

SECTOR_WISE_TREND_SR_PAYLOAD_ENABLED = str(

    os.getenv('SECTOR_WISE_TREND_SR_PAYLOAD_ENABLED', '')

).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

SECTOR_WISE_MASTER_SCORE_ENABLED = str(

    os.getenv('SECTOR_WISE_MASTER_SCORE_ENABLED', '1')

).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}



_ALLOWED_PAGE_SIZES = {15, 25, 50, 100, 200}

_DEFAULT_PAGE_SIZE = 15

_MAX_LEGACY_PAGE_SIZE = 5000



SECTOR_CODE_ALIASES: dict[str, list[str]] = {

    'AGRICULTURE': ['AGRICULTURE'],
    'FERTILIZERS_AGROCHEMICALS': ['FERTILIZERS_AGROCHEMICALS'],
    'PESTICIDES_AGROCHEMICALS': ['PESTICIDES_AGROCHEMICALS'],

    'AUTO': ['AUTO'],
    'AUTO_COMPONENTS_EQUIPMENTS': ['AUTO_COMPONENTS_EQUIPMENTS', 'AUTO_COMP_EQUIP'],

    'CAPITAL_GOODS': ['CAPITAL_GOODS'],

    'CHEMICALS': ['CHEMICALS', 'CHEM'],
    'SPECIALTY_CHEMICALS': ['SPECIALTY_CHEMICALS'],
    'PETROCHEMICALS': ['PETROCHEMICALS'],
    'PAINTS': ['PAINTS'],
    'PLASTIC_PRODUCTS': ['PLASTIC_PRODUCTS'],
    'EXPLOSIVES': ['EXPLOSIVES'],
    'ABRASIVES': ['ABRASIVES'],
    'ELECTRODES_REFRACTORIES': ['ELECTRODES_REFRACTORIES'],

    'CONSTRUCTION': ['CONSTRUCTION'],

    'CONSUMER_DURABLES': ['CONSUMER_DURABLES', 'CONS_DUR'],
    'CONS_DUR': ['CONSUMER_DURABLES', 'CONS_DUR'],

    'FIN_SERV': ['FIN_SERV'],

    'FINANCIAL_SERVICES': ['FIN_SERV'],

    'FMCG': ['FMCG'],
    'HOUSEHOLD_PERSONAL_PRODUCTS': ['HOUSEHOLD_PERSONAL_PRODUCTS'],

    'ELEC_SERVICES_CONS_DURABLES': ['ELEC_SERVICES_CONS_DURABLES', 'ELECTRONICS_SERVICES_CONSUMER_DURABLES'],
    'CONSUMER_ELECTRONICS': ['CONSUMER_ELECTRONICS'],
    'CONSUMER_SERVICES': ['CONSUMER_SERVICES'],

    'HEALTHCARE': ['HEALTHCARE', 'HEALTH'],
    'BIOTECHNOLOGY': ['BIOTECHNOLOGY'],
    'MEDICAL_EQUIPMENT_SUPPLIES': ['MEDICAL_EQUIPMENT_SUPPLIES'],

    'HEALTHCARE_INDEX': ['HEALTHCARE_INDEX', 'HEALTHCARE'],

    'NIFTY500_HEALTHCARE': ['NIFTY500_HEALTHCARE', 'HEALTHCARE'],

    'MIDSMALL_HEALTHCARE': ['MIDSMALL_HEALTHCARE'],

    'MIDSMALL_IT_TELECOM': ['MIDSMALL_IT_TELECOM'],

    'IT': ['IT'],
    'IT_ENABLED_SERVICES': ['IT_ENABLED_SERVICES'],
    'SOFTWARE_PRODUCTS_SERVICES': ['SOFTWARE_PRODUCTS_SERVICES'],

    'MEDIA': ['MEDIA'],
    'MEDIA_ENTERTAINMENT': ['MEDIA_ENTERTAINMENT'],
    'PRINT_MEDIA_PUBLISHING': ['PRINT_MEDIA_PUBLISHING'],

    'METAL': ['METAL'],
    'METALS_MINING': ['METALS_MINING'],
    'IRON_STEEL': ['IRON_STEEL'],
    'MINING': ['MINING'],
    'NON_FERROUS_METALS': ['NON_FERROUS_METALS'],

    'PHARMA': ['PHARMA'],

    'PRIVATE_BANK': ['PRIVATE_BANK', 'PVT_BANK'],

    'PVT_BANK': ['PRIVATE_BANK', 'PVT_BANK'],

    'POWER': ['POWER'],

    'PSU_BANK': ['PSU_BANK'],

    'OIL_GAS': ['OIL_GAS'],

    'OIL_AND_GAS': ['OIL_AND_GAS', 'OIL_GAS'],
    'LPG_CNG_PNG_LNG_SUPPLIER': ['LPG_CNG_PNG_LNG_SUPPLIER'],
    'LUBRICANTS': ['LUBRICANTS'],
    'OIL_EQUIPMENT_SERVICES': ['OIL_EQUIPMENT_SERVICES'],
    'PETROLEUM_PRODUCTS_REFINERIES': ['PETROLEUM_PRODUCTS_REFINERIES'],

    'REALTY_REAL_ESTATE': ['REALTY_REAL_ESTATE'],

    'RUBBER_PRODUCTS_TYRES': ['RUBBER_PRODUCTS_TYRES', 'RUBBER_TYRES'],

    'CEMENT_CEMENT_PRODUCTS': ['CEMENT_CEMENT_PRODUCTS', 'CEMENT'],
    'CONSTRUCTION_MATERIALS': ['CONSTRUCTION_MATERIALS'],
    'INFRASTRUCTURE': ['INFRASTRUCTURE'],

    'SERVICES': ['SERVICES'],

    'TELECOM': ['TELECOM'],

    'TELECOMMUNICATION': ['TELECOMMUNICATION', 'TELECOM'],

    'UTILITIES': ['UTILITIES'],

    'AVIATION_AIR_TRANSPORT': ['AVIATION_AIR_TRANSPORT'],
    'LOGISTICS_SHIPPING': ['LOGISTICS_SHIPPING'],
    'PORT_AND_PORT_SERVICES': ['PORT_AND_PORT_SERVICES'],
    'ROAD_RAIL_TRANSPORT': ['ROAD_RAIL_TRANSPORT'],
    'TRANSPORT_INFRASTRUCTURE': ['TRANSPORT_INFRASTRUCTURE'],

    'ENGINEERING': ['ENGINEERING'],
    'ELEC_HEAVY_EQUIPMENT': ['ELEC_HEAVY_EQUIPMENT'],
    'ELEC_HEAVY_EQUIP': ['ELEC_HEAVY_EQUIPMENT', 'ELEC_HEAVY_EQUIP', 'ELECTRICALS_HEAVY_ELECTRICAL_EQUIPMENT'],
    'ELECTRICALS_HEAVY_ELECTRICAL_EQUIPMENT': ['ELEC_HEAVY_EQUIPMENT', 'ELEC_HEAVY_EQUIP', 'ELECTRICALS_HEAVY_ELECTRICAL_EQUIPMENT'],
    'INDUSTRIAL_MANUFACTURING': ['INDUSTRIAL_MANUFACTURING'],
    'INDUSTRIAL_PRODUCTS': ['INDUSTRIAL_PRODUCTS'],
    'INDUSTRIAL_GASES_FUELS': ['INDUSTRIAL_GASES_FUELS'],
    'COMMODITIES_TRADING': ['COMMODITIES_TRADING'],
    'DEFENCE_AEROSPACE_DEFENSE': ['DEFENCE_AEROSPACE_DEFENSE'],
    'DIVERSIFIED': ['DIVERSIFIED'],
    'PAPER_PACKAGING': ['PAPER_PACKAGING'],
    'WASTE_WATER_MANAGEMENT': ['WASTE_WATER_MANAGEMENT'],

    'RETAILING_SPECIALITY_RETAIL': ['RETAILING_SPECIALITY_RETAIL'],
    'ECOMMERCE_ERETAI': ['ECOMMERCE_ERETAI'],
    'FOOTWEAR': ['FOOTWEAR'],
    'GEMS': ['GEMS'],
    'JEWELLERY_WATCHES': ['JEWELLERY_WATCHES'],
    'LEATHER_LEATHER_PRODUCTS': ['LEATHER_LEATHER_PRODUCTS'],
    'TEXTILES_APPARELS': ['TEXTILES_APPARELS'],

    'RESTAURANTS': ['RESTAURANTS'],
    'HOSPITALITY_HOTELS_RESORTS': ['HOSPITALITY_HOTELS_RESORTS'],
    'TOURISM_TRAVEL': ['TOURISM_TRAVEL'],
    'EDUCATION_E_LEARNING': ['EDUCATION_E_LEARNING'],

}



_STRICT_SECTOR_TABLE_MAP: dict[str, str] = {

    'DAIRY_MILK_PRODUCTS': 'NSE_NIFTY_DAIRY_MILK_PRODUCTS_STAGING',

    'NBFC': 'NSE_NIFTY_NBFC_STAGING',
    'INSURANCE': 'NSE_NIFTY_INSURANCE_STAGING',
    'CAPITAL_MARKETS': 'NSE_NIFTY_CAPITAL_MARKETS_STAGING',
    'ASSET_MANAGEMENT_COMPANY': 'NSE_NIFTY_ASSET_MANAGEMENT_COMPANY_STAGING',
    'FINTECH': 'NSE_NIFTY_FINTECH_STAGING',
    'HOUSING_FINANCE_COMPANY': 'NSE_NIFTY_HOUSING_FINANCE_COMPANY_STAGING',
    'STOCKBROKING_AND_ALLIED': 'NSE_NIFTY_STOCKBROKING_AND_ALLIED_STAGING',

    'ALCOHOL_BREWERIES': 'NSE_NIFTY_ALCOHOL_BREWERIES_STAGING',

    'AGRICULTURE': 'NSE_NIFTY_AGRICULTURE_STAGING',
    'FERTILIZERS_AGROCHEMICALS': 'NSE_NIFTY_FERTILIZERS_AGROCHEMICALS_STAGING',
    'PESTICIDES_AGROCHEMICALS': 'NSE_NIFTY_PESTICIDES_AGROCHEMICALS_STAGING',

    'AUTO': 'NSE_NIFTY_AUTO_STAGING',

    'AUTO_ANCILLARIES': 'NSE_NIFTY_AUTO_ANCILLARIES_STAGING',
    'AUTO_COMPONENTS_EQUIPMENTS': 'NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING',

    'CAPITAL_GOODS': 'NSE_NIFTY_CAPITAL_GOODS_STAGING',

    'CHEMICALS': 'NSE_NIFTY_CHEMICALS_STAGING',
    'SPECIALTY_CHEMICALS': 'NSE_NIFTY_SPECIALTY_CHEMICALS_STAGING',
    'PETROCHEMICALS': 'NSE_NIFTY_PETROCHEMICALS_STAGING',
    'PAINTS': 'NSE_NIFTY_PAINTS_STAGING',
    'PLASTIC_PRODUCTS': 'NSE_NIFTY_PLASTIC_PRODUCTS_STAGING',
    'EXPLOSIVES': 'NSE_NIFTY_EXPLOSIVES_STAGING',
    'ABRASIVES': 'NSE_NIFTY_ABRASIVES_STAGING',
    'ELECTRODES_REFRACTORIES': 'NSE_NIFTY_ELECTRODES_REFRACTORIES_STAGING',

    'CONSTRUCTION': 'NSE_NIFTY_CONSTRUCTION_STAGING',

    'CONSUMER_DURABLES': 'NSE_NIFTY_CONSUMER_DURABLES_STAGING',
    'CONS_DUR': 'NSE_NIFTY_CONSUMER_DURABLES_STAGING',

    'FIN_SERV': 'NSE_NIFTY_FINANCIAL_SERVICES_STAGING',

    'FINANCIAL_SERVICES': 'NSE_NIFTY_FINANCIAL_SERVICES_STAGING',

    'FMCG': 'NSE_NIFTY_FMCG_STAGING',
    'HOUSEHOLD_PERSONAL_PRODUCTS': 'NSE_NIFTY_HOUSEHOLD_PERSONAL_PRODUCTS_STAGING',

    'ELECTRONICS_SERVICES_CONSUMER_DURABLES': 'NSE_NIFTY_ELECTRONICS_SERVICES_CONSUMER_DURABLES_STAGING',
    'ELEC_SERVICES_CONS_DURABLES': 'NSE_NIFTY_ELECTRONICS_SERVICES_CONSUMER_DURABLES_STAGING',
    'CONSUMER_ELECTRONICS': 'NSE_NIFTY_CONSUMER_ELECTRONICS_STAGING',
    'CONSUMER_SERVICES': 'NSE_NIFTY_CONSUMER_SERVICES_STAGING',

    'HEALTHCARE': 'NSE_NIFTY_HEALTHCARE_INDEX_STAGING',
    'BIOTECHNOLOGY': 'NSE_NIFTY_BIOTECHNOLOGY_STAGING',
    'MEDICAL_EQUIPMENT_SUPPLIES': 'NSE_NIFTY_MEDICAL_EQUIPMENT_SUPPLIES_STAGING',

    'HEALTHCARE_INDEX': 'NSE_NIFTY_HEALTHCARE_INDEX_STAGING',

    'NIFTY500_HEALTHCARE': 'NSE_NIFTY500_HEALTHCARE_STAGING',

    'MIDSMALL_HEALTHCARE': 'NSE_NIFTY_MIDSMALL_HEALTHCARE_STAGING',

    'MIDSMALL_IT_TELECOM': 'NSE_NIFTY_MIDSMALL_IT_TELECOM_STAGING',

    'IT': 'NSE_NIFTY_IT_STAGING',
    'IT_ENABLED_SERVICES': 'NSE_NIFTY_IT_ENABLED_SERVICES_STAGING',
    'SOFTWARE_PRODUCTS_SERVICES': 'NSE_NIFTY_SOFTWARE_PRODUCTS_SERVICES_STAGING',

    'MEDIA': 'NSE_NIFTY_MEDIA_STAGING',
    'MEDIA_ENTERTAINMENT': 'NSE_NIFTY_MEDIA_ENTERTAINMENT_STAGING',
    'PRINT_MEDIA_PUBLISHING': 'NSE_NIFTY_PRINT_MEDIA_PUBLISHING_STAGING',

    'METAL': 'NSE_NIFTY_METAL_STAGING',
    'METALS_MINING': 'NSE_NIFTY_METALS_MINING_STAGING',
    'IRON_STEEL': 'NSE_NIFTY_IRON_STEEL_STAGING',
    'MINING': 'NSE_NIFTY_MINING_STAGING',
    'NON_FERROUS_METALS': 'NSE_NIFTY_NON_FERROUS_METALS_STAGING',

    'PHARMA': 'NSE_NIFTY_PHARMA_STAGING',

    'PRIVATE_BANK': 'NSE_NIFTY_PRIVATE_BANK_STAGING',

    'PVT_BANK': 'NSE_NIFTY_PRIVATE_BANK_STAGING',

    'POWER': 'NSE_NIFTY_POWER_STAGING',

    'PSU_BANK': 'NSE_NIFTY_PSU_BANK_STAGING',

    'REALTY_REAL_ESTATE': 'NSE_NIFTY_REALTY_REAL_ESTATE_STAGING',

    'RUBBER_PRODUCTS_TYRES': 'NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING',

    'CEMENT_CEMENT_PRODUCTS': 'NSE_NIFTY_CEMENT_CEMENT_PRODUCTS_STAGING',
    'CONSTRUCTION_MATERIALS': 'NSE_NIFTY_CONSTRUCTION_MATERIALS_STAGING',
    'INFRASTRUCTURE': 'NSE_NIFTY_INFRASTRUCTURE_STAGING',

    'OIL_GAS': 'NSE_NIFTY_OIL_AND_GAS_STAGING',

    'OIL_AND_GAS': 'NSE_NIFTY_OIL_AND_GAS_STAGING',
    'LPG_CNG_PNG_LNG_SUPPLIER': 'NSE_NIFTY_LPG_CNG_PNG_LNG_SUPPLIER_STAGING',
    'LUBRICANTS': 'NSE_NIFTY_LUBRICANTS_STAGING',
    'OIL_EQUIPMENT_SERVICES': 'NSE_NIFTY_OIL_EQUIPMENT_SERVICES_STAGING',
    'PETROLEUM_PRODUCTS_REFINERIES': 'NSE_NIFTY_PETROLEUM_PRODUCTS_REFINERIES_STAGING',

    'SERVICES': 'NSE_NIFTY_SERVICES_STAGING',

    'TELECOM': 'NSE_NIFTY_TELECOMMUNICATION_STAGING',

    'TELECOMMUNICATION': 'NSE_NIFTY_TELECOMMUNICATION_STAGING',

    'UTILITIES': 'NSE_NIFTY_UTILITIES_STAGING',

    'AVIATION_AIR_TRANSPORT': 'NSE_NIFTY_AVIATION_AIR_TRANSPORT_STAGING',
    'LOGISTICS_SHIPPING': 'NSE_NIFTY_LOGISTICS_SHIPPING_STAGING',
    'PORT_AND_PORT_SERVICES': 'NSE_NIFTY_PORT_AND_PORT_SERVICES_STAGING',
    'ROAD_RAIL_TRANSPORT': 'NSE_NIFTY_ROAD_RAIL_TRANSPORT_STAGING',
    'TRANSPORT_INFRASTRUCTURE': 'NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING',

    'ENGINEERING': 'NSE_NIFTY_ENGINEERING_STAGING',
    'ELEC_HEAVY_EQUIPMENT': 'NSE_NIFTY_ELEC_HEAVY_EQUIP_STAGING',
    'ELEC_HEAVY_EQUIP': 'NSE_NIFTY_ELEC_HEAVY_EQUIP_STAGING',
    'ELECTRICALS_HEAVY_ELECTRICAL_EQUIPMENT': 'NSE_NIFTY_ELEC_HEAVY_EQUIP_STAGING',
    'INDUSTRIAL_MANUFACTURING': 'NSE_NIFTY_INDUSTRIAL_MANUFACTURING_STAGING',
    'INDUSTRIAL_PRODUCTS': 'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING',
    'INDUSTRIAL_GASES_FUELS': 'NSE_NIFTY_INDUSTRIAL_GASES_FUELS_STAGING',
    'COMMODITIES_TRADING': 'NSE_NIFTY_COMMODITIES_TRADING_STAGING',
    'DEFENCE_AEROSPACE_DEFENSE': 'NSE_NIFTY_DEFENCE_AEROSPACE_DEFENSE_STAGING',
    'DIVERSIFIED': 'NSE_NIFTY_DIVERSIFIED_STAGING',
    'PAPER_PACKAGING': 'NSE_NIFTY_PAPER_PACKAGING_STAGING',
    'WASTE_WATER_MANAGEMENT': 'NSE_NIFTY_WASTE_WATER_MANAGEMENT_STAGING',

    'RETAILING_SPECIALITY_RETAIL': 'NSE_NIFTY_RETAILING_SPECIALITY_RETAIL_STAGING',
    'ECOMMERCE_ERETAI': 'NSE_NIFTY_ECOMMERCE_ERETAI_STAGING',
    'FOOTWEAR': 'NSE_NIFTY_FOOTWEAR_STAGING',
    'GEMS': 'NSE_NIFTY_GEMS_STAGING',
    'JEWELLERY_WATCHES': 'NSE_NIFTY_JEWELLERY_WATCHES_STAGING',
    'LEATHER_LEATHER_PRODUCTS': 'NSE_NIFTY_LEATHER_LEATHER_PRODUCTS_STAGING',
    'TEXTILES_APPARELS': 'NSE_NIFTY_TEXTILES_APPARELS_STAGING',

    'RESTAURANTS': 'NSE_NIFTY_RESTAURANTS_STAGING',
    'HOSPITALITY_HOTELS_RESORTS': 'NSE_NIFTY_HOSPITALITY_HOTELS_RESORTS_STAGING',
    'TOURISM_TRAVEL': 'NSE_NIFTY_TOURISM_TRAVEL_STAGING',
    'EDUCATION_E_LEARNING': 'NSE_NIFTY_EDUCATION_E_LEARNING_STAGING',

}

_STRICT_SYMBOL_CACHE_PREFIX = 'strict-sector-symbols:'

_STRICT_SYMBOL_LOOKUP_CACHE_PREFIX = 'strict-sector-symbol-lookups:'

_MERGED_SECTOR_FILTER_CACHE_TOKENS: dict[str, str] = {

    'HEALTHCARE': 'exclude_pharma_v1',

}

_SECTOR_DISPLAY_NAME_OVERRIDES: dict[str, str] = {

    'NBFC': 'NBFC',
    'INSURANCE': 'Insurance',
    'CAPITAL_MARKETS': 'Capital Markets',
    'ASSET_MANAGEMENT_COMPANY': 'Asset Management Company',
    'FINTECH': 'Fintech',
    'HOUSING_FINANCE_COMPANY': 'Housing Finance Company',
    'STOCKBROKING_AND_ALLIED': 'Stockbroking & Allied',

    'ALCOHOL_BREWERIES': 'Alcohol Breweries',

    'AGRICULTURE': 'Agriculture',
    'FERTILIZERS_AGROCHEMICALS': 'Fertilizers & Agrochemicals',
    'PESTICIDES_AGROCHEMICALS': 'Pesticides & Agrochemicals',

    'AUTO': 'Auto Mobile',

    'AUTO_ANCILLARIES': 'Auto Ancillaries',
    'AUTO_COMPONENTS_EQUIPMENTS': 'Auto Components & Equipments',

    'CHEMICALS': 'Chemicals',
    'SPECIALTY_CHEMICALS': 'Specialty Chemicals',
    'PETROCHEMICALS': 'Petrochemicals',
    'PAINTS': 'Paints',
    'PLASTIC_PRODUCTS': 'Plastic Products',
    'EXPLOSIVES': 'Explosives',
    'ABRASIVES': 'Abrasives',
    'ELECTRODES_REFRACTORIES': 'Electrodes & Refractories',

    'ELEC_SERVICES_CONS_DURABLES': 'Electronics & Services Consumer Durables',
    'CONSUMER_DURABLES': 'Consumer Durables',
    'CONS_DUR': 'Consumer Durables',
    'CONSUMER_ELECTRONICS': 'Consumer Electronics',
    'CONSUMER_SERVICES': 'Consumer Services',

    'HOUSEHOLD_PERSONAL_PRODUCTS': 'Household & Personal Products',

    'BIOTECHNOLOGY': 'Biotechnology',
    'MEDICAL_EQUIPMENT_SUPPLIES': 'Medical Equipment & Supplies',

    'IT_ENABLED_SERVICES': 'IT Enabled Services',
    'SOFTWARE_PRODUCTS_SERVICES': 'Software Products & Services',

    'MEDIA_ENTERTAINMENT': 'Media & Entertainment',
    'PRINT_MEDIA_PUBLISHING': 'Print Media & Publishing',

    'METALS_MINING': 'Metals & Mining',
    'IRON_STEEL': 'Iron & Steel',
    'MINING': 'Mining',
    'NON_FERROUS_METALS': 'Non-Ferrous Metals',

    'PHARMA': 'Pharma',

    'LPG_CNG_PNG_LNG_SUPPLIER': 'LPG CNG PNG LNG Supplier',
    'LUBRICANTS': 'Lubricants',
    'OIL_EQUIPMENT_SERVICES': 'Oil Equipment & Services',
    'PETROLEUM_PRODUCTS_REFINERIES': 'Petroleum Products & Refineries',

    'RUBBER_PRODUCTS_TYRES': 'Rubber Products Tyres',

    'CEMENT_CEMENT_PRODUCTS': 'Cement & Cement Products',
    'CONSTRUCTION_MATERIALS': 'Construction Materials',
    'INFRASTRUCTURE': 'Infrastructure',

    'AVIATION_AIR_TRANSPORT': 'Aviation Air Transport',
    'LOGISTICS_SHIPPING': 'Logistics, Shipping',
    'PORT_AND_PORT_SERVICES': 'Port & Port Services',
    'ROAD_RAIL_TRANSPORT': 'Road & Rail Transport',
    'TRANSPORT_INFRASTRUCTURE': 'Transport Infrastructure',

    'ENGINEERING': 'Engineering',
    'ELEC_HEAVY_EQUIPMENT': 'Electricals Heavy Electrical Equipment',
    'ELEC_HEAVY_EQUIP': 'Electricals Heavy Electrical Equipment',
    'ELECTRICALS_HEAVY_ELECTRICAL_EQUIPMENT': 'Electricals Heavy Electrical Equipment',
    'INDUSTRIAL_MANUFACTURING': 'Industrial Manufacturing',
    'INDUSTRIAL_PRODUCTS': 'Industrial Products',
    'INDUSTRIAL_GASES_FUELS': 'Industrial Gases & Fuels',
    'COMMODITIES_TRADING': 'Commodities & Trading',
    'DEFENCE_AEROSPACE_DEFENSE': 'Defence Aerospace & Defense',
    'DIVERSIFIED': 'Diversified',
    'PAPER_PACKAGING': 'Paper & Packaging',
    'WASTE_WATER_MANAGEMENT': 'Waste & Water Management',

    'FIN_SERV': 'Financial Services',
    'FINANCIAL_SERVICES': 'Financial Services',

    'RETAILING_SPECIALITY_RETAIL': 'Retailing Speciality Retail',
    'ECOMMERCE_ERETAI': 'E-Commerce E-Retail',
    'FOOTWEAR': 'Footwear',
    'GEMS': 'Gems',
    'JEWELLERY_WATCHES': 'Jewellery & Watches',
    'LEATHER_LEATHER_PRODUCTS': 'Leather & Leather Products',
    'TEXTILES_APPARELS': 'Textiles & Apparels',

    'RESTAURANTS': 'Restaurants',
    'HOSPITALITY_HOTELS_RESORTS': 'Hospitality Hotels & Resorts',
    'TOURISM_TRAVEL': 'Tourism & Travel',
    'EDUCATION_E_LEARNING': 'Education & E-Learning',

}



_MERGED_SECTOR_SOURCE_CODES: dict[str, tuple[str, ...]] = {

    'HEALTHCARE': (

        'HEALTHCARE_INDEX',

        'NIFTY500_HEALTHCARE',

        'MIDSMALL_HEALTHCARE',

    ),

}

_MERGED_SECTOR_ALIASES: dict[str, str] = {

    'HEALTH': 'HEALTHCARE',

    'HEALTHCARE': 'HEALTHCARE',

    'HEALTHCARE_INDEX': 'HEALTHCARE',

    'NIFTY_HEALTHCARE': 'HEALTHCARE',

    'NIFTY_HEALTHCARE_INDEX': 'HEALTHCARE',

    'NIFTY_500_HEALTHCARE': 'HEALTHCARE',

    'NIFTY500_HEALTHCARE': 'HEALTHCARE',

    'NSE_NIFTY500_HEALTHCARE': 'HEALTHCARE',

    'MIDSMALL_HEALTHCARE': 'HEALTHCARE',

    'MID_SMALL_HEALTHCARE': 'HEALTHCARE',

    'MID_HEALTH': 'HEALTHCARE',

}

_MERGED_SECTOR_TABLE_LABELS: dict[str, str] = {

    'HEALTHCARE': 'MERGED_HEALTHCARE_STAGING',

}

_MERGED_SECTOR_DISPLAY_NAMES: dict[str, str] = {

    'HEALTHCARE': 'Healthcare',

}

_SECTOR_ROTATION_GROUP_ALIASES: dict[str, str] = {

    **_MERGED_SECTOR_ALIASES,

    'CONS_DUR': 'CONSUMER_DURABLES',
    'ELEC_SERVICES_CONS_DURABLES': 'ELECTRONICS_SERVICES_CONSUMER_DURABLES',
    'ELEC_HEAVY_EQUIP': 'ELEC_HEAVY_EQUIPMENT',
    'ELECTRICALS_HEAVY_ELECTRICAL_EQUIPMENT': 'ELEC_HEAVY_EQUIPMENT',
    'FIN_SERV': 'FINANCIAL_SERVICES',

    'OIL_GAS': 'OIL_AND_GAS',

    'TELECOM': 'TELECOMMUNICATION',

}



_SORT_COLUMN_MAP = {

    'SYMBOL': 'UPPER(b.symbol)',

    'CLOSE_PRICE': 'b.close_price',

    'RSI55_GT0': 'b.rsi55_gt0',

    'RSI50_GT0': 'b.rsi50_gt0',

    'SMA20': 'b.sma20',

    'SMA50': 'b.sma50',

    'SMA100': 'b.sma100',

    'LTC_DATE': 'b.ltc_date',

    'INDEX_CODE': 'b.index_code',

    'CAP_BUCKET': 'b.cap_bucket',

}



_SORT_ALIASES = {

    'PRICE': 'CLOSE_PRICE',

    'CLOSE': 'CLOSE_PRICE',

    'CLOSEPRICE': 'CLOSE_PRICE',

}



_SECTOR_WISE_SORT_FIELDS = {

    'S_NO',

    'STOCK',

    'LTC_DATE',

    'PRICE',

    'MCAP',

    'MCAP_RANK',

    'INDEX',

    'GAP',

    '52WH',

    '52WL',

    'ATH',

    'EMA20_FLAG',

    'EMA50_FLAG',

    'EMA100_FLAG',

    'EMA200_FLAG',

    'TREND',

    'SCORE',

}



_SECTOR_WISE_SORT_ALIASES = {

    'SNO': 'S_NO',

    'S_NO': 'S_NO',

    'STOCK': 'STOCK',

    'SYMBOL': 'STOCK',

    'LTC_DATE': 'LTC_DATE',

    'LTCDATE': 'LTC_DATE',

    'PRICE': 'PRICE',

    'MCAP': 'MCAP',

    'MCAP_RANK': 'MCAP_RANK',

    'MCAPRANK': 'MCAP_RANK',

    'MARKET_CAP_RANK': 'MCAP_RANK',

    'MARKETCAPRANK': 'MCAP_RANK',

    'TOTAL_MCAP': 'MCAP',

    'TOTALMCAP': 'MCAP',

    'INDEX': 'INDEX',

    'GAP': 'GAP',

    '52WH': '52WH',

    'W52H': '52WH',

    '52WL': '52WL',

    'W52L': '52WL',

    'ATH': 'ATH',

    'EMA20_FLAG': 'EMA20_FLAG',

    'EMA50_FLAG': 'EMA50_FLAG',

    'EMA100_FLAG': 'EMA100_FLAG',

    'EMA200_FLAG': 'EMA200_FLAG',

    'TREND': 'TREND',

    'SCORE': 'SCORE',

    'SCORESORT': 'SCORE',

    'MASTER_SCORE': 'SCORE',

    'MASTERSCORE': 'SCORE',

}



_SECTOR_TREND_LABELS = (

    'Strong Uptrend',

    'Uptrend',

    'Pullback in Uptrend',

    'Downtrend',

    'Sideways',

    'Consolidation',

    'Possible Reversal',

    'Unknown / Insufficient Data',

)



_SECTOR_TREND_SORT_ASC = {

    'STRONG UPTREND': 0,

    'UPTREND': 1,

    'PULLBACK IN UPTREND': 2,

    'POSSIBLE REVERSAL': 3,

    'SIDEWAYS': 4,

    'CONSOLIDATION': 5,

    'DOWNTREND': 6,

    'UNKNOWN / INSUFFICIENT DATA': 7,

}



_SECTOR_WISE_SNAPSHOT_CANDIDATES: dict[str, list[str]] = {

    'ath': ['ATH', 'ALL_TIME_HIGH', 'HIGH_ATH', 'HIGH_ALL_TIME', 'ALLTIMEHIGH', 'ATH_PRICE'],

    'high_52w': ['HIGH_52W', 'HIGH52W', 'WEEK52_HIGH', 'HIGH_1Y', 'W52H', '52WH'],

    'low_52w': ['LOW_52W', 'LOW52W', 'WEEK52_LOW', 'LOW_1Y', 'W52L', '52WL'],

    'ema20': ['EMA20', 'EMA_20'],

    'ema50': ['EMA50', 'EMA_50'],

    'ema100': ['EMA100', 'EMA_100'],

    'ema200': ['EMA200', 'EMA_200'],

    'total_mcap': ['TOTAL_MCAP_CR', 'TOTAL_MCAP', 'MCAP', 'MARKET_CAP', 'MKT_CAP', 'TOTAL_MARKET_CAP'],

    'mcap_rank': ['MCAP_RANK', 'MCAP_RNK', 'MARKET_CAP_RANK', 'RANK'],

}



_SECTOR_WISE_FLAG_CANDIDATES: dict[str, list[str]] = {

    'ema20_flag': ['EMA20_FLAG', 'EMA20FLAG', 'ABOVE_EMA20', 'ABOVE_EMA_20'],

    'ema50_flag': ['EMA50_FLAG', 'EMA50FLAG', 'ABOVE_EMA50', 'ABOVE_EMA_50'],

    'ema100_flag': ['EMA100_FLAG', 'EMA100FLAG', 'ABOVE_EMA100', 'ABOVE_EMA_100'],

    'ema200_flag': ['EMA200_FLAG', 'EMA200FLAG', 'ABOVE_EMA200', 'ABOVE_EMA_200'],

}



_SNAPSHOT_METRIC_CANDIDATES: dict[str, list[str]] = {

    'rsi55_gt0': ['RSI55_GT0', 'RSI55_GT0_PCT', 'RSI55', 'RSI_55'],

    'rsi50_gt0': ['RSI50_GT0', 'RSI50_GT0_PCT', 'RSI50', 'RSI_50'],

    'sma20': ['SMA20', 'SMA20_PCT', 'SMA_20', 'SMA20_GT0'],

    'sma50': ['SMA50', 'SMA50_PCT', 'SMA_50', 'SMA50_GT0'],

    'sma100': ['SMA100', 'SMA100_PCT', 'SMA_100', 'SMA100_GT0'],

}



_BREADTH_FALLBACK_COLUMN: dict[str, str] = {

    'rsi55_gt0': 'breadth.rsi55_gt0_pct',

    'rsi50_gt0': 'breadth.rsi50_gt0_pct',

    'sma20': 'breadth.sma20_pct',

    'sma50': 'breadth.sma50_pct',

    'sma100': 'breadth.sma100_pct',

}



SQL_SECTORS = """

SELECT

    m.sector_code AS "sectorCode",

    m.sector_name AS "sectorName",

    m.parent_sector AS "parentSector",

    m.industry AS "industry",

    m.index_code AS "indexCode",

    m.display_order AS "displayOrder"

FROM (

    SELECT

        t.sector_code,

        t.sector_name,

        t.parent_sector,

        t.industry,

        t.index_code,

        NVL(t.display_order, 9999) AS display_order,

        ROW_NUMBER() OVER (

            PARTITION BY t.sector_code

            ORDER BY NVL(t.display_order, 9999), t.sector_name

        ) AS rn

    FROM nse_sector_master t

) m

WHERE m.rn = 1

ORDER BY m.display_order, m.sector_name, m.sector_code

"""



SQL_BREADTH = """

SELECT

    m.sector_code AS "sectorCode",

    m.sector_name AS "sectorName",

    m.parent_sector AS "parentSector",

    m.industry AS "industry",

    m.index_code AS "indexCode",

    NVL(b.total_symbols, 0) AS "totalSymbols",

    ROUND(NVL(b.rsi55_gt0_pct, 0), 2) AS "rsi55Pct",

    ROUND(NVL(b.rsi50_gt0_pct, 0), 2) AS "rsi50Pct",

    ROUND(NVL(b.sma20_pct, 0), 2) AS "sma20Pct",

    ROUND(NVL(b.sma50_pct, 0), 2) AS "sma50Pct",

    ROUND(NVL(b.sma100_pct, 0), 2) AS "sma100Pct",

    (

        SELECT MAX(snap.ltc_date)

        FROM mv_nse_sector_ui_snapshot snap

        WHERE snap.sector = m.sector_code

    ) AS "asOfDate"

FROM (

    SELECT

        t.sector_code,

        t.sector_name,

        t.parent_sector,

        t.industry,

        t.index_code,

        NVL(t.display_order, 9999) AS display_order,

        ROW_NUMBER() OVER (

            PARTITION BY t.sector_code

            ORDER BY NVL(t.display_order, 9999), t.sector_name

        ) AS rn

    FROM nse_sector_master t

) m

LEFT JOIN vw_sector_breadth b

    ON b.sector_code = m.sector_code

WHERE m.rn = 1

ORDER BY m.display_order, m.sector_name, m.sector_code

"""



SQL_VIEW_EXISTS = """

SELECT COUNT(1)

FROM user_objects

WHERE object_name = :object_name

  AND object_type IN ('VIEW', 'MATERIALIZED VIEW', 'TABLE')

"""



SQL_DISCOVER_SECTOR_TABLES = """

SELECT utc.table_name AS "tableName"

FROM user_tab_columns utc

JOIN user_tables ut

  ON ut.table_name = utc.table_name

WHERE utc.column_name = 'SYMBOL'

  AND utc.table_name LIKE 'NSE_NIFTY%STAGING'

  AND utc.table_name NOT IN (

      'NSE_NIFTY_FINANCIAL_SERVICES_25_50_STAGING',

      'NSE_NIFTY_FINANCIAL_SERVICES_EX_BANK_STAGING',

      'NSE_NIFTY_MIDSMALL_FINANCIAL_SERVICES_STAGING'

  )

GROUP BY utc.table_name

ORDER BY utc.table_name

"""



_DYNAMIC_SORT_COLS: dict[str, str] = {

    'SYMBOL': 'UPPER(TRIM(symbol))',

    'COMPANY_NAME': 'UPPER(company_name)',

    'SECTOR': 'UPPER(sector)',

    'INDUSTRY': 'UPPER(industry)',

    'SERIES': 'UPPER(series)',

    'ISIN_CODE': 'UPPER(isin_code)',

    'UPDATED_DATE': 'updated_date',

    'CREATED_DATE': 'created_date',

}



_UI_FRIENDLY_TOKEN_MAP: dict[str, str] = {

    'FMCG': 'FMCG',

    'IT': 'IT',

    'PSU': 'PSU',

    '25': '25',

    '50': '50',

    'EX': 'Ex',

    'BANK': 'Bank',

    'INDEX': 'Index',

    'MIDSMALL': 'Midsmall',

    'NIFTY500': 'Nifty500',

    'REALTY_REAL_ESTATE': 'Realty Real Estate',

    
    'TELECOMMUNICATION': 'Telecommunication',

    'OIL': 'Oil',

    'AND': '&',

    'GAS': 'Gas',

}





def _normalize(value: Any) -> Any:

    if isinstance(value, Decimal):

        if value == value.to_integral_value():

            return int(value)

        return float(value)

    if isinstance(value, (datetime, date)):

        return value.isoformat()

    return value





def _coerce_int(value: Any, default: int = 0) -> int:

    if value is None:

        return default

    try:

        return int(value)

    except Exception:

        try:

            return int(float(value))

        except Exception:

            return default





def _query_rows(sql: str, binds: dict[str, Any] | None = None) -> list[dict[str, Any]]:

    conn = get_oracle_connection()

    try:

        with conn.cursor() as cursor:

            cursor.arraysize = 500

            cursor.execute(sql, binds or {})

            columns = [col[0] for col in cursor.description]

            rows = cursor.fetchall()

        return [{columns[idx]: _normalize(row[idx]) for idx in range(len(columns))} for row in rows]

    finally:

        conn.close()





def _query_scalar(sql: str, binds: dict[str, Any] | None = None, default: Any = None) -> Any:

    conn = get_oracle_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(sql, binds or {})

            row = cursor.fetchone()

            if not row:

                return default

            return _normalize(row[0])

    finally:

        conn.close()





def _zero_breadth_rows() -> list[dict[str, Any]]:

    try:

        sectors = _query_rows(SQL_SECTORS)

    except Exception:

        return []

    return [{

        'sectorCode': row.get('sectorCode'),

        'sectorName': row.get('sectorName'),

        'indexCode': row.get('indexCode'),

        'totalSymbols': 0,

        'rsi55Pct': 0,

        'rsi50Pct': 0,

        'sma20Pct': 0,

        'sma50Pct': 0,

        'sma100Pct': 0,

        'asOfDate': None,

        'relativeMomentum': 0,

        'absoluteTrend': 0,

        'breadthComposite': 0,

        'mcapBreadth': 0,

        'ffmcBreadth': 0,

        'countBreadth': 0,

        'riskAdjustment': 0,

        'rotationScore': 0,

        'finalRotation': 0,

        'rankScore': 0,

        'stockConfirmationScreening': 'Neutral / NA',

        'stockConfirmationLabel': 'Neutral',

        'confirmedStocks': 0,

        'screenedStocks': 0,

        'stockConfirmationScoreAvg': 0,

        'finalRotationDelta5': None,

        'finalRotationDelta21': None,

        'rankChange5': None,

        'rankChange21': None,

        'priceSource': None,

        'priceSourceTradeDate': None,

    } for row in sectors]





def _map_sector_codes() -> set[str]:

    cached = _cache.get(_MAP_SECTOR_CACHE_KEY)

    if isinstance(cached, set):

        return cached

    try:

        rows = _query_rows('SELECT DISTINCT sector AS "sectorCode" FROM mv_nse_sector_ui_snapshot')

        codes = {str(row.get('sectorCode') or '').upper() for row in rows if row.get('sectorCode')}

    except Exception:

        codes = set()

    try:

        for item in _discover_sector_staging_tables():

            table_sector_code = str(item.get('sectorCode') or '').strip().upper()

            if table_sector_code:

                codes.add(table_sector_code)

    except Exception:

        pass

    _cache.set(_MAP_SECTOR_CACHE_KEY, codes)

    return codes





def _resolve_sector_candidates(requested_code: str) -> list[str]:

    requested = (requested_code or '').strip().upper()

    if not requested:

        return []



    available = _map_sector_codes()

    candidates: list[str] = [requested]

    for alias_code in SECTOR_CODE_ALIASES.get(requested, []):

        if alias_code not in candidates:

            candidates.append(alias_code)



    if available:

        filtered = [code for code in candidates if code in available]

        if filtered:

            return filtered

    return candidates





def _parse_positive_int(value: Any, default: int, minimum: int = 1, maximum: int | None = None) -> int:

    try:

        parsed = int(str(value).strip())

    except Exception:

        parsed = default

    if parsed < minimum:

        parsed = minimum

    if maximum is not None and parsed > maximum:

        parsed = maximum

    return parsed





def _normalize_page_size(value: Any) -> int:

    parsed = _parse_positive_int(value, _DEFAULT_PAGE_SIZE, minimum=1, maximum=max(_ALLOWED_PAGE_SIZES))

    if parsed not in _ALLOWED_PAGE_SIZES:

        return _DEFAULT_PAGE_SIZE

    return parsed





def _normalize_sort_key(value: Any) -> str:

    raw = str(value or 'CLOSE_PRICE').strip().upper()

    normalized = _SORT_ALIASES.get(raw, raw)

    return normalized if normalized in _SORT_COLUMN_MAP else 'CLOSE_PRICE'





def _normalize_sort_dir(value: Any) -> str:

    raw = str(value or 'DESC').strip().upper()

    return 'ASC' if raw == 'ASC' else 'DESC'





def _normalize_cap_bucket(value: Any) -> str:

    raw = str(value or 'ALL').strip().upper()

    return raw if raw in {'ALL', 'LARGE', 'MID', 'SMALL'} else 'ALL'





def _normalize_index_code(value: Any) -> str:

    raw = str(value or 'ALL').strip().upper()

    if not raw:

        return 'ALL'

    return raw[:64]





def _normalize_index_token(value: Any) -> str:

    if value is None:

        return ''

    token = str(value).strip().upper()

    if not token:

        return ''

    return token.replace('_', '').replace(' ', '')





def _normalize_search_token(value: Any) -> str:

    raw = str(value or '').strip().upper()

    return raw[:32]





def _normalize_search_bind(search_token: str) -> str | None:

    if not search_token:

        return None

    escaped = search_token.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

    return f'%{escaped}%'





def _normalize_symbol_token(value: Any) -> str:
    return canonical_nse_symbol_key(value)





_INDEX_SYMBOL_ALIAS_MAP: dict[str, str] = {

    'LTIM': 'LTM',

}



_INDEX_SYMBOL_EXCLUDE_SET: set[str] = {

    'DUMMYALCAR',

}





def _normalize_index_lookup_symbol(value: Any) -> str:

    token = _normalize_symbol_token(value)

    if not token:

        return ''

    token = _INDEX_SYMBOL_ALIAS_MAP.get(token, token)

    if token in _INDEX_SYMBOL_EXCLUDE_SET:

        return ''

    return token





def _normalized_symbol_expr(expr: str) -> str:

    return (

        "REGEXP_REPLACE("

        "REGEXP_REPLACE(REPLACE(REPLACE(UPPER(TRIM(" + expr + ")), 'NSE:', ''), 'BSE:', ''), '-(EQ|BE|SM|ST|BZ)$', ''), "

        "'[^A-Z0-9]+', ''"

        ")"

    )





def _symbol_variants(tokens: list[str]) -> list[str]:

    variants: set[str] = set()

    for raw in tokens:

        raw_token = str(raw or '').strip().upper()

        token = _normalize_symbol_token(raw)

        if not token:

            continue

        if raw_token:

            variants.add(raw_token)

        canonical = canonical_nse_symbol(raw)

        for symbol_value in {canonical, token}:

            if not symbol_value:

                continue

            variants.add(symbol_value)

            for symbol_series in NSE_CASH_SERIES:

                variants.add(f'{symbol_value}-{symbol_series}')

                variants.add(f'NSE:{symbol_value}-{symbol_series}')

                variants.add(f'BSE:{symbol_value}-{symbol_series}')

    return sorted(variants)





def _build_sector_binds(candidates: list[str]) -> tuple[str, dict[str, Any]]:

    binds: dict[str, Any] = {}

    placeholders: list[str] = []

    for idx, code in enumerate(candidates):

        bind_name = f'sector_{idx}'

        placeholders.append(f':{bind_name}')

        binds[bind_name] = code

    return ', '.join(placeholders), binds





def _build_symbol_binds(symbols: list[str]) -> tuple[str, dict[str, Any]]:

    binds: dict[str, Any] = {}

    placeholders: list[str] = []

    for idx, symbol in enumerate(symbols):

        bind_name = f'symbol_{idx}'

        placeholders.append(f':{bind_name}')

        binds[bind_name] = symbol

    return ', '.join(placeholders), binds





def _load_strict_sector_symbols(sector_code: str) -> list[str] | None:

    normalized = str(sector_code or '').strip().upper()

    table_name = _STRICT_SECTOR_TABLE_MAP.get(normalized)

    if not table_name:

        return None

    if not _is_safe_sql_name(table_name, allow_dot=False):

        return None



    cache_key = f'{_STRICT_SYMBOL_CACHE_PREFIX}v3:{normalized}'

    cached = _cache.get(cache_key)

    if isinstance(cached, list):

        return cached



    conn = get_oracle_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(

                """

                SELECT COUNT(*)

                FROM user_tables

                WHERE table_name = :table_name

                """,

                {'table_name': table_name},

            )

            row = cursor.fetchone()

            if _coerce_int(row[0] if row else 0, default=0) <= 0:

                _cache.set(cache_key, [])

                return []

            cursor.execute(

                f"""

                SELECT DISTINCT UPPER(TRIM(symbol)) AS symbol

                FROM {table_name}

                WHERE symbol IS NOT NULL

                  AND TRIM(symbol) IS NOT NULL

                ORDER BY UPPER(TRIM(symbol))

                """

            )

            symbol_map: dict[str, str] = {}

            for row in (cursor.fetchall() or []):

                display_symbol = str(row[0] or '').strip().upper() if row and row[0] else ''

                if not display_symbol:

                    continue

                lookup_symbol = _normalize_index_lookup_symbol(display_symbol) or _normalize_symbol_token(display_symbol)

                if not lookup_symbol:

                    continue

                display_symbol = 'LTM' if display_symbol == 'LTIM' else display_symbol

                if lookup_symbol not in symbol_map or symbol_map[lookup_symbol] == 'LTIM':

                    symbol_map[lookup_symbol] = display_symbol

            symbols = sorted(symbol_map.values())

            _cache.set(cache_key, symbols)

            return symbols

    except Exception:

        logger.exception('Failed strict sector symbol load for %s from %s', normalized, table_name)

        return None

    finally:

        conn.close()





def _load_strict_sector_symbol_lookups(sector_code: str) -> set[str]:

    normalized = str(sector_code or '').strip().upper()

    if not normalized:

        return set()

    cache_key = f'{_STRICT_SYMBOL_LOOKUP_CACHE_PREFIX}v2:{normalized}'

    cached = _cache.get(cache_key)

    if isinstance(cached, set):

        return cached



    symbols = _load_strict_sector_symbols(normalized) or []

    lookups: set[str] = set()

    for symbol in symbols:

        lookup_symbol = _normalize_index_lookup_symbol(symbol) or _normalize_symbol_token(symbol)

        if lookup_symbol:

            lookups.add(lookup_symbol)

    _cache.set(cache_key, lookups)

    return lookups





def _sector_alias_lookup_key(value: Any) -> str:
    return normalize_sector_alias(value)


def _resolve_canonical_sector_code(value: Any) -> str:
    """Resolve code or display-name aliases through the sector master."""
    token = normalize_sector_alias(value)
    if not token:
        return ''
    try:
        rows = _query_rows(
            """
            SELECT sector_code AS "sectorCode", sector_name AS "sectorName"
            FROM nse_sector_master
            WHERE NVL(is_active, 'Y') = 'Y'
            """
        )
        for row in rows:
            code = str(row.get('sectorCode') or '').strip().upper()
            name = str(row.get('sectorName') or '').strip()
            if token in {normalize_sector_alias(code), normalize_sector_alias(name)}:
                return code
    except Exception:
        logger.debug('Sector master alias lookup unavailable', exc_info=True)
    return canonical_sector_code(value)


def _apply_sector_hierarchy(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach master hierarchy metadata to cached/live rows in one fixed query."""
    if not rows:
        return rows
    try:
        master_rows = _query_rows(
            'SELECT sector_code AS "sectorCode", sector_name AS "sectorName", '
            'parent_sector AS "parentSector", industry AS "industry" '
            'FROM nse_sector_master WHERE NVL(is_active, \'Y\') = \'Y\''
        )
        by_code = {str(item.get('sectorCode') or '').strip().upper(): item for item in master_rows}
        for row in rows:
            hierarchy_fields(row)
            code = str(row.get('sectorCode') or '').strip().upper()
            master = by_code.get(code)
            if master:
                row['sectorName'] = master.get('sectorName') or row.get('sectorName')
                row['parentSector'] = master.get('parentSector')
                row['industry'] = master.get('industry')
        return rows
    except Exception:
        return [hierarchy_fields(row) for row in rows]





def _canonical_merged_sector_code(sector_code: Any) -> str:

    normalized = _sector_alias_lookup_key(sector_code)

    return _MERGED_SECTOR_ALIASES.get(normalized, '')





def _canonical_sector_rotation_group_code(sector_code: Any) -> str:

    normalized = _sector_alias_lookup_key(sector_code)

    return _SECTOR_ROTATION_GROUP_ALIASES.get(normalized, '')





def _strict_sector_table_name(sector_code: str) -> str:

    normalized = str(sector_code or '').strip().upper()

    table_name = str(_STRICT_SECTOR_TABLE_MAP.get(normalized) or '').strip().upper()

    return table_name if _is_safe_sql_name(table_name, allow_dot=False) else ''


def _canonical_unique_sector_selector_code(sector_code: Any) -> str:

    normalized = _sector_alias_lookup_key(sector_code)

    if not normalized:

        return ''

    canonical = _SECTOR_ROTATION_GROUP_ALIASES.get(normalized)

    if canonical:

        return canonical

    return {

        'CONS_DUR': 'CONSUMER_DURABLES',

        'ELEC_SERVICES_CONS_DURABLES': 'ELECTRONICS_SERVICES_CONSUMER_DURABLES',

        'ELEC_HEAVY_EQUIP': 'ELEC_HEAVY_EQUIPMENT',

        'ELECTRICALS_HEAVY_ELECTRICAL_EQUIPMENT': 'ELEC_HEAVY_EQUIPMENT',

    }.get(normalized, normalized)


def _collapse_sector_entries_for_unique_ui(entries: Any) -> list[dict[str, Any]]:

    normalized_entries = _normalize_sector_table_entries(entries) or []

    if not normalized_entries:

        return []

    collapsed: dict[str, dict[str, Any]] = {}

    for item in normalized_entries:

        raw_code = str(item.get('sectorCode') or '').strip().upper()

        raw_table_name = str(item.get('tableName') or '').strip().upper()

        canonical_code = _canonical_unique_sector_selector_code(raw_code) or raw_code

        if not canonical_code:

            continue

        canonical_table_name = (

            _MERGED_SECTOR_TABLE_LABELS.get(canonical_code)

            or _strict_sector_table_name(canonical_code)

            or raw_table_name

        )

        # Master-backed discovery may provide an exact display label (including
        # punctuation such as '&'); preserve it instead of reformatting the code.
        display_name = str(item.get('sectorName') or '').strip() or _resolve_display_sector_name(
            canonical_code,
            canonical_code,
        )

        stock_count = _coerce_int(item.get('stockCount'), default=0)

        existing = collapsed.get(canonical_code)

        if existing is None:

            collapsed[canonical_code] = {

                'sectorCode': canonical_code,

                'sectorName': display_name,

                'tableName': canonical_table_name,

                'stockCount': stock_count,
                'parentSector': item.get('parentSector'),
                'industry': item.get('industry'),

                'table_name': canonical_table_name,

                'sector_key': canonical_code.lower().replace('_', '-'),

                'sector_name': display_name,

                'display_name': display_name,

                'source': 'unique_sector_selector',

                'sourceTables': [raw_table_name] if raw_table_name else [],

            }

            continue

        existing['stockCount'] = max(_coerce_int(existing.get('stockCount'), default=0), stock_count)

        source_tables = existing.setdefault('sourceTables', [])

        if raw_table_name and raw_table_name not in source_tables:

            source_tables.append(raw_table_name)

    unique_entries = list(collapsed.values())

    unique_entries.sort(key=lambda item: (str(item.get('sectorName') or ''), str(item.get('sectorCode') or '')))

    return unique_entries





def _to_safe_oracle_name(value: Any) -> str:

    token = str(value or '').strip().upper()

    if not token:

        return ''

    if not re.fullmatch(r'[A-Z][A-Z0-9_$#]*', token):

        return ''

    return token





def _sector_code_from_table_name(table_name: str) -> str:

    token = str(table_name or '').strip().upper()

    if token.startswith('NSE_NIFTY_') and token.endswith('_STAGING'):

        core = token[10:-8]

    elif token.startswith('NSE_NIFTY500_') and token.endswith('_STAGING'):

        core = f'NIFTY500_{token[13:-8]}'

    else:

        core = token

    core = core

    return core





def _friendly_sector_name_from_code(sector_code: str) -> str:

    core = _sector_code_from_table_name(sector_code)

    if not core:

        return ''

    override = _SECTOR_DISPLAY_NAME_OVERRIDES.get(core)

    if override:

        return override

    tokens = [item for item in core.split('_') if item]

    formatted: list[str] = []

    for token in tokens:

        mapped = _UI_FRIENDLY_TOKEN_MAP.get(token)

        if mapped is not None:

            formatted.append(mapped)

        else:

            formatted.append(token.title())

    text = ' '.join(formatted).strip()

    text = re.sub(r'\s+&\s+', ' & ', text)

    return text





def _resolve_display_sector_name(sector_code: Any, fallback: Any = None) -> str:

    normalized = _sector_alias_lookup_key(sector_code) or str(sector_code or '').strip().upper()

    override = _SECTOR_DISPLAY_NAME_OVERRIDES.get(normalized)

    if override:

        return override

    merged_label = _MERGED_SECTOR_DISPLAY_NAMES.get(normalized)

    if merged_label:

        return merged_label

    text = str(fallback or '').strip()

    if text:

        return text

    return _friendly_sector_name_from_code(normalized)





def _friendly_sector_name_from_table(table_name: str) -> str:

    return _resolve_display_sector_name(_sector_code_from_table_name(table_name))





def _load_sector_table_columns(table_name: str) -> set[str]:

    normalized = _to_safe_oracle_name(table_name)

    if not normalized:

        return set()

    cache_key = f'{_SECTOR_TABLE_COLUMNS_CACHE_PREFIX}{normalized}'

    cached = _cache.get(cache_key)

    if isinstance(cached, set):

        return cached

    rows = _query_rows(

        """

        SELECT column_name AS "columnName"

        FROM user_tab_columns

        WHERE table_name = :table_name

        """,

        {'table_name': normalized},

    )

    columns = {str(row.get('columnName') or '').strip().upper() for row in rows if row.get('columnName')}

    _cache.set(cache_key, columns)

    return columns





def _sector_table_entries_have_counts(entries: Any) -> bool:

    if not isinstance(entries, list) or not entries:

        return False

    for item in entries:

        if not isinstance(item, dict):

            return False

        value = item.get('stockCount')

        if isinstance(value, bool):

            return False

        if not isinstance(value, (int, float)):

            return False

        if value < 0:

            return False

    return True





def _normalize_sector_table_entries(entries: Any) -> list[dict[str, Any]] | None:

    if entries is None:

        return None

    if not isinstance(entries, list):

        return None

    normalized_entries: list[dict[str, Any]] = []

    for item in entries:

        if not isinstance(item, dict):

            continue

        table_name = _to_safe_oracle_name(item.get('tableName') or item.get('table_name'))

        code = str(item.get('sectorCode') or item.get('sector_key') or _sector_code_from_table_name(table_name)).strip().upper()

        if not code or not table_name:

            continue

        name = _resolve_display_sector_name(code, item.get('sectorName') or item.get('sector_name') or item.get('display_name'))

        normalized_entries.append({

            'sectorCode': code,

            'sectorName': name,

            'tableName': table_name,

            'stockCount': _coerce_int(item.get('stockCount'), default=0),

            # Preserve additional discovery fields

            'table_name': table_name,

            'sector_key': item.get('sector_key') or code.lower().replace('_', '-'),

            'sector_name': name,

            'display_name': name,

            'source': item.get('source') or 'oracle_metadata',

            'discovered_at': item.get('discovered_at') or datetime.now().isoformat()

        })



    normalized_entries.sort(key=lambda item: (str(item.get('sectorName') or ''), str(item.get('tableName') or '')))

    return normalized_entries





import hashlib
import time

_SECTOR_DISCOVERY_STATE = {
    'last_checked': 0.0,
    'signature': None,
    'tables': None
}
_SECTOR_TABLE_DISCOVERY_TTL_SECONDS = 300

def _read_snapshot_from_disk() -> dict[str, Any] | None:
    try:
        if _SECTOR_TABLES_SNAPSHOT_PATH.exists():
            data = json.loads(_SECTOR_TABLES_SNAPSHOT_PATH.read_text(encoding='utf-8'))
            if isinstance(data, dict) and 'tables' in data:
                return data
            # Backward-compatible check: if it was a flat list
            elif isinstance(data, list):
                return {
                    'generated_at': datetime.now().isoformat(),
                    'table_count': len(data),
                    'signature': '',
                    'tables': data
                }
    except Exception:
        logger.exception('Failed reading sector tables snapshot from disk')
    return None

def _write_atomic_snapshot(tables: list[dict[str, Any]], signature: str) -> None:
    try:
        _SECTOR_TABLES_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'generated_at': datetime.now().isoformat(),
            'table_count': len(tables),
            'signature': signature,
            'tables': tables
        }
        # Atomic write
        temp_path = _SECTOR_TABLES_SNAPSHOT_PATH.with_suffix('.tmp')
        temp_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding='utf-8')
        if temp_path.exists():
            temp_path.replace(_SECTOR_TABLES_SNAPSHOT_PATH)
            logger.info(
                'event=sector_discovery_snapshot_written table_count=%d signature=%s snapshot_path=%s',
                len(tables),
                signature,
                _SECTOR_TABLES_SNAPSHOT_PATH,
            )
    except Exception:
        logger.exception('Failed atomic writing of sector tables snapshot')

def _invalidate_dependent_caches(sector_entries: list[dict[str, Any]] | None = None) -> None:
    _cache.clear()
    _popup_cache.clear()
    _sector_wise_trend_cache.clear()
    sector_cache_service.clear_sector_cache()
    sector_stock_cache_service.clear_sector_memory_cache()
    try:
        if _SNAPSHOT_PATH.exists():
            _SNAPSHOT_PATH.unlink()
    except Exception:
        logger.exception('Failed removing local breadth snapshot during sector discovery refresh')
    for entry in sector_entries or []:
        table_name = _to_safe_oracle_name(entry.get('tableName'))
        if not table_name:
            continue
        try:
            sector_stock_cache_service.delete_snapshot(table_name)
        except Exception:
            logger.exception('Failed removing sector stock snapshot for %s', table_name)
    try:
        from services.sector_rotation_service import invalidate_sector_groups_cache
        invalidate_sector_groups_cache()
    except Exception:
        logger.exception("Failed to invalidate dynamic UI sector groups cache")
    logger.info(
        'event=sector_discovery_refresh_forced table_count=%d snapshot_path=%s',
        len(sector_entries or []),
        _SECTOR_TABLES_SNAPSHOT_PATH,
    )


def _dedupe_canonical_sector_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for raw_row in rows or []:
        if not isinstance(raw_row, dict):
            continue
        raw_symbol = raw_row.get('stock') or raw_row.get('symbol')
        canonical_symbol = canonical_nse_symbol(raw_symbol)
        canonical_key = canonical_nse_symbol_key(canonical_symbol)
        if not canonical_key:
            continue
        row = dict(raw_row)
        row['stock'] = canonical_symbol
        if 'symbol' in row:
            row['symbol'] = canonical_symbol
        existing = deduped.get(canonical_key)
        if existing is None:
            deduped[canonical_key] = row
            continue
        for key, value in row.items():
            if existing.get(key) in (None, '', '-') and value not in (None, '', '-'):
                existing[key] = value
    return list(deduped.values())

def _discover_sector_staging_tables(force_refresh: bool = False) -> list[dict[str, Any]]:
    global _SECTOR_DISCOVERY_STATE
    now = time.monotonic()

    # 1. TTL Check for Memory Cache
    if not force_refresh:
        if _SECTOR_DISCOVERY_STATE['tables'] is not None:
            if now - _SECTOR_DISCOVERY_STATE['last_checked'] < _SECTOR_TABLE_DISCOVERY_TTL_SECONDS:
                logger.info('event=sector_discovery_cache_hit table_count=%d', len(_SECTOR_DISCOVERY_STATE['tables']))
                return _SECTOR_DISCOVERY_STATE['tables']

    # 2. Check Oracle metadata table list
    oracle_tables = []
    oracle_available = False
    try:
        rows = _query_rows(SQL_DISCOVER_SECTOR_TABLES)
        oracle_tables = [str(r.get('tableName') or '').strip().upper() for r in rows if r.get('tableName')]
        oracle_available = True
    except Exception:
        logger.exception('Failed querying Oracle metadata for staging tables')

    if oracle_available:
        # Compute signature of discovered tables
        table_signature = hashlib.sha256(json.dumps(sorted(oracle_tables)).encode('utf-8')).hexdigest()

        # If TTL expired but signature is unchanged, reuse memory cache
        if not force_refresh and _SECTOR_DISCOVERY_STATE['tables'] is not None:
            if _SECTOR_DISCOVERY_STATE['signature'] == table_signature:
                _SECTOR_DISCOVERY_STATE['last_checked'] = now
                logger.info('event=sector_discovery_cache_stale reason=signature_match_extend_ttl table_count=%d', len(_SECTOR_DISCOVERY_STATE['tables']))
                return _SECTOR_DISCOVERY_STATE['tables']

        # Either force_refresh = True or signature changed
        logger.info('event=sector_discovery_start force_refresh=%s', force_refresh)
        sector_entries = []
        conn = get_oracle_connection()
        try:
            with conn.cursor() as cursor:
                for table_name in oracle_tables:
                    logger.info('[SECTOR_TABLE_DISCOVERY] table=%s', table_name)
                    try:
                        cursor.execute(
                            f"""
                            SELECT COUNT(DISTINCT UPPER(TRIM(symbol)))
                            FROM {table_name}
                            WHERE symbol IS NOT NULL
                              AND TRIM(symbol) IS NOT NULL
                            """
                        )
                        item = cursor.fetchone()
                        stock_count = _coerce_int(item[0] if item else 0, default=0)
                    except Exception:
                        logger.exception('Failed stock count for sector table %s', table_name)
                        stock_count = 0
                    
                    code = _sector_code_from_table_name(table_name)
                    name = _resolve_display_sector_name(code)
                    sector_entries.append({
                        'sectorCode': code,
                        'sectorName': name,
                        'tableName': table_name,
                        'stockCount': stock_count,
                        # Detailed fields for generic discovery
                        'table_name': table_name,
                        'sector_key': code.lower().replace('_', '-'),
                        'sector_name': name,
                        'display_name': name,
                        'source': 'oracle_metadata',
                        'discovered_at': datetime.now().isoformat()
                    })
        finally:
            conn.close()

        sector_entries = _normalize_sector_table_entries(sector_entries) or []

        if force_refresh:
            _invalidate_dependent_caches(sector_entries)

        # Write snapshot atomically
        _write_atomic_snapshot(sector_entries, table_signature)

        # Update in-memory state
        _SECTOR_DISCOVERY_STATE.update({
            'last_checked': now,
            'signature': table_signature,
            'tables': sector_entries
        })
        _cache.set(_SECTOR_TABLES_CACHE_KEY, sector_entries)

        logger.info('event=sector_discovery_success table_count=%d signature=%s', len(sector_entries), table_signature)
        return sector_entries

    # 3. Fallback to Snapshot on Oracle failure
    logger.warning('event=sector_discovery_failed reason=oracle_unavailable_fallback_to_snapshot')
    snapshot_payload = _read_snapshot_from_disk()
    if snapshot_payload is not None:
        tables = _normalize_sector_table_entries(snapshot_payload.get('tables'))
        if tables:
            _SECTOR_DISCOVERY_STATE.update({
                'last_checked': now,
                'signature': snapshot_payload.get('signature'),
                'tables': tables
            })
            _cache.set(_SECTOR_TABLES_CACHE_KEY, tables)
            return tables

    # Final fallback to existing memory state if any
    if _SECTOR_DISCOVERY_STATE['tables'] is not None:
        return _SECTOR_DISCOVERY_STATE['tables']

    return []

# Exported reusable function alias
discover_sector_staging_tables = _discover_sector_staging_tables





def _load_sector_rotation_summary_from_sector_tables(force_refresh: bool = False) -> dict[str, dict[str, Any]]:

    cache_key = f'sector_rotation_summary:staging:{_SECTOR_ROTATION_CANONICAL_GROUPING_VERSION}'

    if not force_refresh:

        cached = _cache.get(cache_key)

        if isinstance(cached, dict):

            return cached



    source = _raw_sma_source()

    if not source:

        return {}

    table_name, close_col = source



    try:

        sector_tables = _discover_sector_staging_tables()

    except Exception:

        logger.exception('Failed loading sector tables for rotation summary fallback')

        return {}



    symbol_to_sector_code: dict[str, str] = {}

    sector_names: dict[str, str] = {}

    healthcare_excluded_symbols = _load_strict_sector_symbol_lookups('PHARMA')

    for item in sector_tables:

        code = str(item.get('sectorCode') or '').strip().upper()

        if not code:

            continue

        canonical_code = _canonical_sector_rotation_group_code(code) or code

        sector_names[canonical_code] = _resolve_display_sector_name(

            canonical_code,

            str(item.get('sectorName') or canonical_code).strip(),

        )

        symbols = _load_strict_sector_symbols(code) or []

        for symbol in symbols:

            normalized = _normalize_symbol_token(symbol)

            if canonical_code == 'HEALTHCARE' and normalized in healthcare_excluded_symbols:

                continue

            if normalized and normalized not in symbol_to_sector_code:

                symbol_to_sector_code[normalized] = canonical_code



    normalized_symbols = sorted(symbol_to_sector_code)

    symbol_variants = _symbol_variants(normalized_symbols)

    if not symbol_variants:

        return {}

    owned_symbol_counts: dict[str, int] = {}

    for code in symbol_to_sector_code.values():

        owned_symbol_counts[code] = owned_symbol_counts.get(code, 0) + 1

    data_backed_symbols: dict[str, set[str]] = {

        code: set()

        for code in sector_names

    }



    stats: dict[str, dict[str, Any]] = {

        code: {

            'sectorCode': code,

            'sectorName': sector_names.get(code, code),

            'totalSymbols': owned_symbol_counts.get(code, 0),

            'validRsiCount': 0,

            'rsi55Hits': 0,

            'rsi50Hits': 0,

            'sma20Hits': 0,

            'sma50Hits': 0,

            'sma100Hits': 0,

            'confirmedStocks': 0,

            'latestTradingDate': None,

        }

        for code in sector_names

    }



    chunk_size = 900

    conn = get_oracle_connection()

    try:

        for idx in range(0, len(symbol_variants), chunk_size):

            chunk = symbol_variants[idx:idx + chunk_size]

            binds: dict[str, Any] = {}

            placeholders: list[str] = []

            for jdx, symbol in enumerate(chunk):

                bind_name = f'rot_sym_{idx}_{jdx}'

                placeholders.append(f':{bind_name}')

                binds[bind_name] = symbol

            sql = f"""

WITH ranked AS (

    SELECT

        REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(t.symbol)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '') AS stock,

        t.trading_date AS trading_date,

        t.{close_col} AS close_val,

        ROW_NUMBER() OVER (

            PARTITION BY REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(t.symbol)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '')

            ORDER BY t.trading_date DESC

        ) AS rn_desc

    FROM {table_name} t

    WHERE t.symbol IN ({', '.join(placeholders)})

      AND t.trading_date IS NOT NULL

      AND t.{close_col} IS NOT NULL

),

history AS (

    SELECT *

    FROM ranked

    WHERE rn_desc <= 140

),

calc1 AS (

    SELECT

        h.*,

        LAG(h.close_val) OVER (PARTITION BY h.stock ORDER BY h.trading_date) AS prev_close,

        LAG(h.close_val, 55) OVER (PARTITION BY h.stock ORDER BY h.trading_date) AS close_lag55,

        AVG(h.close_val) OVER (PARTITION BY h.stock ORDER BY h.trading_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS sma20,

        AVG(h.close_val) OVER (PARTITION BY h.stock ORDER BY h.trading_date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS sma50,

        AVG(h.close_val) OVER (PARTITION BY h.stock ORDER BY h.trading_date ROWS BETWEEN 99 PRECEDING AND CURRENT ROW) AS sma100

    FROM history h

),

calc2 AS (

    SELECT

        c1.*,

        GREATEST(c1.close_val - c1.prev_close, 0) AS gain,

        GREATEST(c1.prev_close - c1.close_val, 0) AS loss

    FROM calc1 c1

),

calc3 AS (

    SELECT

        c2.*,

        AVG(c2.gain) OVER (PARTITION BY c2.stock ORDER BY c2.trading_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_gain14,

        AVG(c2.loss) OVER (PARTITION BY c2.stock ORDER BY c2.trading_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_loss14

    FROM calc2 c2

)

SELECT

    stock AS "stock",

    trading_date AS "tradingDate",

    close_val AS "closePrice",

    close_lag55 AS "closeLag55",

    sma20 AS "sma20",

    sma50 AS "sma50",

    sma100 AS "sma100",

    CASE

        WHEN avg_loss14 IS NULL THEN NULL

        WHEN avg_loss14 = 0 AND avg_gain14 = 0 THEN 50

        WHEN avg_loss14 = 0 THEN 100

        ELSE 100 - (100 / (1 + (avg_gain14 / NULLIF(avg_loss14, 0))))

    END AS "rsi14"

FROM calc3

WHERE rn_desc = 1

"""

            with conn.cursor() as cursor:

                cursor.arraysize = 1000

                cursor.execute(sql, binds)

                cols = [str(col[0]) for col in (cursor.description or [])]

                for raw in cursor.fetchall() or []:

                    row = {cols[pos]: _normalize(raw[pos]) for pos in range(len(cols))}

                    stock = _normalize_symbol_token(row.get('stock'))

                    if not stock:

                        continue

                    close_price = _to_float(row.get('closePrice'))

                    if close_price is None:

                        continue

                    trading_date = _coerce_date(row.get('tradingDate'))

                    rsi14 = _to_float(row.get('rsi14'))

                    sma20 = _to_float(row.get('sma20'))

                    sma50 = _to_float(row.get('sma50'))

                    sma100 = _to_float(row.get('sma100'))

                    code = symbol_to_sector_code.get(stock)

                    if code:

                        item = stats.setdefault(code, {'sectorCode': code, 'sectorName': sector_names.get(code, code)})
                        data_backed_symbols.setdefault(code, set()).add(stock)

                        latest_trading_date = _coerce_date(item.get('latestTradingDate'))

                        if trading_date is not None and (latest_trading_date is None or trading_date > latest_trading_date):

                            item['latestTradingDate'] = trading_date

                        if rsi14 is not None:

                            item['validRsiCount'] = _coerce_int(item.get('validRsiCount'), default=0) + 1

                            if rsi14 > 50:

                                item['rsi50Hits'] = _coerce_int(item.get('rsi50Hits'), default=0) + 1

                            if rsi14 > 55:

                                item['rsi55Hits'] = _coerce_int(item.get('rsi55Hits'), default=0) + 1

                        if sma20 is not None and close_price > sma20:

                            item['sma20Hits'] = _coerce_int(item.get('sma20Hits'), default=0) + 1

                        if sma50 is not None and close_price > sma50:

                            item['sma50Hits'] = _coerce_int(item.get('sma50Hits'), default=0) + 1

                        if sma100 is not None and close_price > sma100:

                            item['sma100Hits'] = _coerce_int(item.get('sma100Hits'), default=0) + 1

                        if all([

                            sma20 is not None and close_price > sma20,

                            sma50 is not None and close_price > sma50,

                            sma100 is not None and close_price > sma100,

                        ]):

                            item['confirmedStocks'] = _coerce_int(item.get('confirmedStocks'), default=0) + 1

    finally:

        conn.close()



    result: dict[str, dict[str, Any]] = {}

    for code, item in stats.items():

        total = _coerce_int(item.get('totalSymbols'), default=0)
        data_backed_total_stocks = len(data_backed_symbols.get(code) or ())

        if total <= 0:

            continue

        valid_rsi_count = _coerce_int(item.get('validRsiCount'), default=0)

        rsi55_hits = _coerce_int(item.get('rsi55Hits'), default=0)

        rsi50_hits = _coerce_int(item.get('rsi50Hits'), default=0)

        if valid_rsi_count > 0:

            rsi55_pct = round((rsi55_hits / valid_rsi_count) * 100, 2)

            rsi50_pct = round((rsi50_hits / valid_rsi_count) * 100, 2)

        else:

            rsi55_pct = 0.0

            rsi50_pct = 0.0

        if rsi55_hits > rsi50_hits or rsi55_pct > rsi50_pct:

            logger.warning(

                '[SECTOR_ROTATION_RSI_INVARIANT] sector=%s rsi55_pct=%.2f rsi50_pct=%.2f rsi55_hits=%s rsi50_hits=%s valid_rsi_count=%s effective_date=%s',

                code,

                rsi55_pct,

                rsi50_pct,

                rsi55_hits,

                rsi50_hits,

                valid_rsi_count,

                _coerce_date(item.get('latestTradingDate')),

            )

        sma20_pct = round((_coerce_int(item.get('sma20Hits'), default=0) / total) * 100, 2)

        sma50_pct = round((_coerce_int(item.get('sma50Hits'), default=0) / total) * 100, 2)

        sma100_pct = round((_coerce_int(item.get('sma100Hits'), default=0) / total) * 100, 2)

        breadth = round((0.20 * rsi55_pct + 0.10 * rsi50_pct + 0.15 * sma20_pct + 0.15 * sma50_pct + 0.10 * sma100_pct) / 100, 6)

        confirmed = _coerce_int(item.get('confirmedStocks'), default=0)

        ratio = confirmed / total if total else 0

        label = 'Strong' if ratio >= 0.65 else 'Moderate' if ratio >= 0.35 else 'Weak'

        result[code] = {

            'sectorCode': code,

            'sectorName': item.get('sectorName') or code,

            'totalStocks': total,

            'availableSymbols': data_backed_total_stocks,

            'totalSymbols': total,

            'rsi55Pct': rsi55_pct,

            'rsi50Pct': rsi50_pct,

            'sma20Pct': sma20_pct,

            'sma50Pct': sma50_pct,

            'sma100Pct': sma100_pct,

            'breadthComposite': breadth,

            'confirmedStocks': confirmed,

            'screenedStocks': total,

            'stockConfirmationScoreAvg': round(ratio, 6),

            'stockConfirmationLabel': label,

            'stockConfirmationScreening': f'{label} ({confirmed}/{total})',

        }

    _cache.set(cache_key, result)

    logger.info('[SECTOR_ROTATION_SUMMARY] sectors=%s source=staging_raw', len(result))

    return result





def _supplement_breadth_rows_with_sector_tables(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:

    raw_summary = _load_sector_rotation_summary_from_sector_tables()

    if not raw_summary:

        return [dict(row) for row in rows if isinstance(row, dict)]

    try:

        sector_tables = _discover_sector_staging_tables()

    except Exception:

        logger.exception('Failed sector table supplement for breadth response')

        return [dict(row) for row in rows if isinstance(row, dict)]



    covered_codes = {

        _canonical_sector_rotation_group_code(item.get('sectorCode')) or str(item.get('sectorCode') or '').strip().upper()

        for item in sector_tables

        if str(item.get('sectorCode') or '').strip()

    }

    missing_summary_codes = {code for code in covered_codes if code and code not in raw_summary}

    if missing_summary_codes:

        raw_summary = _load_sector_rotation_summary_from_sector_tables(force_refresh=True)



    existing_rows: list[dict[str, Any]] = []

    for row in rows:

        if not isinstance(row, dict):

            continue

        canonical_code = (

            _canonical_sector_rotation_group_code(row.get('sectorCode'))

            or _canonical_sector_rotation_group_code(row.get('sectorName'))

            or _canonical_sector_rotation_group_code(row.get('sector'))

        )

        row_code = str(row.get('sectorCode') or row.get('sector') or '').strip().upper()

        row_group = canonical_code or row_code

        if row_group in covered_codes:

            continue

        existing_rows.append(dict(row))



    existing_codes = {

        str(row.get('sectorCode') or '').strip().upper()

        for row in existing_rows

        if str(row.get('sectorCode') or '').strip()

    }

    as_of = None

    price_source = None

    price_source_trade_date = None

    for row in existing_rows:

        if as_of is None and row.get('asOfDate') is not None:

            as_of = row.get('asOfDate')

        if price_source is None and row.get('priceSource') is not None:

            price_source = row.get('priceSource')

        if price_source_trade_date is None and row.get('priceSourceTradeDate') is not None:

            price_source_trade_date = row.get('priceSourceTradeDate')

    if as_of is None:

        latest_raw = _latest_raw_trading_date()

        as_of = latest_raw.isoformat() if latest_raw is not None else None



    for item in sector_tables:

        raw_code = str(item.get('sectorCode') or '').strip().upper()

        code = _canonical_sector_rotation_group_code(raw_code) or raw_code

        if not code or code in existing_codes:

            continue

        summary = raw_summary.get(code, {}) if isinstance(raw_summary, dict) else {}

        if not summary:

            existing_codes.add(code)

            continue

        existing_codes.add(code)

        staging_stock_count = _coerce_int(item.get('stockCount'), default=0)
        summary_total_stocks = _coerce_int(summary.get('totalStocks'), default=0)
        summary_total_symbols = _coerce_int(summary.get('totalSymbols'), default=0)
        if code in _MERGED_SECTOR_SOURCE_CODES:
            display_total_stocks = max(summary_total_stocks, summary_total_symbols) or staging_stock_count
        else:
            display_total_stocks = max(staging_stock_count, summary_total_stocks, summary_total_symbols)

        existing_rows.append({

            'sectorCode': code,

            'sectorName': _resolve_display_sector_name(code, item.get('sectorName')),

            'indexCode': code,

            'tableName': _MERGED_SECTOR_TABLE_LABELS.get(code, str(item.get('tableName') or '').strip().upper()),

            'totalStocks': display_total_stocks,

            'availableSymbols': _coerce_int(
                summary.get('availableSymbols'),
                default=display_total_stocks,
            ),

            'totalSymbols': max(summary_total_symbols, display_total_stocks),

            'rsi55Pct': _to_float(summary.get('rsi55Pct')) if summary else 0,

            'rsi50Pct': _to_float(summary.get('rsi50Pct')) if summary else 0,

            'sma20Pct': _to_float(summary.get('sma20Pct')) if summary else 0,

            'sma50Pct': _to_float(summary.get('sma50Pct')) if summary else 0,

            'sma100Pct': _to_float(summary.get('sma100Pct')) if summary else 0,

            'asOfDate': as_of,

            'relativeMomentum': 0,

            'absoluteTrend': 0,

            'breadthComposite': _to_float(summary.get('breadthComposite')) if summary else 0,

            'mcapBreadth': 0,

            'ffmcBreadth': 0,

            'countBreadth': _to_float(summary.get('breadthComposite')) if summary else 0,

            'riskAdjustment': 0,

            'rotationScore': _to_float(summary.get('breadthComposite')) if summary else 0,

            'finalRotation': _to_float(summary.get('breadthComposite')) if summary else 0,

            'rankScore': 0,

            'stockConfirmationScreening': str(summary.get('stockConfirmationScreening') or 'Neutral / NA'),

            'stockConfirmationLabel': str(summary.get('stockConfirmationLabel') or 'Neutral'),

            'confirmedStocks': _coerce_int(summary.get('confirmedStocks'), default=0),

            'screenedStocks': max(_coerce_int(summary.get('screenedStocks'), default=0), display_total_stocks),

            'stockConfirmationScoreAvg': _to_float(summary.get('stockConfirmationScoreAvg')) if summary else 0,

            'finalRotationDelta5': None,

            'finalRotationDelta21': None,

            'rankChange5': None,

            'rankChange21': None,

            'priceSource': price_source,

            'priceSourceTradeDate': price_source_trade_date,

        })



    existing_rows.sort(key=lambda row: str(row.get('sectorName') or row.get('sectorCode') or ''))

    return existing_rows





def _resolve_sector_table(table_name: Any = None, sector_name: Any = None) -> dict[str, Any] | None:

    candidates = _discover_sector_staging_tables()

    by_table = {str(item.get('tableName') or '').upper(): item for item in candidates}

    token_table = _to_safe_oracle_name(table_name)

    if token_table and token_table in by_table:

        return by_table[token_table]

    if token_table == 'NSE_NIFTY500_HEALTHCARE_STAGING' and 'NSE_NIFTY_HEALTHCARE_STAGING' in by_table:

        logger.info(

            '[SECTOR_TABLE_COMPAT_FALLBACK] requested=%s resolved=%s',

            token_table,

            'NSE_NIFTY_HEALTHCARE_STAGING',

        )

        return by_table['NSE_NIFTY_HEALTHCARE_STAGING']

    token_name = str(sector_name or '').strip().upper()

    if not token_name:

        return None

    for item in candidates:

        code = str(item.get('sectorCode') or '').strip().upper()

        label = str(item.get('sectorName') or '').strip().upper()

        if token_name in {code, label}:

            return item

    return None





def _cap_bucket_view_exists() -> bool:

    cached = _cache.get(_CAP_VIEW_EXISTS_CACHE_KEY)

    if isinstance(cached, bool):

        return cached

    try:

        exists = _coerce_int(_query_scalar(SQL_VIEW_EXISTS, {'object_name': 'VW_SYMBOL_CAP_BUCKET'}, default=0), default=0) > 0

    except Exception:

        exists = False

    _cache.set(_CAP_VIEW_EXISTS_CACHE_KEY, exists)

    return exists





def _breadth_view_exists() -> bool:

    cached = _cache.get(_BREADTH_VIEW_EXISTS_CACHE_KEY)

    if isinstance(cached, bool):

        return cached



    exists = True

    conn = get_oracle_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute('SELECT 1 FROM vw_sector_breadth WHERE 1 = 0')

    except Exception:

        exists = False

    finally:

        conn.close()



    _cache.set(_BREADTH_VIEW_EXISTS_CACHE_KEY, exists)

    return exists





def _mcap_index_view_exists() -> bool:

    cached = _cache.get(_MCAP_INDEX_VIEW_EXISTS_CACHE_KEY)

    if isinstance(cached, bool):

        return cached



    object_name = str(_NSE_MCAP_INDEX_VIEW or '').strip().upper().split('.')[-1]

    try:

        exists = _coerce_int(_query_scalar(SQL_VIEW_EXISTS, {'object_name': object_name}, default=0), default=0) > 0

    except Exception:

        exists = False

    _cache.set(_MCAP_INDEX_VIEW_EXISTS_CACHE_KEY, exists)

    return exists





def _is_safe_sql_name(value: str, allow_dot: bool = True) -> bool:

    if not value:

        return False

    pattern = r'^[A-Z0-9_$.]+$' if allow_dot else r'^[A-Z0-9_$]+$'

    return re.match(pattern, value.upper()) is not None





def _resolve_raw_close_column(columns: set[str]) -> str | None:

    candidates = [

        'CLOSE_PRICE', 'CLOSE', 'ADJ_CLOSE', 'LTP',

        'LAST_PRICE', 'LAST_TRADED_PRICE', 'LASTTRADEPRICE',

        'CLOSING_PRICE', 'CLOSE_RATE', 'CLOSEVALUE', 'CLOSE_VAL',

        'CLOSEPRICE', 'CLOSEP', 'PREVIOUS_CLOSE',

    ]

    for col in candidates:

        if col in columns:

            return col

    for col in sorted(columns):

        if 'CLOSE' in col or 'LTP' in col or 'LAST' in col:

            return col

    return None





def _first_present_column(columns: set[str], candidates: list[str]) -> str | None:

    for col in candidates:

        token = str(col or '').strip().upper()

        if token and token in columns:

            return token

    return None





def _raw_sma_source() -> tuple[str, str] | None:

    cached = _cache.get(_RAW_SMA_SOURCE_CACHE_KEY)

    if isinstance(cached, dict):

        if not cached.get('available'):

            return None

        table = str(cached.get('table') or '').strip()

        close_col = str(cached.get('close_col') or '').strip()

        if table and close_col:

            return table, close_col

        return None



    schema = str(os.getenv('ORACLE_SCHEMA') or '').strip().upper()

    table = str(os.getenv('ORACLE_TABLE') or 'NSE_NIFTY500_DAILY_RAW_DATA_DEV').strip().upper()

    qualified = f'{schema}.{table}' if schema else table



    if not _is_safe_sql_name(qualified, allow_dot=True):

        _cache.set(_RAW_SMA_SOURCE_CACHE_KEY, {'available': False})

        return None



    conn = get_oracle_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(f'SELECT * FROM {qualified} WHERE ROWNUM = 0')

            cols = {str(col[0]).strip().upper() for col in (cursor.description or []) if col and col[0]}

    except Exception:

        _cache.set(_RAW_SMA_SOURCE_CACHE_KEY, {'available': False})

        return None

    finally:

        conn.close()



    if 'SYMBOL' not in cols or 'TRADING_DATE' not in cols:

        _cache.set(_RAW_SMA_SOURCE_CACHE_KEY, {'available': False})

        return None



    close_col = _resolve_raw_close_column(cols)

    if not close_col or not _is_safe_sql_name(close_col, allow_dot=False):

        _cache.set(_RAW_SMA_SOURCE_CACHE_KEY, {'available': False})

        return None



    payload = {'available': True, 'table': qualified, 'close_col': close_col}

    _cache.set(_RAW_SMA_SOURCE_CACHE_KEY, payload)

    return qualified, close_col





def _raw_extrema_source() -> tuple[str, str, str, str, str] | None:

    cached = _cache.get(_RAW_EXTREMA_SOURCE_CACHE_KEY)

    if isinstance(cached, dict):

        if not cached.get('available'):

            return None

        table = str(cached.get('table') or '').strip()

        symbol_col = str(cached.get('symbol_col') or '').strip()

        trade_col = str(cached.get('trade_col') or '').strip()

        high_col = str(cached.get('high_col') or '').strip()

        low_col = str(cached.get('low_col') or '').strip()

        if table and symbol_col and trade_col and high_col and low_col:

            return table, symbol_col, trade_col, high_col, low_col

        return None



    raw_source = _raw_sma_source()

    if raw_source is None:

        _cache.set(_RAW_EXTREMA_SOURCE_CACHE_KEY, {'available': False})

        return None

    table_name, _ = raw_source



    conn = get_oracle_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(f'SELECT * FROM {table_name} WHERE ROWNUM = 0')

            cols = {str(col[0]).strip().upper() for col in (cursor.description or []) if col and col[0]}

    except Exception:

        _cache.set(_RAW_EXTREMA_SOURCE_CACHE_KEY, {'available': False})

        return None

    finally:

        conn.close()



    symbol_col = _first_present_column(cols, ['SYMBOL', 'STOCK', 'TICKER'])

    trade_col = _first_present_column(cols, ['TRADING_DATE', 'TRADE_DATE', 'DATE'])

    high_col = _first_present_column(cols, ['HIGH_PRICE', 'HIGH', 'H', 'DAY_HIGH'])

    low_col = _first_present_column(cols, ['LOW_PRICE', 'LOW', 'L', 'DAY_LOW'])

    if not symbol_col or not trade_col or not high_col or not low_col:

        _cache.set(_RAW_EXTREMA_SOURCE_CACHE_KEY, {'available': False})

        return None



    if not _is_safe_sql_name(symbol_col, allow_dot=False):

        _cache.set(_RAW_EXTREMA_SOURCE_CACHE_KEY, {'available': False})

        return None

    if not _is_safe_sql_name(trade_col, allow_dot=False):

        _cache.set(_RAW_EXTREMA_SOURCE_CACHE_KEY, {'available': False})

        return None

    if not _is_safe_sql_name(high_col, allow_dot=False):

        _cache.set(_RAW_EXTREMA_SOURCE_CACHE_KEY, {'available': False})

        return None

    if not _is_safe_sql_name(low_col, allow_dot=False):

        _cache.set(_RAW_EXTREMA_SOURCE_CACHE_KEY, {'available': False})

        return None



    payload = {

        'available': True,

        'table': table_name,

        'symbol_col': symbol_col,

        'trade_col': trade_col,

        'high_col': high_col,

        'low_col': low_col,

    }

    _cache.set(_RAW_EXTREMA_SOURCE_CACHE_KEY, payload)

    return table_name, symbol_col, trade_col, high_col, low_col





def _snapshot_columns() -> set[str]:

    cached = _cache.get(_SNAPSHOT_COLUMNS_CACHE_KEY)

    if isinstance(cached, set):

        return cached



    columns: set[str] = set()

    try:

        conn = get_oracle_connection()

        try:

            with conn.cursor() as cursor:

                cursor.execute('SELECT * FROM mv_nse_sector_ui_snapshot WHERE 1 = 0')

                columns = {str(col[0]).strip().upper() for col in (cursor.description or []) if col and col[0]}

        finally:

            conn.close()

    except Exception:

        columns = set()



    if not columns:

        columns = {

            'SYMBOL',

            'SECTOR',

            'INDEX_CODE',

            'LTC_DATE',

            'CLOSE_PRICE',

            'ATH',

            'HIGH_52W',

            'LOW_52W',

            'EMA20',

            'EMA50',

            'EMA100',

            'EMA200',

            'EMA20_FLAG',

            'EMA50_FLAG',

            'EMA100_FLAG',

            'EMA200_FLAG',

            'RSI55_GT0',

            'RSI50_GT0',

            'SMA20',

            'SMA50',

            'SMA100',

        }

    _cache.set(_SNAPSHOT_COLUMNS_CACHE_KEY, columns)

    return columns





def _metric_expr(alias: str, metric_key: str, available_columns: set[str], use_breadth_fallback: bool) -> str:

    candidates = _SNAPSHOT_METRIC_CANDIDATES.get(metric_key, [])

    base_expr = 'NULL'

    for col in candidates:

        if col in available_columns:

            base_expr = f'{alias}.{col.lower()}'

            break

    fallback = _BREADTH_FALLBACK_COLUMN.get(metric_key)

    if fallback and use_breadth_fallback:

        return f'COALESCE({base_expr}, {fallback})'

    return base_expr





def _cap_bucket_from_index_sql(alias: str) -> str:

    upper_index = f'UPPER({alias}.index_code)'

    return (

        "CASE "

        f"WHEN {upper_index} LIKE '%NEXT50%' OR {upper_index} LIKE '%NEXT_50%' OR {upper_index} LIKE '%NEXT 50%' THEN 'LARGE' "

        f"WHEN {upper_index} LIKE '%SMALL%' THEN 'SMALL' "

        f"WHEN {upper_index} LIKE '%MID%' THEN 'MID' "

        f"WHEN {upper_index} LIKE '%LARGE%' THEN 'LARGE' "

        f"WHEN {upper_index} LIKE '%NIFTY50%' OR {upper_index} LIKE '%NIFTY_50%' OR {upper_index} LIKE '%NIFTY 50%' THEN 'LARGE' "

        f"WHEN {upper_index} LIKE '%NIFTY100%' OR {upper_index} LIKE '%NIFTY_100%' OR {upper_index} LIKE '%NIFTY 100%' THEN 'LARGE' "

        "ELSE NULL END"

    )





def _normalized_index_sql(expr: str) -> str:

    return f"REPLACE(REPLACE(UPPER(TRIM({expr})), '_', ''), ' ', '')"





def _build_popup_base_cte(

    candidates: list[str],

    symbol_filter: list[str] | None,

    include_cap_bucket: bool,

    include_breadth_fallback: bool,

    include_raw_sma_fallback: bool,

    raw_sma_source: tuple[str, str] | None,

) -> tuple[str, dict[str, Any]]:

    sector_clause, sector_binds = _build_sector_binds(candidates)

    symbol_clause = ''

    symbol_binds: dict[str, Any] = {}

    if symbol_filter:

        filtered_symbols = [str(item).strip().upper() for item in symbol_filter if str(item or '').strip()]

        if filtered_symbols:

            symbol_placeholders, symbol_binds = _build_symbol_binds(filtered_symbols)

            symbol_clause = f'AND UPPER(TRIM(snap.symbol)) IN ({symbol_placeholders})'

    derived_cap_expr = _cap_bucket_from_index_sql('snap')

    normalized_index_expr = _normalized_index_sql('snap.index_code')

    available_columns = _snapshot_columns()

    rsi55_expr = _metric_expr('snap', 'rsi55_gt0', available_columns, include_breadth_fallback)

    rsi50_expr = _metric_expr('snap', 'rsi50_gt0', available_columns, include_breadth_fallback)

    snap_sma20_expr = _metric_expr('snap', 'sma20', available_columns, include_breadth_fallback)

    snap_sma50_expr = _metric_expr('snap', 'sma50', available_columns, include_breadth_fallback)

    snap_sma100_expr = _metric_expr('snap', 'sma100', available_columns, include_breadth_fallback)

    if include_cap_bucket:

        cap_join = 'LEFT JOIN vw_symbol_cap_bucket cap ON cap.symbol = UPPER(TRIM(snap.symbol))'

        cap_expr = f'COALESCE(cap.cap_bucket, {derived_cap_expr})'

    else:

        cap_join = ''

        cap_expr = derived_cap_expr

    cap_select = f'{cap_expr} AS cap_bucket'

    cap_filter = f"AND (:cap_bucket = 'ALL' OR {cap_expr} = :cap_bucket)"



    breadth_join = 'LEFT JOIN vw_sector_breadth breadth ON breadth.sector_code = snap.sector' if include_breadth_fallback else ''



    raw_sma_cte = ''

    raw_sma_join = ''

    base_sma20_expr = 'sb.sma20'

    base_sma50_expr = 'sb.sma50'

    base_sma100_expr = 'sb.sma100'

    if include_raw_sma_fallback and raw_sma_source:

        raw_table, raw_close_col = raw_sma_source

        raw_sma_cte = f"""

, raw_sma AS (

    SELECT

        x.symbol,

        x.sma20,

        x.sma50,

        x.sma100

    FROM (

        SELECT

            y.symbol,

            AVG(y.close_val) OVER (

                PARTITION BY y.symbol

                ORDER BY y.trading_date

                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW

            ) AS sma20,

            AVG(y.close_val) OVER (

                PARTITION BY y.symbol

                ORDER BY y.trading_date

                ROWS BETWEEN 49 PRECEDING AND CURRENT ROW

            ) AS sma50,

            AVG(y.close_val) OVER (

                PARTITION BY y.symbol

                ORDER BY y.trading_date

                ROWS BETWEEN 99 PRECEDING AND CURRENT ROW

            ) AS sma100,

            ROW_NUMBER() OVER (

                PARTITION BY y.symbol

                ORDER BY y.trading_date DESC

            ) AS rn

        FROM (

            SELECT

                z.symbol,

                z.trading_date,

                z.close_val

            FROM (

                SELECT

                    r.symbol AS symbol,

                    r.trading_date AS trading_date,

                    r.{raw_close_col} AS close_val,

                    ROW_NUMBER() OVER (

                        PARTITION BY r.symbol

                        ORDER BY r.trading_date DESC

                    ) AS recent_rn

                FROM {raw_table} r

                JOIN (SELECT DISTINCT symbol FROM snap_base) sb2

                  ON r.symbol = sb2.symbol

                WHERE r.{raw_close_col} IS NOT NULL

                  AND r.trading_date IS NOT NULL

            ) z

            WHERE z.recent_rn <= 130

        ) y

    ) x

    WHERE x.rn = 1

)

"""

        raw_sma_join = 'LEFT JOIN raw_sma rs ON rs.symbol = sb.symbol'

        base_sma20_expr = 'COALESCE(sb.sma20, rs.sma20)'

        base_sma50_expr = 'COALESCE(sb.sma50, rs.sma50)'

        base_sma100_expr = 'COALESCE(sb.sma100, rs.sma100)'



    base_cte = f"""

WITH snap_base AS (

    SELECT DISTINCT

        snap.symbol,

        snap.sector,

        snap.index_code,

        snap.ltc_date,

        snap.close_price,

        {rsi55_expr} AS rsi55_gt0,

        {rsi50_expr} AS rsi50_gt0,

        {snap_sma20_expr} AS sma20,

        {snap_sma50_expr} AS sma50,

        {snap_sma100_expr} AS sma100,

        {cap_select}

    FROM mv_nse_sector_ui_snapshot snap

    {breadth_join}

    {cap_join}

    WHERE snap.sector IN ({sector_clause})

      {symbol_clause}

      {cap_filter}

      AND (

        :index_code IS NULL

        OR {normalized_index_expr} = REPLACE(REPLACE(UPPER(TRIM(:index_code)), '_', ''), ' ', '')

      )

      AND (:search_term IS NULL OR UPPER(snap.symbol) LIKE :search_term ESCAPE '\\')

)

{raw_sma_cte}

, base_rows AS (

    SELECT DISTINCT

        sb.symbol,

        sb.sector,

        sb.index_code,

        sb.ltc_date,

        sb.close_price,

        sb.rsi55_gt0,

        sb.rsi50_gt0,

        {base_sma20_expr} AS sma20,

        {base_sma50_expr} AS sma50,

        {base_sma100_expr} AS sma100,

        sb.cap_bucket

    FROM snap_base sb

    {raw_sma_join}

)

"""

    merged_binds = dict(sector_binds)

    merged_binds.update(symbol_binds)

    return base_cte, merged_binds





def _build_count_sql(base_cte: str) -> str:

    return f"""

{base_cte}

SELECT COUNT(1) AS "totalCount"

FROM base_rows

"""





def _build_index_options_sql(base_cte: str) -> str:

    return f"""

{base_cte}

SELECT DISTINCT

    TRIM(UPPER(b.index_code)) AS "indexCode"

FROM base_rows b

WHERE b.index_code IS NOT NULL

ORDER BY TRIM(UPPER(b.index_code))

"""





def _build_page_sql(base_cte: str, sort_key: str, sort_dir: str) -> str:

    sort_expr = _SORT_COLUMN_MAP.get(sort_key, _SORT_COLUMN_MAP['CLOSE_PRICE'])

    if sort_key == 'SYMBOL':

        order_clause = f'{sort_expr} {sort_dir}'

    else:

        order_clause = f'{sort_expr} {sort_dir} NULLS LAST, UPPER(b.symbol) ASC'



    return f"""

{base_cte}

, numbered AS (

    SELECT

        b.symbol,

        b.sector,

        b.index_code,

        b.ltc_date,

        b.close_price,

        b.rsi55_gt0,

        b.rsi50_gt0,

        b.sma20,

        b.sma50,

        b.sma100,

        b.cap_bucket,

        ROW_NUMBER() OVER (ORDER BY {order_clause}) AS rn

    FROM base_rows b

)

SELECT

    n.rn AS "sNo",

    n.symbol AS "symbol",

    n.sector AS "sector",

    n.index_code AS "indexCode",

    n.ltc_date AS "ltcDate",

    n.close_price AS "closePrice",

    n.close_price AS "price",

    n.close_price AS "close_price",

    n.rsi55_gt0 AS "rsi55Gt0",

    n.rsi55_gt0 AS "rsi55Pct",

    n.rsi50_gt0 AS "rsi50Gt0",

    n.rsi50_gt0 AS "rsi50Pct",

    n.sma20 AS "sma20",

    n.sma20 AS "sma20Pct",

    n.sma50 AS "sma50",

    n.sma50 AS "sma50Pct",

    n.sma100 AS "sma100",

    n.sma100 AS "sma100Pct",

    CAST(NULL AS NUMBER) AS "volume",

    n.cap_bucket AS "capBucket"

FROM numbered n

WHERE n.rn BETWEEN :row_start AND :row_end

ORDER BY n.rn

"""





def _query_popup_page(

    *,

    candidates: list[str],

    symbol_filter: list[str] | None,

    page: int,

    page_size: int,

    sort_key: str,

    sort_dir: str,

    cap_bucket: str,

    index_code: str,

    search_bind: str | None,

) -> tuple[int, int, int, list[dict[str, Any]], list[str]]:

    def _run(

        include_cap_bucket: bool,

        include_breadth_fallback: bool,

        include_raw_sma_fallback: bool,

    ) -> tuple[int, int, int, list[dict[str, Any]], list[str]]:

        raw_source = _raw_sma_source() if include_raw_sma_fallback else None

        if include_raw_sma_fallback and raw_source is None:

            include_raw_sma_fallback = False

        base_cte, sector_binds = _build_popup_base_cte(

            candidates,

            symbol_filter,

            include_cap_bucket,

            include_breadth_fallback,

            include_raw_sma_fallback,

            raw_source,

        )

        binds = dict(sector_binds)

        binds['search_term'] = search_bind

        binds['index_code'] = None if index_code == 'ALL' else index_code

        binds['cap_bucket'] = cap_bucket



        index_binds = dict(binds)

        index_binds['search_term'] = None

        index_binds['index_code'] = None

        index_options_sql = _build_index_options_sql(base_cte)

        index_rows = _query_rows(index_options_sql, index_binds)

        index_options = [str(row.get('indexCode') or '').strip().upper() for row in index_rows if row.get('indexCode')]



        count_sql = _build_count_sql(base_cte)

        total_count = _coerce_int(_query_scalar(count_sql, binds, default=0), default=0)

        if total_count <= 0:

            return 0, 0, 1, [], index_options



        total_pages = int(math.ceil(total_count / float(page_size)))

        effective_page = min(max(page, 1), max(total_pages, 1))



        row_start = ((effective_page - 1) * page_size) + 1

        row_end = row_start + page_size - 1



        page_sql = _build_page_sql(base_cte, sort_key, sort_dir)

        page_binds = dict(binds)

        page_binds.update({'row_start': row_start, 'row_end': row_end})

        rows = _query_rows(page_sql, page_binds)

        return total_count, total_pages, effective_page, rows, index_options



    has_cap_view = _cap_bucket_view_exists()

    has_breadth_view = _breadth_view_exists()

    has_raw_sma = _raw_sma_source() is not None



    attempts: list[tuple[bool, bool, bool]] = []

    for combo in [

        (has_cap_view, has_breadth_view, has_raw_sma),

        (has_cap_view, has_breadth_view, False),

        (has_cap_view, False, has_raw_sma),

        (False, has_breadth_view, has_raw_sma),

        (has_cap_view, False, False),

        (False, has_breadth_view, False),

        (False, False, has_raw_sma),

        (False, False, False),

    ]:

        if combo not in attempts:

            attempts.append(combo)



    last_error: Exception | None = None

    for include_cap, include_breadth, include_raw_sma in attempts:

        try:

            return _run(include_cap, include_breadth, include_raw_sma)

        except Exception as exc:

            last_error = exc

            if include_cap:

                _cache.set(_CAP_VIEW_EXISTS_CACHE_KEY, False)

            if include_breadth:

                _cache.set(_BREADTH_VIEW_EXISTS_CACHE_KEY, False)

            if include_raw_sma:

                _cache.set(_RAW_SMA_SOURCE_CACHE_KEY, {'available': False})

            logger.exception(

                'Popup query attempt failed (cap_join=%s breadth_fallback=%s raw_sma_fallback=%s)',

                include_cap,

                include_breadth,

                include_raw_sma,

            )

            continue



    if last_error is not None:

        raise last_error

    return 0, 0, 1, [], []





def _empty_popup_payload(

    sector: str,

    page: int,

    page_size: int,

    selected_index: str = 'ALL',

) -> dict[str, Any]:

    return {

        'sector': sector,

        'page': page,

        'pageSize': page_size,

        'totalCount': 0,

        'totalPages': 0,

        'selectedIndex': selected_index,

        'indexOptions': [],

        'rows': [],

    }





def _popup_cache_key(

    *,

    sector: str,

    candidates: list[str],

    page: int,

    page_size: int,

    sort_key: str,

    sort_dir: str,

    cap_bucket: str,

    index_code: str,

    search_token: str,

) -> str:

    candidate_token = ','.join(candidates)

    return f'popup:v6:{sector}:{candidate_token}:{page}:{page_size}:{sort_key}:{sort_dir}:{cap_bucket}:{index_code}:{search_token}'





def _load_sector_stocks_payload(

    *,

    sector_code: str,

    page: int,

    page_size: int,

    sort_key: str,

    sort_dir: str,

    cap_bucket: str,

    index_code: str,

    search_text: str,

    allow_large_page: bool = False,

    force_refresh: bool = False,

) -> dict[str, Any]:

    normalized_sector = (sector_code or '').strip().upper().replace('-', '_')

    if not normalized_sector:

        return _empty_popup_payload('', 1, _DEFAULT_PAGE_SIZE)



    normalized_page = _parse_positive_int(page, 1, minimum=1, maximum=10_000)

    if allow_large_page:

        normalized_page_size = _parse_positive_int(page_size, _DEFAULT_PAGE_SIZE, minimum=1, maximum=_MAX_LEGACY_PAGE_SIZE)

    else:

        normalized_page_size = _normalize_page_size(page_size)

    normalized_sort = _normalize_sort_key(sort_key)

    normalized_dir = _normalize_sort_dir(sort_dir)

    normalized_cap = _normalize_cap_bucket(cap_bucket)

    normalized_index = _normalize_index_code(index_code)

    normalized_search_token = _normalize_search_token(search_text)

    normalized_search_bind = _normalize_search_bind(normalized_search_token)



    candidates = _resolve_sector_candidates(normalized_sector)

    if not candidates:

        return _empty_popup_payload(normalized_sector, normalized_page, normalized_page_size)

    strict_symbols = _load_strict_sector_symbols(normalized_sector)



    cache_key = _popup_cache_key(

        sector=normalized_sector,

        candidates=candidates,

        page=normalized_page,

        page_size=normalized_page_size,

        sort_key=normalized_sort,

        sort_dir=normalized_dir,

        cap_bucket=normalized_cap,

        index_code=normalized_index,

        search_token=normalized_search_token,

    )

    if not force_refresh:

        cached = _popup_cache.get(cache_key)

        if isinstance(cached, dict):

            cached_source = str(cached.get('athSource') or '').strip().upper()

            if cached_source == _ATH_SOURCE_TABLE:

                return cached

            log_stale_snapshot_warning(endpoint='/api/sector/sector-wise', source='cache')



    total_count, total_pages, effective_page, rows, index_options = _query_popup_page(

        candidates=candidates,

        symbol_filter=strict_symbols,

        page=normalized_page,

        page_size=normalized_page_size,

        sort_key=normalized_sort,

        sort_dir=normalized_dir,

        cap_bucket=normalized_cap,

        index_code=normalized_index,

        search_bind=normalized_search_bind,

    )

    if total_count <= 0 and strict_symbols:

        fallback_rows = _build_strict_symbol_fallback_rows(

            strict_symbols,

            search_token=normalized_search_token,

        )

        fallback_rows.sort(key=lambda row: str(row.get('symbol') or '').upper())

        if normalized_sort in {'CLOSE_PRICE', 'PRICE'}:

            fallback_rows.sort(

                key=lambda row: (_to_float(row.get('price')) is None, _to_float(row.get('price')) or 0.0),

                reverse=(normalized_dir == 'DESC'),

            )

        elif normalized_sort == 'SYMBOL':

            fallback_rows.sort(

                key=lambda row: str(row.get('symbol') or '').upper(),

                reverse=(normalized_dir == 'DESC'),

            )

        total_count = len(fallback_rows)

        total_pages = int(math.ceil(total_count / float(normalized_page_size))) if total_count > 0 else 0

        effective_page = min(max(normalized_page, 1), max(total_pages, 1)) if total_pages > 0 else 1

        row_start = (effective_page - 1) * normalized_page_size

        row_end = row_start + normalized_page_size

        page_rows = fallback_rows[row_start:row_end]

        rows = []

        for idx, row in enumerate(page_rows, start=row_start + 1):

            rows.append({

                'sNo': idx,

                'symbol': row.get('symbol'),

                'sector': normalized_sector,

                'indexCode': normalized_sector,

                'ltcDate': row.get('ltcDate'),

                'closePrice': row.get('price'),

                'price': row.get('price'),

                'close_price': row.get('price'),

                'rsi55Gt0': None,

                'rsi55Pct': None,

                'rsi50Gt0': None,

                'rsi50Pct': None,

                'sma20': None,

                'sma20Pct': None,

                'sma50': None,

                'sma50Pct': None,

                'sma100': None,

                'sma100Pct': None,

                'volume': None,

                'capBucket': None,

            })

        index_options = []



    row_symbols = sorted({

        str((row or {}).get('symbol') or (row or {}).get('stock') or '').strip().upper()

        for row in rows

        if isinstance(row, dict)

    })

    row_symbols = [symbol for symbol in row_symbols if symbol]

    if row_symbols:

        latest_trade_map = _load_sector_wise_raw_latest_trade_rows(row_symbols, datetime.utcnow().date())

        for row in rows:

            if not isinstance(row, dict):

                continue

            stock = str(row.get('symbol') or row.get('stock') or '').strip().upper()

            if not stock:

                continue

            latest_trade = latest_trade_map.get(stock) if isinstance(latest_trade_map, dict) else None

            latest_raw_date = _coerce_date((latest_trade or {}).get('latestDate')) if isinstance(latest_trade, dict) else None

            latest_raw_close = _to_float((latest_trade or {}).get('latestClose')) if isinstance(latest_trade, dict) else None

            if latest_raw_date is None and latest_raw_close is None:

                continue

            current_ltc_date = _coerce_date(row.get('ltcDate'))

            if latest_raw_date is not None and (current_ltc_date is None or latest_raw_date > current_ltc_date):

                row['ltcDate'] = latest_raw_date.isoformat()

                if latest_raw_close is not None:

                    row['closePrice'] = latest_raw_close

                    row['price'] = latest_raw_close

                    row['close_price'] = latest_raw_close

            elif latest_raw_close is not None:

                if _to_float(row.get('price')) is None:

                    row['price'] = latest_raw_close

                if _to_float(row.get('closePrice')) is None:

                    row['closePrice'] = latest_raw_close

                if _to_float(row.get('close_price')) is None:

                    row['close_price'] = latest_raw_close



    if normalized_index != 'ALL':

        selected_token = _normalize_index_token(normalized_index)

        option_by_token = {_normalize_index_token(option): option for option in index_options}

        if selected_token in option_by_token:

            normalized_index = option_by_token[selected_token]

        else:

            normalized_index = 'ALL'



    payload = {

        'sector': normalized_sector,

        'page': effective_page,

        'pageSize': normalized_page_size,

        'totalCount': total_count,

        'totalPages': total_pages,

        'selectedIndex': normalized_index,

        'indexOptions': index_options,

        'rows': rows,

    }

    _popup_cache.set(cache_key, payload)

    return payload





def _to_float(value: Any) -> float | None:

    if value is None:

        return None

    if isinstance(value, Decimal):

        return float(value)

    try:

        return float(value)

    except Exception:

        return None





def _normalize_cap_index_value(value: Any, rank_value: Any = None) -> str:

    token = str(value or '').strip().upper()

    if token in {'LARGE', 'MID', 'SMALL'}:

        return token

    rank = _coerce_int(rank_value, default=0)

    if 1 <= rank <= 100:

        return 'LARGE'

    if 101 <= rank <= 250:

        return 'MID'

    if rank > 250:

        return 'SMALL'

    return '-'





def _load_sector_wise_latest_index_map(symbols: list[str]) -> tuple[dict[str, str], dict[str, int], str]:

    normalized_symbols = sorted({

        _normalize_index_lookup_symbol(symbol) for symbol in symbols if _normalize_index_lookup_symbol(symbol)

    })

    if not normalized_symbols:

        return {}, {}, 'none'



    chunk_size = 800

    index_map: dict[str, str] = {}

    mcap_rank_map: dict[str, int] = {}

    conn = get_oracle_connection()

    try:

        if _mcap_index_view_exists():

            normalized_symbol_expr = _normalized_symbol_expr('v.symbol')

            try:

                for idx in range(0, len(normalized_symbols), chunk_size):

                    chunk = normalized_symbols[idx:idx + chunk_size]

                    binds: dict[str, Any] = {}

                    placeholders: list[str] = []

                    for jdx, symbol in enumerate(chunk):

                        bind_name = f'idx_sym_{idx}_{jdx}'

                        placeholders.append(f':{bind_name}')

                        binds[bind_name] = symbol

                    sql = f"""

SELECT

    q.stock AS "stock",

    q.index_category AS "indexCategory",

    q.mcap_rank AS "mcapRank"

FROM (

    SELECT

        {normalized_symbol_expr} AS stock,

        UPPER(TRIM(v.index_category)) AS index_category,

        v.mcap_rank AS mcap_rank,

        ROW_NUMBER() OVER (

            PARTITION BY {normalized_symbol_expr}

            ORDER BY v.mcap_rank ASC NULLS LAST

        ) AS rn

    FROM {_NSE_MCAP_INDEX_VIEW} v

    WHERE {normalized_symbol_expr} IN ({', '.join(placeholders)})

) q

WHERE q.rn = 1

"""

                    with conn.cursor() as cursor:

                        cursor.arraysize = 500

                        cursor.execute(sql, binds)

                        cols = [str(col[0]) for col in (cursor.description or [])]

                        for raw in cursor.fetchall() or []:

                            row = {cols[pos]: _normalize(raw[pos]) for pos in range(len(cols))}

                            stock = _normalize_index_lookup_symbol(row.get('stock'))

                            if stock:

                                rank_value = _coerce_int(row.get('mcapRank'), default=0)

                                index_map[stock] = _normalize_cap_index_value(row.get('indexCategory'), rank_value)

                                if rank_value > 0:

                                    mcap_rank_map[stock] = rank_value

                return index_map, mcap_rank_map, _NSE_MCAP_INDEX_VIEW

            except Exception:

                _cache.set(_MCAP_INDEX_VIEW_EXISTS_CACHE_KEY, False)

                logger.exception('Failed loading index category from %s; fallback to %s', _NSE_MCAP_INDEX_VIEW, _NSE_MCAP_HIST_TABLE)



        index_map = {}

        mcap_rank_map = {}

        normalized_symbol_expr = _normalized_symbol_expr('z.symbol')

        for idx in range(0, len(normalized_symbols), chunk_size):

            chunk = normalized_symbols[idx:idx + chunk_size]

            binds = {}

            placeholders = []

            for jdx, symbol in enumerate(chunk):

                bind_name = f'mcap_sym_{idx}_{jdx}'

                placeholders.append(f':{bind_name}')

                binds[bind_name] = symbol

            sql = f"""

SELECT

    q.stock AS "stock",

    q.mcap_rank AS "mcapRank"

FROM (

    SELECT

        {normalized_symbol_expr} AS stock,

        ROW_NUMBER() OVER (

            ORDER BY z.total_mcap_cr DESC NULLS LAST, {normalized_symbol_expr} ASC

        ) AS mcap_rank

    FROM (

        SELECT

            t.symbol,

            MAX(t.total_mcap_cr) KEEP (DENSE_RANK LAST ORDER BY t.trade_date, t.fetch_ts) AS total_mcap_cr

        FROM {_NSE_MCAP_HIST_TABLE} t

        WHERE t.trade_date = (

            SELECT MAX(trade_date) FROM {_NSE_MCAP_HIST_TABLE} WHERE total_mcap_cr IS NOT NULL

        )

          AND t.total_mcap_cr IS NOT NULL

        GROUP BY t.symbol

    ) z

) q

WHERE q.stock IN ({', '.join(placeholders)})

"""

            with conn.cursor() as cursor:

                cursor.arraysize = 500

                cursor.execute(sql, binds)

                cols = [str(col[0]) for col in (cursor.description or [])]

                for raw in cursor.fetchall() or []:

                    row = {cols[pos]: _normalize(raw[pos]) for pos in range(len(cols))}

                    stock = _normalize_index_lookup_symbol(row.get('stock'))

                    if stock:

                        rank_value = _coerce_int(row.get('mcapRank'), default=0)

                        index_map[stock] = _normalize_cap_index_value(None, rank_value)

                        if rank_value > 0:

                            mcap_rank_map[stock] = rank_value

        return index_map, mcap_rank_map, _NSE_MCAP_HIST_TABLE

    finally:

        conn.close()





_MCAP_RANK_RESPONSE_KEYS = (

    'mcapRank',

    'mcap_rank',

    'MCAP_RANK',

    'MCAPRank',

    'market_cap_rank',

    'MARKET_CAP_RANK',

    'rank',

    'RANK',

    'MCAP_RANKING',

    'mcapRanking',

    'mcap_ranking',

)





def _row_has_mcap_rank(row: dict[str, Any]) -> bool:

    return any(_coerce_int(row.get(key), default=0) > 0 for key in _MCAP_RANK_RESPONSE_KEYS)





def _apply_mcap_rank_aliases(row: dict[str, Any], rank_value: int) -> None:

    row['mcapRank'] = rank_value

    row['mcap_rank'] = rank_value

    row['MCAP_RANK'] = rank_value

    row['MCAPRank'] = rank_value

    row['market_cap_rank'] = rank_value

    row['MARKET_CAP_RANK'] = rank_value

    row['rank'] = rank_value

    row['RANK'] = rank_value

    row['MCAP_RANKING'] = rank_value

    row['mcapRanking'] = rank_value

    row['mcap_ranking'] = rank_value





def _backfill_sector_wise_mcap_ranks(rows: list[dict[str, Any]]) -> int:

    symbols = [

        str(row.get('stock') or row.get('symbol') or '').strip().upper()

        for row in rows

        if isinstance(row, dict)

        and not _row_has_mcap_rank(row)

        and str(row.get('stock') or row.get('symbol') or '').strip()

    ]

    if not symbols:

        return 0



    _index_map, mcap_rank_map, index_source = _load_sector_wise_latest_index_map(symbols)

    backfilled = 0

    for row in rows:

        if not isinstance(row, dict) or _row_has_mcap_rank(row):

            continue

        lookup_symbol = _normalize_index_lookup_symbol(row.get('stock') or row.get('symbol'))

        rank_value = _coerce_int(mcap_rank_map.get(lookup_symbol) if lookup_symbol else None, default=0)

        if rank_value > 0:

            _apply_mcap_rank_aliases(row, rank_value)

            backfilled += 1

    if backfilled:

        logger.info('[SECTOR_MCAP_RANK_BACKFILL] source=%s rowsMatched=%s', index_source, backfilled)

    return backfilled





def _build_strict_symbol_fallback_rows(

    symbols: list[str],

    *,

    search_token: str = '',

) -> list[dict[str, Any]]:

    scoped_map: dict[str, str] = {}

    for item in symbols:

        display_symbol = str(item or '').strip().upper()

        if not display_symbol:

            continue

        display_symbol = 'LTM' if display_symbol == 'LTIM' else display_symbol

        lookup_symbol = _normalize_index_lookup_symbol(display_symbol) or _normalize_symbol_token(display_symbol)

        if lookup_symbol and lookup_symbol not in scoped_map:

            scoped_map[lookup_symbol] = display_symbol

    scoped = sorted(scoped_map.values())

    if search_token:

        token = str(search_token).strip().upper()

        scoped = [sym for sym in scoped if token in sym or token in _normalize_symbol_token(sym)]

    if not scoped:

        return []



    as_of = datetime.utcnow().date()

    latest_trade_started_at = time.perf_counter()

    latest_trade_map = _load_sector_wise_raw_latest_trade_rows(scoped, as_of)

    latest_trade_ms = int((time.perf_counter() - latest_trade_started_at) * 1000)

    extrema_started_at = time.perf_counter()

    extrema_map = _load_sector_wise_raw_extrema(scoped, as_of)

    extrema_ms = int((time.perf_counter() - extrema_started_at) * 1000)

    ema_started_at = time.perf_counter()

    ema_map = _load_sector_wise_raw_ema(scoped, as_of)

    ema_ms = int((time.perf_counter() - ema_started_at) * 1000)

    total_mcap_started_at = time.perf_counter()

    total_mcap_map = _load_sector_wise_latest_total_mcap(scoped)

    total_mcap_ms = int((time.perf_counter() - total_mcap_started_at) * 1000)

    index_started_at = time.perf_counter()

    index_map, mcap_rank_map, index_source = _load_sector_wise_latest_index_map(scoped)

    index_ms = int((time.perf_counter() - index_started_at) * 1000)

    logger.info('[SECTOR_INDEX_JOIN] source=%s rowsMatched=%s fallbackRows=%s', index_source, len(index_map), len(scoped))

    logger.info(

        '[SECTOR_RAW_FALLBACK_TIMING] latestTradeMs=%s extremaMs=%s emaMs=%s totalMcapMs=%s indexMs=%s rows=%s',

        latest_trade_ms,

        extrema_ms,

        ema_ms,

        total_mcap_ms,

        index_ms,

        len(scoped),

    )



    rows: list[dict[str, Any]] = []

    missing_index_symbols_logged: set[tuple[str, str]] = set()

    for sym in scoped:

        sym_lookup = _normalize_symbol_token(sym)

        latest_trade = latest_trade_map.get(sym_lookup) if isinstance(latest_trade_map, dict) else None

        extrema = (extrema_map.get(sym_lookup) or {}) if isinstance(extrema_map, dict) else {}

        ema = (ema_map.get(sym_lookup) or {}) if isinstance(ema_map, dict) else {}

        total_mcap = _to_float(total_mcap_map.get(sym_lookup)) if isinstance(total_mcap_map, dict) else None

        index_lookup_symbol = _normalize_index_lookup_symbol(sym)

        index_value = _normalize_cap_index_value(index_map.get(index_lookup_symbol) if index_lookup_symbol else None)

        mcap_rank_value = _coerce_int(mcap_rank_map.get(index_lookup_symbol) if index_lookup_symbol else None, default=0)

        mcap_rank = mcap_rank_value if mcap_rank_value > 0 else None

        if sym in _INDEX_SYMBOL_EXCLUDE_SET:

            index_value = '-'

        if index_value == '-' and sym not in _INDEX_SYMBOL_EXCLUDE_SET:

            log_key = (sym, index_lookup_symbol)

            if log_key not in missing_index_symbols_logged:

                missing_index_symbols_logged.add(log_key)

                logger.info(

                    '[SECTOR_INDEX_MISSING] symbol=%s normalized_symbol=%s source=%s fallback=%s',

                    sym,

                    index_lookup_symbol or '-',

                    index_source,

                    index_value,

                )

        price = _to_float((latest_trade or {}).get('latestClose')) if isinstance(latest_trade, dict) else None

        latest_date = _coerce_date((latest_trade or {}).get('latestDate')) if isinstance(latest_trade, dict) else None

        ath = _to_float(extrema.get('ath'))

        high52w = _to_float(extrema.get('high52w'))

        low52w = _to_float(extrema.get('low52w'))

        ema20 = _to_float(ema.get('ema20'))

        ema50 = _to_float(ema.get('ema50'))

        ema100 = _to_float(ema.get('ema100'))

        ema200 = _to_float(ema.get('ema200'))

        ema20_flag = _compute_ema_flag(price, ema20)

        ema50_flag = _compute_ema_flag(price, ema50)

        ema100_flag = _compute_ema_flag(price, ema100)

        ema200_flag = _compute_ema_flag(price, ema200)

        gap_pct = _compute_gap_pct(price, ath)

        trend_decision = calculate_sector_stock_trend(

            sector_name='',

            symbol=sym,

            price=price,

            ath=ath,

            high52w=high52w,

            low52w=low52w,

            gap_pct=gap_pct,

            ema20_flag=ema20_flag,

            ema50_flag=ema50_flag,

            ema100_flag=ema100_flag,

            ema200_flag=ema200_flag,

            support_price=None,

            resistance_price=None,

            sr_source='NONE',

            sr_trend_direction=None,

        )

        trend_direction = _normalize_sector_trend(trend_decision.get('trend'))

        trend_sort_value = _to_float(trend_decision.get('trendSort'))

        trend_sort = int(trend_sort_value) if trend_sort_value is not None else _trend_sort_rank(trend_direction)

        row_payload = {

            'stock': sym,

            'symbol': sym,

            'index': index_value,

            'INDEX': index_value,

            'index_value': index_value,

            'INDEX_VALUE': index_value,

            'market_cap_index': index_value,

            'MARKET_CAP_INDEX': index_value,

            'totalMcap': total_mcap,

            'mcap': total_mcap,

            'MCAP': total_mcap,

            'mcapRank': mcap_rank,

            'mcap_rank': mcap_rank,

            'MCAP_RANK': mcap_rank,

            'market_cap_rank': mcap_rank,

            'rank': mcap_rank,

            'ltcDate': latest_date.isoformat() if latest_date else None,

            'ltc_date': latest_date.isoformat() if latest_date else None,

            'price': price,

            'closePrice': price,

            'close_price': price,

            'ath': ath,

            'high52w': high52w,

            'low52w': low52w,

            'ema20': ema20,

            'ema50': ema50,

            'ema100': ema100,

            'ema200': ema200,

            'ema20FlagRaw': None,

            'ema50FlagRaw': None,

            'ema100FlagRaw': None,

            'ema200FlagRaw': None,

            'ema20Flag': ema20_flag,

            'ema50Flag': ema50_flag,

            'ema100Flag': ema100_flag,

            'ema200Flag': ema200_flag,

            'gapPct': gap_pct,

            'gap': _format_gap(gap_pct),

            'trend': trend_direction,

            'trendDirection': trend_direction,

            'trendSort': trend_sort,

            'trendDirectionSort': trend_sort,

            'trendDecisionReason': str(trend_decision.get('decisionReason') or '').strip() or 'NA',

            'trendSource': 'NONE',

            'trendSupport': '',

            'trendResistance': '',

            'supportPrice': None,

            'resistancePrice': None,

            'supportSource': 'NONE',

            'resistanceSource': 'NONE',

        }

        rows.append(_apply_sector_master_score(row_payload))

    return rows





def _build_minimal_sector_symbol_rows(symbols: list[str]) -> list[dict[str, Any]]:

    rows: list[dict[str, Any]] = []

    scoped_map: dict[str, str] = {}

    for item in symbols:

        display_symbol = str(item or '').strip().upper()

        if not display_symbol:

            continue

        display_symbol = 'LTM' if display_symbol == 'LTIM' else display_symbol

        lookup_symbol = _normalize_index_lookup_symbol(display_symbol) or _normalize_symbol_token(display_symbol)

        if lookup_symbol and lookup_symbol not in scoped_map:

            scoped_map[lookup_symbol] = display_symbol

    for sym in sorted(scoped_map.values()):

        row_payload = {

            'stock': sym,

            'symbol': sym,

            'index': '-',

            'INDEX': '-',

            'index_value': '-',

            'INDEX_VALUE': '-',

            'market_cap_index': '-',

            'MARKET_CAP_INDEX': '-',

            'totalMcap': None,

            'mcap': None,

            'MCAP': None,

            'mcapRank': None,

            'mcap_rank': None,

            'MCAP_RANK': None,

            'market_cap_rank': None,

            'rank': None,

            'ltcDate': None,

            'ltc_date': None,

            'price': None,

            'closePrice': None,

            'close_price': None,

            'ath': None,

            'high52w': None,

            'low52w': None,

            'ema20': None,

            'ema50': None,

            'ema100': None,

            'ema200': None,

            'ema20Flag': 'N',

            'ema50Flag': 'N',

            'ema100Flag': 'N',

            'ema200Flag': 'N',

            'trend': 'Unknown / Insufficient Data',

            'trendDirection': 'Unknown / Insufficient Data',

            'trendSort': _trend_sort_rank('Unknown / Insufficient Data'),

            'trendDirectionSort': _trend_sort_rank('Unknown / Insufficient Data'),

            'trendDecisionReason': 'Missing price or EMA data',

            'trendSource': 'NONE',

            'trendSupport': '',

            'trendResistance': '',

            'supportPrice': None,

            'resistancePrice': None,

            'supportSource': 'NONE',

            'resistanceSource': 'NONE',

        }

        rows.append(_apply_sector_master_score(row_payload))

    return rows





def _normalize_sector_wise_sort_key(value: Any) -> str:

    token = str(value or 'STOCK').strip().upper().replace(' ', '_')

    mapped = _SECTOR_WISE_SORT_ALIASES.get(token, token)

    if mapped not in _SECTOR_WISE_SORT_FIELDS:

        return 'STOCK'

    return mapped





def _snapshot_column_expr(alias: str, column: str) -> str:

    token = str(column or '').strip().upper()

    if not token:

        return 'NULL'

    if re.fullmatch(r'[A-Z][A-Z0-9_$]*', token):

        return f'{alias}.{token.lower()}'

    escaped = token.replace('"', '""')

    return f'{alias}."{escaped}"'





def _snapshot_value_expr(

    alias: str,

    metric_key: str,

    available_columns: set[str],

    *,

    candidate_map: dict[str, list[str]] | None = None,

    null_expr: str = 'CAST(NULL AS NUMBER)',

) -> str:

    source = candidate_map if isinstance(candidate_map, dict) else _SECTOR_WISE_SNAPSHOT_CANDIDATES

    for col in source.get(metric_key, []):

        if col in available_columns:

            return _snapshot_column_expr(alias, col)

    return null_expr





def _build_sector_wise_rows_sql(candidates: list[str], symbol_filter: list[str] | None = None) -> tuple[str, dict[str, Any]]:

    sector_clause, sector_binds = _build_sector_binds(candidates)

    symbol_clause = ''

    symbol_binds: dict[str, Any] = {}

    normalized_symbol_expr = _normalized_symbol_expr('snap.symbol')

    if symbol_filter:

        filtered_symbols = [_normalize_symbol_token(item) for item in symbol_filter if _normalize_symbol_token(item)]

        if filtered_symbols:

            symbol_placeholders, symbol_binds = _build_symbol_binds(filtered_symbols)

            symbol_clause = f'AND {normalized_symbol_expr} IN ({symbol_placeholders})'

    available_columns = _snapshot_columns()

    ath_expr = _snapshot_value_expr('snap', 'ath', available_columns)

    high_52w_expr = _snapshot_value_expr('snap', 'high_52w', available_columns)

    low_52w_expr = _snapshot_value_expr('snap', 'low_52w', available_columns)

    ema20_expr = _snapshot_value_expr('snap', 'ema20', available_columns)

    ema50_expr = _snapshot_value_expr('snap', 'ema50', available_columns)

    ema100_expr = _snapshot_value_expr('snap', 'ema100', available_columns)

    ema200_expr = _snapshot_value_expr('snap', 'ema200', available_columns)

    total_mcap_expr = _snapshot_value_expr('snap', 'total_mcap', available_columns)

    mcap_rank_expr = _snapshot_value_expr('snap', 'mcap_rank', available_columns)

    ema20_flag_expr = _snapshot_value_expr(

        'snap',

        'ema20_flag',

        available_columns,

        candidate_map=_SECTOR_WISE_FLAG_CANDIDATES,

        null_expr='CAST(NULL AS VARCHAR2(8))',

    )

    ema50_flag_expr = _snapshot_value_expr(

        'snap',

        'ema50_flag',

        available_columns,

        candidate_map=_SECTOR_WISE_FLAG_CANDIDATES,

        null_expr='CAST(NULL AS VARCHAR2(8))',

    )

    ema100_flag_expr = _snapshot_value_expr(

        'snap',

        'ema100_flag',

        available_columns,

        candidate_map=_SECTOR_WISE_FLAG_CANDIDATES,

        null_expr='CAST(NULL AS VARCHAR2(8))',

    )

    ema200_flag_expr = _snapshot_value_expr(

        'snap',

        'ema200_flag',

        available_columns,

        candidate_map=_SECTOR_WISE_FLAG_CANDIDATES,

        null_expr='CAST(NULL AS VARCHAR2(8))',

    )



    sql = f"""

WITH ranked AS (

    SELECT

        {normalized_symbol_expr} AS symbol,

        snap.ltc_date AS ltc_date,

        snap.close_price AS close_price,

        {ath_expr} AS ath,

        {high_52w_expr} AS high_52w,

        {low_52w_expr} AS low_52w,

        {ema20_expr} AS ema20,

        {ema50_expr} AS ema50,

        {ema100_expr} AS ema100,

        {ema200_expr} AS ema200,

        {total_mcap_expr} AS total_mcap,

        {mcap_rank_expr} AS mcap_rank,

        {ema20_flag_expr} AS ema20_flag,

        {ema50_flag_expr} AS ema50_flag,

        {ema100_flag_expr} AS ema100_flag,

        {ema200_flag_expr} AS ema200_flag,

        ROW_NUMBER() OVER (

            PARTITION BY {normalized_symbol_expr}

            ORDER BY snap.ltc_date DESC NULLS LAST, snap.close_price DESC NULLS LAST, {normalized_symbol_expr} ASC

        ) AS rn

    FROM mv_nse_sector_ui_snapshot snap

    WHERE snap.sector IN ({sector_clause})

      {symbol_clause}

      AND (:search_term IS NULL OR {normalized_symbol_expr} LIKE :search_term ESCAPE '\\')

)

SELECT

    r.symbol AS "stock",

    r.ltc_date AS "ltcDate",

    r.close_price AS "price",

    r.total_mcap AS "totalMcap",

    r.mcap_rank AS "mcapRank",

    r.ath AS "ath",

    r.high_52w AS "high52w",

    r.low_52w AS "low52w",

    r.ema20 AS "ema20",

    r.ema50 AS "ema50",

    r.ema100 AS "ema100",

    r.ema200 AS "ema200",

    r.ema20_flag AS "ema20FlagRaw",

    r.ema50_flag AS "ema50FlagRaw",

    r.ema100_flag AS "ema100FlagRaw",

    r.ema200_flag AS "ema200FlagRaw"

FROM ranked r

WHERE r.rn = 1

"""

    merged_binds = dict(sector_binds)

    merged_binds.update(symbol_binds)

    return sql, merged_binds





_FIRST_NUMBER_RE = re.compile(r'-?\d+(?:\.\d+)?')





def _trend_token(value: Any) -> str:

    return str(value or '').strip().upper()





def _normalize_sector_trend(value: Any) -> str:

    token = _trend_token(value)

    if not token or token in {'-', 'NA', 'N/A'}:

        return 'Unknown / Insufficient Data'

    compact = token.replace('_', ' ')

    if 'STRONG' in compact and 'UP' in compact:

        return 'Strong Uptrend'

    if 'PULLBACK' in compact and 'UP' in compact:

        return 'Pullback in Uptrend'

    if 'POSSIBLE' in compact and 'REVERSAL' in compact:

        return 'Possible Reversal'

    if 'REVERSAL' in compact:

        return 'Possible Reversal'

    if 'SIDEWAYS' in compact:

        return 'Sideways'

    if 'CONSOLIDATION' in compact:

        return 'Consolidation'

    if 'RANGE' in compact:

        return 'Consolidation'

    if 'UP' in compact:

        return 'Uptrend'

    if 'DOWN' in compact or 'BREAKDOWN' in compact:

        return 'Downtrend'

    if 'UNKNOWN' in compact or 'INSUFFICIENT' in compact:

        return 'Unknown / Insufficient Data'

    return str(value or '').strip() or 'Unknown / Insufficient Data'


_SECTOR_OVERVIEW_STATIC_TRENDS = (
    'Strong Uptrend',
    'Uptrend',
    'Downtrend',
    'Sideway',
    'Pullback in Uptrend',
    'Unknown / Insufficient Data',
)


def _build_sector_overview_row(*, stock: str, ltc_date: str, price: Any, trend: str) -> dict[str, Any]:
    return {
        'stock': stock,
        'ltc_date': ltc_date,
        'price': _to_float(price),
        'trend': trend,
    }


def _load_sector_overview_symbols(sector_codes: list[str]) -> list[str]:

    normalized_codes = sorted({str(code or '').strip().upper() for code in sector_codes if str(code or '').strip()})

    if not normalized_codes:

        return []

    conn = get_oracle_connection()

    try:

        binds: dict[str, Any] = {}

        placeholders: list[str] = []

        for idx, code in enumerate(normalized_codes):

            bind_name = f'sector_code_{idx}'

            binds[bind_name] = code

            placeholders.append(f':{bind_name}')

        sql = f"""
SELECT DISTINCT UPPER(TRIM(symbol)) AS symbol
FROM nse_symbol_sector_map
WHERE UPPER(TRIM(sector_code)) IN ({', '.join(placeholders)})
  AND symbol IS NOT NULL
"""

        with conn.cursor() as cursor:

            cursor.arraysize = 1000

            cursor.execute(sql, binds)

            return sorted({
                canonical_nse_symbol(raw[0])
                for raw in (cursor.fetchall() or [])
                if raw and canonical_nse_symbol(raw[0])
            })

    except Exception:

        logger.exception('Failed sector overview symbol lookup from nse_symbol_sector_map')

        return []

    finally:

        conn.close()


def _format_overview_date(value: Any) -> str:

    if isinstance(value, datetime):

        return value.strftime('%d-%m-%Y')

    if isinstance(value, date):

        return value.strftime('%d-%m-%Y')

    text = str(value or '').strip()

    if not text:

        return ''

    match = re.match(r'^(\d{4})-(\d{2})-(\d{2})', text)

    if match:

        return f'{match.group(3)}-{match.group(2)}-{match.group(1)}'

    legacy = re.match(r'^(\d{2})-(\d{2})-(\d{4})$', text)

    if legacy:

        return text

    return text


def _normalize_sector_overview_trend(value: Any) -> str:

    raw = str(value or '').strip()

    token = raw.upper().replace('_', ' ')

    token = re.sub(r'\s+', ' ', token).strip()

    if not token or token in {'-', 'NA', 'N/A', 'NULL', 'NONE', 'BLANK'}:

        return 'Unknown / Insufficient Data'

    if 'NO HISTORICAL' in token:

        return 'Unknown / Insufficient Data'

    if 'UNKNOWN' in token or 'INSUFFICIENT' in token:

        return 'Unknown / Insufficient Data'

    if 'STRONG' in token and 'UP' in token:

        return 'Strong Uptrend'

    if 'PULLBACK' in token and 'UP' in token:

        return 'Pullback in Uptrend'

    if token in {'SIDEWAY', 'SIDEWAYS'} or 'SIDEWAY' in token or 'SIDEWAYS' in token:

        return 'Sideway'

    if 'CONSOLIDATION' in token or 'RANGE' in token:

        return 'Sideway'

    if token == 'UP TREND':

        return 'Uptrend'

    if token == 'DOWN TREND':

        return 'Downtrend'

    if 'DOWN' in token or 'BREAKDOWN' in token:

        return 'Downtrend'

    if 'UP' in token:

        return 'Uptrend'

    return raw or 'Unknown / Insufficient Data'


def _should_promote_sector_overview_strong_uptrend(
    *,
    price: float | None,
    ath: float | None,
    high52w: float | None,
    ema20: float | None,
    ema50: float | None,
    ema100: float | None,
    ema200: float | None,
    adx: float | None,
    rsi: float | None,
) -> bool:

    if price is None:

        return False

    high_gap_candidates = [
        gap for gap in (
            _pct_below_level(price, ath),
            _pct_below_level(price, high52w),
        ) if gap is not None
    ]

    if not high_gap_candidates or min(high_gap_candidates) > SECTOR_TREND_NEAR_HIGH_PERCENT:

        return False

    bullish_stack = (
        ema20 is not None
        and ema50 is not None
        and ema100 is not None
        and ema200 is not None
        and price > ema20 > ema50 > ema100 > ema200
    )

    if not bullish_stack:

        return False

    if adx is not None and adx < 20.0:

        return False

    if rsi is not None and rsi > 75.0:

        return False

    return True


def _resolve_sector_overview_trend(
    *,
    symbol: str,
    latest_meta: dict[str, Any] | None,
    trend_meta: dict[str, Any] | None,
    extrema_meta: dict[str, Any] | None,
    ema_meta: dict[str, Any] | None,
) -> str:

    cached_trend = _normalize_sector_overview_trend(
        (trend_meta or {}).get('trendDirection') if isinstance(trend_meta, dict) else None
    )

    if cached_trend != 'Unknown / Insufficient Data':

        return cached_trend

    price = _to_float((latest_meta or {}).get('latestClose')) if isinstance(latest_meta, dict) else None

    if price is None:

        return cached_trend

    ath = _to_float((extrema_meta or {}).get('ath')) if isinstance(extrema_meta, dict) else None

    high52w = _to_float((extrema_meta or {}).get('high52w')) if isinstance(extrema_meta, dict) else None

    low52w = _to_float((extrema_meta or {}).get('low52w')) if isinstance(extrema_meta, dict) else None

    ema20 = _to_float((ema_meta or {}).get('ema20')) if isinstance(ema_meta, dict) else None

    ema50 = _to_float((ema_meta or {}).get('ema50')) if isinstance(ema_meta, dict) else None

    ema100 = _to_float((ema_meta or {}).get('ema100')) if isinstance(ema_meta, dict) else None

    ema200 = _to_float((ema_meta or {}).get('ema200')) if isinstance(ema_meta, dict) else None

    trend_metrics = (
        (extrema_meta or {}).get('trendMetrics')
        if isinstance(extrema_meta, dict) and isinstance((extrema_meta or {}).get('trendMetrics'), dict)
        else {}
    )
    adx = _to_float(
        (extrema_meta or {}).get('adx14')
        if isinstance(extrema_meta, dict)
        else None
    )
    if adx is None:

        adx = _to_float(
            (extrema_meta or {}).get('adx')
            if isinstance(extrema_meta, dict)
            else None
        )
    if adx is None:

        adx = _to_float(trend_metrics.get('strength'))

    rsi = _to_float(
        (extrema_meta or {}).get('rsi')
        if isinstance(extrema_meta, dict)
        else None
    )
    if rsi is None:

        rsi = _to_float(
            (extrema_meta or {}).get('rsi14')
            if isinstance(extrema_meta, dict)
            else None
        )
    if rsi is None:

        rsi = _to_float(trend_metrics.get('rsi'))

    trend_decision = calculate_sector_stock_trend(
        sector_name='Sector Overview',
        symbol=symbol,
        price=price,
        ath=ath,
        high52w=high52w,
        low52w=low52w,
        gap_pct=_compute_gap_pct(price, ath),
        ema20_flag=_resolve_ema_flag_for_trend(price=price, ema_value=ema20, raw_flag=None),
        ema50_flag=_resolve_ema_flag_for_trend(price=price, ema_value=ema50, raw_flag=None),
        ema100_flag=_resolve_ema_flag_for_trend(price=price, ema_value=ema100, raw_flag=None),
        ema200_flag=_resolve_ema_flag_for_trend(price=price, ema_value=ema200, raw_flag=None),
        support_price=None,
        resistance_price=None,
        sr_source=str((trend_meta or {}).get('srLevelSource') or 'NONE') if isinstance(trend_meta, dict) else 'NONE',
        sr_trend_direction=_normalize_sector_trend(
            (trend_meta or {}).get('trendDirection') if isinstance(trend_meta, dict) else None
        ),
    )

    computed_trend = _normalize_sector_overview_trend(
        trend_decision.get('trend') if isinstance(trend_decision, dict) else None
    )

    if (
        computed_trend == 'Uptrend'
        and isinstance(trend_decision, dict)
        and str(trend_decision.get('decisionReason') or '').strip().upper() == 'NEAR_HIGH_WITH_BULLISH_EMA'
        and _should_promote_sector_overview_strong_uptrend(
            price=price,
            ath=ath,
            high52w=high52w,
            ema20=ema20,
            ema50=ema50,
            ema100=ema100,
            ema200=ema200,
            adx=adx,
            rsi=rsi,
        )
    ):

        return 'Strong Uptrend'

    if computed_trend != 'Unknown / Insufficient Data':

        return computed_trend

    return cached_trend


def _load_sector_overview_snapshot_rows(
    sector_codes: list[str],
    symbols: list[str],
) -> dict[str, dict[str, Any]]:

    normalized_sector_codes = [
        str(code or '').strip().upper()
        for code in sector_codes
        if str(code or '').strip()
    ]

    normalized_symbols = [
        _normalize_symbol_token(symbol)
        for symbol in symbols
        if _normalize_symbol_token(symbol)
    ]

    if not normalized_sector_codes or not normalized_symbols:

        return {}

    sql, binds = _build_sector_wise_rows_sql(normalized_sector_codes, normalized_symbols)
    query_binds = dict(binds)
    query_binds['search_term'] = None

    rows = _query_rows(sql, query_binds)
    snapshot_rows: dict[str, dict[str, Any]] = {}

    for row in rows:

        if not isinstance(row, dict):

            continue

        symbol = _normalize_symbol_token(row.get('stock'))

        if not symbol:

            continue

        snapshot_rows[symbol] = row

    return snapshot_rows


def _load_sector_overview_trend_snapshot_rows(
    symbols: list[str],
) -> dict[str, dict[str, Any]]:

    normalized_symbols = {
        _normalize_symbol_token(symbol)
        for symbol in symbols
        if _normalize_symbol_token(symbol)
    }

    if not normalized_symbols:

        return {}

    snapshot_path = Path(__file__).resolve().parents[1] / 'data' / 'snapshot_trend_daily.json'

    try:

        payload = json.loads(snapshot_path.read_text(encoding='utf-8'))

    except Exception:

        return {}

    bucket_names = (
        'ema20',
        'ema50',
        'ema100',
        'ema200',
        'ema200100',
        'ema20010050',
        'ema2001005020',
    )

    merged_rows: dict[str, dict[str, Any]] = {}

    for bucket in bucket_names:

        rows = payload.get(bucket) if isinstance(payload, dict) else None

        if not isinstance(rows, list):

            continue

        for row in rows:

            if not isinstance(row, dict):

                continue

            symbol = _normalize_symbol_token(row.get('symbol') or row.get('stock'))

            if not symbol or symbol not in normalized_symbols:

                continue

            existing = merged_rows.get(symbol, {})
            merged_rows[symbol] = {**existing, **row}

    return merged_rows


def _load_sector_overview_trendline_snapshot_rows(
    symbols: list[str],
    latest_ltc_date: date | None,
) -> tuple[dict[str, dict[str, Any]], str, bool]:

    normalized_symbols = {
        _normalize_symbol_token(symbol)
        for symbol in symbols
        if _normalize_symbol_token(symbol)
    }

    if not normalized_symbols:

        return {}, '', False

    snapshot_dir = Path(__file__).resolve().parents[1] / 'data' / 'cache' / 'strong_technicals'
    snapshot_files = sorted(
        snapshot_dir.glob('trendline_v1_daily_latest_1_ltc_*.json'),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not snapshot_files:

        return {}, '', False

    latest_token = latest_ltc_date.isoformat() if isinstance(latest_ltc_date, date) else ''
    selected_path: Path | None = None
    selected_token = ''
    exact_match = False

    for path in snapshot_files:

        match = re.search(r'_ltc_(\d{4}-\d{2}-\d{2})\.json$', path.name)
        file_token = str(match.group(1) if match else '').strip()

        if latest_token and file_token == latest_token:

            selected_path = path
            selected_token = file_token
            exact_match = True
            break

        if selected_path is None:

            selected_path = path
            selected_token = file_token

    if selected_path is None:

        return {}, '', False

    try:

        payload = json.loads(selected_path.read_text(encoding='utf-8'))

    except Exception:

        return {}, selected_token, False

    meta = payload.get('meta') if isinstance(payload, dict) else {}
    snapshot_token = str((meta or {}).get('latestTradingDate') or selected_token or '').strip()[:10]
    if latest_token and snapshot_token == latest_token:

        exact_match = True

    rows = payload.get('rows') if isinstance(payload, dict) else None
    if not isinstance(rows, list):

        return {}, snapshot_token, exact_match

    snapshot_rows: dict[str, dict[str, Any]] = {}

    for row in rows:

        if not isinstance(row, dict):

            continue

        symbol = _normalize_symbol_token(row.get('symbol') or row.get('stock') or row.get('SYMBOL'))

        if not symbol or symbol not in normalized_symbols:

            continue

        snapshot_rows[symbol] = row

    return snapshot_rows, snapshot_token, exact_match


def _merge_sector_overview_snapshot_rows(
    primary_rows: dict[str, dict[str, Any]] | None,
    fallback_rows: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:

    merged_rows: dict[str, dict[str, Any]] = {}

    if isinstance(primary_rows, dict):
        for symbol, row in primary_rows.items():
            if isinstance(row, dict):
                merged_rows[symbol] = dict(row)

    if not isinstance(fallback_rows, dict):

        return merged_rows

    for symbol, row in fallback_rows.items():

        if not isinstance(row, dict):

            continue

        existing = merged_rows.get(symbol)

        if existing is None:

            merged_rows[symbol] = dict(row)
            continue

        for key, value in row.items():

            if existing.get(key) in (None, '') and value not in (None, ''):

                existing[key] = value

    return merged_rows


def _load_sector_overview_raw_fallback_rows(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Reuse Sector Wise DEV calculations for snapshot-missing overview rows."""
    normalized_symbols = sorted({_normalize_symbol_token(symbol) for symbol in symbols if _normalize_symbol_token(symbol)})
    if not normalized_symbols:
        return {}

    raw_latest_date = _latest_raw_trading_date()
    cache_key = f"sector-overview-raw-trend:{raw_latest_date.isoformat() if raw_latest_date else 'unknown'}:{','.join(normalized_symbols)}"
    cached = _sector_wise_trend_cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    try:
        rows = _build_strict_symbol_fallback_rows(normalized_symbols, search_token='')
    except Exception:
        logger.exception('Failed Sector Wise DEV fallback for Sector Overview rows')
        return {}

    fallback_rows: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue

        symbol = _normalize_symbol_token(row.get('stock') or row.get('symbol'))
        latest_date = _coerce_date(row.get('ltcDate') or row.get('ltc_date'))
        price = _to_float(row.get('price') or row.get('closePrice') or row.get('close_price'))
        if symbol and (latest_date is not None or price is not None):
            fallback_rows[symbol] = row

    _sector_wise_trend_cache.set(cache_key, fallback_rows)
    return fallback_rows


def _load_sector_overview_latest_trade_rows(
    symbols: list[str],
    latest_ltc_date: date | None,
) -> dict[str, dict[str, Any]]:
    """Load only the global latest DEV date and key rows by canonical symbol."""
    if latest_ltc_date is None:
        return {}
    source = _raw_sma_source()
    if not source:
        return {}
    table_name, close_col = source
    wanted = {_normalize_symbol_token(symbol) for symbol in symbols if _normalize_symbol_token(symbol)}
    if not wanted:
        return {}

    sql = f"""
SELECT
    UPPER(TRIM(t.symbol)) AS "stock",
    t.trading_date AS "latestDate",
    t.{close_col} AS "latestClose"
FROM {table_name} t
WHERE t.trading_date >= :latest_ltc_date
  AND t.trading_date < :latest_ltc_date + 1
"""
    result: dict[str, dict[str, Any]] = {}
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            cursor.arraysize = 2000
            cursor.execute(sql, {'latest_ltc_date': latest_ltc_date})
            cols = [str(col[0]) for col in (cursor.description or [])]
            for raw in cursor.fetchall() or []:
                row = {cols[pos]: _normalize(raw[pos]) for pos in range(len(cols))}
                stock = _normalize_symbol_token(row.get('stock'))
                if not stock or stock not in wanted:
                    continue
                latest_date = _coerce_date(row.get('latestDate'))
                latest_close = _to_float(row.get('latestClose'))
                existing = result.get(stock)
                if existing is None or (
                    existing.get('latestClose') is None and latest_close is not None
                ):
                    result[stock] = {
                        'latestDate': latest_date,
                        'latestClose': latest_close,
                    }
    finally:
        conn.close()

    missing_symbols = [
        symbol
        for symbol in symbols
        if _normalize_symbol_token(symbol) not in result
    ]
    if missing_symbols:
        result.update(
            _load_sector_wise_raw_latest_trade_rows(
                missing_symbols,
                latest_ltc_date,
            )
        )
    return result


def _read_sector_overview_payload_snapshot(latest_date: date | None) -> dict[str, Any] | None:
    try:
        payload = json.loads(_SECTOR_OVERVIEW_SNAPSHOT_PATH.read_text(encoding='utf-8'))
    except Exception:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get('rows'), list):
        return None
    expected = latest_date.isoformat() if isinstance(latest_date, date) else ''
    if expected and str(payload.get('source_dev_ltc_date') or '') != expected:
        return None
    return payload


def _write_sector_overview_payload_snapshot(payload: dict[str, Any]) -> None:
    _SECTOR_OVERVIEW_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = _SECTOR_OVERVIEW_SNAPSHOT_PATH.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=True, separators=(',', ':')), encoding='utf-8')
    temporary.replace(_SECTOR_OVERVIEW_SNAPSHOT_PATH)


def _supplement_overview_unknowns_from_v3(payload: dict[str, Any]) -> dict[str, Any]:
    """Expose genuine V3 data gaps in the Overview KPI without live DB work."""
    rows = [dict(row) for row in payload.get('rows', []) if isinstance(row, dict)]
    known_symbols = {_normalize_symbol_token(row.get('stock') or row.get('symbol')) for row in rows}
    try:
        stock_snapshot = json.loads(_SECTOR_V3_STOCK_SNAPSHOT_PATH.read_text(encoding='utf-8'))
    except Exception:
        return payload
    overview_date = _coerce_date(payload.get('ltc_date'))
    v3_date = _coerce_date(stock_snapshot.get('asOfDate')) if isinstance(stock_snapshot, dict) else None
    if overview_date is not None and v3_date is not None and overview_date != v3_date:
        return payload
    sectors = stock_snapshot.get('sectors') if isinstance(stock_snapshot, dict) else None
    if not isinstance(sectors, dict):
        return payload

    additions: list[dict[str, Any]] = []
    for sector in sectors.values():
        for row in (sector or {}).get('rows', []) if isinstance(sector, dict) else []:
            if not isinstance(row, dict):
                continue
            raw_trend = row.get('trendState') or row.get('trend')
            trend = _normalize_sector_overview_trend(raw_trend)
            symbol = str(row.get('symbol') or row.get('stock') or '').strip()
            key = _normalize_symbol_token(symbol)
            raw_token = str(raw_trend or '').strip().upper().replace(' ', '_')
            is_unknown = raw_token in {'DATA_WEAK', 'UNKNOWN', 'INSUFFICIENT'} or trend == 'Unknown / Insufficient Data'
            if not is_unknown or not key or key in known_symbols:
                continue
            known_symbols.add(key)
            additions.append(_build_sector_overview_row(
                stock=symbol,
                ltc_date=str(row.get('ltcDate') or ''),
                price=_to_float(row.get('price')),
                trend='Unknown / Insufficient Data',
            ))
    if not additions:
        return payload

    result = dict(payload)
    result['rows'] = sorted(rows + additions, key=lambda row: str(row.get('stock') or '').upper())
    result['total_stocks'] = len(result['rows'])
    trend_counts = dict(result.get('trend_counts') or {})
    trend_counts['Unknown / Insufficient Data'] = _coerce_int(
        trend_counts.get('Unknown / Insufficient Data'), default=0
    ) + len(additions)
    result['trend_counts'] = trend_counts
    source = str(result.get('sector_data_source') or '')
    result['sector_data_source'] = f'{source}+V3_UNKNOWN_FALLBACK' if source else 'V3_UNKNOWN_FALLBACK'
    return result


def _load_v3_unknown_symbols(as_of_date: date | None = None) -> list[str]:
    """Return V3 DATA_WEAK symbols that need an Overview DEV refresh."""
    try:
        payload = json.loads(_SECTOR_V3_STOCK_SNAPSHOT_PATH.read_text(encoding='utf-8'))
    except Exception:
        return []
    snapshot_date = _coerce_date(payload.get('asOfDate')) if isinstance(payload, dict) else None
    if as_of_date is not None and snapshot_date is not None and snapshot_date != as_of_date:
        return []
    sectors = payload.get('sectors') if isinstance(payload, dict) else None
    if not isinstance(sectors, dict):
        return []
    symbols: set[str] = set()
    for sector in sectors.values():
        for row in (sector or {}).get('rows', []) if isinstance(sector, dict) else []:
            if not isinstance(row, dict):
                continue
            raw_token = str(row.get('trendState') or row.get('trend') or '').strip().upper().replace(' ', '_')
            if raw_token not in {'DATA_WEAK', 'UNKNOWN', 'INSUFFICIENT'}:
                continue
            symbol = str(row.get('symbol') or row.get('stock') or '').strip()
            if symbol:
                symbols.add(symbol)
    return sorted(symbols)


def _load_sector_overview_sector_tables(force_refresh: bool = False) -> list[dict[str, Any]]:
    """Use the persisted discovery snapshot for normal overview reads.

    Live discovery counts every staging table individually, which is appropriate for
    an explicit refresh but too expensive for a page-load request.
    """
    if not force_refresh:
        snapshot_payload = _read_snapshot_from_disk()
        if isinstance(snapshot_payload, dict):
            snapshot_tables = _normalize_sector_table_entries(snapshot_payload.get('tables'))
            if snapshot_tables:
                logger.info(
                    'event=sector_overview_discovery_snapshot_hit table_count=%d',
                    len(snapshot_tables),
                )
                return snapshot_tables

    if force_refresh:
        # Overview only needs the sector identities; it obtains its symbols
        # through the canonical map below.  Avoid the shared discovery helper
        # here because it runs a COUNT(DISTINCT symbol) query for every staging
        # table solely to populate stockCount, a field this payload never uses.
        try:
            rows = _query_rows(SQL_DISCOVER_SECTOR_TABLES)
            table_names = [
                str(row.get('tableName') or '').strip().upper()
                for row in rows
                if isinstance(row, dict) and str(row.get('tableName') or '').strip()
            ]
            refreshed_tables = _normalize_sector_table_entries([
                {
                    'sectorCode': _sector_code_from_table_name(table_name),
                    'sectorName': _resolve_display_sector_name(_sector_code_from_table_name(table_name)),
                    'tableName': table_name,
                    'source': 'oracle_metadata',
                }
                for table_name in table_names
            ])
            if refreshed_tables:
                logger.info(
                    'event=sector_overview_metadata_refresh table_count=%d',
                    len(refreshed_tables),
                )
                return refreshed_tables
        except Exception:
            logger.exception('Failed lightweight sector overview table refresh')

    return _discover_sector_staging_tables(force_refresh=force_refresh)


def _load_sector_overview_payload(force_refresh: bool = False) -> dict[str, Any]:
    raw_sector_tables = _load_sector_overview_sector_tables(force_refresh=force_refresh)

    sectors = _collapse_sector_entries_for_unique_ui(raw_sector_tables)

    trend_counts: dict[str, int] = {trend: 0 for trend in _SECTOR_OVERVIEW_STATIC_TRENDS}

    dynamic_trend_counts: dict[str, int] = {}
    overview_rows: list[dict[str, Any]] = []

    latest_ltc_date = ''

    latest_ltc_sort_key: date | None = None

    unique_ltc_dates: set[str] = set()

    symbol_tokens: set[str] = set()

    sector_codes: list[str] = []

    for sector_entry in sectors:

        sector_code = str(sector_entry.get('sectorCode') or '').strip().upper()

        if not sector_code:

            continue

        sector_codes.append(sector_code)

    latest_fast_date = get_latest_ltc_date_fast() if force_refresh else None
    symbols = _load_sector_overview_symbols(sector_codes)

    if force_refresh:
        existing_symbol_keys = {_normalize_symbol_token(symbol) for symbol in symbols}
        v3_unknown_symbols = [
            symbol for symbol in _load_v3_unknown_symbols(latest_fast_date)
            if _normalize_symbol_token(symbol) not in existing_symbol_keys
        ]
        if v3_unknown_symbols:
            symbols = [*symbols, *v3_unknown_symbols]
            logger.info(
                'event=sector_overview_v3_unknown_symbol_backfill count=%d',
                len(v3_unknown_symbols),
            )

    if not symbols:
        for sector_code in sector_codes:
            strict_symbols = _load_strict_sector_symbols(sector_code) or []

            for symbol in strict_symbols:

                token = canonical_nse_symbol(symbol)

                if token:

                    symbol_tokens.add(token)

        symbols = sorted(symbol_tokens)

    total_stocks = len(symbols)

    trendline_snapshot_rows, trendline_snapshot_token, trendline_exact_match = _load_sector_overview_trendline_snapshot_rows(
        symbols,
        latest_fast_date,
    )
    trend_bucket_rows = _load_sector_overview_trend_snapshot_rows(symbols)
    trend_snapshot_rows = _merge_sector_overview_snapshot_rows(trendline_snapshot_rows, trend_bucket_rows)
    if force_refresh:
        for snapshot_row in trend_snapshot_rows.values():
            if isinstance(snapshot_row, dict):
                snapshot_row['ltcDate'] = None
                snapshot_row['price'] = None
    latest_trade_rows = (
        _load_sector_overview_latest_trade_rows(symbols, latest_fast_date)
        if force_refresh
        else {}
    )
    for symbol, latest_trade_row in latest_trade_rows.items():
        canonical_key = _normalize_symbol_token(symbol)
        if not canonical_key or not isinstance(latest_trade_row, dict):
            continue
        current_row = trend_snapshot_rows.setdefault(canonical_key, {'stock': canonical_key})
        latest_trade_date = _coerce_date(latest_trade_row.get('latestDate'))
        latest_trade_close = _to_float(latest_trade_row.get('latestClose'))
        if latest_trade_date is not None:
            current_row['ltcDate'] = latest_trade_date.isoformat()
        if latest_trade_close is not None:
            current_row['price'] = latest_trade_close
    missing_snapshot_symbols: list[str] = []
    for symbol in symbols:
        symbol_key = _normalize_symbol_token(symbol)
        snapshot_row = trend_snapshot_rows.get(symbol_key)
        snapshot_trend = _normalize_sector_overview_trend(
            (snapshot_row or {}).get('trendDirection') or (snapshot_row or {}).get('trend')
        ) if isinstance(snapshot_row, dict) else 'Unknown / Insufficient Data'
        if symbol_key in latest_trade_rows and (
            not isinstance(snapshot_row, dict)
            or _to_float(snapshot_row.get('price')) is None
            or (
                snapshot_trend == 'Unknown / Insufficient Data'
                and not any(
                    _to_float(snapshot_row.get(field)) is not None
                    for field in ('ema20', 'ema50', 'ema100', 'ema200', 'ath', 'high52w', 'low52w')
                )
            )
        ):
            missing_snapshot_symbols.append(symbol)
    raw_fallback_rows = (
        _load_sector_overview_raw_fallback_rows(missing_snapshot_symbols)
        if force_refresh
        else {}
    )
    raw_fallback_symbols = set(raw_fallback_rows)
    trend_snapshot_rows = _merge_sector_overview_snapshot_rows(trend_snapshot_rows, raw_fallback_rows)
    for symbol_key, snapshot_row in trend_snapshot_rows.items():
        if force_refresh and isinstance(snapshot_row, dict) and symbol_key not in latest_trade_rows:
            snapshot_row['ltcDate'] = None
            snapshot_row['price'] = None
    # Sector Overview refresh already obtains current prices from DEV and fills
    # snapshot gaps through the targeted DEV fallback above.  Do not force the
    # broad Sector Rotation trend payload here: on installations without the
    # materialized trend view it can trigger a full strategy recomputation and
    # block this request beyond the client timeout.  A previously warmed trend
    # cache remains a useful optional enrichment for both normal and refresh
    # reads; otherwise the overview resolves trends from its own data.
    cached_trend_map = _sector_wise_trend_cache.get(_SECTOR_WISE_TREND_CACHE_KEY)
    trend_map = cached_trend_map if isinstance(cached_trend_map, dict) else {}

    for symbol in symbols:
        symbol_key = _normalize_symbol_token(symbol)
        trend_snapshot_row = trend_snapshot_rows.get(symbol_key) if isinstance(trend_snapshot_rows, dict) else None

        latest_meta = (
            {
                'latestClose': (trend_snapshot_row or {}).get('price'),
                'latestDate': _coerce_date((trend_snapshot_row or {}).get('ltcDate')),
            }
            if isinstance(trend_snapshot_row, dict)
            else None
        )

        sortable_ltc_date = _coerce_date((latest_meta or {}).get('latestDate')) if isinstance(latest_meta, dict) else None

        normalized_ltc_date = _format_overview_date(sortable_ltc_date)

        if normalized_ltc_date:

            unique_ltc_dates.add(normalized_ltc_date)

            if latest_ltc_sort_key is None or sortable_ltc_date > latest_ltc_sort_key:

                latest_ltc_sort_key = sortable_ltc_date

                latest_ltc_date = normalized_ltc_date

        trend_meta = trend_map.get(symbol_key) if isinstance(trend_map, dict) else None
        if not isinstance(trend_meta, dict) and isinstance(trend_snapshot_row, dict):
            snapshot_trend = (
                trend_snapshot_row.get('trendDirection')
                or trend_snapshot_row.get('trend')
                or trend_snapshot_row.get('Trend_Direction')
                or trend_snapshot_row.get('TREND_DIRECTION')
                or trend_snapshot_row.get('trend_direction')
            )
            if _normalize_sector_overview_trend(snapshot_trend) != 'Unknown / Insufficient Data':
                trend_meta = {'trendDirection': snapshot_trend}
        if symbol_key in raw_fallback_symbols:
            raw_trend = _normalize_sector_overview_trend(
                (trend_snapshot_row or {}).get('trendDirection') or (trend_snapshot_row or {}).get('trend')
            )
            if raw_trend != 'Unknown / Insufficient Data':
                trend_meta = {**(trend_meta or {}), 'trendDirection': raw_trend}

        has_snapshot_trade = (
            isinstance(latest_meta, dict)
            and latest_meta.get('latestDate') is not None
            and _to_float(latest_meta.get('latestClose')) is not None
        )
        if symbol_key not in latest_trade_rows and not has_snapshot_trade:
            normalized_trend = 'Unknown / Insufficient Data'
        else:
            normalized_trend = _resolve_sector_overview_trend(
                symbol=symbol,
                latest_meta=latest_meta if isinstance(latest_meta, dict) else None,
                trend_meta=trend_meta if isinstance(trend_meta, dict) else None,
                extrema_meta=trend_snapshot_row if isinstance(trend_snapshot_row, dict) else None,
                ema_meta=trend_snapshot_row if isinstance(trend_snapshot_row, dict) else None,
            )

        if normalized_trend in trend_counts:

            trend_counts[normalized_trend] += 1

        else:

            dynamic_trend_counts[normalized_trend] = dynamic_trend_counts.get(normalized_trend, 0) + 1

        overview_rows.append(
            _build_sector_overview_row(
                stock=symbol,
                ltc_date=normalized_ltc_date,
                price=(trend_snapshot_row or {}).get('price') if isinstance(trend_snapshot_row, dict) else None,
                trend=normalized_trend,
            )
        )

    overview_rows.sort(key=lambda row: (str(row.get('stock') or '').upper(), str(row.get('ltc_date') or '')))

    sorted_dynamic_trend_counts = {
        key: dynamic_trend_counts[key]
        for key in sorted(dynamic_trend_counts, key=lambda item: (-dynamic_trend_counts[item], item))
    }

    sector_sources: list[str] = []
    if trendline_snapshot_rows:
        sector_sources.append('TRENDLINE_SNAPSHOT')
    if trend_bucket_rows:
        sector_sources.append('TREND_DAILY_BUCKETS')
    if raw_fallback_rows:
        sector_sources.append('RAW_DATA_DEV_TREND_FALLBACK')
    if latest_trade_rows:
        sector_sources.append('RAW_DATA_DEV_LATEST')
    if isinstance(trend_map, dict) and trend_map:
        sector_sources.append('TREND_CACHE')
    sector_source_label = '+'.join(sector_sources) if sector_sources else 'STRICT_SYMBOLS'

    if latest_fast_date is not None:
        latest_ltc_date = _format_overview_date(latest_fast_date)
    elif not latest_ltc_date and trendline_snapshot_token:
        latest_ltc_date = _format_overview_date(_coerce_date(trendline_snapshot_token))

    ltc_date_count = len(unique_ltc_dates)
    ltc_date_consistent = len(unique_ltc_dates) <= 1
    is_stale = total_stocks == 0 or not trendline_exact_match

    if not latest_ltc_date and latest_fast_date is not None:
        latest_ltc_date = _format_overview_date(latest_fast_date)

    return {
        'status': 'success',
        'success': True,
        'total_sectors': len(sectors),
        'total_stocks': total_stocks,
        'ltc_date': latest_ltc_date,
        'ltc_date_count': ltc_date_count,
        'ltc_date_consistent': ltc_date_consistent,
        'ltc_date_scope': 'LATEST_PER_SYMBOL',
        'trend_counts': trend_counts,
        'dynamic_trend_counts': sorted_dynamic_trend_counts,
        'rows': overview_rows,
        'sector_data_source': sector_source_label,
        'is_stale': is_stale,
        'generated_at': datetime.now().isoformat(),
    }





def _trend_sort_rank(value: Any) -> int:

    normalized = _normalize_sector_trend(value)

    return _SECTOR_TREND_SORT_ASC.get(_trend_token(normalized), _SECTOR_TREND_SORT_ASC['UNKNOWN / INSUFFICIENT DATA'])





def _pct_below_level(price: float | None, level: float | None) -> float | None:

    if price is None or level is None or level <= 0:

        return None

    return ((level - price) / level) * 100.0





def _pct_above_level(price: float | None, level: float | None) -> float | None:

    if price is None or level is None or level <= 0:

        return None

    return ((price - level) / level) * 100.0





def _is_at_level(price: float | None, level: float | None, tolerance_pct: float = 0.2) -> bool:

    if price is None or level is None or level <= 0:

        return False

    return abs(((price - level) / level) * 100.0) <= max(0.0, float(tolerance_pct or 0.0))





def _is_near_high(price: float | None, level: float | None, near_percent: float) -> bool:

    gap_pct = _pct_below_level(price, level)

    if gap_pct is None:

        return False

    return 0.0 <= gap_pct <= max(0.0, near_percent)





def _is_near_low(price: float | None, level: float | None, near_percent: float) -> bool:

    gap_pct = _pct_above_level(price, level)

    if gap_pct is None:

        return False

    return 0.0 <= gap_pct <= max(0.0, near_percent)





def _resolve_ema_flag_for_trend(

    *,

    price: float | None,

    ema_value: float | None,

    raw_flag: Any,

) -> str:

    if price is not None and ema_value is not None:

        return 'Y' if price > ema_value else 'N'

    explicit = _normalize_yn_flag(raw_flag)

    if explicit in {'Y', 'N'}:

        return explicit

    return ''





def _ema_alignment_summary(flags: list[str]) -> tuple[int, int, int]:

    bullish = sum(1 for flag in flags if flag == 'Y')

    bearish = sum(1 for flag in flags if flag == 'N')

    known = bullish + bearish

    return bullish, bearish, known





def calculate_sector_stock_trend(

    *,

    sector_name: str,

    symbol: str,

    price: float | None,

    ath: float | None,

    high52w: float | None,

    low52w: float | None,

    gap_pct: float | None,

    ema20_flag: str,

    ema50_flag: str,

    ema100_flag: str,

    ema200_flag: str,

    support_price: float | None,

    resistance_price: float | None,

    sr_source: str,

    sr_trend_direction: str | None,

) -> dict[str, Any]:

    if price is None:

        trend = 'Unknown / Insufficient Data'

        reason = 'PRICE_MISSING'

        return {

            'trend': trend,

            'trendSort': _trend_sort_rank(trend),

            'decisionReason': reason,

            'debug': {

                'sector': sector_name,

                'symbol': symbol,

                'price': None,

                'ath': ath,

                'high52w': high52w,

                'low52w': low52w,

                'gapPct': gap_pct,

                'ema20': ema20_flag,

                'ema50': ema50_flag,

                'ema100': ema100_flag,

                'ema200': ema200_flag,

                'bullishEmaCount': 0,

                'bearishEmaCount': 0,

                'nearAth': False,

                'near52Wh': False,

                'near52Wl': False,

                'support': support_price,

                'resistance': resistance_price,

                'srSource': sr_source,

                'finalTrend': trend,

                'reason': reason,

            },

        }



    near_high_percent = SECTOR_TREND_NEAR_HIGH_PERCENT

    near_low_percent = SECTOR_TREND_NEAR_LOW_PERCENT

    far_below_high_percent = SECTOR_TREND_FAR_BELOW_HIGH_PERCENT

    near_level_percent = SECTOR_TREND_NEAR_LEVEL_PERCENT



    ema20 = ema20_flag if ema20_flag in {'Y', 'N'} else ''

    ema50 = ema50_flag if ema50_flag in {'Y', 'N'} else ''

    ema100 = ema100_flag if ema100_flag in {'Y', 'N'} else ''

    ema200 = ema200_flag if ema200_flag in {'Y', 'N'} else ''

    ema_flags = [ema20, ema50, ema100, ema200]

    bullish_count, bearish_count, known_ema_count = _ema_alignment_summary(ema_flags)

    bullish_majority = bullish_count >= SECTOR_TREND_EMA_BULLISH_THRESHOLD

    bearish_majority = bearish_count >= SECTOR_TREND_EMA_BEARISH_THRESHOLD

    mixed_ema = bullish_count > 0 and bearish_count > 0

    ema20_pullback_structure = (

        ema20 == 'N' and ema50 == 'Y' and ema100 == 'Y' and ema200 == 'Y'

    )



    near_ath = _is_near_high(price, ath, near_high_percent)

    near_52wh = _is_near_high(price, high52w, near_high_percent)

    near_52wl = _is_near_low(price, low52w, near_low_percent)



    at_ath = _is_at_level(price, ath)

    at_52wh = _is_at_level(price, high52w)

    at_or_above_ath = (

        ath is not None and ath > 0 and (

            at_ath or price >= (ath * (1.0 + (SECTOR_TREND_BREAKOUT_BUFFER_PERCENT / 100.0)))

        )

    )

    at_or_above_52wh = (

        high52w is not None and high52w > 0 and (

            at_52wh or price >= (high52w * (1.0 + (SECTOR_TREND_BREAKOUT_BUFFER_PERCENT / 100.0)))

        )

    )



    high_gap_candidates = [

        gap for gap in (

            _pct_below_level(price, ath),

            _pct_below_level(price, high52w),

        ) if gap is not None

    ]

    nearest_high_gap_pct = min(high_gap_candidates) if high_gap_candidates else None

    far_below_high = (

        nearest_high_gap_pct is not None and nearest_high_gap_pct >= far_below_high_percent

    )



    low_gap_pct = _pct_above_level(price, low52w)

    below_52wl = low_gap_pct is not None and low_gap_pct < 0.0



    support_gap_pct = _pct_above_level(price, support_price)

    resistance_gap_pct = _pct_above_level(price, resistance_price)

    breakdown_buffer = SECTOR_TREND_BREAKDOWN_BUFFER_PERCENT

    breakout_buffer = SECTOR_TREND_BREAKOUT_BUFFER_PERCENT



    below_support = (

        support_gap_pct is not None and support_gap_pct < (0.0 - breakdown_buffer)

    )

    above_resistance = (

        resistance_gap_pct is not None and resistance_gap_pct > breakout_buffer

    )



    near_support = (

        support_gap_pct is not None and

        abs(support_gap_pct) <= near_level_percent and

        support_gap_pct >= (0.0 - breakdown_buffer)

    )

    near_resistance = (

        resistance_gap_pct is not None and

        abs(resistance_gap_pct) <= near_level_percent and

        resistance_gap_pct <= breakout_buffer

    )



    between_sr = (

        support_price is not None

        and resistance_price is not None

        and support_price < resistance_price

        and not above_resistance

        and not below_support

        and price >= support_price

        and price <= resistance_price

    )



    normalized_sr_trend = _normalize_sector_trend(sr_trend_direction)



    trend = 'Unknown / Insufficient Data'

    reason = 'DEFAULT_UNKNOWN'



    if at_or_above_ath or at_or_above_52wh:

        trend = 'Strong Uptrend'

        reason = 'PRICE_AT_OR_ABOVE_ATH_52WH'

    elif near_ath or near_52wh:

        if below_support and bearish_majority:

            trend = 'Downtrend'

            reason = 'NEAR_HIGH_BUT_SUPPORT_BREAKDOWN_BEARISH'

        elif bullish_majority:

            trend = 'Uptrend'

            reason = 'NEAR_HIGH_WITH_BULLISH_EMA'

        elif ema20_pullback_structure:

            trend = 'Pullback in Uptrend'

            reason = 'NEAR_HIGH_PULLBACK_STRUCTURE'

        elif above_resistance:

            trend = 'Uptrend'

            reason = 'NEAR_HIGH_AND_RESISTANCE_BREAKOUT'

        elif not bearish_majority:

            trend = 'Uptrend'

            reason = 'NEAR_HIGH_NO_STRONG_BEARISH_CONFIRMATION'

        else:

            trend = 'Consolidation'

            reason = 'NEAR_HIGH_MIXED_SIGNALS'

    elif above_resistance and bullish_majority:

        trend = 'Uptrend'

        reason = 'RESISTANCE_BREAKOUT_WITH_BULLISH_EMA'

    elif below_support and bearish_majority:

        trend = 'Downtrend'

        reason = 'SUPPORT_BREAKDOWN_WITH_BEARISH_EMA'

    elif near_52wl:

        if bearish_majority or below_52wl:

            trend = 'Downtrend'

            reason = 'NEAR_52WL_WITH_BEARISH_EMA'

        elif near_support and (bullish_majority or ema20_pullback_structure or mixed_ema):

            trend = 'Possible Reversal'

            reason = 'NEAR_52WL_BOUNCING_AT_SUPPORT'

        else:

            trend = 'Possible Reversal'

            reason = 'NEAR_52WL_WITH_NON_BEARISH_STRUCTURE'

    elif near_support and bullish_majority:

        trend = 'Pullback in Uptrend'

        reason = 'NEAR_SUPPORT_WITH_BULLISH_EMA'

    elif near_resistance and not above_resistance:

        trend = 'Consolidation'

        reason = 'NEAR_RESISTANCE_NO_BREAKOUT'

    elif between_sr:

        if mixed_ema:

            trend = 'Sideways'

            reason = 'BETWEEN_SUPPORT_RESISTANCE_MIXED_EMA'

        elif bullish_majority and not bearish_majority:

            trend = 'Consolidation'

            reason = 'BETWEEN_SUPPORT_RESISTANCE_BULLISH_BUT_RANGEBOUND'

        elif bearish_majority and not bullish_majority:

            trend = 'Consolidation'

            reason = 'BETWEEN_SUPPORT_RESISTANCE_BEARISH_BUT_RANGEBOUND'

        else:

            trend = 'Sideways'

            reason = 'BETWEEN_SUPPORT_RESISTANCE'

    elif ema20_pullback_structure and not bearish_majority:

        trend = 'Pullback in Uptrend'

        reason = 'EMA20_PULLBACK_EMA50_100_200_BULLISH'

    elif bullish_majority:

        trend = 'Uptrend'

        reason = 'BULLISH_EMA_MAJORITY'

    elif bearish_majority and (far_below_high or below_52wl or below_support):

        trend = 'Downtrend'

        reason = 'BEARISH_EMA_MAJORITY_WITH_WEAK_PRICE_ACTION'

    elif normalized_sr_trend in {'Uptrend', 'Downtrend', 'Consolidation'}:

        trend = normalized_sr_trend

        reason = 'SR_TREND_FALLBACK'

    elif mixed_ema:

        trend = 'Sideways'

        reason = 'MIXED_EMA_WITHOUT_BREAKOUT_BREAKDOWN'

    elif known_ema_count == 0 and ath is None and high52w is None and low52w is None:

        trend = 'Unknown / Insufficient Data'

        reason = 'INSUFFICIENT_PRICE_ACTION_INPUTS'

    else:

        trend = 'Consolidation'

        reason = 'DEFAULT_CONSOLIDATION'



    trend = _normalize_sector_trend(trend)

    decision = {

        'trend': trend,

        'trendSort': _trend_sort_rank(trend),

        'decisionReason': reason,

        'debug': {

            'sector': sector_name,

            'symbol': symbol,

            'price': price,

            'ath': ath,

            'high52w': high52w,

            'low52w': low52w,

            'gapPct': gap_pct,

            'ema20': ema20 or '-',

            'ema50': ema50 or '-',

            'ema100': ema100 or '-',

            'ema200': ema200 or '-',

            'bullishEmaCount': bullish_count,

            'bearishEmaCount': bearish_count,

            'nearAth': near_ath,

            'near52Wh': near_52wh,

            'near52Wl': near_52wl,

            'support': support_price,

            'resistance': resistance_price,

            'srSource': sr_source or 'NONE',

            'finalTrend': trend,

            'reason': reason,

        },

    }

    return decision





def _pick_first_display(*values: Any) -> str:

    for value in values:

        if value is None:

            continue

        text = str(value).strip()

        if not text:

            continue

        if text.upper() in {'NA', 'N/A'}:

            continue

        return text

    return ''





def _normalize_sr_source(value: Any) -> str | None:

    token = str(value or '').strip().lower()

    if not token:

        return None

    if token.startswith('manual'):

        return 'MANUAL'

    if token in {'generated', 'dynamic', 'computed', 'auto'}:

        return 'DYNAMIC'

    return None





def _level_type_token(value: Any) -> str:

    token = str(value or '').strip().lower()

    if token in {'support', 's'}:

        return 'support'

    if token in {'resistance', 'r'}:

        return 'resistance'

    return ''





def _extract_levels_from_row(row: dict[str, Any], kind: str) -> list[dict[str, Any]]:

    token = kind.strip().lower()

    if token not in {'support', 'resistance'}:

        return []

    keys = (

        ('supportLevels', 'supports', 'SUPPORT_LEVELS')

        if token == 'support'

        else ('resistanceLevels', 'resistances', 'RESISTANCE_LEVELS')

    )

    levels: list[dict[str, Any]] = []

    for key in keys:

        raw_levels = row.get(key)

        if not isinstance(raw_levels, list):

            continue

        for item in raw_levels:

            if not isinstance(item, dict):

                continue

            item_type = _level_type_token(item.get('type'))

            label = str(item.get('label') or '').strip().upper()

            if item_type and item_type != token:

                continue

            if not item_type:

                if token == 'support' and label.startswith('R'):

                    continue

                if token == 'resistance' and label.startswith('S'):

                    continue

            levels.append(item)

    return levels





def _level_source(item: dict[str, Any]) -> str | None:

    source = _normalize_sr_source(item.get('source'))

    if source:

        return source

    manual_flag = item.get('manual')

    if manual_flag is True:

        return 'MANUAL'

    if manual_flag is False:

        return 'DYNAMIC'

    return None





def _pick_preferred_level_price(levels: list[dict[str, Any]], preferred_source: str | None = None) -> tuple[float | None, str]:

    preferred = str(preferred_source or '').strip().upper() or None

    candidates: list[tuple[float, str]] = []

    fallback: list[tuple[float, str]] = []

    for item in levels:

        price = _to_float(item.get('price'))

        if price is None:

            price = _to_float(item.get('level'))

        if price is None:

            continue

        source = _level_source(item) or 'UNKNOWN'

        fallback.append((price, source))

        if preferred and source == preferred:

            candidates.append((price, source))

    if candidates:

        return candidates[0]

    if fallback:

        return fallback[0]

    return (None, 'NONE')





def _parse_level_from_display(display: str) -> float | None:

    text = str(display or '').replace(',', '').strip()

    if not text:

        return None

    match = _FIRST_NUMBER_RE.search(text)

    if not match:

        return None

    return _to_float(match.group(0))





def _resolve_primary_level(

    levels: list[dict[str, Any]],

    display_text: str,

    *,

    preferred_source: str | None,

    fallback_source: str,

) -> tuple[float | None, str]:

    price, source = _pick_preferred_level_price(levels, preferred_source=preferred_source)

    if price is not None:

        return price, source

    parsed = _parse_level_from_display(display_text)

    if parsed is not None:

        return parsed, fallback_source or 'UNKNOWN'

    return None, 'NONE'





def _collect_level_sources(levels: Any) -> set[str]:

    sources: set[str] = set()

    if not isinstance(levels, list):

        return sources

    for level in levels:

        if not isinstance(level, dict):

            continue

        source_token = _normalize_sr_source(level.get('source'))

        if source_token:

            sources.add(source_token)

        manual_flag = level.get('manual')

        if manual_flag is True:

            sources.add('MANUAL')

        elif manual_flag is False:

            sources.add('DYNAMIC')

    return sources





def _resolve_sr_level_source(row: dict[str, Any]) -> str:

    sources: set[str] = set()

    sources.update(_collect_level_sources(row.get('supportLevels') or row.get('supports')))

    sources.update(_collect_level_sources(row.get('resistanceLevels') or row.get('resistances')))

    sources.update(_collect_level_sources(row.get('SUPPORT_LEVELS')))

    sources.update(_collect_level_sources(row.get('RESISTANCE_LEVELS')))

    for key in ('supportSource', 'resistanceSource', 'support_source', 'resistance_source'):

        source_token = _normalize_sr_source(row.get(key))

        if source_token:

            sources.add(source_token)

    if 'MANUAL' in sources and 'DYNAMIC' in sources:

        return 'MIXED'

    if 'MANUAL' in sources:

        return 'MANUAL'

    if 'DYNAMIC' in sources:

        return 'DYNAMIC'

    return 'NONE'





def _build_sector_trend_entry(row: dict[str, Any]) -> dict[str, Any]:

    trend_direction = _normalize_sector_trend(

        row.get('trendDirection') or row.get('trend_direction') or row.get('TREND_DIRECTION')

    )

    support_display = _pick_first_display(

        row.get('supportDisplay'),

        row.get('support_display'),

        row.get('support'),

        row.get('SUPPORT_DISPLAY'),

    )

    resistance_display = _pick_first_display(

        row.get('resistanceDisplay'),

        row.get('resistance_display'),

        row.get('resistance'),

        row.get('RESISTANCE_DISPLAY'),

    )

    sr_level_source = _resolve_sr_level_source(row)

    support_levels = _extract_levels_from_row(row, 'support')

    resistance_levels = _extract_levels_from_row(row, 'resistance')

    support_price, support_source = _resolve_primary_level(

        support_levels,

        support_display,

        preferred_source='MANUAL',

        fallback_source=sr_level_source,

    )

    resistance_price, resistance_source = _resolve_primary_level(

        resistance_levels,

        resistance_display,

        preferred_source='MANUAL',

        fallback_source=sr_level_source,

    )

    return {

        'trendDirection': trend_direction,

        'supportDisplay': support_display,

        'resistanceDisplay': resistance_display,

        'supportPrice': support_price,

        'resistancePrice': resistance_price,

        'supportSource': support_source,

        'resistanceSource': resistance_source,

        'srLevelSource': sr_level_source,

        'trendSort': _trend_sort_rank(trend_direction),

    }





def _has_sr_levels_mv() -> bool:

    cached = _cache.get(_SR_LEVELS_VIEW_EXISTS_CACHE_KEY)

    if isinstance(cached, bool):

        return cached



    conn = get_oracle_connection()

    exists = False

    try:

        with conn.cursor() as cursor:

            cursor.execute('SELECT 1 FROM sr_levels_mv WHERE ROWNUM = 1')

            exists = cursor.fetchone() is not None

    except Exception:

        exists = False

    finally:

        conn.close()



    _cache.set(_SR_LEVELS_VIEW_EXISTS_CACHE_KEY, exists)

    return exists





def _load_sector_wise_trend_map(force_refresh: bool = False) -> dict[str, dict[str, Any]]:

    if not force_refresh:

        cached = _sector_wise_trend_cache.get(_SECTOR_WISE_TREND_CACHE_KEY)

        if isinstance(cached, dict):

            sample = next(iter(cached.values()), None)

            if sample is None or isinstance(sample, dict):

                return cached



    trend_map: dict[str, dict[str, Any]] = {}

    if _has_sr_levels_mv():

        conn = get_oracle_connection()

        try:

            with conn.cursor() as cursor:

                cursor.arraysize = 500

                cursor.execute(

                    """

                    SELECT

                        UPPER(TRIM(symbol)) AS symbol,

                        trend_direction AS trend_direction,

                        support_display AS support_display,

                        resistance_display AS resistance_display

                    FROM sr_levels_mv

                    WHERE timeframe = :timeframe

                      AND tolerance = :tolerance

                    """,

                    {'timeframe': 'daily', 'tolerance': 0.05},

                )

                cols = [str(col[0]) for col in (cursor.description or [])]

                for raw in cursor.fetchall() or []:

                    row = {cols[pos]: _normalize(raw[pos]) for pos in range(len(cols))}

                    symbol = _normalize_symbol_token(row.get('SYMBOL'))

                    if not symbol:

                        continue

                    trend_map[symbol] = _build_sector_trend_entry(row)

        except Exception:

            logger.exception('Failed to load sector-wise trend map from sr_levels_mv')

            trend_map = {}

        finally:

            conn.close()



    if (

        not trend_map

        and SECTOR_WISE_TREND_SR_PAYLOAD_ENABLED

        and _sr_compute_base_payload is not None

        and _sr_get_cached_trading_window is not None

    ):

        try:

            trading_window, _ = _sr_get_cached_trading_window(force_refresh=force_refresh)  # type: ignore[misc]

            base_payload = _sr_compute_base_payload(0.05, 'daily', trading_window, force_refresh=force_refresh)  # type: ignore[misc]

            rows = list(base_payload.get('rows', [])) if isinstance(base_payload, dict) else []

            for row in rows:

                if not isinstance(row, dict):

                    continue

                raw_symbol = row.get('symbol')

                if _sr_normalize_symbol is not None:

                    symbol = _sr_normalize_symbol(raw_symbol)  # type: ignore[misc]

                else:

                    symbol = _normalize_symbol_token(raw_symbol)

                if not symbol:

                    continue

                trend_map[symbol] = _build_sector_trend_entry(row)

        except Exception:

            logger.exception('Failed to load SR trend map for sector-wise stocks')

            trend_map = {}



    _sector_wise_trend_cache.set(_SECTOR_WISE_TREND_CACHE_KEY, trend_map)

    return trend_map





def _compute_gap_pct(price: float | None, ath: float | None) -> float | None:

    if price is None or ath is None or ath == 0:

        return None

    return round(((price - ath) / ath) * 100.0, 2)





def _format_gap(gap_pct: float | None) -> str:

    if gap_pct is None:

        return '-'

    return f'{gap_pct:+.2f}%'





def _compute_ema_flag(price: float | None, ema_value: float | None) -> str:

    if price is None or ema_value is None:

        return 'N'

    return 'Y' if price > ema_value else 'N'





def _normalize_yn_flag(value: Any) -> str | None:

    token = str(value or '').strip().upper()

    if token in {'Y', 'YES', 'TRUE', 'T', '1'}:

        return 'Y'

    if token in {'N', 'NO', 'FALSE', 'F', '0'}:

        return 'N'

    return None





def _coerce_date(value: Any) -> date | None:

    if isinstance(value, datetime):

        return value.date()

    if isinstance(value, date):

        return value

    text = str(value or '').strip()

    if not text:

        return None

    for fmt in ('%Y-%m-%d', '%d-%m-%Y'):

        try:

            return datetime.strptime(text[:10], fmt).date()

        except Exception:

            continue

    return None





def _latest_raw_trading_date() -> date | None:

    cached = _cache.get(_RAW_LATEST_DATE_CACHE_KEY)

    if isinstance(cached, date):

        return cached

    if cached is False:

        return None



    source = _raw_sma_source()

    if not source:

        _cache.set(_RAW_LATEST_DATE_CACHE_KEY, False)

        return None



    table_name, _ = source

    try:

        latest_value = _query_scalar(f'SELECT MAX(TRADING_DATE) FROM {table_name}')

        latest_date = _coerce_date(latest_value)

    except Exception:

        latest_date = None



    _cache.set(_RAW_LATEST_DATE_CACHE_KEY, latest_date if latest_date is not None else False)

    return latest_date





def _latest_snapshot_ltc_date(*, force_refresh: bool = False) -> date | None:

    if not force_refresh:

        cached = _cache.get(_SNAPSHOT_MAX_DATE_CACHE_KEY)

        if isinstance(cached, date):

            return cached

        if cached is False:

            return None

    try:

        max_value = _query_scalar('SELECT MAX(ltc_date) FROM mv_nse_sector_ui_snapshot')

        max_date = _coerce_date(max_value)

    except Exception:

        max_date = None

    _cache.set(_SNAPSHOT_MAX_DATE_CACHE_KEY, max_date if max_date is not None else False)

    return max_date





def _latest_sector_snapshot_row_date(rows: list[dict[str, Any]]) -> date | None:

    latest_date: date | None = None

    for row in rows:

        if not isinstance(row, dict):

            continue

        candidate = _coerce_date(

            row.get('ltcDate')

            or row.get('ltc_date')

            or row.get('latestTradingDate')

            or row.get('tradingDateMax')

        )

        if candidate is not None and (latest_date is None or candidate > latest_date):

            latest_date = candidate

    return latest_date





def _sector_snapshot_matches_raw_latest(

    snapshot_entry: dict[str, Any] | None,

    raw_latest_date: date | None,

) -> tuple[bool, date | None]:

    if not isinstance(snapshot_entry, dict):

        return False, None

    rows = snapshot_entry.get('rows') if isinstance(snapshot_entry.get('rows'), list) else []

    if not rows:

        return False, None

    snapshot_latest = _latest_sector_snapshot_row_date(rows)

    if snapshot_latest is None:

        return False, None

    if raw_latest_date is None:

        return True, snapshot_latest

    return snapshot_latest >= raw_latest_date, snapshot_latest





def _is_sector_snapshot_stale(*, force_refresh: bool = False) -> bool:

    snapshot_date = _latest_snapshot_ltc_date(force_refresh=force_refresh)

    raw_date = _latest_raw_trading_date()

    status = 'CURRENT'

    if raw_date and (snapshot_date is None or raw_date > snapshot_date):

        status = 'STALE'

    logger.info(

        '[SECTOR_SNAPSHOT_FRESHNESS_CHECK] snapshotMaxDate=%s rawMaxDate=%s status=%s',

        snapshot_date.isoformat() if snapshot_date else 'NULL',

        raw_date.isoformat() if raw_date else 'NULL',

        status,

    )

    return status == 'STALE'





def _load_sector_wise_raw_extrema(

    symbols: list[str],

    as_of_date: date | None,

) -> dict[str, dict[str, float | None]]:

    source = _raw_extrema_source()

    if not source:

        return {}

    table_name, symbol_col, trade_col, high_col, low_col = source



    symbol_variants = _symbol_variants(symbols)

    if not symbol_variants:

        return {}



    effective_as_of = as_of_date or datetime.utcnow().date()

    cutoff_date = effective_as_of - timedelta(days=364)

    chunk_size = 800

    result: dict[str, dict[str, float | None]] = {}



    conn = get_oracle_connection()

    try:

        for idx in range(0, len(symbol_variants), chunk_size):

            chunk = symbol_variants[idx:idx + chunk_size]

            binds: dict[str, Any] = {

                'cutoff_date': cutoff_date,

                'as_of_date': effective_as_of,

            }

            placeholders: list[str] = []

            for jdx, symbol in enumerate(chunk):

                bind_name = f'sym_{idx}_{jdx}'

                placeholders.append(f':{bind_name}')

                binds[bind_name] = symbol

            sql = f"""

SELECT

    UPPER(TRIM(t.{symbol_col})) AS "stock",

    MAX(t.{high_col}) AS "ath",

    MAX(CASE WHEN t.{trade_col} >= :cutoff_date THEN t.{high_col} END) AS "high52w",

    MIN(CASE WHEN t.{trade_col} >= :cutoff_date THEN t.{low_col} END) AS "low52w"

FROM {table_name} t

WHERE UPPER(TRIM(t.{symbol_col})) IN ({', '.join(placeholders)})

  AND t.{trade_col} <= :as_of_date

GROUP BY UPPER(TRIM(t.{symbol_col}))

"""

            with conn.cursor() as cursor:

                cursor.arraysize = 500

                cursor.execute(sql, binds)

                cols = [str(col[0]) for col in (cursor.description or [])]

                for raw in cursor.fetchall() or []:

                    row = {cols[pos]: _normalize(raw[pos]) for pos in range(len(cols))}

                    stock = _normalize_symbol_token(row.get('stock'))

                    if not stock:

                        continue

                    result[stock] = {

                        'ath': _to_float(row.get('ath')),

                        'high52w': _to_float(row.get('high52w')),

                        'low52w': _to_float(row.get('low52w')),

                    }

    finally:

        conn.close()

    return result





def _next_ema(

    prev: float | None,

    price: float,

    period: int,

    seed_window: list[float],

) -> float | None:

    """

    Match the EMA page bootstrap in services.trend_service.ema:

    seed the series from the first close, then apply the recursive EMA.

    """

    if prev is None:

        return float(price)



    alpha = 2.0 / (float(period) + 1.0)

    return (float(price) - float(prev)) * alpha + float(prev)





def _load_sector_wise_raw_ema(

    symbols: list[str],

    as_of_date: date | None,

) -> dict[str, dict[str, float | None]]:

    source = _raw_sma_source()

    if not source:

        return {}

    table_name, close_col = source



    symbol_variants = _symbol_variants(symbols)

    if not symbol_variants:

        return {}



    effective_as_of = as_of_date or datetime.utcnow().date()

    chunk_size = 800

    ema_by_symbol: dict[str, dict[str, float | None]] = {}



    conn = get_oracle_connection()

    try:

        for idx in range(0, len(symbol_variants), chunk_size):

            chunk = symbol_variants[idx:idx + chunk_size]

            binds: dict[str, Any] = {'as_of_date': effective_as_of}

            placeholders: list[str] = []

            for jdx, symbol in enumerate(chunk):

                bind_name = f'ema_sym_{idx}_{jdx}'

                placeholders.append(f':{bind_name}')

                binds[bind_name] = symbol

            sql = f"""

SELECT

    UPPER(TRIM(t.symbol)) AS "stock",

    t.trading_date AS "tradingDate",

    t.{close_col} AS "closeVal"

FROM {table_name} t

WHERE UPPER(TRIM(t.symbol)) IN ({', '.join(placeholders)})

  AND t.trading_date <= :as_of_date

  AND t.{close_col} IS NOT NULL

  AND t.trading_date IS NOT NULL

ORDER BY UPPER(TRIM(t.symbol)), t.trading_date

"""

            with conn.cursor() as cursor:

                cursor.arraysize = 1000

                cursor.execute(sql, binds)

                cols = [str(col[0]) for col in (cursor.description or [])]

                ema_state: dict[str, dict[int, float | None]] = {}

                ema_seed_windows: dict[str, dict[int, list[float]]] = {}

                for raw in cursor.fetchall() or []:

                    row = {cols[pos]: _normalize(raw[pos]) for pos in range(len(cols))}

                    stock = _normalize_symbol_token(row.get('stock'))

                    close_val = _to_float(row.get('closeVal'))

                    if not stock or close_val is None:

                        continue

                    state = ema_state.setdefault(stock, {20: None, 50: None, 100: None, 200: None})

                    windows = ema_seed_windows.setdefault(stock, {20: [], 50: [], 100: [], 200: []})

                    state[20] = _next_ema(state[20], close_val, 20, windows[20])

                    state[50] = _next_ema(state[50], close_val, 50, windows[50])

                    state[100] = _next_ema(state[100], close_val, 100, windows[100])

                    state[200] = _next_ema(state[200], close_val, 200, windows[200])

                for stock, state in ema_state.items():

                    ema_by_symbol[stock] = {

                        'ema20': _to_float(state.get(20)),

                        'ema50': _to_float(state.get(50)),

                        'ema100': _to_float(state.get(100)),

                        'ema200': _to_float(state.get(200)),

                    }

    finally:

        conn.close()

    return ema_by_symbol





def _load_sector_wise_raw_latest_trade_rows(

    symbols: list[str],

    as_of_date: date | None,

) -> dict[str, dict[str, Any]]:

    source = _raw_sma_source()

    if not source:

        return {}

    table_name, close_col = source



    symbol_variants = _symbol_variants(symbols)

    if not symbol_variants:

        return {}



    effective_as_of = as_of_date or datetime.utcnow().date()

    chunk_size = 800

    result: dict[str, dict[str, Any]] = {}



    conn = get_oracle_connection()

    try:

        for idx in range(0, len(symbol_variants), chunk_size):

            chunk = symbol_variants[idx:idx + chunk_size]

            binds: dict[str, Any] = {'as_of_date': effective_as_of}

            placeholders: list[str] = []

            for jdx, symbol in enumerate(chunk):

                bind_name = f'dt_sym_{idx}_{jdx}'

                placeholders.append(f':{bind_name}')

                binds[bind_name] = symbol

            sql = f"""

SELECT

    q.stock AS "stock",

    q.trading_date AS "latestDate",

    q.close_val AS "latestClose"

FROM (

    SELECT

        UPPER(TRIM(t.symbol)) AS stock,

        t.trading_date AS trading_date,

        t.{close_col} AS close_val,

        ROW_NUMBER() OVER (

            PARTITION BY UPPER(TRIM(t.symbol))

            ORDER BY t.trading_date DESC NULLS LAST,

                     CASE WHEN t.{close_col} IS NULL THEN 1 ELSE 0 END ASC,

                     t.{close_col} DESC NULLS LAST

        ) AS rn

    FROM {table_name} t

    WHERE UPPER(TRIM(t.symbol)) IN ({', '.join(placeholders)})

      AND t.trading_date <= :as_of_date

) q

WHERE q.rn = 1

"""

            with conn.cursor() as cursor:

                cursor.arraysize = 500

                cursor.execute(sql, binds)

                cols = [str(col[0]) for col in (cursor.description or [])]

                for raw in cursor.fetchall() or []:

                    row = {cols[pos]: _normalize(raw[pos]) for pos in range(len(cols))}

                    stock = _normalize_symbol_token(row.get('stock'))

                    latest_date = _coerce_date(row.get('latestDate'))

                    latest_close = _to_float(row.get('latestClose'))

                    if stock and (latest_date is not None or latest_close is not None):

                        result[stock] = {

                            'latestDate': latest_date,

                            'latestClose': latest_close,

                        }

    finally:

        conn.close()

    return result





def _load_sector_wise_latest_total_mcap(

    symbols: list[str],

) -> dict[str, float]:

    symbol_variants = _symbol_variants(symbols)

    if not symbol_variants:

        return {}



    chunk_size = 800

    result: dict[str, float] = {}

    conn = get_oracle_connection()

    try:

        for idx in range(0, len(symbol_variants), chunk_size):

            chunk = symbol_variants[idx:idx + chunk_size]

            binds: dict[str, Any] = {}

            placeholders: list[str] = []

            for jdx, symbol in enumerate(chunk):

                bind_name = f'mcap_sym_{idx}_{jdx}'

                placeholders.append(f':{bind_name}')

                binds[bind_name] = symbol

            sql = f"""

SELECT

    q.stock AS "stock",

    q.total_mcap_cr AS "totalMcap"

FROM (

    SELECT

        UPPER(TRIM(t.symbol)) AS stock,

        t.total_mcap_cr AS total_mcap_cr,

        ROW_NUMBER() OVER (

            PARTITION BY UPPER(TRIM(t.symbol))

            ORDER BY t.trade_date DESC NULLS LAST, t.fetch_ts DESC NULLS LAST, t.total_mcap_cr DESC NULLS LAST

        ) AS rn

    FROM {_NSE_MCAP_HIST_TABLE} t

    WHERE UPPER(TRIM(t.symbol)) IN ({', '.join(placeholders)})

      AND t.total_mcap_cr IS NOT NULL

) q

WHERE q.rn = 1

"""

            with conn.cursor() as cursor:

                cursor.arraysize = 500

                cursor.execute(sql, binds)

                cols = [str(col[0]) for col in (cursor.description or [])]

                for raw in cursor.fetchall() or []:

                    row = {cols[pos]: _normalize(raw[pos]) for pos in range(len(cols))}

                    stock = _normalize_symbol_token(row.get('stock'))

                    total_mcap = _to_float(row.get('totalMcap'))

                    if stock and total_mcap is not None:

                        result[stock] = total_mcap

    except Exception:

        logger.exception('Failed loading total MCAP fallback from %s', _NSE_MCAP_HIST_TABLE)

        return {}

    finally:

        conn.close()

    return result





def _load_sector_wise_raw_latest_dates(

    symbols: list[str],

    as_of_date: date | None,

) -> dict[str, date]:

    latest_map = _load_sector_wise_raw_latest_trade_rows(symbols, as_of_date)

    result: dict[str, date] = {}

    for stock, payload in latest_map.items():

        if not isinstance(payload, dict):

            continue

        latest_date = _coerce_date(payload.get('latestDate'))

        if latest_date is not None:

            result[stock] = latest_date

    return result





def _sector_wise_sort_value(row: dict[str, Any], sort_key: str) -> Any:

    if sort_key == 'S_NO':

        return row.get('stock')

    if sort_key == 'STOCK':

        return str(row.get('stock') or '')

    if sort_key == 'LTC_DATE':

        return str(row.get('ltcDate') or '')

    if sort_key == 'PRICE':

        return _to_float(row.get('price'))

    if sort_key == 'MCAP':

        return _to_float(row.get('totalMcap'))

    if sort_key == 'MCAP_RANK':

        return _to_float(

            row.get('mcapRank')

            if row.get('mcapRank') is not None

            else row.get('mcap_rank')

        )

    if sort_key == 'INDEX':

        token = _normalize_cap_index_value(row.get('index'))

        order = {'LARGE': 0, 'MID': 1, 'SMALL': 2, '-': 3}

        return order.get(token, 3)

    if sort_key == 'GAP':

        return _to_float(row.get('gapPct'))

    if sort_key == '52WH':

        return _to_float(row.get('high52w'))

    if sort_key == '52WL':

        return _to_float(row.get('low52w'))

    if sort_key == 'ATH':

        return _to_float(row.get('ath'))

    if sort_key == 'EMA20_FLAG':

        return row.get('ema20Flag')

    if sort_key == 'EMA50_FLAG':

        return row.get('ema50Flag')

    if sort_key == 'EMA100_FLAG':

        return row.get('ema100Flag')

    if sort_key == 'EMA200_FLAG':

        return row.get('ema200Flag')

    if sort_key == 'TREND':

        trend_rank = _to_float(

            row.get('trendSort')

            if row.get('trendSort') is not None

            else row.get('trendDirectionSort')

        )

        if trend_rank is not None:

            return int(trend_rank)

        return _trend_sort_rank(row.get('trend'))

    if sort_key == 'SCORE':

        return _to_float(

            row.get('score')

            if row.get('score') is not None

            else row.get('masterScore')

        )

    return row.get('stock')





def _compare_sector_wise_rows(a: dict[str, Any], b: dict[str, Any], sort_key: str, sort_dir: str) -> int:

    va = _sector_wise_sort_value(a, sort_key)

    vb = _sector_wise_sort_value(b, sort_key)

    if va is None and vb is None:

        cmp_val = 0

    elif va is None:

        cmp_val = 1

    elif vb is None:

        cmp_val = -1

    else:

        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):

            cmp_val = -1 if float(va) < float(vb) else (1 if float(va) > float(vb) else 0)

        else:

            sa = str(va).upper()

            sb = str(vb).upper()

            cmp_val = -1 if sa < sb else (1 if sa > sb else 0)

    if sort_dir == 'DESC':

        cmp_val *= -1

    if cmp_val != 0:

        return cmp_val



    sa = str(a.get('stock') or '').upper()

    sb = str(b.get('stock') or '').upper()

    if sa < sb:

        return -1

    if sa > sb:

        return 1

    return 0





def _empty_sector_wise_payload(sector: str, page: int, page_size: int, sort_key: str, sort_dir: str) -> dict[str, Any]:

    return {

        'sector': sector,

        'page': page,

        'pageSize': page_size,

        'totalCount': 0,

        'totalPages': 0,

        'sort': sort_key,

        'dir': sort_dir,

        'rows': [],

    }




def _build_fast_sector_wise_snapshot_payload(

    *,

    sector: str,

    page: int,

    page_size: int,

    sort_key: str,

    sort_dir: str,

    search_text: str,

    snapshot_entry: dict[str, Any],

    source: str,

) -> dict[str, Any]:

    rows = [dict(row) for row in snapshot_entry.get('rows') or [] if isinstance(row, dict)]

    search_token = str(search_text or '').strip().upper()

    if search_token:

        rows = [row for row in rows if search_token in str(row.get('stock') or row.get('symbol') or '').upper()]

    rows.sort(key=cmp_to_key(lambda left, right: _compare_sector_wise_rows(left, right, sort_key, sort_dir)))

    total_count = len(rows)

    page_start = max(0, (page - 1) * page_size)

    page_rows = rows[page_start:page_start + page_size]

    is_stale = source == 'stale_snapshot'

    loaded_at = snapshot_entry.get('loadedAt')

    expires_at = snapshot_entry.get('expiresAt')

    payload = _empty_sector_wise_payload(sector, page, page_size, sort_key, sort_dir)

    payload.update({

        'status': 'success',

        'source': source,

        'tableName': str(snapshot_entry.get('tableName') or '').strip().upper(),

        'sectorName': str(snapshot_entry.get('sectorName') or sector).strip(),

        'totalRows': total_count,

        'totalCount': total_count,

        'stock_count': total_count,

        'totalPages': max(1, math.ceil(total_count / page_size)) if total_count else 0,

        'rows': page_rows,

        'isStale': is_stale,

        'staleReason': 'local_snapshot_expired_revalidating' if is_stale else None,

        'cacheVersion': str(snapshot_entry.get('cacheVersion') or _SECTOR_STOCK_CACHE_VERSION),

        'loadedAt': loaded_at.isoformat() if isinstance(loaded_at, datetime) else loaded_at,

        'expiresAt': expires_at.isoformat() if isinstance(expires_at, datetime) else expires_at,

        'ttlSeconds': int(snapshot_entry.get('ttlSeconds') or _SECTOR_STOCK_CACHE_TTL_SECONDS),

    })

    return payload





def _sector_wise_cache_key(

    *,

    sector: str,

    candidates: list[str],

    page: int,

    page_size: int,

    sort_key: str,

    sort_dir: str,

    search_token: str,

) -> str:

    candidate_token = ','.join(candidates)

    return f'sectorwise:{_SECTOR_STOCK_CACHE_VERSION}:{sector}:{candidate_token}:{page}:{page_size}:{sort_key}:{sort_dir}:{search_token}'





def _sector_stock_full_cache_key(*, table_name: str, sector: str) -> str:

    token = str(table_name or '').strip().upper() or str(sector or '').strip().upper()

    return f'{_SECTOR_STOCK_CACHE_PREFIX}{_SECTOR_STOCK_CACHE_VERSION}::{token}'





def _sector_stock_rows_need_refresh(rows: Any, expected_count: int = 0) -> tuple[bool, str]:

    if not isinstance(rows, list) or not rows:

        return (expected_count > 0, 'empty_rows')

    if expected_count > 0 and len(rows) < expected_count:

        return True, 'partial_rows'

    technical_rows = 0

    blank_primary_rows = 0

    for row in rows:

        if not isinstance(row, dict):

            continue

        if not any(key in row for key in ('index', 'INDEX', 'index_value', 'INDEX_VALUE', 'market_cap_index', 'MARKET_CAP_INDEX')):

            return True, 'missing_index_field'

        if 'totalMcap' not in row and 'mcap' not in row and 'MCAP' not in row:

            return True, 'missing_mcap_field'

        if 'trend' not in row and 'trendDirection' not in row and 'TREND' not in row:

            return True, 'missing_trend_field'

        if SECTOR_WISE_MASTER_SCORE_ENABLED and 'score' not in row and 'masterScore' not in row:

            return True, 'missing_master_score_field'

        if row.get('price') in (None, '') and row.get('ltcDate') in (None, '') and row.get('ath') in (None, ''):

            blank_primary_rows += 1

        # A cached row with a current price/date must include its 52-week range.
        # These values are produced from the same raw DEV candles as the price, so
        # serving a partial cache creates a misleading Sector Wise table instead
        # of letting the existing fallback rebuild it from the canonical source.
        has_current_trade = (
            _to_float(row.get('price')) is not None
            and _coerce_date(row.get('ltcDate') or row.get('ltc_date')) is not None
        )
        if has_current_trade and (
            _to_float(row.get('high52w') or row.get('high_52w')) is None
            or _to_float(row.get('low52w') or row.get('low_52w')) is None
        ):
            return True, 'missing_52_week_range'

        has_technical = any(

            row.get(key) not in (None, '')

            for key in ('price', 'ltcDate', 'ath', 'high52w', 'low52w', 'ema20', 'ema50', 'ema100', 'ema200')

        )

        if has_technical:

            technical_rows += 1

            if not str(row.get('trend') or row.get('trendDirection') or '').strip():

                return True, 'missing_trend'

    if expected_count > 0 and technical_rows == 0:

        return True, 'blank_technical_rows'

    if len(rows) >= 10 and blank_primary_rows >= int(len(rows) * 0.7):

        return True, 'mostly_blank_primary_fields'

    return False, ''


def _publish_sector_wise_local_snapshot(
    *,
    table_name: str,
    sector_name: str,
    rows: list[dict[str, Any]],
    expected_symbols: list[str],
) -> bool:
    expected_members = {
        _normalize_index_lookup_symbol(symbol)
        for symbol in expected_symbols
        if _normalize_index_lookup_symbol(symbol)
    }
    actual_members = {
        _normalize_index_lookup_symbol(row.get('stock') or row.get('symbol'))
        for row in rows
        if isinstance(row, dict) and _normalize_index_lookup_symbol(row.get('stock') or row.get('symbol'))
    }
    if not expected_members:
        logger.warning(
            '[SECTOR_SNAPSHOT_PUBLISH_SKIPPED] table=%s reason=missing_expected_members rows=%s',
            table_name,
            len(rows),
        )
        return False

    rows_invalid, invalid_reason = _sector_stock_rows_need_refresh(rows, len(expected_members))
    if rows_invalid or actual_members != expected_members:
        logger.warning(
            '[SECTOR_SNAPSHOT_PUBLISH_SKIPPED] table=%s reason=%s rows=%s expected=%s actualMembers=%s',
            table_name,
            invalid_reason or 'membership_mismatch',
            len(rows),
            len(expected_members),
            len(actual_members),
        )
        return False

    snapshot_path = sector_stock_cache_service.set_snapshot(
        table_name,
        sector_name=sector_name,
        rows=rows,
        ttl_seconds=None,
    )
    if snapshot_path is None:
        return False
    logger.info('[SECTOR_SNAPSHOT_WRITE] table=%s file=%s rows=%s', table_name, snapshot_path.name, len(rows))
    return True





def _background_enrich_sector_cache(sector_code: str) -> None:

    normalized = str(sector_code or '').strip().upper()

    if not normalized:

        return

    with _SECTOR_FAST_ENRICH_LOCK:

        if normalized in _SECTOR_FAST_ENRICH_INFLIGHT:

            return

        _SECTOR_FAST_ENRICH_INFLIGHT.add(normalized)



    def _worker() -> None:

        try:

            _load_sector_wise_payload(

                sector_code=normalized,

                page=1,

                page_size=_DEFAULT_PAGE_SIZE,

                sort_key='STOCK',

                sort_dir='ASC',

                search_text='',

                force_refresh=True,

                allow_fast_path=False,

            )

            logger.info('[SECTOR_FAST_ENRICH_DONE] sector=%s', normalized)

        except Exception:

            logger.exception('Failed background sector enrichment for %s', normalized)

        finally:

            with _SECTOR_FAST_ENRICH_LOCK:

                _SECTOR_FAST_ENRICH_INFLIGHT.discard(normalized)



    threading.Thread(target=_worker, daemon=True, name=f'fast-enrich:{normalized}').start()




def _write_sector_wise_snapshot_async(sector_code: str, ltc_date: date, rows: list[dict[str, Any]]) -> None:

    normalized = str(sector_code or '').strip().upper()

    snapshot_rows = [dict(row) for row in rows if isinstance(row, dict)]

    if not normalized or not snapshot_rows:

        return

    inflight_key = f'{normalized}:{ltc_date.isoformat()}'

    with _SECTOR_ORACLE_SNAPSHOT_LOCK:

        if inflight_key in _SECTOR_ORACLE_SNAPSHOT_INFLIGHT:

            return

        _SECTOR_ORACLE_SNAPSHOT_INFLIGHT.add(inflight_key)



    def _worker() -> None:

        try:

            write_sector_wise_snapshot(normalized, ltc_date, snapshot_rows)

        except Exception:

            logger.exception('Failed async sector-wise Oracle snapshot write sector=%s', normalized)

        finally:

            with _SECTOR_ORACLE_SNAPSHOT_LOCK:

                _SECTOR_ORACLE_SNAPSHOT_INFLIGHT.discard(inflight_key)



    threading.Thread(

        target=_worker,

        daemon=True,

        name=f'sector-oracle-snapshot:{normalized}',

    ).start()





def _merged_sector_row_key(row: dict[str, Any]) -> str:

    return _normalize_index_lookup_symbol(row.get('stock') or row.get('symbol')) or _normalize_symbol_token(

        row.get('stock') or row.get('symbol')

    )





def _merged_sector_row_score(row: dict[str, Any]) -> int:

    keys = (

        'price',

        'ltcDate',

        'ath',

        'high52w',

        'low52w',

        'ema20',

        'ema50',

        'ema100',

        'ema200',

        'totalMcap',

        'mcapRank',

        'index',

        'trend',

        'score',

    )

    return sum(1 for key in keys if row.get(key) not in (None, ''))





def _dedupe_merged_sector_rows(rows_by_source: list[tuple[str, list[dict[str, Any]]]]) -> list[dict[str, Any]]:

    source_priority = {

        source_code: priority

        for priority, source_code in enumerate(_MERGED_SECTOR_SOURCE_CODES.get('HEALTHCARE', ()))

    }

    merged: dict[str, tuple[int, int, dict[str, Any]]] = {}

    for source_code, rows in rows_by_source:

        priority = source_priority.get(source_code, len(source_priority))

        for row in rows:

            if not isinstance(row, dict):

                continue

            key = _merged_sector_row_key(row)

            if not key:

                continue

            row_copy = dict(row)

            score = _merged_sector_row_score(row_copy)

            existing = merged.get(key)

            if existing is None or score > existing[0] or (score == existing[0] and priority < existing[1]):

                merged[key] = (score, priority, row_copy)

    return [item[2] for item in merged.values()]





def _merged_sector_excluded_symbol_lookups(canonical_sector: str) -> set[str]:

    normalized = str(canonical_sector or '').strip().upper()

    if normalized != 'HEALTHCARE':

        return set()

    return _load_strict_sector_symbol_lookups('PHARMA')





def _apply_merged_sector_exclusions(canonical_sector: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:

    excluded_symbols = _merged_sector_excluded_symbol_lookups(canonical_sector)

    if not excluded_symbols:

        return rows



    filtered_rows: list[dict[str, Any]] = []

    excluded_count = 0

    for row in rows:

        lookup_symbol = _merged_sector_row_key(row)

        if lookup_symbol and lookup_symbol in excluded_symbols:

            excluded_count += 1

            continue

        filtered_rows.append(row)

    if excluded_count:

        logger.info('[SECTOR_MERGED_EXCLUSION] sector=%s excludedRows=%s', canonical_sector, excluded_count)

    return filtered_rows





def _load_merged_sector_wise_payload(

    *,

    canonical_sector: str,

    page: int,

    page_size: int,

    sort_key: str,

    sort_dir: str,

    search_text: str,

    force_refresh: bool = False,

    allow_fast_path: bool = True,

) -> dict[str, Any]:

    normalized_page = _parse_positive_int(page, 1, minimum=1, maximum=10_000)

    normalized_page_size = _normalize_page_size(page_size)

    normalized_sort = _normalize_sector_wise_sort_key(sort_key)

    normalized_dir = _normalize_sort_dir(sort_dir)

    normalized_search_token = _normalize_search_token(search_text)

    filter_token = _MERGED_SECTOR_FILTER_CACHE_TOKENS.get(canonical_sector, '')

    source_codes = _MERGED_SECTOR_SOURCE_CODES.get(canonical_sector, ())

    table_label = _MERGED_SECTOR_TABLE_LABELS.get(canonical_sector, canonical_sector)

    display_name = _MERGED_SECTOR_DISPLAY_NAMES.get(canonical_sector, canonical_sector)

    cache_key = (

        f'merged-sectorwise:{_SECTOR_STOCK_CACHE_VERSION}:{canonical_sector}:{filter_token}:'

        f'{normalized_page}:{normalized_page_size}:{normalized_sort}:{normalized_dir}:{normalized_search_token}'

    )



    if not force_refresh:

        cached = _popup_cache.get(cache_key)

        if isinstance(cached, dict):

            cached_payload = dict(cached)

            cached_payload['source'] = 'merged_cache'

            return cached_payload



    rows_by_source: list[tuple[str, list[dict[str, Any]]]] = []

    source_labels: list[str] = []

    for source_code in source_codes:

        source_payload = _load_sector_wise_payload(

            sector_code=source_code,

            page=1,

            page_size=200,

            sort_key='STOCK',

            sort_dir='ASC',

            search_text='',

            force_refresh=force_refresh,

            allow_fast_path=allow_fast_path,

            merge_sector_groups=False,

        )

        rows = source_payload.get('rows') if isinstance(source_payload.get('rows'), list) else []

        rows_by_source.append((source_code, rows))

        source_label = str(source_payload.get('source') or '').strip()

        if source_label:

            source_labels.append(source_label)



    loaded_rows = _apply_merged_sector_exclusions(canonical_sector, _dedupe_merged_sector_rows(rows_by_source))

    if normalized_search_token:

        filtered_rows = [

            row for row in loaded_rows

            if normalized_search_token in str(row.get('stock') or '').strip().upper()

        ]

    else:

        filtered_rows = list(loaded_rows)



    filtered_rows.sort(key=cmp_to_key(lambda a, b: _compare_sector_wise_rows(a, b, normalized_sort, normalized_dir)))

    total_count = len(filtered_rows)

    total_pages = int(math.ceil(total_count / float(normalized_page_size))) if total_count > 0 else 0

    effective_page = min(max(normalized_page, 1), max(total_pages, 1))

    row_start = (effective_page - 1) * normalized_page_size

    row_end = row_start + normalized_page_size

    page_rows = []

    for idx, row in enumerate(filtered_rows[row_start:row_end], start=row_start + 1):

        row_copy = dict(row)

        row_copy['sNo'] = idx

        page_rows.append(row_copy)



    payload = {

        'status': 'success',

        'sector': canonical_sector,

        'sectorName': display_name,

        'tableName': table_label,

        'sourceTables': [

            _STRICT_SECTOR_TABLE_MAP[source_code]

            for source_code in source_codes

            if source_code in _STRICT_SECTOR_TABLE_MAP

        ],

        'sourceSectors': list(source_codes),

        'page': effective_page,

        'pageSize': normalized_page_size,

        'totalCount': total_count,

        'totalRows': total_count,

        'totalPages': total_pages,

        'sort': normalized_sort,

        'dir': normalized_dir,

        'rows': page_rows,

        'athSource': _ATH_SOURCE_TABLE,

        'source': f"merged:{'+'.join(sorted(set(source_labels)))}" if source_labels else 'merged',

        'cacheVersion': f'{_SECTOR_STOCK_CACHE_VERSION}:{filter_token}' if filter_token else _SECTOR_STOCK_CACHE_VERSION,

        'loadedAt': None,

        'ttlSeconds': _SECTOR_STOCK_CACHE_TTL_SECONDS,

    }

    _popup_cache.set(cache_key, payload)

    logger.info(

        '[SECTOR_MERGED_RESPONSE] sector=%s sourceSectors=%s totalRows=%s pageRows=%s',

        canonical_sector,

        ','.join(source_codes),

        total_count,

        len(page_rows),

    )

    return payload





def _load_sector_wise_payload(

    *,

    sector_code: str,

    page: int,

    page_size: int,

    sort_key: str,

    sort_dir: str,

    search_text: str,

    force_refresh: bool = False,

    allow_fast_path: bool = True,

    merge_sector_groups: bool = True,

) -> dict[str, Any]:

    request_started_at = time.perf_counter()

    normalized_sector = (sector_code or '').strip().upper().replace('-', '_')

    normalized_page = _parse_positive_int(page, 1, minimum=1, maximum=10_000)

    normalized_page_size = _normalize_page_size(page_size)

    normalized_sort = _normalize_sector_wise_sort_key(sort_key)

    normalized_dir = _normalize_sort_dir(sort_dir)

    normalized_search_token = _normalize_search_token(search_text)

    normalized_search_bind = _normalize_search_bind(normalized_search_token)



    if not normalized_sector:

        return _empty_sector_wise_payload('', normalized_page, normalized_page_size, normalized_sort, normalized_dir)



    canonical_merged_sector = _canonical_merged_sector_code(normalized_sector)

    if merge_sector_groups and canonical_merged_sector:

        payload = _load_merged_sector_wise_payload(

            canonical_sector=canonical_merged_sector,

            page=normalized_page,

            page_size=normalized_page_size,

            sort_key=normalized_sort,

            sort_dir=normalized_dir,

            search_text=search_text,

            force_refresh=force_refresh,

            allow_fast_path=allow_fast_path,

        )

        payload['elapsedMs'] = int((time.perf_counter() - request_started_at) * 1000)

        return payload



    candidates = _resolve_sector_candidates(normalized_sector)

    if not candidates:

        return _empty_sector_wise_payload(normalized_sector, normalized_page, normalized_page_size, normalized_sort, normalized_dir)

    sector_table_name = _strict_sector_table_name(normalized_sector)

    strict_symbols = _load_strict_sector_symbols(normalized_sector)

    sector_symbol_count = len(strict_symbols) if isinstance(strict_symbols, list) else 0

    strict_display_map: dict[str, str] = {}

    if isinstance(strict_symbols, list):

        for symbol in strict_symbols:

            display_symbol = str(symbol or '').strip().upper()

            if not display_symbol:

                continue

            display_symbol = 'LTM' if display_symbol == 'LTIM' else display_symbol

            token = _normalize_symbol_token(display_symbol)

            if token:

                strict_display_map[token] = display_symbol

    snapshot_stale = _is_sector_snapshot_stale(force_refresh=force_refresh)

    raw_latest_date = _latest_raw_trading_date() if snapshot_stale else None

    if snapshot_stale:

        logger.warning('[SECTOR_SNAPSHOT_BYPASS] reason=stale_snapshot sector=%s', normalized_sector)

    logger.info(

        '[SECTOR_STOCKS_REQUEST] sector=%s table=%s page=%s pageSize=%s refresh=%s',

        normalized_sector,

        sector_table_name or '-',

        normalized_page,

        normalized_page_size,

        int(bool(force_refresh)),

    )

    if sector_table_name:

        logger.info('[SECTOR_TABLE_VALID] table=%s', sector_table_name)

    logger.info('[SECTOR_SYMBOL_COUNT] table=%s count=%s', sector_table_name or normalized_sector, sector_symbol_count)



    cache_key = _sector_wise_cache_key(

        sector=normalized_sector,

        candidates=candidates,

        page=normalized_page,

        page_size=normalized_page_size,

        sort_key=normalized_sort,

        sort_dir=normalized_dir,

        search_token=normalized_search_token,

    )

    if not force_refresh:

        cached = _popup_cache.get(cache_key)

        if isinstance(cached, dict):

            cached_total = _coerce_int(cached.get('totalRows', cached.get('totalCount')), default=0)

            cached_rows = cached.get('rows') if isinstance(cached.get('rows'), list) else []

            rows_invalid, invalid_reason = _sector_stock_rows_need_refresh(cached_rows, 0)

            if sector_symbol_count > 0 and cached_total < sector_symbol_count:

                invalid_reason = 'partial_rows'

                rows_invalid = True

            if rows_invalid:

                logger.warning(

                    '[SECTOR_CACHE_INVALID] type=page table=%s reason=%s cached=%s expected=%s',

                    sector_table_name or normalized_sector,

                    invalid_reason,

                    cached_total,

                    sector_symbol_count,

                )

                _popup_cache.delete(cache_key)

            else:

                elapsed_ms = int((time.perf_counter() - request_started_at) * 1000)

                logger.info(

                    '[SECTOR_CACHE_HIT] type=memory table=%s rows=%s elapsedMs=%s',

                    sector_table_name or normalized_sector,

                    len(cached.get('rows') or []),

                    elapsed_ms,

                )

                logger.info(

                    '[SECTOR_RESPONSE] table=%s source=%s totalRows=%s pageRows=%s elapsedMs=%s',

                    sector_table_name or normalized_sector,

                    'memory_cache',

                    cached_total,

                    len(cached.get('rows') or []),

                    elapsed_ms,

                )

                cached_payload = dict(cached)

                cached_payload['source'] = 'memory_cache'

                cached_payload['elapsedMs'] = elapsed_ms

                return cached_payload

    cache_table_token = sector_table_name or normalized_sector

    full_cache_key = _sector_stock_full_cache_key(table_name=cache_table_token, sector=normalized_sector)



    if force_refresh:

        logger.info('[SECTOR_CACHE_REFRESH] key=%s table=%s', full_cache_key, cache_table_token)

        sector_cache_service.delete_cache(full_cache_key)

        sector_stock_cache_service.delete_memory_cache(full_cache_key)

        if sector_table_name:

            logger.info(
                '[SECTOR_SNAPSHOT_RETAINED_DURING_REFRESH] table=%s',
                sector_table_name,
            )



    full_entry = None

    source = 'memory_cache'

    memory_entry = sector_stock_cache_service.get_memory_cache(full_cache_key)

    if memory_entry is not None:

        memory_rows = memory_entry.get('rows') if isinstance(memory_entry.get('rows'), list) else []

        rows_invalid, invalid_reason = _sector_stock_rows_need_refresh(memory_rows, sector_symbol_count)

        if rows_invalid:

            logger.warning(

                '[SECTOR_CACHE_INVALID] type=memory table=%s reason=%s cached=%s expected=%s',

                cache_table_token,

                invalid_reason,

                len(memory_rows),

                sector_symbol_count,

            )

            sector_stock_cache_service.delete_memory_cache(full_cache_key)

        else:

            full_entry = {

                'data': memory_rows,

                'loaded_at': memory_entry.get('loadedAt'),

                'expires_at': memory_entry.get('expiresAt'),

                'ttl_seconds': memory_entry.get('ttlSeconds'),

            }

            elapsed_ms = int((time.perf_counter() - request_started_at) * 1000)

            logger.info('[SECTOR_CACHE_HIT] type=memory table=%s rows=%s elapsedMs=%s', cache_table_token, len(full_entry.get('data') or []), elapsed_ms)

    if full_entry is None and sector_table_name:

        snapshot_entry = None if force_refresh else sector_stock_cache_service.get_snapshot(sector_table_name)

        snapshot_source = 'fresh'
        snapshot_stale_but_usable = False

        if snapshot_entry is None and not force_refresh:

            snapshot_entry = sector_stock_cache_service.peek_snapshot(sector_table_name)

            if snapshot_entry is not None:

                snapshot_source = 'expired'

        if snapshot_entry is not None:

            rows = snapshot_entry.get('rows') if isinstance(snapshot_entry.get('rows'), list) else []

            snapshot_reference_date = raw_latest_date

            if snapshot_source == 'expired' and snapshot_reference_date is None:

                snapshot_reference_date = _latest_snapshot_ltc_date()

            if snapshot_stale or snapshot_source == 'expired':

                snapshot_current, snapshot_latest_date = _sector_snapshot_matches_raw_latest(snapshot_entry, snapshot_reference_date)

                if not snapshot_current:

                    if not force_refresh and rows:

                        snapshot_stale_but_usable = True

                        logger.warning(

                            '[SECTOR_STALE_SNAPSHOT_USED] table=%s snapshotLatestDate=%s rawLatestDate=%s rows=%s',

                            sector_table_name,

                            snapshot_latest_date.isoformat() if snapshot_latest_date else 'NULL',

                            snapshot_reference_date.isoformat() if snapshot_reference_date else 'NULL',

                            len(rows),

                        )

                    else:

                        logger.warning(

                            '[SECTOR_SNAPSHOT_FILE_BYPASS] table=%s snapshotLatestDate=%s rawLatestDate=%s',

                            sector_table_name,

                            snapshot_latest_date.isoformat() if snapshot_latest_date else 'NULL',

                            snapshot_reference_date.isoformat() if snapshot_reference_date else 'NULL',

                        )

                        rows = []

            rows_invalid, invalid_reason = _sector_stock_rows_need_refresh(rows, sector_symbol_count)

            if rows_invalid:

                logger.warning(

                    '[SECTOR_SNAPSHOT_INVALID] table=%s reason=%s cached=%s expected=%s',

                    sector_table_name,

                    invalid_reason,

                    len(rows),

                    sector_symbol_count,

                )

                sector_stock_cache_service.delete_snapshot(sector_table_name)

            else:

                ttl_seconds = int(snapshot_entry.get('ttlSeconds') or _SECTOR_STOCK_CACHE_TTL_SECONDS)

                if snapshot_source == 'expired' and not snapshot_stale_but_usable:

                    renewed_snapshot_latest = _latest_sector_snapshot_row_date(rows)

                    sector_stock_cache_service.set_snapshot(

                        sector_table_name,

                        sector_name=normalized_sector,

                        rows=rows,

                        ttl_seconds=ttl_seconds,

                    )

                    logger.info(

                        '[SECTOR_SNAPSHOT_RENEWED] table=%s rows=%s latestDate=%s',

                        sector_table_name,

                        len(rows),

                        renewed_snapshot_latest.isoformat() if renewed_snapshot_latest else 'NULL',

                    )

                memory_ttl_seconds = min(ttl_seconds, _SECTOR_STOCK_CACHE_TTL_SECONDS)

                if snapshot_stale_but_usable:

                    memory_ttl_seconds = min(memory_ttl_seconds, _SECTOR_STALE_SNAPSHOT_CACHE_TTL_SECONDS)

                sector_stock_cache_service.set_memory_cache(

                    full_cache_key,

                    table_name=sector_table_name,

                    sector_name=normalized_sector,

                    rows=rows,

                    ttl_seconds=memory_ttl_seconds,

                )

                full_entry = {

                    'data': rows,

                    'loaded_at': snapshot_entry.get('loadedAt'),

                    'expires_at': snapshot_entry.get('expiresAt'),

                    'ttl_seconds': ttl_seconds,

                }

                source = 'stale_snapshot' if snapshot_stale_but_usable else 'snapshot'

                elapsed_ms = int((time.perf_counter() - request_started_at) * 1000)

                logger.info('[SECTOR_SNAPSHOT_HIT] table=%s rows=%s elapsedMs=%s source=%s', sector_table_name, len(rows), elapsed_ms, snapshot_source)

                logger.info('[SECTOR_SNAPSHOT_USED] rows=%s', len(rows))

        if full_entry is None:

            legacy_entry = sector_cache_service.get_cache(full_cache_key)

            if legacy_entry is not None:

                legacy_rows = legacy_entry.get('data') if isinstance(legacy_entry.get('data'), list) else []

                rows_invalid, invalid_reason = _sector_stock_rows_need_refresh(legacy_rows, sector_symbol_count)

                if rows_invalid:

                    logger.warning(

                        '[SECTOR_CACHE_INVALID] type=legacy table=%s reason=%s cached=%s expected=%s',

                        cache_table_token,

                        invalid_reason,

                        len(legacy_rows),

                        sector_symbol_count,

                    )

                    sector_cache_service.delete_cache(full_cache_key)

                else:

                    full_entry = legacy_entry

                    source = 'memory_cache'

                    elapsed_ms = int((time.perf_counter() - request_started_at) * 1000)

                    logger.info('[SECTOR_CACHE_HIT] type=legacy table=%s rows=%s elapsedMs=%s', cache_table_token, len(legacy_entry.get('data') or []), elapsed_ms)



    if full_entry is None:

        logger.info('[SECTOR_CACHE_MISS] table=%s', cache_table_token)

        db_start = time.perf_counter()

        logger.info('[SECTOR_DB_LOAD_START] table=%s', cache_table_token)

        raw_rows: list[dict[str, Any]] = []

        if snapshot_stale:

            if strict_symbols:

                raw_rows = _build_strict_symbol_fallback_rows(

                    strict_symbols,

                    search_token='',

                )

            source = 'raw_fallback'

        else:

            sql, binds = _build_sector_wise_rows_sql(candidates, strict_symbols)

            query_binds = dict(binds)

            query_binds['search_term'] = None

            raw_rows = _query_rows(sql, query_binds)

        if not raw_rows and strict_symbols:

            raw_rows = _build_strict_symbol_fallback_rows(

                strict_symbols,

                search_token='',

            )

            if source != 'raw_fallback':

                source = 'raw_fallback'

        fast_first_mode = (

            _SECTOR_WISE_FAST_FIRST_RESPONSE_ENABLED

            and allow_fast_path

            and not force_refresh

        )

        if fast_first_mode and sector_symbol_count > 0 and len(raw_rows) < sector_symbol_count:

            logger.warning(

                '[SECTOR_FAST_DISABLED] table=%s reason=partial_snapshot snapshotRows=%s expected=%s',

                cache_table_token,

                len(raw_rows),

                sector_symbol_count,

            )

            fast_first_mode = False

        if fast_first_mode:

            logger.info('[SECTOR_FAST_FIRST_RESPONSE] table=%s rows=%s', cache_table_token, len(raw_rows))

        if source == 'raw_fallback':

            logger.info('[SECTOR_RAW_FALLBACK_REUSE] table=%s rows=%s', cache_table_token, len(raw_rows))

        trend_map = {} if source == 'raw_fallback' else _load_sector_wise_trend_map(force_refresh=force_refresh)

        extrema_fallback_map: dict[str, dict[str, float | None]] = {}

        ema_fallback_map: dict[str, dict[str, float | None]] = {}

        latest_trade_map: dict[str, dict[str, Any]] = {}

        total_mcap_map: dict[str, float] = {}

        needs_extrema_fallback = False

        needs_ema_fallback = False

        fallback_symbols: list[str] = []

        fallback_as_of: date | None = None

        raw_stock_tokens = [

            str(raw.get('stock') or '').strip().upper()

            for raw in raw_rows

            if str(raw.get('stock') or '').strip()

        ]

        has_ltm_raw = any(token == 'LTM' for token in raw_stock_tokens)

        for raw in raw_rows:

            stock = str(raw.get('stock') or '').strip().upper()

            if not stock:

                continue

            fallback_symbols.append(stock)

            ltc_date_value = _coerce_date(raw.get('ltcDate'))

            if ltc_date_value and (fallback_as_of is None or ltc_date_value > fallback_as_of):

                fallback_as_of = ltc_date_value

            if (

                _to_float(raw.get('ath')) is None

                or _to_float(raw.get('high52w')) is None

                or _to_float(raw.get('low52w')) is None

            ):

                needs_extrema_fallback = True

            if (

                _to_float(raw.get('ema20')) is None

                or _to_float(raw.get('ema50')) is None

                or _to_float(raw.get('ema100')) is None

                or _to_float(raw.get('ema200')) is None

            ):

                needs_ema_fallback = True

        if source != 'raw_fallback' and (not fast_first_mode) and needs_extrema_fallback and fallback_symbols:

            extrema_fallback_map = _load_sector_wise_raw_extrema(fallback_symbols, fallback_as_of)

        if source != 'raw_fallback' and (not fast_first_mode) and needs_ema_fallback and fallback_symbols:

            ema_fallback_map = _load_sector_wise_raw_ema(fallback_symbols, fallback_as_of)

        if source != 'raw_fallback' and (not fast_first_mode) and fallback_symbols:

            latest_trade_map = _load_sector_wise_raw_latest_trade_rows(fallback_symbols, datetime.utcnow().date())

        if source != 'raw_fallback' and fallback_symbols:

            total_mcap_map = _load_sector_wise_latest_total_mcap(fallback_symbols)

        index_map: dict[str, str] = {}

        mcap_rank_map: dict[str, int] = {}

        index_source = 'none'

        if source != 'raw_fallback' and fallback_symbols:

            index_map, mcap_rank_map, index_source = _load_sector_wise_latest_index_map(fallback_symbols)

            logger.info('[SECTOR_INDEX_JOIN] source=%s rowsMatched=%s', index_source, len(index_map))

        authoritative_ath_records: dict[str, dict[str, Any]] = {}

        if source != 'raw_fallback' and (not fast_first_mode) and fallback_symbols and _SECTOR_WISE_USE_AUTHORITATIVE_ATH:

            try:

                authoritative_ath_records = get_all_time_high_for_symbols(

                    fallback_symbols,

                    include_date=True,

                    endpoint='/api/sector/sector-wise',

                )

            except Exception:

                logger.exception('Failed to load authoritative ATH map for sector-wise payload')

                authoritative_ath_records = {}



        rows: list[dict[str, Any]] = []

        stale_ath_detected = False

        missing_index_symbols_logged: set[tuple[str, str]] = set()

        for raw in raw_rows:

            raw_stock = str(raw.get('stock') or '').strip().upper()

            if not raw_stock:

                continue

            if raw_stock == 'LTIM' and has_ltm_raw:

                continue

            stock_source_key = _normalize_symbol_token('LTM' if raw_stock == 'LTIM' else raw_stock)

            stock = strict_display_map.get(stock_source_key, 'LTM' if raw_stock == 'LTIM' else raw_stock)

            price = _to_float(raw.get('price'))

            fallback_metrics = extrema_fallback_map.get(stock_source_key, {})

            fallback_ema = ema_fallback_map.get(stock_source_key, {})

            ath = _to_float(raw.get('ath'))

            ath_record = authoritative_ath_records.get(stock_source_key) or {}

            authoritative_ath = _to_float(ath_record.get('ath'))

            ath_date = ath_record.get('ath_date')

            if authoritative_ath is not None:

                if ath is not None and abs(float(ath) - float(authoritative_ath)) > 0.0001:

                    stale_ath_detected = True

                ath = authoritative_ath

            high52w = _to_float(raw.get('high52w'))

            low52w = _to_float(raw.get('low52w'))

            if ath is None:

                ath = _to_float(fallback_metrics.get('ath'))

            if high52w is None:

                high52w = _to_float(fallback_metrics.get('high52w'))

            if low52w is None:

                low52w = _to_float(fallback_metrics.get('low52w'))

            ema20 = _to_float(raw.get('ema20'))

            ema50 = _to_float(raw.get('ema50'))

            ema100 = _to_float(raw.get('ema100'))

            ema200 = _to_float(raw.get('ema200'))

            if ema20 is None:

                ema20 = _to_float(fallback_ema.get('ema20'))

            if ema50 is None:

                ema50 = _to_float(fallback_ema.get('ema50'))

            if ema100 is None:

                ema100 = _to_float(fallback_ema.get('ema100'))

            if ema200 is None:

                ema200 = _to_float(fallback_ema.get('ema200'))

            ema20_flag_raw = _normalize_yn_flag(raw.get('ema20FlagRaw'))

            ema50_flag_raw = _normalize_yn_flag(raw.get('ema50FlagRaw'))

            ema100_flag_raw = _normalize_yn_flag(raw.get('ema100FlagRaw'))

            ema200_flag_raw = _normalize_yn_flag(raw.get('ema200FlagRaw'))

            ema20_flag = _compute_ema_flag(price, ema20) if ema20 is not None else (ema20_flag_raw or 'N')

            ema50_flag = _compute_ema_flag(price, ema50) if ema50 is not None else (ema50_flag_raw or 'N')

            ema100_flag = _compute_ema_flag(price, ema100) if ema100 is not None else (ema100_flag_raw or 'N')

            ema200_flag = _compute_ema_flag(price, ema200) if ema200 is not None else (ema200_flag_raw or 'N')

            ema20_flag_for_trend = _resolve_ema_flag_for_trend(price=price, ema_value=ema20, raw_flag=raw.get('ema20FlagRaw'))

            ema50_flag_for_trend = _resolve_ema_flag_for_trend(price=price, ema_value=ema50, raw_flag=raw.get('ema50FlagRaw'))

            ema100_flag_for_trend = _resolve_ema_flag_for_trend(price=price, ema_value=ema100, raw_flag=raw.get('ema100FlagRaw'))

            ema200_flag_for_trend = _resolve_ema_flag_for_trend(price=price, ema_value=ema200, raw_flag=raw.get('ema200FlagRaw'))

            gap_pct_for_trend = _compute_gap_pct(price, ath)

            ltc_date = raw.get('ltcDate')

            ltc_date_value = _coerce_date(ltc_date)

            latest_trade = latest_trade_map.get(stock_source_key) if isinstance(latest_trade_map, dict) else None

            latest_raw_date = _coerce_date((latest_trade or {}).get('latestDate')) if isinstance(latest_trade, dict) else None

            latest_raw_close = _to_float((latest_trade or {}).get('latestClose')) if isinstance(latest_trade, dict) else None

            total_mcap = _to_float(raw.get('totalMcap'))

            if total_mcap is None:

                total_mcap = _to_float(total_mcap_map.get(stock_source_key))

            index_lookup_symbol = _normalize_index_lookup_symbol(stock)

            raw_mcap_rank_value = _coerce_int(

                raw.get('mcapRank')

                if raw.get('mcapRank') is not None

                else raw.get('mcap_rank'),

                default=0,

            )

            if source == 'raw_fallback':

                index_value = _normalize_cap_index_value(raw.get('index'), raw_mcap_rank_value)

                mcap_rank_value = raw_mcap_rank_value

            else:

                index_raw_value = index_map.get(index_lookup_symbol) if index_lookup_symbol else None

                index_value = _normalize_cap_index_value(index_raw_value)

                mcap_rank_value = _coerce_int(mcap_rank_map.get(index_lookup_symbol) if index_lookup_symbol else None, default=0)

            mcap_rank = mcap_rank_value if mcap_rank_value > 0 else None

            if stock in _INDEX_SYMBOL_EXCLUDE_SET:

                index_value = '-'

            if index_value == '-' and stock not in _INDEX_SYMBOL_EXCLUDE_SET:

                log_key = (stock, index_lookup_symbol)

                if log_key not in missing_index_symbols_logged:

                    missing_index_symbols_logged.add(log_key)

                    logger.info(

                        '[SECTOR_INDEX_MISSING] symbol=%s normalized_symbol=%s source=%s fallback=%s',

                        stock,

                        index_lookup_symbol or '-',

                        index_source,

                        index_value,

                    )

            if latest_raw_date is not None and (ltc_date_value is None or latest_raw_date > ltc_date_value):

                ltc_date_text = latest_raw_date.isoformat()

                if latest_raw_close is not None:

                    price = latest_raw_close

            else:

                ltc_date_text = str(ltc_date)[:10] if ltc_date is not None else ''

                if price is None and latest_raw_close is not None:

                    price = latest_raw_close

            gap_pct = _compute_gap_pct(price, ath)

            trend_meta = trend_map.get(stock_source_key)

            if isinstance(trend_meta, dict):

                trend_source = str(trend_meta.get('srLevelSource') or 'NONE').strip().upper() or 'NONE'

                support_display = _pick_first_display(trend_meta.get('supportDisplay')) or '-'

                resistance_display = _pick_first_display(trend_meta.get('resistanceDisplay')) or '-'

                support_price = _to_float(trend_meta.get('supportPrice'))

                resistance_price = _to_float(trend_meta.get('resistancePrice'))

                support_source = str(trend_meta.get('supportSource') or 'NONE').strip().upper() or 'NONE'

                resistance_source = str(trend_meta.get('resistanceSource') or 'NONE').strip().upper() or 'NONE'

                sr_trend_direction = _normalize_sector_trend(trend_meta.get('trendDirection'))

            else:

                trend_source = 'NONE'

                support_display = '-'

                resistance_display = '-'

                support_price = None

                resistance_price = None

                support_source = 'NONE'

                resistance_source = 'NONE'

                sr_trend_direction = None



            trend_decision = calculate_sector_stock_trend(

                sector_name=normalized_sector,

                symbol=stock,

                price=price,

                ath=ath,

                high52w=high52w,

                low52w=low52w,

                gap_pct=gap_pct_for_trend,

                ema20_flag=ema20_flag_for_trend,

                ema50_flag=ema50_flag_for_trend,

                ema100_flag=ema100_flag_for_trend,

                ema200_flag=ema200_flag_for_trend,

                support_price=support_price,

                resistance_price=resistance_price,

                sr_source=trend_source,

                sr_trend_direction=sr_trend_direction,

            )

            trend_direction = _normalize_sector_trend(trend_decision.get('trend'))

            trend_sort_value = _to_float(trend_decision.get('trendSort'))

            trend_sort = int(trend_sort_value) if trend_sort_value is not None else _trend_sort_rank(trend_direction)

            decision_reason = str(trend_decision.get('decisionReason') or '').strip() or 'NA'



            if SECTOR_WISE_TREND_DEBUG and logger.isEnabledFor(logging.DEBUG):

                trend_debug = trend_decision.get('debug') if isinstance(trend_decision, dict) else {}

                if not isinstance(trend_debug, dict):

                    trend_debug = {}

                logger.debug(

                    'sector-wise trend sector=%s symbol=%s price=%s ath=%s high52w=%s low52w=%s gap=%s '

                    'ema20=%s ema50=%s ema100=%s ema200=%s bullish=%s bearish=%s '

                    'near_ath=%s near_52wh=%s near_52wl=%s support=%s resistance=%s '

                    'support_source=%s resistance_source=%s sr_source=%s final_trend=%s reason=%s',

                    trend_debug.get('sector', normalized_sector),

                    trend_debug.get('symbol', stock),

                    trend_debug.get('price', price),

                    trend_debug.get('ath', ath),

                    trend_debug.get('high52w', high52w),

                    trend_debug.get('low52w', low52w),

                    trend_debug.get('gapPct', gap_pct),

                    trend_debug.get('ema20', ema20_flag_for_trend or '-'),

                    trend_debug.get('ema50', ema50_flag_for_trend or '-'),

                    trend_debug.get('ema100', ema100_flag_for_trend or '-'),

                    trend_debug.get('ema200', ema200_flag_for_trend or '-'),

                    trend_debug.get('bullishEmaCount', 0),

                    trend_debug.get('bearishEmaCount', 0),

                    trend_debug.get('nearAth', False),

                    trend_debug.get('near52Wh', False),

                    trend_debug.get('near52Wl', False),

                    trend_debug.get('support', support_price),

                    trend_debug.get('resistance', resistance_price),

                    support_source,

                    resistance_source,

                    trend_debug.get('srSource', trend_source),

                    trend_debug.get('finalTrend', trend_direction),

                    trend_debug.get('reason', decision_reason),

                )

            row_payload = {

                'stock': stock,

                'ltcDate': ltc_date_text,

                'ltc_date': ltc_date_text,

                'price': price,

                'totalMcap': total_mcap,

                'mcap': total_mcap,

                'MCAP': total_mcap,

                'mcapRank': mcap_rank,

                'mcap_rank': mcap_rank,

                'MCAP_RANK': mcap_rank,

                'market_cap_rank': mcap_rank,

                'rank': mcap_rank,

                'index': index_value,

                'INDEX': index_value,

                'index_value': index_value,

                'INDEX_VALUE': index_value,

                'market_cap_index': index_value,

                'MARKET_CAP_INDEX': index_value,

                'ema20': ema20,

                'ema50': ema50,

                'ema100': ema100,

                'ema200': ema200,

                'gapPct': gap_pct,

                'gap': _format_gap(gap_pct),

                'high52w': high52w,

                'low52w': low52w,

                'ath': ath,

                'athDate': ath_date,

                'ath_date': ath_date,

                'athSource': _ATH_SOURCE_TABLE,

                'ema20Flag': ema20_flag,

                'ema50Flag': ema50_flag,

                'ema100Flag': ema100_flag,

                'ema200Flag': ema200_flag,

                'trend': trend_direction,

                'trendDirection': trend_direction,

                'trendSort': trend_sort,

                'trendDirectionSort': trend_sort,

                'trendDecisionReason': decision_reason,

                'trendSource': trend_source,

                'trendSupport': support_display if support_display != '-' else '',

                'trendResistance': resistance_display if resistance_display != '-' else '',

                'supportPrice': support_price,

                'resistancePrice': resistance_price,

                'supportSource': support_source,

                'resistanceSource': resistance_source,

            }

            rows.append(_apply_sector_master_score(

                row_payload,

                sr_context={

                    'supportPrice': support_price,

                    'resistancePrice': resistance_price,

                    'trendDirection': sr_trend_direction,

                    'srSource': trend_source,

                },

            ))



        if fast_first_mode and strict_symbols:

            existing_symbols = {

                _normalize_index_lookup_symbol(row.get('stock') or row.get('symbol'))

                for row in rows

                if isinstance(row, dict) and _normalize_index_lookup_symbol(row.get('stock') or row.get('symbol'))

            }

            missing_symbols = [

                symbol

                for symbol in strict_symbols

                if _normalize_index_lookup_symbol(symbol) and _normalize_index_lookup_symbol(symbol) not in existing_symbols

            ]

            if missing_symbols:

                minimal_rows = _build_minimal_sector_symbol_rows(missing_symbols)

                rows.extend(minimal_rows)

                logger.warning(

                    '[SECTOR_FAST_PARTIAL_SUPPLEMENT] table=%s baseCount=%s snapshotRows=%s minimalRows=%s',

                    sector_table_name or normalized_sector,

                    sector_symbol_count,

                    len(existing_symbols),

                    len(minimal_rows),

                )



        tech_join_count = 0

        trend_unknown_count = 0

        for row in rows:

            has_tech = any(

                row.get(key) is not None

                for key in ('price', 'ath', 'high52w', 'low52w', 'ema20', 'ema50', 'ema100', 'ema200')

            )

            if has_tech:

                tech_join_count += 1

            if _trend_token(row.get('trend')) == 'UNKNOWN / INSUFFICIENT DATA':

                trend_unknown_count += 1

                missing_fields: list[str] = []

                for field in ('price', 'ema20', 'ema50', 'ema100', 'ema200'):

                    if row.get(field) is None:

                        missing_fields.append(field)

                logger.info(

                    '[SECTOR_TREND_DATA_MISSING] symbol=%s missing=%s',

                    str(row.get('stock') or ''),

                    ','.join(missing_fields) if missing_fields else 'insufficient_signal',

                )

        logger.info('[SECTOR_TECH_JOIN_COUNT] table=%s count=%s', sector_table_name or normalized_sector, tech_join_count)

        logger.info(

            '[SECTOR_TECH_JOIN] table=%s rowsMatched=%s trendUnknown=%s',

            sector_table_name or normalized_sector,

            tech_join_count,

            trend_unknown_count,

        )

        logger.info('[SECTOR_TREND_UNKNOWN_COUNT] table=%s count=%s', sector_table_name or normalized_sector, trend_unknown_count)



        if stale_ath_detected:

            log_stale_snapshot_warning(endpoint='/api/sector/sector-wise', source='snapshot-ath-mismatch')



        full_entry = sector_cache_service.set_cache(full_cache_key, rows, _SECTOR_STOCK_CACHE_TTL_SECONDS)

        sector_stock_cache_service.set_memory_cache(

            full_cache_key,

            table_name=cache_table_token,

            sector_name=normalized_sector,

            rows=rows,

            ttl_seconds=_SECTOR_STOCK_CACHE_TTL_SECONDS,

        )

        if source == 'raw_fallback':

            source = 'db'

        else:

            source = 'db_fast' if fast_first_mode else 'db'

        elapsed_ms = int((time.perf_counter() - db_start) * 1000)

        logger.info('[SECTOR_DB_LOAD_SUCCESS] table=%s rows=%s elapsedMs=%s', cache_table_token, len(rows), elapsed_ms)

        if fast_first_mode and _SECTOR_WISE_BACKGROUND_ENRICH_ENABLED:

            _background_enrich_sector_cache(normalized_sector)

    else:

        cached_rows = full_entry.get('data') if isinstance(full_entry, dict) else []

        if source not in {'memory_cache', 'snapshot', 'stale_snapshot'}:

            source = 'memory_cache'

        logger.info('[SECTOR_CACHE_HIT] type=%s table=%s rows=%s', source, cache_table_token, len(cached_rows) if isinstance(cached_rows, list) else 0)



    loaded_rows = full_entry.get('data') if isinstance(full_entry, dict) else []

    if not isinstance(loaded_rows, list):

        loaded_rows = []

    rank_backfill_count = _backfill_sector_wise_mcap_ranks(loaded_rows)

    if rank_backfill_count:

        full_entry = sector_cache_service.set_cache(

            full_cache_key,

            loaded_rows,

            _SECTOR_STOCK_CACHE_TTL_SECONDS,

        )

        sector_stock_cache_service.set_memory_cache(

            full_cache_key,

            table_name=cache_table_token,

            sector_name=normalized_sector,

            rows=loaded_rows,

            ttl_seconds=_SECTOR_STOCK_CACHE_TTL_SECONDS,

        )

    if strict_symbols and source != 'db_fast':

        existing_symbols = {

            _normalize_index_lookup_symbol(row.get('stock') or row.get('symbol'))

            for row in loaded_rows

            if isinstance(row, dict) and _normalize_index_lookup_symbol(row.get('stock') or row.get('symbol'))

        }

        missing_symbols = [

            symbol

            for symbol in strict_symbols

            if _normalize_index_lookup_symbol(symbol) and _normalize_index_lookup_symbol(symbol) not in existing_symbols

        ]

        if missing_symbols:

            fallback_rows = _build_strict_symbol_fallback_rows(missing_symbols, search_token='')

            if fallback_rows:

                loaded_rows = list(loaded_rows) + fallback_rows

                full_entry = sector_cache_service.set_cache(

                    full_cache_key,

                    loaded_rows,

                    _SECTOR_STOCK_CACHE_TTL_SECONDS,

                )

                sector_stock_cache_service.set_memory_cache(

                    full_cache_key,

                    table_name=cache_table_token,

                    sector_name=normalized_sector,

                    rows=loaded_rows,

                    ttl_seconds=_SECTOR_STOCK_CACHE_TTL_SECONDS,

                )

                logger.warning(

                    '[SECTOR_DB_RESULT_PARTIAL_FALLBACK] table=%s baseCount=%s existingRows=%s fallbackRows=%s',

                    sector_table_name or normalized_sector,

                    sector_symbol_count,

                    len(existing_symbols),

                    len(fallback_rows),

                )

    if not loaded_rows and strict_symbols and source != 'db_fast':

        loaded_rows = _build_strict_symbol_fallback_rows(strict_symbols, search_token='')

        full_entry = sector_cache_service.set_cache(

            full_cache_key,

            loaded_rows,

            _SECTOR_STOCK_CACHE_TTL_SECONDS,

        )

        sector_stock_cache_service.set_memory_cache(

            full_cache_key,

            table_name=cache_table_token,

            sector_name=normalized_sector,

            rows=loaded_rows,

            ttl_seconds=_SECTOR_STOCK_CACHE_TTL_SECONDS,

        )

        source = 'db'

        logger.warning(

            '[SECTOR_DB_RESULT_EMPTY_FALLBACK] table=%s baseCount=%s fallbackRows=%s',

            sector_table_name or normalized_sector,

            sector_symbol_count,

            len(loaded_rows),

        )



    if sector_table_name and source == 'db':

        _publish_sector_wise_local_snapshot(
            table_name=sector_table_name,
            sector_name=normalized_sector,
            rows=loaded_rows,
            expected_symbols=strict_symbols or [],
        )

    loaded_rows = _dedupe_canonical_sector_rows(loaded_rows)

    if normalized_search_token:

        filtered_rows = [

            row for row in loaded_rows

            if normalized_search_token in str(row.get('stock') or '').strip().upper()

        ]

    else:

        filtered_rows = list(loaded_rows)



    filtered_rows.sort(key=cmp_to_key(lambda a, b: _compare_sector_wise_rows(a, b, normalized_sort, normalized_dir)))

    total_count = len(filtered_rows)

    total_pages = int(math.ceil(total_count / float(normalized_page_size))) if total_count > 0 else 0

    effective_page = min(max(normalized_page, 1), max(total_pages, 1))

    row_start = (effective_page - 1) * normalized_page_size

    row_end = row_start + normalized_page_size

    page_rows = []

    for idx, row in enumerate(filtered_rows[row_start:row_end], start=row_start + 1):

        row_copy = dict(row)

        row_copy['sNo'] = idx

        page_rows.append(row_copy)



    loaded_at = full_entry.get('loaded_at') if isinstance(full_entry, dict) else None

    if isinstance(loaded_at, datetime):

        loaded_at_text = loaded_at.strftime('%Y-%m-%d %H:%M:%S')

    elif loaded_at is not None:

        loaded_at_text = str(loaded_at).strip() or None

    else:

        loaded_at_text = None



    payload = {

        'status': 'success',

        'sector': normalized_sector,

        'sectorName': normalized_sector,

        'page': effective_page,

        'pageSize': normalized_page_size,

        'totalCount': total_count,

        'totalRows': total_count,

        'totalPages': total_pages,

        'sort': normalized_sort,

        'dir': normalized_dir,

        'rows': page_rows,

        'athSource': _ATH_SOURCE_TABLE,

        'source': source,

        'isStale': source == 'stale_snapshot',

        'staleReason': 'snapshot_behind_latest_raw_date' if source == 'stale_snapshot' else None,

        'cacheVersion': _SECTOR_STOCK_CACHE_VERSION,

        'loadedAt': loaded_at_text,

        'ttlSeconds': _SECTOR_STOCK_CACHE_TTL_SECONDS,

        'elapsedMs': int((time.perf_counter() - request_started_at) * 1000),

    }

    _popup_cache.set(cache_key, payload)

    logger.info(

        '[SECTOR_RESPONSE] table=%s source=%s totalRows=%s pageRows=%s elapsedMs=%s',

        cache_table_token,

        source,

        total_count,

        len(page_rows),

        payload['elapsedMs'],

    )

    return payload





def _load_dynamic_sector_table_payload(

    *,

    table_name: str,

    sector_name: str,

    page: int,

    page_size: int,

    sort_key: str,

    sort_dir: str,

    search_text: str,

    force_refresh: bool = False,

    allow_fast_path: bool = True,

) -> dict[str, Any]:

    normalized_table = _to_safe_oracle_name(table_name)

    if not normalized_table:

        return {

            'status': 'error',

            'message': 'Invalid sector table name.',

            'tableName': '',

            'sectorName': '',

            'page': 1,

            'pageSize': _DEFAULT_PAGE_SIZE,

            'totalRows': 0,

            'rows': [],

        }



    columns = _load_sector_table_columns(normalized_table)

    if 'SYMBOL' not in columns:

        return {

            'status': 'error',

            'message': 'Selected table is not a valid sector staging table.',

            'tableName': normalized_table,

            'sectorName': sector_name,

            'page': 1,

            'pageSize': _DEFAULT_PAGE_SIZE,

            'totalRows': 0,

            'rows': [],

        }



    normalized_page = _parse_positive_int(page, 1, minimum=1, maximum=10_000)

    normalized_page_size = _parse_positive_int(page_size, 25, minimum=1, maximum=500)

    normalized_search = str(search_text or '').strip().upper()

    normalized_sort = str(sort_key or 'SYMBOL').strip().upper()

    normalized_dir = _normalize_sort_dir(sort_dir)



    sortable_columns = {key: value for key, value in _DYNAMIC_SORT_COLS.items() if key in columns or key == 'SYMBOL'}

    if normalized_sort not in sortable_columns:

        normalized_sort = 'SYMBOL'



    select_columns: list[tuple[str, str]] = [('SYMBOL', 'symbol')]

    if 'COMPANY_NAME' in columns:

        select_columns.append(('COMPANY_NAME', 'companyName'))

    if 'SECTOR' in columns:

        select_columns.append(('SECTOR', 'sector'))

    if 'INDUSTRY' in columns:

        select_columns.append(('INDUSTRY', 'industry'))

    if 'SERIES' in columns:

        select_columns.append(('SERIES', 'series'))

    if 'ISIN_CODE' in columns:

        select_columns.append(('ISIN_CODE', 'isinCode'))

    if 'ACTIVE_FLAG' in columns:

        select_columns.append(('ACTIVE_FLAG', 'activeFlag'))

    if 'UPDATED_DATE' in columns:

        select_columns.append(('UPDATED_DATE', 'updatedDate'))

    if 'CREATED_DATE' in columns:

        select_columns.append(('CREATED_DATE', 'createdDate'))



    full_cache_key = f'{_SECTOR_STOCK_CACHE_PREFIX}{normalized_table}'

    if force_refresh:

        logger.info('[SECTOR_CACHE_REFRESH] table=%s', normalized_table)

        sector_cache_service.delete_cache(full_cache_key)

    full_entry = sector_cache_service.get_cache(full_cache_key)

    source = 'cache'

    if full_entry is None:

        logger.info('[SECTOR_CACHE_MISS] table=%s', normalized_table)

        db_start = time.perf_counter()

        logger.info('[SECTOR_DB_LOAD_START] table=%s', normalized_table)

        select_sql_cols = ', '.join([f"{col} AS \"{alias}\"" for col, alias in select_columns])

        data_sql = f"""

        SELECT {select_sql_cols}

        FROM {normalized_table}

        WHERE symbol IS NOT NULL

          AND TRIM(symbol) IS NOT NULL

        """

        rows = _query_rows(data_sql, {})

        full_entry = sector_cache_service.set_cache(

            full_cache_key,

            rows,

            _SECTOR_STOCK_CACHE_TTL_SECONDS,

        )

        source = 'db'

        elapsed_ms = int((time.perf_counter() - db_start) * 1000)

        logger.info('[SECTOR_DB_LOAD_SUCCESS] table=%s rows=%s elapsedMs=%s', normalized_table, len(rows), elapsed_ms)

    else:

        cached_rows = full_entry.get('data') if isinstance(full_entry, dict) else []

        logger.info('[SECTOR_CACHE_HIT] table=%s rows=%s', normalized_table, len(cached_rows) if isinstance(cached_rows, list) else 0)



    loaded_rows = full_entry.get('data') if isinstance(full_entry, dict) else []

    if not isinstance(loaded_rows, list):

        loaded_rows = []

    filtered_rows = list(loaded_rows)

    if normalized_search:

        filtered_rows = [

            row for row in filtered_rows

            if normalized_search in str(row.get('symbol') or '').strip().upper()

            or normalized_search in str(row.get('companyName') or '').strip().upper()

        ]



    reverse_sort = normalized_dir == 'DESC'

    if normalized_sort == 'SYMBOL':

        filtered_rows.sort(key=lambda row: str(row.get('symbol') or '').strip().upper(), reverse=reverse_sort)

    elif normalized_sort in {'COMPANY_NAME', 'SECTOR', 'INDUSTRY', 'SERIES', 'ISIN_CODE'}:

        alias_map = {

            'COMPANY_NAME': 'companyName',

            'SECTOR': 'sector',

            'INDUSTRY': 'industry',

            'SERIES': 'series',

            'ISIN_CODE': 'isinCode',

        }

        alias_name = alias_map.get(normalized_sort, 'companyName')

        filtered_rows.sort(key=lambda row: str(row.get(alias_name) or '').strip().upper(), reverse=reverse_sort)

    else:

        alias_map = {

            'UPDATED_DATE': 'updatedDate',

            'CREATED_DATE': 'createdDate',

        }

        alias_name = alias_map.get(normalized_sort, 'symbol')

        filtered_rows.sort(key=lambda row: str(row.get(alias_name) or ''), reverse=reverse_sort)



    total_rows = len(filtered_rows)

    total_pages = int(math.ceil(total_rows / float(normalized_page_size))) if total_rows > 0 else 0

    effective_page = min(max(normalized_page, 1), max(total_pages, 1))

    row_start = (effective_page - 1) * normalized_page_size

    row_end = row_start + normalized_page_size

    page_rows = filtered_rows[row_start:row_end]



    loaded_at = full_entry.get('loaded_at') if isinstance(full_entry, dict) else None

    loaded_at_text = loaded_at.strftime('%Y-%m-%d %H:%M:%S') if isinstance(loaded_at, datetime) else None



    return {

        'status': 'success',

        'source': source,

        'tableName': normalized_table,

        'sectorName': sector_name,

        'totalRows': total_rows,

        'totalPages': total_pages,

        'page': effective_page,

        'pageSize': normalized_page_size,

        'loadedAt': loaded_at_text,

        'ttlSeconds': _SECTOR_STOCK_CACHE_TTL_SECONDS,

        'rows': page_rows,

    }





@bp.get('/api/sector-rotation/sectors')

def api_sector_rotation_sectors():

    force_refresh = str(request.args.get('refresh') or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

    started_at = time.perf_counter()

    logger.info('[SECTOR_LIST_REQUEST] refresh=%s', int(force_refresh))

    try:

        raw_sector_tables = _discover_sector_staging_tables(force_refresh=force_refresh)
        raw_sector_tables = _apply_sector_hierarchy(raw_sector_tables)
        sectors = _collapse_sector_entries_for_unique_ui(raw_sector_tables)

        logger.info(

            '[SECTOR_LIST_RESPONSE] totalSectors=%s rawSectorTables=%s elapsedMs=%s',

            len(sectors),

            len(raw_sector_tables),

            int((time.perf_counter() - started_at) * 1000),

        )

        res = {
            'status': 'success',
            'success': True,
            'totalSectors': len(sectors),
            'count': len(sectors),
            'rawSectorTableCount': len(raw_sector_tables),
            'sectors': sectors,
        }
        if force_refresh:
            res.update({
                'refreshed': True,
                'generatedAt': datetime.now().isoformat(),
                'source': 'oracle_refresh',
                'snapshotPath': 'runtime/snapshots/sector_rotation_tables.json'
            })
        return jsonify(res)

    except Exception:

        logger.exception('Failed /api/sector-rotation/sectors query')

        return jsonify({

            'status': 'error',

            'totalSectors': 0,

            'sectors': [],

            'message': 'Unable to load sector staging tables.',

        }), 503

@bp.get('/api/sector-rotation/sectors/debug')
def api_sector_rotation_sectors_debug():
    try:
        snapshot = _read_snapshot_from_disk() or {}
        snapshot_tables = snapshot.get('tables', [])
        snapshot_names = {t['tableName'] for t in snapshot_tables if 'tableName' in t}
        unique_tables = _collapse_sector_entries_for_unique_ui(snapshot_tables)
        
        oracle_tables = []
        try:
            rows = _query_rows(SQL_DISCOVER_SECTOR_TABLES)
            oracle_tables = [str(r.get('tableName') or '').strip().upper() for r in rows if r.get('tableName')]
        except Exception:
            pass
        oracle_names = set(oracle_tables)
        
        table_signature = hashlib.sha256(json.dumps(sorted(oracle_tables)).encode('utf-8')).hexdigest() if oracle_tables else ''
        signature_match = snapshot.get('signature') == table_signature
        
        now = time.monotonic()
        cache_status = 'MISS'
        if _SECTOR_DISCOVERY_STATE['tables'] is not None:
            if now - _SECTOR_DISCOVERY_STATE['last_checked'] < _SECTOR_TABLE_DISCOVERY_TTL_SECONDS:
                cache_status = 'HIT'
            else:
                cache_status = 'STALE'
                
        return jsonify({
            'cache_status': cache_status,
            'memory_cache_count': len(_SECTOR_DISCOVERY_STATE['tables']) if _SECTOR_DISCOVERY_STATE['tables'] is not None else 0,
            'snapshot_count': len(snapshot_tables),
            'unique_snapshot_count': len(unique_tables),
            'oracle_count': len(oracle_tables),
            'generated_at': snapshot.get('generated_at'),
            'last_refresh_at': datetime.fromtimestamp(time.time() - (now - _SECTOR_DISCOVERY_STATE['last_checked'])).isoformat() if _SECTOR_DISCOVERY_STATE['last_checked'] > 0 else None,
            'signature_match': signature_match,
            'missing_in_snapshot': list(oracle_names - snapshot_names),
            'missing_in_oracle': list(snapshot_names - oracle_names)
        })
    except Exception as e:
        logger.exception("Failed /api/sector-rotation/sectors/debug query")
        return jsonify({'ok': False, 'error': str(e)}), 500





@bp.get('/api/sector-rotation/stocks')

def api_sector_rotation_stocks():

    table_name = request.args.get('tableName')

    sector_name = request.args.get('sectorName')

    force_refresh = str(request.args.get('refresh') or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

    resolved = _resolve_sector_table(table_name=table_name, sector_name=sector_name)

    if not resolved:

        return jsonify({

            'status': 'error',

            'message': 'Invalid sector table selection.',

            'tableName': str(table_name or '').strip().upper(),

            'sectorName': str(sector_name or '').strip(),

            'totalRows': 0,

            'page': 1,

            'pageSize': 25,

            'rows': [],

        }), 400

    logger.info(

        '[SECTOR_REQUEST] sectorName=%s tableName=%s',

        str(resolved.get('sectorName') or '').strip(),

        str(resolved.get('tableName') or '').strip().upper(),

    )



    page = _parse_positive_int(request.args.get('page'), 1, minimum=1, maximum=10_000)

    page_size = _parse_positive_int(

        request.args.get('page_size', request.args.get('pageSize')),

        25,

        minimum=1,

        maximum=500,

    )

    sort_key = str(request.args.get('sort') or 'SYMBOL').strip().upper()

    sort_dir = _normalize_sort_dir(request.args.get('dir'))

    search_text = str(request.args.get('search') or '').strip()



    try:

        sector_code = str(resolved.get('sectorCode') or '').strip().upper()

        payload = _load_sector_wise_payload(

            sector_code=sector_code,

            page=page,

            page_size=page_size,

            sort_key=sort_key,

            sort_dir=sort_dir,

            search_text=search_text,

            force_refresh=force_refresh,

        )

        payload['status'] = 'success'

        payload['tableName'] = str(resolved.get('tableName') or '').strip().upper()

        payload['sectorName'] = str(resolved.get('sectorName') or '').strip()

        payload['sector'] = str(resolved.get('sectorCode') or '').strip().upper()

        payload['stock_count'] = payload.get('totalRows', payload.get('totalCount', 0))

        return jsonify(payload)

    except Exception:

        logger.exception('Failed /api/sector-rotation/stocks for table=%s', resolved.get('tableName'))

        return jsonify({

            'status': 'error',

            'message': 'Unable to load sector stocks.',

            'tableName': str(resolved.get('tableName') or ''),

            'sectorName': str(resolved.get('sectorName') or ''),

            'totalRows': 0,

            'page': page,

            'pageSize': page_size,

            'rows': [],

        }), 503





@bp.get('/api/sectors')

def api_sectors():

    cache_key = 'sectors'

    cached = _cache.get(cache_key)

    if cached is not None:

        return jsonify(cached)

    try:

        rows = _query_rows(SQL_SECTORS)

    except Exception:

        logger.exception('Failed /api/sectors query')

        return jsonify([])

    _cache.set(cache_key, rows)

    return jsonify(rows)


@bp.get('/api/sectors/overview')
def api_sectors_overview():

    force_refresh = str(request.args.get('refresh') or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

    started_at = time.perf_counter()

    logger.info('[SECTOR_OVERVIEW_REQUEST] refresh=%s', int(force_refresh))

    try:
        payload = None
        cache_status = 'REFRESH' if force_refresh else 'MISS'
        latest_cache_key = 'sector-overview-payload:latest'

        if not force_refresh:
            cached_payload = _cache.get(latest_cache_key)
            if isinstance(cached_payload, dict):
                payload = dict(cached_payload)
                cache_status = 'MEMORY_HIT'
            else:
                # Snapshot-first keeps the normal page request independent of Oracle.
                # Data refresh remains available through the explicit refresh=1 path.
                snapshot_payload = _read_sector_overview_payload_snapshot(None)
                if isinstance(snapshot_payload, dict):
                    payload = dict(snapshot_payload)
                    _cache.set(latest_cache_key, payload)
                    cache_status = 'SNAPSHOT_HIT'

        if payload is None:
            latest_dev_date = get_latest_ltc_date_fast() if force_refresh else None
            cache_key = f"sector-overview-payload:{latest_dev_date.isoformat() if latest_dev_date else 'unknown'}"

            if not force_refresh:
                dated_cached_payload = _cache.get(cache_key)
                if isinstance(dated_cached_payload, dict):
                    payload = dict(dated_cached_payload)
                    cache_status = 'MEMORY_HIT'
                else:
                    dated_snapshot_payload = _read_sector_overview_payload_snapshot(latest_dev_date)
                    if isinstance(dated_snapshot_payload, dict):
                        payload = dict(dated_snapshot_payload)
                        cache_status = 'SNAPSHOT_HIT'

        if payload is None:
            if not force_refresh:
                # Normal page reads are snapshot-only; live rebuilds are explicit.
                logger.warning('[SECTOR_OVERVIEW_SNAPSHOT_UNAVAILABLE] normal_read=1')
                return jsonify({
                    'status': 'error',
                    'success': False,
                    'code': 'SECTOR_OVERVIEW_SNAPSHOT_UNAVAILABLE',
                    'message': 'Sector overview is preparing its latest snapshot. Please retry shortly.',
                    'total_sectors': 0,
                    'total_stocks': 0,
                    'ltc_date': '',
                    'trend_counts': {trend: 0 for trend in _SECTOR_OVERVIEW_STATIC_TRENDS},
                    'dynamic_trend_counts': {},
                    'rows': [],
                }), 503
            payload = _load_sector_overview_payload(force_refresh=force_refresh)
            payload['source_dev_ltc_date'] = latest_dev_date.isoformat() if latest_dev_date else ''
            payload['cache_status'] = cache_status
            _write_sector_overview_payload_snapshot(payload)
            _cache.set(cache_key, payload)
            _cache.set(latest_cache_key, payload)
        else:
            payload['cache_status'] = cache_status

        payload = _supplement_overview_unknowns_from_v3(payload)
        payload['elapsedMs'] = int((time.perf_counter() - started_at) * 1000)

        response = jsonify(payload)

        response.headers['X-Source'] = 'LIVE_REFRESH' if force_refresh else str(payload.get('sector_data_source') or 'unknown')

        response.headers['X-Response-Time-Ms'] = str(payload['elapsedMs'])

        return response

    except Exception:

        logger.exception('Failed /api/sectors/overview query')

        return jsonify({

            'status': 'error',

            'success': False,

            'message': 'Unable to load sector overview metrics.',

            'total_sectors': 0,

            'total_stocks': 0,

            'ltc_date': '',

            'trend_counts': {trend: 0 for trend in _SECTOR_OVERVIEW_STATIC_TRENDS},

            'dynamic_trend_counts': {},

            'rows': [],

        }), 503


@bp.get('/api/sectors/sector-wise-symbol')
def api_sector_wise_symbol():
    """Return one exact symbol from the existing published Sector Wise V3 snapshot."""
    started_at = time.perf_counter()
    symbol = str(request.args.get('symbol') or '').strip()
    try:
        from services.sector_rotation_v3_stock_service import get_sector_rotation_v3_stock_symbol

        payload, status_code = get_sector_rotation_v3_stock_symbol(symbol)
        response = jsonify(payload)
        response.status_code = status_code
        response.headers['X-Sector-Rotation-Version'] = 'v3'
        response.headers['X-Source'] = str(payload.get('source') or 'V3_ATOMIC_STOCK_SNAPSHOT')
        response.headers['X-Response-Time-Ms'] = str(int((time.perf_counter() - started_at) * 1000))
        return response
    except Exception:
        logger.exception('Failed exact Sector Wise symbol lookup symbol=%s', symbol)
        return jsonify({
            'ok': False,
            'status': 'error',
            'message': 'Unable to load the published Sector Wise symbol.',
            'reason': 'V3_SYMBOL_LOOKUP_FAILED',
        }), 503


@bp.get('/api/sectors/sector-wise-unknown-symbols')
def api_sector_wise_unknown_symbols():
    """Return the published Sector Wise V3 unknown/insufficient symbols without DB fan-out."""
    started_at = time.perf_counter()
    try:
        payload = json.loads(_SECTOR_V3_STOCK_SNAPSHOT_PATH.read_text(encoding='utf-8'))
        sectors = payload.get('sectors') if isinstance(payload, dict) else None
        if not isinstance(sectors, dict):
            raise ValueError('Published Sector Wise V3 snapshot has no sectors')

        symbols: set[str] = set()
        for sector in sectors.values():
            rows = sector.get('rows') if isinstance(sector, dict) else None
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                trend = str(row.get('trend') or '').strip().upper()
                if trend and trend != '-' and 'UNKNOWN' not in trend and 'INSUFFICIENT' not in trend:
                    continue
                symbol = str(row.get('stock') or row.get('symbol') or '').strip()
                if symbol:
                    symbols.add(symbol)

        result = {
            'asOfDate': payload.get('asOfDate'),
            'elapsedMs': int((time.perf_counter() - started_at) * 1000),
            'source': 'SECTOR_WISE_V3_SNAPSHOT',
            'symbols': sorted(symbols),
            'total': len(symbols),
        }
        response = jsonify(result)
        response.headers['X-Source'] = 'SECTOR_WISE_V3_SNAPSHOT'
        response.headers['X-Response-Time-Ms'] = str(result['elapsedMs'])
        return response
    except Exception:
        logger.exception('Failed to read published Sector Wise V3 snapshot for consolidated TXT download')
        return jsonify({
            'message': 'Published Sector Wise data is unavailable. Refresh Sector Rotation and try again.',
            'symbols': [],
            'total': 0,
        }), 503





@bp.get('/api/sectors/breadth')

def api_sectors_breadth():
    import os
    engine_version = request.args.get('version', os.environ.get('SECTOR_ROTATION_ENGINE_VERSION', 'v1')).strip().lower()

    started_at = time.perf_counter()

    requested_trade_date = _coerce_date(request.args.get('tradeDate'))

    include_history_raw = str(request.args.get('includeHistory') or '').strip().lower()

    include_history = include_history_raw in {'1', 'true', 'yes', 'y', 'on'}

    force_refresh = str(request.args.get('refresh') or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

    if force_refresh:
        try:
            _discover_sector_staging_tables(force_refresh=True)
        except Exception:
            logger.exception("Failed to force refresh sector staging tables on breadth refresh")

    is_latest_live_request = requested_trade_date is None and not include_history

    if is_latest_live_request:
        latest_ltc_date = get_latest_ltc_date_fast()
        if not latest_ltc_date:
            latest_ltc_date = date.today()
    else:
        latest_ltc_date = requested_trade_date if requested_trade_date else date.today()

    cache_key = f"sector_rotation:breadth:{latest_ltc_date.isoformat()}:history:{int(include_history)}"
    if engine_version == 'v3':
        cache_key = f'{cache_key}:v3'

    # A V3 cache entry contains the complete published envelope so stored score,
    # rank, run, freshness, and generation metadata are never recomputed.
    if engine_version == 'v3' and not force_refresh:
        cached_v3 = _cache.get(cache_key)
        if isinstance(cached_v3, Mapping):
            cached_v3_rows = _supplement_v3_breadth_membership_counts([
                dict(row) for row in cached_v3.get('rows', []) if isinstance(row, dict)
            ])
            if cached_v3_rows:
                cached_v3_as_of = _coerce_date(cached_v3.get('asOfDate')) or latest_ltc_date
                return _breadth_response(
                    cached_v3_rows,
                    engine_version='v3',
                    cache_status='HIT',
                    source='MEMORY_CACHE',
                    started_at=started_at,
                    as_of_date=cached_v3_as_of,
                    is_stale=bool(cached_v3.get('isStale')) or cached_v3_as_of < latest_ltc_date,
                    cache_key=cache_key,
                    prebuilt_payload=cached_v3,
                )

    # V3 reads only an atomically published V3 snapshot when one has been
    # deployed. Missing V3 objects/data fall through to the isolated shadow
    # calculation and never alter the V1/V2 snapshot path below.
    if engine_version == 'v3' and is_latest_live_request and not force_refresh:
        from services.sector_rotation_v3_repository import read_latest_published_v3_snapshot

        try:
            v3_snapshot = read_latest_published_v3_snapshot(latest_ltc_date)
        except Exception:
            logger.exception('Failed to read published Sector Rotation V3 snapshot; using shadow fallback')
            v3_snapshot = None
        if v3_snapshot:
            v3_rows = _supplement_v3_breadth_membership_counts([
                row for row in v3_snapshot.get('rows', []) if isinstance(row, dict)
            ])
            if v3_rows:
                v3_as_of_date = _coerce_date(v3_snapshot.get('asOfDate')) or latest_ltc_date
                logger.info(
                    '[SECTOR_ROTATION_BREADTH] endpoint=/api/sectors/breadth source=V3_ORACLE_SNAPSHOT rows=%s trade_date=%s duration_ms=%.2f',
                    len(v3_rows),
                    latest_ltc_date.isoformat(),
                    (time.perf_counter() - started_at) * 1000,
                )
                return _breadth_response(
                    v3_rows,
                    engine_version='v3',
                    cache_status='MISS',
                    source='V3_ORACLE_SNAPSHOT',
                    started_at=started_at,
                    as_of_date=v3_as_of_date,
                    is_stale=bool(v3_snapshot.get('isStale')) or v3_as_of_date < latest_ltc_date,
                    cache_key=cache_key,
                    prebuilt_payload=v3_snapshot,
                )

    # 1. Memory Cache
    if not force_refresh:
        cached = _cache.get(cache_key)
        if cached is not None:
            cached_rows = cached if isinstance(cached, list) else []
            cached_rows = _prepare_breadth_engine_rows(cached_rows, engine_version)
            _cache.set(cache_key, cached_rows)
            logger.info(
                '[SECTOR_ROTATION_BREADTH] endpoint=/api/sectors/breadth source=MEMORY_CACHE rows=%s trade_date=%s duration_ms=%.2f',
                len(cached_rows),
                latest_ltc_date.isoformat(),
                (time.perf_counter() - started_at) * 1000,
            )
            return _breadth_response(
                cached_rows,
                engine_version=engine_version,
                cache_status='HIT',
                source='MEMORY_CACHE',
                started_at=started_at,
                as_of_date=latest_ltc_date,
                cache_key=cache_key,
            )

    # 2. Oracle Snapshot
    if is_latest_live_request and not force_refresh:
        snapshot_rows = read_sector_rotation_snapshot(latest_ltc_date)
        if snapshot_rows:
            snapshot_rows = _prepare_breadth_engine_rows(snapshot_rows, engine_version)
            _cache.set(cache_key, snapshot_rows)
            logger.info(
                '[SECTOR_ROTATION_BREADTH] endpoint=/api/sectors/breadth source=ORACLE_SNAPSHOT rows=%s trade_date=%s duration_ms=%.2f',
                len(snapshot_rows),
                latest_ltc_date.isoformat(),
                (time.perf_counter() - started_at) * 1000,
            )
            return _breadth_response(
                snapshot_rows,
                engine_version=engine_version,
                cache_status='MISS',
                source='ORACLE_SNAPSHOT',
                started_at=started_at,
                as_of_date=latest_ltc_date,
                cache_key=cache_key,
            )

        local_snapshot_rows = _load_breadth_snapshot()
        if local_snapshot_rows:
            local_snapshot_rows = _prepare_breadth_engine_rows(local_snapshot_rows, engine_version)
            _cache.set(cache_key, local_snapshot_rows)
            logger.info(
                '[SECTOR_ROTATION_BREADTH] endpoint=/api/sectors/breadth source=LOCAL_SNAPSHOT rows=%s trade_date=%s duration_ms=%.2f',
                len(local_snapshot_rows),
                latest_ltc_date.isoformat(),
                (time.perf_counter() - started_at) * 1000,
            )
            return _breadth_response(
                local_snapshot_rows,
                engine_version=engine_version,
                cache_status='MISS',
                source='LOCAL_SNAPSHOT',
                started_at=started_at,
                as_of_date=latest_ltc_date,
                cache_key=cache_key,
            )

    # 3. Fallback to V1
    try:
        ensure_sector_reference_data_synced()
        rows = fetch_sector_rotation_rows(requested_trade_date, include_history=include_history)
    except Exception:
        logger.exception('Failed /api/sectors/breadth query')
        return jsonify({'ok': False, 'error': 'Unable to load live sector rotation data.'}), 503

    rows = _apply_latest_raw_trade_date(rows)

    if is_latest_live_request:
        rows = _prepare_breadth_engine_rows(rows, engine_version)
    else:
        rows = _apply_breadth_engine_version(rows, engine_version)

    _cache.set(cache_key, rows)

    if is_latest_live_request and rows and engine_version != 'v3':
        try:
            write_sector_rotation_snapshot(latest_ltc_date, rows)
        except Exception:
            logger.exception("Failed to write snapshot on fallback")

    logger.info(
        '[SECTOR_ROTATION_BREADTH] endpoint=/api/sectors/breadth source=V1_FALLBACK rows=%s trade_date=%s duration_ms=%.2f',
        len(rows) if isinstance(rows, list) else 0,
        latest_ltc_date.isoformat(),
        (time.perf_counter() - started_at) * 1000,
    )
    
    return _breadth_response(
        rows,
        engine_version=engine_version,
        cache_status='FALLBACK',
        source='V1_FALLBACK',
        started_at=started_at,
        as_of_date=latest_ltc_date,
        cache_key=cache_key,
    )





@bp.get('/api/sector/<sector_name>/stocks')

def api_sector_stocks_paginated(sector_name: str):

    force_refresh = str(request.args.get('refresh') or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

    normalized_sector = _resolve_canonical_sector_code(sector_name)

    page = _parse_positive_int(request.args.get('page'), 1, minimum=1, maximum=10_000)

    page_size = _normalize_page_size(request.args.get('pageSize'))

    sort_key = _normalize_sort_key(request.args.get('sort'))

    sort_dir = _normalize_sort_dir(request.args.get('dir'))

    cap_bucket = _normalize_cap_bucket(request.args.get('cap'))

    index_code = _normalize_index_code(request.args.get('index'))

    search_text = str(request.args.get('search') or '').strip()



    if not normalized_sector:

        return jsonify(_empty_popup_payload('', page, page_size, selected_index=index_code))



    try:

        ensure_sector_reference_data_synced(force=force_refresh)

        payload = _load_sector_stocks_payload(

            sector_code=normalized_sector,

            page=page,

            page_size=page_size,

            sort_key=sort_key,

            sort_dir=sort_dir,

            cap_bucket=cap_bucket,

            index_code=index_code,

            search_text=search_text,

            force_refresh=force_refresh,

        )

    except Exception:

        logger.exception('Failed paginated sector stocks query for sector=%s', normalized_sector)

        return jsonify({'ok': False, 'error': f'Unable to load live stocks for sector {normalized_sector}.'}), 503

    return jsonify(payload)





@bp.get('/api/sector/<sector_name>/stocks/sector-wise')
def api_sector_stocks_sector_wise(sector_name: str):
    endpoint_started_at = time.perf_counter()
    force_refresh = str(request.args.get('refresh') or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

    # Known sector routes already have an authoritative local alias/table mapping.
    # Resolve those before consulting Oracle so an expired-but-valid local snapshot
    # can keep the card responsive while the market-data pipeline is catching up.
    requested_sector = _sector_alias_lookup_key(sector_name)
    local_sector = _canonical_sector_rotation_group_code(requested_sector) or requested_sector
    if _strict_sector_table_name(local_sector) or _canonical_merged_sector_code(local_sector):
        sector_name = local_sector
    else:
        sector_name = _resolve_canonical_sector_code(sector_name)

    if force_refresh:
        ensure_sector_reference_data_synced(force=True)

    requested_sector = _sector_alias_lookup_key(sector_name)
    local_sector = _canonical_sector_rotation_group_code(requested_sector) or requested_sector
    if _strict_sector_table_name(local_sector) or _canonical_merged_sector_code(local_sector):
        # Known application routes already have an authoritative local mapping. Avoid
        # opening Oracle merely to resolve the same code before the snapshot fast path.
        resolved_id, resolved_name = local_sector, None
    else:
        from services.sector_resolver_service import resolve_sector_key
        resolved_id, resolved_name = resolve_sector_key(sector_name)
    normalized_sector = resolved_id.upper() if resolved_id else requested_sector
    page = _parse_positive_int(request.args.get('page'), 1, minimum=1, maximum=10_000)
    page_size = _normalize_page_size(request.args.get('pageSize'))
    sort_key = _normalize_sector_wise_sort_key(request.args.get('sort'))
    sort_dir = _normalize_sort_dir(request.args.get('dir'))
    search_text = str(request.args.get('search') or '').strip()

    if not normalized_sector:
        return jsonify(_empty_sector_wise_payload('', page, page_size, sort_key, sort_dir))

    engine_version = str(
        request.args.get('version') or os.environ.get('SECTOR_ROTATION_ENGINE_VERSION', 'v1')
    ).strip().lower()
    if engine_version not in {'v1', 'v2', 'v3'}:
        engine_version = 'v1'

    if engine_version == 'v3':
        from services.sector_rotation_v3_stock_service import get_sector_rotation_v3_stock_page

        payload, status_code = get_sector_rotation_v3_stock_page(
            normalized_sector,
            page=page,
            page_size=page_size,
            search=search_text,
            sort_key=str(request.args.get('sort') or 'STOCK_EDGE_SCORE'),
            sort_dir=sort_dir,
        )
        if status_code == 200:
            response = jsonify(payload)
            response.status_code = status_code
            response.headers['X-Sector-Rotation-Version'] = 'v3'
            response.headers['X-Cache-Status'] = 'HIT'
            response.headers['X-Source'] = str(payload.get('source') or 'V3_STOCK_SNAPSHOT')
            response.headers['X-Response-Time-Ms'] = str(int((time.perf_counter() - endpoint_started_at) * 1000))
            return response

        # V3 publication can temporarily contain a subset of discovered sectors.
        # Do not make the shared Sector Wise page unavailable for omitted sectors;
        # use its established V1 snapshot/data path until the next V3 publish.
        logger.warning(
            '[SECTOR_WISE_V3_FALLBACK] sector=%s status=%s reason=%s',
            normalized_sector,
            status_code,
            payload.get('reason') or 'V3_STOCK_SNAPSHOT_UNAVAILABLE',
        )
        engine_version = 'v1'

    cache_key = (
        f"sector_wise_stocks:{_SECTOR_STOCK_CACHE_VERSION}:{engine_version}:{normalized_sector}:"
        f"page:{page}:size:{page_size}:sort:{sort_key}:dir:{sort_dir}:search:{search_text}"
    )

    # 1. Memory Cache
    if not force_refresh:
        cached = _cache.get(cache_key)
        if cached is not None:
            logger.info(
                '[SECTOR_WISE_RESPONSE] sector=%s source=MEMORY_CACHE totalRows=%s loadElapsedMs=%s serializeMs=0 totalMs=%s',
                normalized_sector,
                cached.get('totalRows', 0),
                0,
                int((time.perf_counter() - endpoint_started_at) * 1000)
            )
            response = jsonify(cached)
            cached_source = str(cached.get('source') or '').strip().upper()
            if cached_source == 'STALE_SNAPSHOT':
                response.headers['X-Cache-Status'] = 'STALE'
                response.headers['X-Source'] = 'STALE_SNAPSHOT_MEMORY'
            else:
                response.headers['X-Cache-Status'] = 'HIT'
                response.headers['X-Source'] = 'MEMORY_CACHE'
            response.headers['X-Response-Time-Ms'] = str(int((time.perf_counter() - endpoint_started_at) * 1000))
            return response

    # 2. Local snapshot: keep normal page loads independent of Oracle latency.
    strict_table_name = _strict_sector_table_name(normalized_sector)
    if not force_refresh and engine_version == 'v1' and strict_table_name:
        local_snapshot = sector_stock_cache_service.get_snapshot(strict_table_name)
        local_snapshot_stale = False
        if local_snapshot is None:
            local_snapshot = sector_stock_cache_service.peek_snapshot(strict_table_name)
            local_snapshot_stale = local_snapshot is not None
        if local_snapshot is not None:
            local_rows = local_snapshot.get('rows') if isinstance(local_snapshot.get('rows'), list) else []
            local_rows_invalid, invalid_reason = _sector_stock_rows_need_refresh(local_rows, 0)
            if not local_rows_invalid:
                local_snapshot = dict(local_snapshot)
                local_snapshot['sectorName'] = _resolve_display_sector_name(
                    normalized_sector,
                    local_snapshot.get('sectorName') or normalized_sector,
                )
                local_source = 'stale_snapshot' if local_snapshot_stale else 'snapshot'
                payload = _build_fast_sector_wise_snapshot_payload(
                    sector=normalized_sector,
                    page=page,
                    page_size=page_size,
                    sort_key=sort_key,
                    sort_dir=sort_dir,
                    search_text=search_text,
                    snapshot_entry=local_snapshot,
                    source=local_source,
                )
                payload['elapsedMs'] = int((time.perf_counter() - endpoint_started_at) * 1000)
                _cache.set(cache_key, payload)
                if local_snapshot_stale:
                    _background_enrich_sector_cache(normalized_sector)
                response = jsonify(payload)
                response.headers['X-Cache-Status'] = 'STALE' if local_snapshot_stale else 'HIT'
                response.headers['X-Source'] = 'STALE_LOCAL_SNAPSHOT' if local_snapshot_stale else 'LOCAL_SNAPSHOT'
                response.headers['X-Response-Time-Ms'] = str(int((time.perf_counter() - endpoint_started_at) * 1000))
                logger.info(
                    '[SECTOR_WISE_RESPONSE] sector=%s source=%s totalRows=%s totalMs=%s',
                    normalized_sector,
                    response.headers['X-Source'],
                    payload.get('totalRows', 0),
                    response.headers['X-Response-Time-Ms'],
                )
                return response
            logger.warning(
                '[SECTOR_LOCAL_SNAPSHOT_INVALID] table=%s reason=%s rows=%s',
                strict_table_name,
                invalid_reason,
                len(local_rows),
            )

    latest_ltc_date = get_latest_ltc_date_fast() or date.today()

    # 3. Oracle Snapshot
    if not force_refresh and engine_version == 'v1' and not search_text and page == 1:
        # Optimization: if not searching/paginating, check snapshot for fast return
        # A more robust pagination could apply over the snapshot rows in memory
        snapshot_rows = read_sector_wise_snapshot(normalized_sector, latest_ltc_date)
        snapshot_rows_invalid, snapshot_rows_reason = _sector_stock_rows_need_refresh(snapshot_rows, 0)
        if snapshot_rows and not snapshot_rows_invalid:
            # Reconstruct the expected payload
            payload = _empty_sector_wise_payload(normalized_sector, page, page_size, sort_key, sort_dir)
            payload['status'] = 'success'
            payload['source'] = 'ORACLE_SNAPSHOT'
            
            canonical_merged_sector = _canonical_merged_sector_code(normalized_sector)
            strict_table_name = _strict_sector_table_name(normalized_sector)
            resolved = {} if canonical_merged_sector or strict_table_name else (_resolve_sector_table(table_name=None, sector_name=normalized_sector) or {})
            
            if canonical_merged_sector:
                payload['tableName'] = _MERGED_SECTOR_TABLE_LABELS.get(canonical_merged_sector, canonical_merged_sector)
                payload['sectorName'] = _MERGED_SECTOR_DISPLAY_NAMES.get(canonical_merged_sector, canonical_merged_sector)
                payload['sector'] = canonical_merged_sector
            else:
                payload['tableName'] = str(resolved.get('tableName') or strict_table_name or '').strip().upper()
                payload['sector'] = str(resolved.get('sectorCode') or normalized_sector).strip().upper()
                payload['sectorName'] = _resolve_display_sector_name(payload['sector'], resolved.get('sectorName') or normalized_sector)
                
            # Apply sorting/pagination in memory to snapshot
            # (In reality, for pure optimization, we might just pass the whole array to frontend and let it paginate if it's small, 
            # but to adhere to API contract we slice)
            # Sorting logic might be complex depending on sort_key, skipping complex sorting in python for brevity 
            # if we expect the caller wants the default sort or if we need to sort snapshot_rows here.
            # Assuming payload returned from oracle is already default sorted, we just slice for page 1.
            payload['rows'] = snapshot_rows[:page_size]
            payload['totalRows'] = len(snapshot_rows)
            payload['totalCount'] = len(snapshot_rows)
            payload['stock_count'] = len(snapshot_rows)
            
            import math
            payload['totalPages'] = max(1, math.ceil(len(snapshot_rows) / (page_size if page_size > 0 else 15)))
            
            _cache.set(cache_key, payload)
            logger.info(
                '[SECTOR_WISE_RESPONSE] sector=%s source=ORACLE_SNAPSHOT totalRows=%s loadElapsedMs=%s serializeMs=0 totalMs=%s',
                normalized_sector,
                len(snapshot_rows),
                0,
                int((time.perf_counter() - endpoint_started_at) * 1000)
            )
            response = jsonify(payload)
            response.headers['X-Cache-Status'] = 'MISS'
            response.headers['X-Source'] = 'ORACLE_SNAPSHOT'
            response.headers['X-Response-Time-Ms'] = str(int((time.perf_counter() - endpoint_started_at) * 1000))
            return response
        if snapshot_rows_invalid:
            logger.warning(
                '[SECTOR_ORACLE_SNAPSHOT_BYPASS] sector=%s reason=%s rows=%s',
                normalized_sector,
                snapshot_rows_reason,
                len(snapshot_rows),
            )

    # 4. Fallback to the existing sector-wise loader.
    load_elapsed_ms = 0
    try:
        load_started_at = time.perf_counter()
        payload = _load_sector_wise_payload(
            sector_code=normalized_sector,
            page=page,
            page_size=page_size,
            sort_key=sort_key,
            sort_dir=sort_dir,
            search_text=search_text,
            force_refresh=force_refresh,
        )
        load_elapsed_ms = int((time.perf_counter() - load_started_at) * 1000)
        
        canonical_merged_sector = _canonical_merged_sector_code(normalized_sector)
        strict_table_name = _strict_sector_table_name(normalized_sector)
        payload_source_token = str(payload.get('source') or '').strip().lower()
        resolver_not_required = bool(strict_table_name) or payload_source_token in {'snapshot', 'stale_snapshot'}
        resolved = {} if canonical_merged_sector or resolver_not_required else (_resolve_sector_table(table_name=None, sector_name=normalized_sector) or {})
        
        payload['status'] = 'success'
        if canonical_merged_sector:
            payload['tableName'] = _MERGED_SECTOR_TABLE_LABELS.get(canonical_merged_sector, canonical_merged_sector)
            payload['sectorName'] = _MERGED_SECTOR_DISPLAY_NAMES.get(canonical_merged_sector, canonical_merged_sector)
            payload['sector'] = canonical_merged_sector
        else:
            payload['tableName'] = str(resolved.get('tableName') or strict_table_name or '').strip().upper()
            payload['sector'] = str(resolved.get('sectorCode') or normalized_sector).strip().upper()
            payload['sectorName'] = _resolve_display_sector_name(payload['sector'], resolved.get('sectorName') or normalized_sector)
            
        payload['stock_count'] = payload.get('totalRows', payload.get('totalCount', 0))
        
        from services.stock_trend_v2_service import enrich_stock_with_v2_signals
        if engine_version == 'v2' and 'rows' in payload:
            payload['rows'] = [enrich_stock_with_v2_signals(row) for row in payload['rows']]
        
        # Persist only complete page-1 datasets, outside the response path.
        if not search_text and page == 1:
            snapshot_rows = payload.get('rows') if isinstance(payload.get('rows'), list) else []
            snapshot_total = _coerce_int(payload.get('totalRows', payload.get('totalCount')), default=0)
            if snapshot_rows and len(snapshot_rows) >= snapshot_total:
                _write_sector_wise_snapshot_async(normalized_sector, latest_ltc_date, snapshot_rows)
            elif snapshot_rows:
                logger.info(
                    '[SECTOR_ORACLE_SNAPSHOT_SKIP] sector=%s reason=partial_page pageRows=%s totalRows=%s',
                    normalized_sector,
                    len(snapshot_rows),
                    snapshot_total,
                )
        
        _cache.set(cache_key, payload)
    except Exception:
        logger.exception('Failed sector-wise stocks query for sector=%s', normalized_sector)
        payload = _empty_sector_wise_payload(normalized_sector, page, page_size, sort_key, sort_dir)

    serialize_started_at = time.perf_counter()
    response = jsonify(payload)
    serialize_elapsed_ms = int((time.perf_counter() - serialize_started_at) * 1000)
    
    logger.info(
        '[SECTOR_ENDPOINT_RESPONSE] sector=%s source=%s totalRows=%s pageRows=%s loadElapsedMs=%s serializeMs=%s totalMs=%s',
        normalized_sector,
        payload.get('source') or 'V1_FALLBACK',
        payload.get('totalRows', payload.get('totalCount', 0)),
        len(payload.get('rows') or []) if isinstance(payload.get('rows'), list) else 0,
        load_elapsed_ms,
        serialize_elapsed_ms,
        int((time.perf_counter() - endpoint_started_at) * 1000),
    )
    
    payload_source = str(payload.get('source') or '').strip().upper()
    if payload_source == 'STALE_SNAPSHOT':
        response.headers['X-Cache-Status'] = 'STALE'
        response.headers['X-Source'] = 'STALE_SNAPSHOT'
    elif payload_source == 'SNAPSHOT':
        response.headers['X-Cache-Status'] = 'HIT'
        response.headers['X-Source'] = 'SNAPSHOT'
    else:
        response.headers['X-Cache-Status'] = 'FALLBACK'
        response.headers['X-Source'] = 'V1_FALLBACK'
    response.headers['X-Response-Time-Ms'] = str(int((time.perf_counter() - endpoint_started_at) * 1000))
    return response





@bp.get('/api/sectors/<sector_code>/stocks')

def api_sector_stocks_legacy(sector_code: str):

    force_refresh = str(request.args.get('refresh') or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

    normalized_sector = (sector_code or '').strip().upper().replace('-', '_')

    if not normalized_sector:

        return jsonify([])



    try:

        payload = _load_sector_stocks_payload(

            sector_code=normalized_sector,

            page=1,

            page_size=_MAX_LEGACY_PAGE_SIZE,

            sort_key='SYMBOL',

            sort_dir='ASC',

            cap_bucket='ALL',

            index_code='ALL',

            search_text='',

            allow_large_page=True,

            force_refresh=force_refresh,

        )

        return jsonify(payload.get('rows', []))

    except Exception:

        logger.exception('Failed legacy stocks query for sector=%s', normalized_sector)

        return jsonify([])





@bp.post('/api/sectors/refresh')

def api_sector_refresh():

    global _popup_cache

    engine_version = str(request.args.get('version') or '').strip().lower()
    v3_refresh_result: dict[str, Any] | None = None
    v3_refresh_failed = False



    conn = get_oracle_connection()

    try:

        with conn.cursor() as cursor:

            try:

                cursor.execute("BEGIN DBMS_MVIEW.REFRESH('MV_NSE_SECTOR_UI_SNAPSHOT', 'C'); END;")

            except Exception:

                logger.exception('Failed MV refresh for MV_NSE_SECTOR_UI_SNAPSHOT')

            try:

                cursor.execute("BEGIN DBMS_MVIEW.REFRESH('MV_NSE_SECTOR_BREADTH', 'C'); END;")

            except Exception:

                logger.exception('Failed MV refresh for MV_NSE_SECTOR_BREADTH')

        conn.commit()

    except Exception:

        try:

            conn.rollback()

        except Exception:

            pass

    finally:

        conn.close()

    if engine_version == 'v3':
        try:
            from services.sector_rotation_v3_refresh_service import refresh_sector_rotation_v3_snapshot

            v3_refresh_result = refresh_sector_rotation_v3_snapshot(
                force_reference_sync=True,
            )
        except Exception:
            v3_refresh_failed = True
            logger.exception('Failed to refresh and publish Sector Rotation V3 snapshot')

    if v3_refresh_failed:
        # Preserve all prior in-memory and browser-visible caches. The stock
        # snapshot publisher is atomic, so the previous complete pair remains
        # available and no partial refresh is advertised.
        return jsonify({
            'ok': False,
            'error': 'Unable to refresh and publish complete Sector Rotation V3 data.',
        }), 503



    _cache.set('sectors', None)

    _cache.set('breadth', None)

    _cache.set(_MAP_SECTOR_CACHE_KEY, None)

    _cache.set(_CAP_VIEW_EXISTS_CACHE_KEY, None)

    _cache.set(_BREADTH_VIEW_EXISTS_CACHE_KEY, None)

    _cache.set(_RAW_SMA_SOURCE_CACHE_KEY, None)

    _cache.set(_RAW_EXTREMA_SOURCE_CACHE_KEY, None)

    _cache.set(_RAW_LATEST_DATE_CACHE_KEY, None)

    _cache.set(_SNAPSHOT_MAX_DATE_CACHE_KEY, None)

    _cache.set(_SNAPSHOT_COLUMNS_CACHE_KEY, None)

    _cache.set(_SECTOR_WISE_TREND_CACHE_KEY, None)

    _cache.set(_SR_LEVELS_VIEW_EXISTS_CACHE_KEY, None)

    _cache.set(_SECTOR_TABLES_CACHE_KEY, None)

    for sector_code in _STRICT_SECTOR_TABLE_MAP:

            _cache.set(f'{_STRICT_SYMBOL_CACHE_PREFIX}v3:{sector_code}', None)

            _cache.set(f'{_STRICT_SYMBOL_LOOKUP_CACHE_PREFIX}v2:{sector_code}', None)

    sector_cache_service.clear_sector_cache()

    try:

        for entry in _discover_sector_staging_tables(force_refresh=True):

            table_name = _to_safe_oracle_name(entry.get('tableName'))

            if table_name:

                _cache.set(f'{_SECTOR_TABLE_COLUMNS_CACHE_PREFIX}{table_name}', None)

    except Exception:

        logger.exception('Failed clearing dynamic sector-table column caches')

    _sector_wise_trend_cache.clear()

    _popup_cache = TTLCache(ttl_seconds=_POPUP_CACHE_TTL, max_items=512)

    refreshed = ['MV_NSE_SECTOR_UI_SNAPSHOT', 'MV_NSE_SECTOR_BREADTH']
    if engine_version == 'v3':
        v3_as_of_date = _coerce_date((v3_refresh_result or {}).get('asOfDate'))
        if v3_as_of_date is None:
            v3_as_of_date = get_latest_ltc_date_fast()
        if v3_as_of_date is not None:
            for include_history_flag in (0, 1):
                _cache.set(
                    f'sector_rotation:breadth:{v3_as_of_date.isoformat()}:history:{include_history_flag}:v3',
                    None,
                )

        refreshed.append('NSE_SECTOR_ROTATION_V3_SNAPSHOT')
        refreshed.append('SECTOR_ROTATION_V3_STOCK_SNAPSHOT')

    return jsonify({'ok': True, 'refreshed': refreshed, 'v3': v3_refresh_result})


