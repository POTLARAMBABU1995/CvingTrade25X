from __future__ import annotations

import json
import logging
import math
import os
import re
import uuid
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import oracledb
except Exception:  # pragma: no cover
    oracledb = None  # type: ignore

try:
    from ..db import fetch_ohlc_series_from_oracle
except ImportError:  # pragma: no cover
    from db import fetch_ohlc_series_from_oracle  # type: ignore

try:
    from ..db_pool import pool
except ImportError:  # pragma: no cover
    from db_pool import pool  # type: ignore


_logger = logging.getLogger(__name__)
_IDENT_RE = re.compile(r'^[A-Za-z0-9_.$#]+$')
_RUN_SOURCE_MAX_LENGTH = 20

PARAMS_TABLE = (os.getenv('STRATEGY_PARAMS_TABLE') or 'CVING_STRATEGY_PARAMS').strip()
RUNS_TABLE = (os.getenv('STRATEGY_AGENT_RUNS_TABLE') or 'CVING_STRATEGY_AGENT_RUNS').strip()
BACKTEST_TABLE = (os.getenv('STRATEGY_AGENT_BACKTESTS_TABLE') or 'CVING_STRATEGY_AGENT_BACKTESTS').strip()

ASURA_AGENT_SOURCE = 'ASURA'
YAMUNA_AGENT_SOURCE = 'YAMUNA'
BHRAMHASTRA_AGENT_SOURCE = 'BHRAMHASTRA'
BACKTEST_NIFTY50_SOURCE = 'BACKTESTNIFTY50'
BACKTEST_NIFTY50_V2_SOURCE = 'BACKTESTNIFTY50V2'
SUCCESS_EPSILON = 1e-9
MAX_BACKTEST_ROWS = 250
_RUNTIME_INIT_LOCK = threading.Lock()
_RUNTIME_INIT_READY = False

DEFAULT_STRATEGY_PARAMS: Dict[str, Dict[str, Any]] = {
    'asura': {
        'enabled': 1,
        'timeframe': 'daily',
        'lookback_days': 365,
        'min_signal': 60.0,
        'min_adx': 20.0,
        'breakout_only': 0,
        'bull_stack_only': 0,
        'entry_min_volume_ratio': 0.0,
        'entry_min_level_score': 0.0,
        'entry_min_rsi': 0.0,
        'entry_max_rsi': 100.0,
        'macd_positive_only': 0,
        'stop_mode': 'PCT',
        'stop_pct': 0.05,
        'stop_buffer_pct': 0.0,
        'atr_mult': 1.25,
        'atr_buffer_mult': 0.0,
        'volume_min_ratio': 1.75,
        'volume_buffer_pct': 0.0,
        'target1_rr': 2.0,
        'target2_rr': 3.0,
        'max_holding_days': 45,
        'apply_threshold_pct': 0.5,
        'success_target_pct': 75.0,
        'min_trade_retention_ratio': 0.35,
        'cooldown_days': 5,
    },
    'yamuna': {
        'enabled': 1,
        'lookback_days': 365,
        'include_gainers': 1,
        'include_losers': 1,
        'include_volume': 1,
        'volume_min_ratio': 3.0,
        'stop_mode': 'PCT',
        'stop_pct': 0.05,
        'stop_buffer_pct': 0.0,
        'atr_mult': 1.0,
        'atr_buffer_mult': 0.0,
        'volume_buffer_pct': 0.0,
        'target1_rr': 2.0,
        'target2_rr': 3.0,
        'max_holding_days': 30,
        'apply_threshold_pct': 0.5,
        'success_target_pct': 75.0,
        'min_trade_retention_ratio': 0.35,
        'cooldown_days': 2,
    },
    'bhramhastra': {
        'enabled': 1,
        'timeframe': 'daily',
        'lookback_days': 365,
        'entry_min_rsi': 50.0,
        'entry_max_rsi': 55.0,
        'macd_positive_only': 1,
        'stop_mode': 'PCT',
        'stop_pct': 0.05,
        'stop_buffer_pct': 0.0,
        'atr_mult': 1.0,
        'atr_buffer_mult': 1.0,
        'target1_rr': 2.0,
        'target2_rr': 3.0,
        'max_holding_days': 45,
        'apply_threshold_pct': 0.5,
        'success_target_pct': 75.0,
        'min_trade_retention_ratio': 0.35,
        'cooldown_days': 3,
    },
    'backtestnifty50': {
        'enabled': 1,
        'lookback_days': 12000,
        'start_date': '1998-01-01',
        'ema_fast_period': 20,
        'ema_slow_period': 50,
        'rsi_period': 14,
        'rsi_threshold': 50.0,
        'macd_fast_period': 12,
        'macd_slow_period': 26,
        'macd_signal_period': 9,
        'macd_positive_only': 1,
        'stop_mode': 'PCT',
        'stop_pct': 0.05,
        'stop_buffer_pct': 0.0,
        'atr_mult': 1.0,
        'atr_buffer_mult': 1.0,
        'volume_min_ratio': 1.5,
        'volume_buffer_pct': 0.0,
        'target1_rr': 2.0,
        'target2_rr': 3.0,
        'max_holding_days': 60,
        'apply_threshold_pct': 0.0,
        'success_target_pct': 75.0,
        'min_trade_retention_ratio': 0.0,
        'cooldown_days': 0,
    },
    'backtestnifty50v2': {
        'enabled': 1,
        'lookback_days': 12000,
        'start_date': '1998-01-01',
        'ema_fast_period': 20,
        'ema_slow_period': 50,
        'rsi_period': 14,
        'rsi_threshold': 60.0,
        'macd_fast_period': 12,
        'macd_slow_period': 26,
        'macd_signal_period': 9,
        'macd_positive_only': 1,
        'adx_period': 14,
        'adx_threshold': 35.0,
        'breakout_lookback': 20,
        'breakout_margin_atr_mult': 0.25,
        'support_buffer_atr_mult': 0.10,
        'breakout_body_atr_min': 0.50,
        'close_to_high_max_pct': 0.25,
        'trendline_fast_window': 10,
        'trendline_slow_window': 20,
        'trendline_min_rise_pct': 1.00,
        'stop_mode': 'PCT',
        'stop_pct': 0.05,
        'stop_buffer_pct': 0.0,
        'atr_mult': 1.0,
        'atr_buffer_mult': 1.0,
        'volume_min_ratio': 1.5,
        'volume_buffer_pct': 0.0,
        'target1_rr': 2.0,
        'target2_rr': 3.0,
        'max_holding_days': 25,
        'apply_threshold_pct': 0.25,
        'success_target_pct': 60.0,
        'min_trade_retention_ratio': 0.05,
        'cooldown_days': 0,
    },
}

_PARAM_TYPES = {
    'enabled': 'number',
    'timeframe': 'text',
    'lookback_days': 'number',
    'start_date': 'text',
    'ema_fast_period': 'number',
    'ema_slow_period': 'number',
    'rsi_period': 'number',
    'rsi_threshold': 'number',
    'macd_fast_period': 'number',
    'macd_slow_period': 'number',
    'macd_signal_period': 'number',
    'adx_period': 'number',
    'adx_threshold': 'number',
    'breakout_lookback': 'number',
    'breakout_margin_atr_mult': 'number',
    'support_buffer_atr_mult': 'number',
    'breakout_body_atr_min': 'number',
    'close_to_high_max_pct': 'number',
    'trendline_fast_window': 'number',
    'trendline_slow_window': 'number',
    'trendline_min_rise_pct': 'number',
    'min_signal': 'number',
    'min_adx': 'number',
    'breakout_only': 'number',
    'bull_stack_only': 'number',
    'entry_min_volume_ratio': 'number',
    'entry_min_level_score': 'number',
    'entry_min_rsi': 'number',
    'entry_max_rsi': 'number',
    'macd_positive_only': 'number',
    'stop_mode': 'text',
    'stop_pct': 'number',
    'stop_buffer_pct': 'number',
    'atr_mult': 'number',
    'atr_buffer_mult': 'number',
    'target1_rr': 'number',
    'target2_rr': 'number',
    'max_holding_days': 'number',
    'apply_threshold_pct': 'number',
    'success_target_pct': 'number',
    'min_trade_retention_ratio': 'number',
    'cooldown_days': 'number',
    'include_gainers': 'number',
    'include_losers': 'number',
    'include_volume': 'number',
    'volume_min_ratio': 'number',
    'volume_buffer_pct': 'number',
    'last_success_rate': 'number',
    'last_fail_rate': 'number',
    'last_total_trades': 'number',
    'last_avg_rr': 'number',
    'last_run_at': 'text',
    'last_run_note': 'text',
}

_ASURA_REQUIRED_COLUMNS = {
    'SIGNAL_SCORE',
    'ADX14',
    'EMA_STACK',
    'BREAKOUT_FLAG',
    'TREND_DIRECTION',
}


@dataclass(frozen=True)
class TradeSignal:
    strategy_name: str
    source_name: str
    symbol: str
    direction: str
    entry_date: date
    entry_price: float
    signal_score: Optional[float] = None
    atr: Optional[float] = None
    breakout_flag: Optional[str] = None
    trend_direction: Optional[str] = None
    setup_type: Optional[str] = None
    percentage: Optional[float] = None
    points: Optional[float] = None


@dataclass(frozen=True)
class DailyBar:
    trade_date: date
    open_price: Optional[float]
    high_price: Optional[float]
    low_price: Optional[float]
    close_price: Optional[float]
    volume: Optional[float]


def _safe_identifier(value: str) -> str:
    text = (value or '').strip()
    if not text or not _IDENT_RE.match(text):
        raise ValueError(f'Invalid identifier: {value!r}')
    return text


PARAMS_TABLE_SQL = _safe_identifier(PARAMS_TABLE)
RUNS_TABLE_SQL = _safe_identifier(RUNS_TABLE)
BACKTEST_TABLE_SQL = _safe_identifier(BACKTEST_TABLE)


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return float(value)
    text = str(value).strip().replace(',', '')
    if not text:
        return None
    try:
        parsed = float(text)
    except Exception:
        return None
    return parsed if math.isfinite(parsed) else None


def _to_int(value: Any, default: int = 0) -> int:
    num = _to_float(value)
    if num is None:
        return default
    try:
        return int(round(num))
    except Exception:
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return float(value) != 0.0
    text = str(value).strip().lower()
    if text in ('1', 'true', 'yes', 'y', 'on'):
        return True
    if text in ('0', 'false', 'no', 'n', 'off'):
        return False
    return default


def _to_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    token = text[:10]
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%Y/%m/%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(token, fmt).date()
        except Exception:
            continue
    return None


def _date_to_iso(value: Optional[date]) -> Optional[str]:
    if not value:
        return None
    return value.strftime('%Y-%m-%d')


def _datetime_to_iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day).strftime('%Y-%m-%d %H:%M:%S')
    return None


def _normalize_text(value: Any) -> str:
    return str(value or '').strip()


def _pick_column(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    upper_map = {str(col).upper(): str(col) for col in columns}
    for candidate in candidates:
        if candidate.upper() in upper_map:
            return upper_map[candidate.upper()]
    return None


def _split_owner_and_name(identifier: str) -> Tuple[Optional[str], str]:
    text = _safe_identifier(identifier)
    if '.' in text:
        owner, name = text.rsplit('.', 1)
        return owner.upper(), name.upper()
    return None, text.upper()


def _base_object_name(identifier: str) -> str:
    return _split_owner_and_name(identifier)[1]


def _table_exists(conn, table_name: str) -> bool:
    owner, name = _split_owner_and_name(table_name)
    sql = 'SELECT 1 FROM USER_TABLES WHERE TABLE_NAME = :name'
    binds: Dict[str, Any] = {'name': name}
    if owner:
        sql = 'SELECT 1 FROM ALL_TABLES WHERE OWNER = :owner AND TABLE_NAME = :name'
        binds['owner'] = owner
    with conn.cursor() as cur:
        cur.execute(sql, binds)
        return cur.fetchone() is not None


def _index_exists(conn, index_name: str) -> bool:
    owner, name = _split_owner_and_name(index_name)
    sql = 'SELECT 1 FROM USER_INDEXES WHERE INDEX_NAME = :name'
    binds: Dict[str, Any] = {'name': name}
    if owner:
        sql = 'SELECT 1 FROM ALL_INDEXES WHERE OWNER = :owner AND INDEX_NAME = :name'
        binds['owner'] = owner
    with conn.cursor() as cur:
        cur.execute(sql, binds)
        return cur.fetchone() is not None


def _runtime_index_name(table_identifier: str, suffix: str) -> str:
    return f"IDX_{_base_object_name(table_identifier)[-18:]}_{suffix}"


def _execute_ddl(conn, ddl: str) -> None:
    with conn.cursor() as cur:
        try:
            cur.execute(ddl)
        except Exception as exc:
            msg = str(exc)
            if 'ORA-00955' in msg or 'ORA-01408' in msg:
                return
            raise


def ensure_strategy_agent_tables(conn) -> None:
    params_pk_name = f"PK_{_base_object_name(PARAMS_TABLE_SQL)[-20:]}"
    params_upd_idx = _runtime_index_name(PARAMS_TABLE_SQL, 'UPD')
    runs_ck_name = f"CK_{_base_object_name(RUNS_TABLE_SQL)[-16:]}_JSON"
    runs_strat_idx = _runtime_index_name(RUNS_TABLE_SQL, 'STRAT')
    backtests_run_idx = _runtime_index_name(BACKTEST_TABLE_SQL, 'RUN')
    backtests_strat_idx = _runtime_index_name(BACKTEST_TABLE_SQL, 'STRAT')

    if not _table_exists(conn, PARAMS_TABLE_SQL):
        _execute_ddl(conn, f'''
            CREATE TABLE {PARAMS_TABLE_SQL} (
              STRATEGY_NAME      VARCHAR2(30) NOT NULL,
              PARAM_NAME         VARCHAR2(80) NOT NULL,
              PARAM_VALUE_TEXT   VARCHAR2(4000),
              PARAM_VALUE_NUMBER NUMBER(18,6),
              VALUE_TYPE         VARCHAR2(20) DEFAULT 'text' NOT NULL,
              NOTES              VARCHAR2(400),
              UPDATED_BY         VARCHAR2(64),
              UPDATED_AT         TIMESTAMP DEFAULT SYSTIMESTAMP,
              IS_ACTIVE          CHAR(1) DEFAULT 'Y' NOT NULL,
              CONSTRAINT {params_pk_name} PRIMARY KEY (STRATEGY_NAME, PARAM_NAME)
            )
        ''')
    if not _index_exists(conn, params_upd_idx):
        _execute_ddl(conn, f'CREATE INDEX {params_upd_idx} ON {PARAMS_TABLE_SQL} (UPDATED_AT)')

    if not _table_exists(conn, RUNS_TABLE_SQL):
        _execute_ddl(conn, f'''
            CREATE TABLE {RUNS_TABLE_SQL} (
              RUN_ID                  VARCHAR2(36) PRIMARY KEY,
              STRATEGY_NAME           VARCHAR2(30) NOT NULL,
              RUN_SOURCE              VARCHAR2(20),
              RUN_AT                  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
              STATUS                  VARCHAR2(20) NOT NULL,
              APPLIED_FLAG            CHAR(1) DEFAULT 'N' NOT NULL,
              BASELINE_SUCCESS_RATE   NUMBER(9,4),
              CANDIDATE_SUCCESS_RATE  NUMBER(9,4),
              BASELINE_FAIL_RATE      NUMBER(9,4),
              CANDIDATE_FAIL_RATE     NUMBER(9,4),
              BASELINE_TOTAL_TRADES   NUMBER,
              CANDIDATE_TOTAL_TRADES  NUMBER,
              BASELINE_AVG_RR         NUMBER(12,6),
              CANDIDATE_AVG_RR        NUMBER(12,6),
              PARAMS_JSON             CLOB,
              NOTES                   CLOB,
              CONSTRAINT {runs_ck_name} CHECK (PARAMS_JSON IS JSON OR PARAMS_JSON IS NULL)
            )
        ''')
    if not _index_exists(conn, runs_strat_idx):
        _execute_ddl(conn, f'CREATE INDEX {runs_strat_idx} ON {RUNS_TABLE_SQL} (STRATEGY_NAME, RUN_AT DESC)')

    if not _table_exists(conn, BACKTEST_TABLE_SQL):
        _execute_ddl(conn, f'''
            CREATE TABLE {BACKTEST_TABLE_SQL} (
              BACKTEST_ID      VARCHAR2(64) PRIMARY KEY,
              RUN_ID           VARCHAR2(36) NOT NULL,
              STRATEGY_NAME    VARCHAR2(30) NOT NULL,
              SOURCE_NAME      VARCHAR2(30),
              SYMBOL           VARCHAR2(50) NOT NULL,
              DIRECTION        VARCHAR2(10) NOT NULL,
              ENTRY_DATE       DATE NOT NULL,
              EXIT_DATE        DATE,
              ENTRY_PRICE      NUMBER(18,4),
              EXIT_PRICE       NUMBER(18,4),
              STOP_LOSS        NUMBER(18,4),
              TARGET1          NUMBER(18,4),
              TARGET2          NUMBER(18,4),
              TARGET1_DATE     DATE,
              TARGET2_DATE     DATE,
              EXIT_REASON      VARCHAR2(40),
              RESULT_FLAG      VARCHAR2(10),
              SUCCESS_FLAG     NUMBER(1) DEFAULT 0 NOT NULL,
              FAIL_FLAG        NUMBER(1) DEFAULT 0 NOT NULL,
              TRADING_DAYS     NUMBER,
              DAYS_TO_T1       NUMBER,
              DAYS_TO_T2       NUMBER,
              RETURN_PCT       NUMBER(12,4),
              RETURN_RR        NUMBER(12,6),
              WHY_TRADE        VARCHAR2(400),
              CREATED_AT       TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
            )
        ''')
    if not _index_exists(conn, backtests_run_idx):
        _execute_ddl(conn, f'CREATE INDEX {backtests_run_idx} ON {BACKTEST_TABLE_SQL} (RUN_ID, ENTRY_DATE DESC)')
    if not _index_exists(conn, backtests_strat_idx):
        _execute_ddl(conn, f'CREATE INDEX {backtests_strat_idx} ON {BACKTEST_TABLE_SQL} (STRATEGY_NAME, ENTRY_DATE DESC)')
    conn.commit()


def _upsert_param(conn, strategy_name: str, param_name: str, value: Any, notes: str = '', updated_by: str = 'agent') -> None:
    value_type = _PARAM_TYPES.get(param_name, 'text')
    number_value = _to_float(value) if value_type == 'number' else None
    text_value = None
    if value_type == 'text':
        text_value = str(value)
    elif value is not None and value_type != 'number':
        text_value = str(value)
    with conn.cursor() as cur:
        cur.execute(
            f'''
            MERGE INTO {PARAMS_TABLE_SQL} t
            USING (SELECT :strategy_name AS strategy_name, :param_name AS param_name FROM dual) s
               ON (t.STRATEGY_NAME = s.strategy_name AND t.PARAM_NAME = s.param_name)
            WHEN MATCHED THEN UPDATE SET
                PARAM_VALUE_TEXT = :text_value,
                PARAM_VALUE_NUMBER = :number_value,
                VALUE_TYPE = :value_type,
                NOTES = :notes,
                UPDATED_BY = :updated_by,
                UPDATED_AT = SYSTIMESTAMP,
                IS_ACTIVE = 'Y'
            WHEN NOT MATCHED THEN INSERT (
                STRATEGY_NAME, PARAM_NAME, PARAM_VALUE_TEXT, PARAM_VALUE_NUMBER, VALUE_TYPE, NOTES, UPDATED_BY, UPDATED_AT, IS_ACTIVE
            ) VALUES (
                :strategy_name, :param_name, :text_value, :number_value, :value_type, :notes, :updated_by, SYSTIMESTAMP, 'Y'
            )
            ''',
            {
                'strategy_name': strategy_name,
                'param_name': param_name,
                'text_value': text_value,
                'number_value': number_value,
                'value_type': value_type,
                'notes': notes[:400] if notes else None,
                'updated_by': updated_by,
            },
        )


def _seed_param(conn, strategy_name: str, param_name: str, value: Any, notes: str = 'default seed') -> None:
    value_type = _PARAM_TYPES.get(param_name, 'text')
    number_value = _to_float(value) if value_type == 'number' else None
    text_value = str(value) if value is not None and value_type != 'number' else (str(value) if value_type == 'text' else None)
    with conn.cursor() as cur:
        cur.execute(
            f'''
            MERGE INTO {PARAMS_TABLE_SQL} t
            USING (SELECT :strategy_name AS strategy_name, :param_name AS param_name FROM dual) s
               ON (t.STRATEGY_NAME = s.strategy_name AND t.PARAM_NAME = s.param_name)
            WHEN NOT MATCHED THEN INSERT (
                STRATEGY_NAME, PARAM_NAME, PARAM_VALUE_TEXT, PARAM_VALUE_NUMBER, VALUE_TYPE, NOTES, UPDATED_BY, UPDATED_AT, IS_ACTIVE
            ) VALUES (
                :strategy_name, :param_name, :text_value, :number_value, :value_type, :notes, 'system-seed', SYSTIMESTAMP, 'Y'
            )
            ''',
            {
                'strategy_name': strategy_name,
                'param_name': param_name,
                'text_value': text_value,
                'number_value': number_value,
                'value_type': value_type,
                'notes': notes[:400] if notes else None,
            },
        )


def ensure_default_strategy_params(conn) -> None:
    for strategy_name, defaults in DEFAULT_STRATEGY_PARAMS.items():
        for key, value in defaults.items():
            _seed_param(conn, strategy_name, key, value, notes='default seed')
    conn.commit()


def ensure_strategy_agent_runtime(conn) -> None:
    global _RUNTIME_INIT_READY
    if _RUNTIME_INIT_READY:
        return
    with _RUNTIME_INIT_LOCK:
        if _RUNTIME_INIT_READY:
            return
        ensure_strategy_agent_tables(conn)
        ensure_default_strategy_params(conn)
        _RUNTIME_INIT_READY = True


def get_strategy_params(strategy_name: str, conn=None) -> Dict[str, Any]:
    strategy_key = (strategy_name or '').strip().lower()
    defaults = dict(DEFAULT_STRATEGY_PARAMS.get(strategy_key, {}))
    owns_conn = conn is None
    if owns_conn:
        conn = pool.acquire()
    try:
        ensure_strategy_agent_runtime(conn)
        with conn.cursor() as cur:
            cur.execute(
                f'''
                SELECT PARAM_NAME, PARAM_VALUE_TEXT, PARAM_VALUE_NUMBER, VALUE_TYPE
                FROM {PARAMS_TABLE_SQL}
                WHERE STRATEGY_NAME = :strategy_name
                  AND IS_ACTIVE = 'Y'
                ''',
                {'strategy_name': strategy_key},
            )
            for param_name, text_value, number_value, value_type in cur.fetchall() or []:
                key = _normalize_text(param_name).lower()
                if (value_type or '').lower() == 'number':
                    defaults[key] = _to_float(number_value)
                else:
                    defaults[key] = text_value
        return defaults
    except Exception:
        _logger.exception('Failed to read strategy params for %s; using defaults.', strategy_key)
        return defaults
    finally:
        if owns_conn and conn is not None:
            conn.close()


def _serialize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, float):
            out[key] = round(value, 6)
        else:
            out[key] = value
    return out

def _build_asura_candidates(timeframe: str) -> List[str]:
    schema = (os.getenv('ASURA_SCHEMA') or os.getenv('ORACLE_SCHEMA') or '').strip()
    explicit = (os.getenv('ASURA_SIGNAL_TABLE') or os.getenv('ASURA_BULLISH_TREND_TABLE') or os.getenv('ASURA_SIGNAL_VIEW_DAILY') or os.getenv('ASURA_VIEW') or '').strip()
    if timeframe == 'weekly':
        explicit = (os.getenv('ASURA_SIGNAL_VIEW_WEEKLY') or os.getenv('ASURA_VIEW_WEEKLY') or '').strip()
    bases = ['ASURA_BULLISH_TREND_STRATEGY_TESTING', 'ASURA_SCAN_DAILY_FACT', 'MV_ASURA_SCAN_DAILY', 'V_ASURA_SCAN_LATEST']
    if timeframe == 'weekly':
        bases = ['ASURA_SCAN_WEEKLY_FACT', 'MV_ASURA_SCAN_WEEKLY', 'V_ASURA_SCAN_WEEKLY_LATEST']
    out: List[str] = []

    def add(name: str) -> None:
        value = (name or '').strip()
        if not value:
            return
        try:
            cleaned = _safe_identifier(value)
        except ValueError:
            return
        if cleaned not in out:
            out.append(cleaned)

    if explicit:
        add(explicit)
    for base in bases:
        add(base)
        if schema:
            add(f'{schema}.{base}')
    return out


def _get_source_columns(conn, source: str) -> List[str]:
    with conn.cursor() as cur:
        cur.execute(f'SELECT * FROM {source} WHERE ROWNUM = 0')
        return [str(col[0]) for col in (cur.description or []) if col and col[0]]


def _resolve_asura_source(conn, timeframe: str) -> Tuple[str, List[str]]:
    for candidate in _build_asura_candidates(timeframe):
        try:
            columns = _get_source_columns(conn, candidate)
        except Exception as exc:
            if 'ORA-00942' in str(exc):
                continue
            raise
        upper = {col.upper() for col in columns}
        if _ASURA_REQUIRED_COLUMNS.issubset(upper) and _pick_column(columns, ('SYMBOL', 'STOCK')) and _pick_column(columns, ('BUYING_DATE', 'TRADE_DATE', 'TRADING_DATE', 'BT_DATE')):
            return candidate, columns
    raise RuntimeError('No historical Asura signal source found for backtesting')


def _query_rows(conn, sql: str, binds: Dict[str, Any]) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, binds)
        columns = [str(col[0]).lower() for col in (cur.description or [])]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def _load_asura_signals(conn, params: Dict[str, Any]) -> List[TradeSignal]:
    if not _to_bool(params.get('enabled'), True):
        return []
    timeframe = _normalize_text(params.get('timeframe') or 'daily').lower() or 'daily'
    lookback_days = max(30, _to_int(params.get('lookback_days'), 365))
    start_date = datetime.utcnow().date() - timedelta(days=lookback_days)
    source, columns = _resolve_asura_source(conn, timeframe)

    trade_col = _pick_column(columns, ('BUYING_DATE', 'TRADE_DATE', 'TRADING_DATE', 'BT_DATE')) or 'BUYING_DATE'
    symbol_col = _pick_column(columns, ('SYMBOL', 'STOCK')) or 'SYMBOL'
    price_col = _pick_column(columns, ('ENTRY_PRICE', 'CLOSE_PRICE', 'PRICE', 'BUYING_PRICE', 'LTP', 'LAST_PRICE', 'CLOSE')) or 'CLOSE_PRICE'
    signal_col = _pick_column(columns, ('SIGNAL_SCORE',))
    adx_col = _pick_column(columns, ('ADX14', 'ADX'))
    atr_col = _pick_column(columns, ('ATR14', 'ATR'))
    breakout_col = _pick_column(columns, ('BREAKOUT_FLAG', 'BO_FLAG'))
    trend_col = _pick_column(columns, ('TREND_DIRECTION',))
    ema_stack_col = _pick_column(columns, ('EMA_STACK',))
    setup_col = _pick_column(columns, ('SETUP_TYPE', 'SETUPTYPE'))

    select_cols = [
        f'{symbol_col} AS symbol',
        f'{trade_col} AS trade_date',
        f'{price_col} AS entry_price',
    ]
    volume_ratio_col = _pick_column(columns, ('VOLUME_RATIO20', 'VOL_RATIO20'))
    rsi_col = _pick_column(columns, ('RSI14', 'RSI'))
    macd_col = _pick_column(columns, ('MACD_HIST', 'MACD'))
    level_score_col = _pick_column(columns, ('LEVEL_SCORE',))

    if signal_col:
        select_cols.append(f'{signal_col} AS signal_score')
    if adx_col:
        select_cols.append(f'{adx_col} AS adx14')
    if atr_col:
        select_cols.append(f'{atr_col} AS atr14')
    if breakout_col:
        select_cols.append(f'{breakout_col} AS breakout_flag')
    if trend_col:
        select_cols.append(f'{trend_col} AS trend_direction')
    if ema_stack_col:
        select_cols.append(f'{ema_stack_col} AS ema_stack')
    if setup_col:
        select_cols.append(f'{setup_col} AS setup_type')
    if volume_ratio_col:
        select_cols.append(f'{volume_ratio_col} AS volume_ratio20')
    if rsi_col:
        select_cols.append(f'{rsi_col} AS rsi14')
    if macd_col:
        select_cols.append(f'{macd_col} AS macd_hist')
    if level_score_col:
        select_cols.append(f'{level_score_col} AS level_score')

    sql = f'''
        SELECT {', '.join(select_cols)}
        FROM {source}
        WHERE {trade_col} >= :start_date
          AND NVL({trend_col}, 'UPTREND') = 'UPTREND'
          AND NVL({signal_col}, 0) >= :min_signal
          AND NVL({adx_col}, 0) >= :min_adx
          AND (NVL(:breakout_only, 0) = 0 OR NVL({breakout_col}, 'NONE') = 'BREAKOUT')
          AND (NVL({ema_stack_col}, 'BULL_STACK') = 'BULL_STACK' OR NVL({ema_stack_col}, 'BULL_STACK') = 'MIXED')
        ORDER BY {trade_col}, {symbol_col}
    '''
    rows = _query_rows(
        conn,
        sql,
        {
            'start_date': start_date,
            'min_signal': _to_float(params.get('min_signal')) or 60.0,
            'min_adx': _to_float(params.get('min_adx')) or 20.0,
            'breakout_only': 1 if _to_bool(params.get('breakout_only')) else 0,
        },
    )

    bull_stack_only = _to_bool(params.get('bull_stack_only'))
    entry_min_volume_ratio = max(0.0, _to_float(params.get('entry_min_volume_ratio')) or 0.0)
    entry_min_level_score = max(0.0, _to_float(params.get('entry_min_level_score')) or 0.0)
    entry_min_rsi = max(0.0, _to_float(params.get('entry_min_rsi')) or 0.0)
    entry_max_rsi = min(100.0, _to_float(params.get('entry_max_rsi')) or 100.0)
    macd_positive_only = _to_bool(params.get('macd_positive_only'))

    signals: List[TradeSignal] = []
    for row in rows:
        ema_stack = _normalize_text(row.get('ema_stack')).upper() or None
        volume_ratio20 = _to_float(row.get('volume_ratio20'))
        rsi14 = _to_float(row.get('rsi14'))
        macd_hist = _to_float(row.get('macd_hist'))
        level_score = _to_float(row.get('level_score'))
        if bull_stack_only and ema_stack != 'BULL_STACK':
            continue
        if entry_min_volume_ratio > 0 and (volume_ratio20 is None or volume_ratio20 < entry_min_volume_ratio):
            continue
        if entry_min_level_score > 0 and (level_score is None or level_score < entry_min_level_score):
            continue
        if entry_min_rsi > 0 and (rsi14 is None or rsi14 < entry_min_rsi):
            continue
        if entry_max_rsi < 100.0 and (rsi14 is None or rsi14 > entry_max_rsi):
            continue
        if macd_positive_only and (macd_hist is None or macd_hist <= 0):
            continue
        symbol = _normalize_text(row.get('symbol')).upper()
        entry_date = _to_date(row.get('trade_date'))
        entry_price = _to_float(row.get('entry_price'))
        if not symbol or not entry_date or entry_price is None or entry_price <= 0:
            continue
        signals.append(
            TradeSignal(
                strategy_name='asura',
                source_name=ASURA_AGENT_SOURCE,
                symbol=symbol,
                direction='LONG',
                entry_date=entry_date,
                entry_price=entry_price,
                signal_score=_to_float(row.get('signal_score')),
                atr=_to_float(row.get('atr14')),
                breakout_flag=_normalize_text(row.get('breakout_flag')).upper() or None,
                trend_direction=_normalize_text(row.get('trend_direction')).upper() or None,
                setup_type=_normalize_text(row.get('setup_type')) or None,
            )
        )
    return signals


def _load_table_rows(conn, table_name: str, extra_where: str = '', binds: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if not _table_exists(conn, table_name):
        return []
    columns = _get_source_columns(conn, table_name)
    stock_col = _pick_column(columns, ('STOCK', 'SYMBOL'))
    trade_col = _pick_column(columns, ('LTC_DATE', 'TRADE_DATE', 'TRADING_DATE', 'BT_DATE'))
    price_col = _pick_column(columns, ('PRICE', 'LTP', 'LAST_PRICE', 'CLOSE_PRICE', 'CLOSE'))
    pct_col = _pick_column(columns, ('PERCENTAGE', 'PCT_CHANGE', 'CHANGE_PCT', 'PERCENT_CHANGE'))
    points_col = _pick_column(columns, ('POINTS', 'CHANGE', 'POINT_CHANGE'))
    volume_col = _pick_column(columns, ('VOLUME', 'TOTTRDQTY', 'TOTAL_TRADED_QTY', 'VOLUME_TRADED'))
    if not stock_col or not trade_col or not price_col:
        _logger.warning('Yamuna source %s skipped because required columns are missing: %s', table_name, ', '.join(columns))
        return []
    select_cols = [
        f'{stock_col} AS STOCK',
        f'{trade_col} AS LTC_DATE',
        f'{price_col} AS PRICE',
        f'{pct_col} AS PERCENTAGE' if pct_col else 'CAST(NULL AS NUMBER) AS PERCENTAGE',
        f'{points_col} AS POINTS' if points_col else 'CAST(NULL AS NUMBER) AS POINTS',
        f'{volume_col} AS VOLUME' if volume_col else 'CAST(NULL AS NUMBER) AS VOLUME',
    ]
    sql = f'''
        SELECT {", ".join(select_cols)}
        FROM {table_name}
        WHERE {trade_col} >= :start_date
        {extra_where}
        ORDER BY {trade_col}, {stock_col}
    '''
    return _query_rows(conn, sql, binds or {})


def _load_yamuna_signals(conn, params: Dict[str, Any]) -> List[TradeSignal]:
    if not _to_bool(params.get('enabled'), True):
        return []
    lookback_days = max(30, _to_int(params.get('lookback_days'), 365))
    start_date = datetime.utcnow().date() - timedelta(days=lookback_days)
    gainers_table = _safe_identifier((os.getenv('YAMUNA_GAINERS_TABLE') or 'GAINERS_TOP25').strip())
    losers_table = _safe_identifier((os.getenv('YAMUNA_LOOSERS_TABLE') or 'LOOSERS_TOP25').strip())
    volume_table = _safe_identifier((os.getenv('YAMUNA_VOLUME_TABLE') or 'VOLUME_MOVERS_TOP25').strip())
    schema = (os.getenv('YAMUNA_SCHEMA') or os.getenv('ORACLE_SCHEMA') or '').strip()
    if schema:
        if '.' not in gainers_table:
            gainers_table = f'{_safe_identifier(schema)}.{gainers_table}'
        if '.' not in losers_table:
            losers_table = f'{_safe_identifier(schema)}.{losers_table}'
        if '.' not in volume_table:
            volume_table = f'{_safe_identifier(schema)}.{volume_table}'

    binds = {'start_date': start_date}
    signals: List[TradeSignal] = []

    if _to_bool(params.get('include_gainers'), True):
        for row in _load_table_rows(conn, gainers_table, binds=binds):
            symbol = _normalize_text(row.get('stock')).upper()
            entry_date = _to_date(row.get('ltc_date'))
            entry_price = _to_float(row.get('price'))
            if not symbol or not entry_date or entry_price is None or entry_price <= 0:
                continue
            signals.append(TradeSignal('yamuna', 'GAINERS', symbol, 'LONG', entry_date, entry_price, percentage=_to_float(row.get('percentage')), points=_to_float(row.get('points'))))

    if _to_bool(params.get('include_losers'), True):
        for row in _load_table_rows(conn, losers_table, binds=binds):
            symbol = _normalize_text(row.get('stock')).upper()
            entry_date = _to_date(row.get('ltc_date'))
            entry_price = _to_float(row.get('price'))
            if not symbol or not entry_date or entry_price is None or entry_price <= 0:
                continue
            signals.append(TradeSignal('yamuna', 'LOSERS', symbol, 'SHORT', entry_date, entry_price, percentage=_to_float(row.get('percentage')), points=_to_float(row.get('points'))))

    if _to_bool(params.get('include_volume'), True):
        for row in _load_table_rows(conn, volume_table, binds=binds):
            symbol = _normalize_text(row.get('stock')).upper()
            entry_date = _to_date(row.get('ltc_date'))
            entry_price = _to_float(row.get('price'))
            pct = _to_float(row.get('percentage'))
            if not symbol or not entry_date or entry_price is None or entry_price <= 0:
                continue
            direction = 'SHORT' if pct is not None and pct < 0 else 'LONG'
            signals.append(TradeSignal('yamuna', 'VOLUME', symbol, direction, entry_date, entry_price, percentage=pct, points=_to_float(row.get('points'))))

    signals.sort(key=lambda item: (item.entry_date, item.symbol, item.source_name))
    return signals



def _load_bhramhastra_signals(conn, params: Dict[str, Any]) -> List[TradeSignal]:
    if not _to_bool(params.get('enabled'), True):
        return []
    lookback_days = max(30, _to_int(params.get('lookback_days'), 365))
    start_date = datetime.utcnow().date() - timedelta(days=lookback_days)
    try:
        table_name = _resolve_table_with_schema(
            conn,
            'BHRAMHASTRA_TABLE',
            'Bhramhastra_BackTesting_Data',
            ('BHRAMHASTRA_SCHEMA', 'ORACLE_SCHEMA'),
        )
        columns = _get_source_columns(conn, table_name)
    except RuntimeError:
        return []
    symbol_col = _pick_required_column(columns, ('SYMBOL', 'STOCK'), table_name)
    ltc_col = _pick_required_column(columns, ('LTC_DATE', 'TRADE_DATE', 'TRADING_DATE', 'BT_DATE'), table_name)
    entry_col = _pick_required_column(columns, ('ENTRY_PRICE', 'PRICE', 'CLOSE_PRICE', 'CLOSE'), table_name)
    atr_col = _pick_column(columns, ('ATR14', 'ATR'))
    rsi_col = _pick_column(columns, ('RSI14', 'RSI'))
    macd_col = _pick_column(columns, ('MACD_HIST', 'MACD'))
    status_col = _pick_column(columns, ('STATUS',))

    select_cols = [
        f'{symbol_col} AS symbol',
        f'{ltc_col} AS ltc_date',
        f'{entry_col} AS entry_price',
        f'{atr_col} AS atr14' if atr_col else 'CAST(NULL AS NUMBER) AS atr14',
        f'{rsi_col} AS rsi14' if rsi_col else 'CAST(NULL AS NUMBER) AS rsi14',
        f'{macd_col} AS macd_hist' if macd_col else 'CAST(NULL AS NUMBER) AS macd_hist',
        f'{status_col} AS status' if status_col else "CAST('OPEN' AS VARCHAR2(10)) AS status",
    ]
    sql = f'''
        SELECT {", ".join(select_cols)}
        FROM {table_name}
        WHERE {ltc_col} >= :start_date
        ORDER BY {ltc_col}, {symbol_col}
    '''
    rows = _query_rows(conn, sql, {'start_date': start_date})
    entry_min_rsi = max(0.0, _to_float(params.get('entry_min_rsi')) or 0.0)
    entry_max_rsi = min(100.0, _to_float(params.get('entry_max_rsi')) or 100.0)
    macd_positive_only = _to_bool(params.get('macd_positive_only'))

    signals: List[TradeSignal] = []
    for row in rows:
        symbol = _normalize_text(row.get('symbol')).upper()
        entry_date = _to_date(row.get('ltc_date'))
        entry_price = _to_float(row.get('entry_price'))
        rsi_value = _to_float(row.get('rsi14'))
        macd_value = _to_float(row.get('macd_hist'))
        if not symbol or not entry_date or entry_price is None or entry_price <= 0:
            continue
        if entry_min_rsi > 0 and (rsi_value is None or rsi_value < entry_min_rsi):
            continue
        if entry_max_rsi < 100.0 and (rsi_value is None or rsi_value > entry_max_rsi):
            continue
        if macd_positive_only and (macd_value is None or macd_value <= 0):
            continue
        signals.append(
            TradeSignal(
                strategy_name='bhramhastra',
                source_name=BHRAMHASTRA_AGENT_SOURCE,
                symbol=symbol,
                direction='LONG',
                entry_date=entry_date,
                entry_price=entry_price,
                atr=_to_float(row.get('atr14')),
            )
        )

    signals.sort(key=lambda item: (item.entry_date, item.symbol, item.source_name))
    return signals


def _resolve_table_with_schema(conn, env_var_name: str, default_table: str, schema_env_names: Sequence[str]) -> str:
    candidates: List[str] = []

    def add_candidate(value: str) -> None:
        text = (value or '').strip()
        if not text:
            return
        try:
            safe_value = _safe_identifier(text)
        except ValueError:
            return
        if safe_value not in candidates:
            candidates.append(safe_value)

    explicit = (os.getenv(env_var_name) or default_table).strip()
    add_candidate(explicit)
    for schema_env in schema_env_names:
        schema = (os.getenv(schema_env) or '').strip()
        if not schema or '.' in explicit:
            continue
        add_candidate(f'{_safe_identifier(schema)}.{explicit}')

    for candidate in candidates:
        try:
            if _table_exists(conn, candidate):
                return candidate
        except Exception:
            continue
    raise RuntimeError(f'Unable to resolve Oracle table for {env_var_name}')


def _pick_required_column(columns: Sequence[str], candidates: Sequence[str], context: str) -> str:
    column = _pick_column(columns, candidates)
    if column:
        return column
    raise RuntimeError(f'{context} is missing required columns: {", ".join(candidates)}')


def _load_universe_symbols(conn, table_name: str) -> List[str]:
    columns = _get_source_columns(conn, table_name)
    symbol_col = _pick_required_column(columns, ('SYMBOL', 'STOCK'), table_name)
    rows = _query_rows(
        conn,
        f'''SELECT DISTINCT {symbol_col} AS symbol FROM {table_name} WHERE {symbol_col} IS NOT NULL ORDER BY {symbol_col}''',
        {},
    )
    return [
        _normalize_text(row.get('symbol')).upper()
        for row in rows
        if _normalize_text(row.get('symbol'))
    ]


def _load_price_bars_for_universe(conn, table_name: str, symbols: Sequence[str], start_date: date) -> Dict[str, List[DailyBar]]:
    if not symbols:
        return {}
    columns = _get_source_columns(conn, table_name)
    symbol_col = _pick_required_column(columns, ('SYMBOL', 'STOCK'), table_name)
    trade_col = _pick_required_column(columns, ('TRADING_DATE', 'TRADE_DATE', 'DATE'), table_name)
    open_col = _pick_column(columns, ('OPEN_PRICE', 'OPEN', 'O'))
    high_col = _pick_required_column(columns, ('HIGH_PRICE', 'HIGH', 'H'), table_name)
    low_col = _pick_required_column(columns, ('LOW_PRICE', 'LOW', 'L'), table_name)
    close_col = _pick_column(columns, ('CLOSE_PRICE', 'CLOSE', 'ADJ_CLOSE', 'LTP', 'PREVIOUS_CLOSE', 'LAST_PRICE', 'CLOSEVALUE', 'CLOSING_PRICE'))
    if not close_col:
        fallback_cols = [col for col in columns if 'CLOSE' in col.upper() or 'LTP' in col.upper() or 'LAST' in col.upper()]
        close_col = fallback_cols[0] if fallback_cols else None
    if not close_col:
        raise RuntimeError(f'{table_name} is missing a close-like column for backtesting')
    volume_col = _pick_column(columns, ('VOLUME', 'TOTTRDQTY', 'TOT_TRDQTY', 'QTY', 'DELIV_QTY'))

    symbol_binds = {f'sym_{idx}': symbol for idx, symbol in enumerate(sorted(set(symbols)))}
    in_clause = ', '.join(f':{key}' for key in symbol_binds)
    sql = f'''
        SELECT
          {symbol_col} AS symbol,
          {trade_col} AS trade_date,
          {open_col} AS open_price,
          {high_col} AS high_price,
          {low_col} AS low_price,
          {close_col} AS close_price,
          {volume_col} AS volume_val
        FROM {table_name}
        WHERE {trade_col} >= :start_date
          AND {symbol_col} IN ({in_clause})
        ORDER BY {symbol_col}, {trade_col}
    '''
    binds: Dict[str, Any] = {'start_date': start_date}
    binds.update(symbol_binds)
    rows = _query_rows(conn, sql, binds)

    bars_by_symbol: Dict[str, List[DailyBar]] = {}
    for row in rows:
        symbol = _normalize_text(row.get('symbol')).upper()
        trade_date = _to_date(row.get('trade_date'))
        close_price = _to_float(row.get('close_price'))
        if not symbol or not trade_date or close_price is None or close_price <= 0:
            continue
        bars_by_symbol.setdefault(symbol, []).append(
            DailyBar(
                trade_date=trade_date,
                open_price=_to_float(row.get('open_price')),
                high_price=_to_float(row.get('high_price')),
                low_price=_to_float(row.get('low_price')),
                close_price=close_price,
                volume=_to_float(row.get('volume_val')),
            )
        )
    return bars_by_symbol


def _ema_series_values(closes: Sequence[Optional[float]], period: int) -> List[Optional[float]]:
    if period <= 0:
        return [None for _ in closes]
    values: List[Optional[float]] = []
    seed: List[float] = []
    ema_value: Optional[float] = None
    multiplier = 2.0 / (float(period) + 1.0)
    for close in closes:
        price = _to_float(close)
        if price is None:
            values.append(None)
            continue
        if ema_value is None:
            seed.append(price)
            if len(seed) < period:
                values.append(None)
                continue
            ema_value = sum(seed[-period:]) / float(period)
            values.append(ema_value)
            continue
        ema_value = ((price - ema_value) * multiplier) + ema_value
        values.append(ema_value)
    return values


def _rsi_series_values(closes: Sequence[Optional[float]], period: int) -> List[Optional[float]]:
    values: List[Optional[float]] = [None for _ in closes]
    if period <= 0 or len(closes) <= period:
        return values
    avg_gain: Optional[float] = None
    avg_loss: Optional[float] = None
    gains: List[float] = []
    losses: List[float] = []
    prev_close = _to_float(closes[0])

    for idx in range(1, len(closes)):
        current_close = _to_float(closes[idx])
        if current_close is None or prev_close is None:
            prev_close = current_close
            continue
        change = current_close - prev_close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        if idx <= period:
            gains.append(gain)
            losses.append(loss)
            if idx == period:
                avg_gain = sum(gains) / float(period)
                avg_loss = sum(losses) / float(period)
        elif avg_gain is not None and avg_loss is not None:
            avg_gain = ((avg_gain * (period - 1)) + gain) / float(period)
            avg_loss = ((avg_loss * (period - 1)) + loss) / float(period)

        if avg_gain is not None and avg_loss is not None:
            if avg_loss == 0:
                values[idx] = 100.0 if avg_gain > 0 else 50.0
            else:
                rs = avg_gain / avg_loss
                values[idx] = 100.0 - (100.0 / (1.0 + rs))
        prev_close = current_close
    return values


def _macd_line_values(closes: Sequence[Optional[float]], fast_period: int, slow_period: int) -> List[Optional[float]]:
    fast_values = _ema_series_values(closes, fast_period)
    slow_values = _ema_series_values(closes, slow_period)
    macd_values: List[Optional[float]] = []
    for fast_value, slow_value in zip(fast_values, slow_values):
        if fast_value is None or slow_value is None:
            macd_values.append(None)
        else:
            macd_values.append(fast_value - slow_value)
    return macd_values


def _adx_series_values(bars: Sequence[DailyBar], period: int) -> List[Optional[float]]:
    values: List[Optional[float]] = [None for _ in bars]
    if period <= 1 or len(bars) <= (period * 2):
        return values
    true_ranges = [0.0 for _ in bars]
    plus_dm = [0.0 for _ in bars]
    minus_dm = [0.0 for _ in bars]

    for idx in range(1, len(bars)):
        current = bars[idx]
        previous = bars[idx - 1]
        if current.high_price is None or current.low_price is None or previous.high_price is None or previous.low_price is None:
            continue
        reference_close = previous.close_price if previous.close_price is not None else current.close_price
        if reference_close is None:
            continue
        up_move = current.high_price - previous.high_price
        down_move = previous.low_price - current.low_price
        plus_dm[idx] = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm[idx] = down_move if down_move > up_move and down_move > 0 else 0.0
        true_ranges[idx] = max(
            current.high_price - current.low_price,
            abs(current.high_price - reference_close),
            abs(current.low_price - reference_close),
        )

    dx_values: List[Optional[float]] = [None for _ in bars]
    for idx in range(period, len(bars)):
        tr_sum = sum(true_ranges[idx - period + 1: idx + 1])
        if tr_sum <= 0:
            continue
        plus_sum = sum(plus_dm[idx - period + 1: idx + 1])
        minus_sum = sum(minus_dm[idx - period + 1: idx + 1])
        plus_di = (plus_sum / tr_sum) * 100.0
        minus_di = (minus_sum / tr_sum) * 100.0
        denom = plus_di + minus_di
        if denom <= 0:
            continue
        dx_values[idx] = (abs(plus_di - minus_di) / denom) * 100.0

    for idx in range((period * 2) - 1, len(bars)):
        window = [value for value in dx_values[idx - period + 1: idx + 1] if value is not None]
        if len(window) == period:
            values[idx] = sum(window) / float(period)
    return values


def _build_backtestnifty50_signals(bars_by_symbol: Dict[str, List[DailyBar]], params: Dict[str, Any], atr_lookup: Dict[str, Dict[date, float]]) -> List[TradeSignal]:
    ema_fast_period = max(2, _to_int(params.get('ema_fast_period'), 20))
    ema_slow_period = max(ema_fast_period + 1, _to_int(params.get('ema_slow_period'), 50))
    rsi_period = max(2, _to_int(params.get('rsi_period'), 14))
    rsi_threshold = _to_float(params.get('rsi_threshold')) or 50.0
    macd_fast_period = max(2, _to_int(params.get('macd_fast_period'), 12))
    macd_slow_period = max(macd_fast_period + 1, _to_int(params.get('macd_slow_period'), 26))

    signals: List[TradeSignal] = []
    for symbol, bars in bars_by_symbol.items():
        closes = [bar.close_price for bar in bars]
        ema_fast_values = _ema_series_values(closes, ema_fast_period)
        ema_slow_values = _ema_series_values(closes, ema_slow_period)
        rsi_values = _rsi_series_values(closes, rsi_period)
        macd_values = _macd_line_values(closes, macd_fast_period, macd_slow_period)
        for idx, bar in enumerate(bars):
            close_price = _to_float(bar.close_price)
            ema_fast = ema_fast_values[idx]
            ema_slow = ema_slow_values[idx]
            rsi_value = rsi_values[idx]
            macd_value = macd_values[idx]
            if close_price is None or ema_fast is None or ema_slow is None or rsi_value is None or macd_value is None:
                continue
            if not (close_price > ema_fast > ema_slow and rsi_value > rsi_threshold and macd_value > 0):
                continue
            spread_pct = ((ema_fast - ema_slow) / close_price) * 100.0 if close_price else 0.0
            signal_score = min(100.0, 55.0 + max(0.0, rsi_value - rsi_threshold) + max(0.0, spread_pct * 10.0))
            signals.append(
                TradeSignal(
                    strategy_name='backtestnifty50',
                    source_name=BACKTEST_NIFTY50_SOURCE,
                    symbol=symbol,
                    direction='LONG',
                    entry_date=bar.trade_date,
                    entry_price=close_price,
                    signal_score=round(signal_score, 2),
                    atr=(atr_lookup.get(symbol) or {}).get(bar.trade_date),
                    breakout_flag='RULE_MATCH',
                    trend_direction='UPTREND',
                    setup_type='EMA20>EMA50 | RSI>50 | MACD>0',
                )
            )
    signals.sort(key=lambda item: (item.entry_date, item.symbol, item.source_name))
    return signals


def _build_backtestnifty50_v2_signals(bars_by_symbol: Dict[str, List[DailyBar]], params: Dict[str, Any], atr_lookup: Dict[str, Dict[date, float]]) -> List[TradeSignal]:
    ema_fast_period = max(2, _to_int(params.get('ema_fast_period'), 20))
    ema_slow_period = max(ema_fast_period + 1, _to_int(params.get('ema_slow_period'), 50))
    rsi_period = max(2, _to_int(params.get('rsi_period'), 14))
    rsi_threshold = _to_float(params.get('rsi_threshold')) or 55.0
    macd_fast_period = max(2, _to_int(params.get('macd_fast_period'), 12))
    macd_slow_period = max(macd_fast_period + 1, _to_int(params.get('macd_slow_period'), 26))
    adx_period = max(2, _to_int(params.get('adx_period'), 14))
    adx_threshold = _to_float(params.get('adx_threshold')) or 25.0
    breakout_lookback = max(10, _to_int(params.get('breakout_lookback'), 55))
    breakout_margin_atr_mult = max(0.0, _to_float(params.get('breakout_margin_atr_mult')) or 0.25)
    support_buffer_atr_mult = max(0.0, _to_float(params.get('support_buffer_atr_mult')) or 0.10)
    breakout_body_atr_min = max(0.0, _to_float(params.get('breakout_body_atr_min')) or 0.35)
    close_to_high_max_pct = min(0.95, max(0.0, _to_float(params.get('close_to_high_max_pct')) or 0.35))
    trendline_fast_window = max(3, _to_int(params.get('trendline_fast_window'), 10))
    trendline_slow_window = max(trendline_fast_window + 5, _to_int(params.get('trendline_slow_window'), 20))
    trendline_min_rise_pct = max(0.0, _to_float(params.get('trendline_min_rise_pct')) or 0.50)

    signals: List[TradeSignal] = []
    for symbol, bars in bars_by_symbol.items():
        closes = [bar.close_price for bar in bars]
        ema_fast_values = _ema_series_values(closes, ema_fast_period)
        ema_slow_values = _ema_series_values(closes, ema_slow_period)
        rsi_values = _rsi_series_values(closes, rsi_period)
        macd_values = _macd_line_values(closes, macd_fast_period, macd_slow_period)
        adx_values = _adx_series_values(bars, adx_period)
        min_index = max(breakout_lookback, trendline_fast_window + trendline_slow_window)
        for idx, bar in enumerate(bars):
            if idx < min_index:
                continue
            close_price = _to_float(bar.close_price)
            open_price = _to_float(bar.open_price)
            high_price = _to_float(bar.high_price)
            low_price = _to_float(bar.low_price)
            ema_fast = ema_fast_values[idx]
            ema_slow = ema_slow_values[idx]
            rsi_value = rsi_values[idx]
            macd_value = macd_values[idx]
            adx_value = adx_values[idx]
            atr_value = (atr_lookup.get(symbol) or {}).get(bar.trade_date)
            if None in (close_price, open_price, high_price, low_price, ema_fast, ema_slow, rsi_value, macd_value, adx_value, atr_value):
                continue
            if not (close_price > ema_fast > ema_slow and rsi_value > rsi_threshold and macd_value > 0 and adx_value > adx_threshold):
                continue

            resistance_window = [item.high_price for item in bars[idx - breakout_lookback:idx] if item.high_price is not None]
            recent_support_window = [item.low_price for item in bars[idx - trendline_fast_window:idx] if item.low_price is not None]
            base_support_window = [item.low_price for item in bars[idx - trendline_fast_window - trendline_slow_window: idx - trendline_fast_window] if item.low_price is not None]
            recent_high_window = [item.high_price for item in bars[idx - trendline_fast_window:idx] if item.high_price is not None]
            base_high_window = [item.high_price for item in bars[idx - trendline_fast_window - trendline_slow_window: idx - trendline_fast_window] if item.high_price is not None]
            if not resistance_window or not recent_support_window or not base_support_window or not recent_high_window or not base_high_window:
                continue

            prior_resistance = max(resistance_window)
            recent_support = min(recent_support_window)
            base_support = min(base_support_window)
            recent_high = max(recent_high_window)
            base_high = max(base_high_window)
            trendline_ok = recent_support > (base_support * (1.0 + (trendline_min_rise_pct / 100.0))) and recent_high >= base_high
            if not trendline_ok:
                continue

            breakout_margin = atr_value * breakout_margin_atr_mult
            support_buffer = atr_value * support_buffer_atr_mult
            candle_range = max(high_price - low_price, 0.0)
            candle_body = max(close_price - open_price, 0.0)
            close_to_high_ratio = ((high_price - close_price) / candle_range) if candle_range > 0 else 0.0
            price_action_ok = close_price > open_price and candle_body >= (atr_value * breakout_body_atr_min) and close_to_high_ratio <= close_to_high_max_pct
            breakout_ok = close_price > (prior_resistance + breakout_margin)
            support_ok = close_price > (prior_resistance + support_buffer)
            if not (price_action_ok and breakout_ok and support_ok):
                continue

            breakout_pct = ((close_price - prior_resistance) / close_price) * 100.0 if close_price else 0.0
            signal_score = min(
                100.0,
                60.0 + max(0.0, adx_value - adx_threshold) * 0.65 + max(0.0, rsi_value - rsi_threshold) * 0.45 + max(0.0, breakout_pct * 12.0),
            )
            signals.append(
                TradeSignal(
                    strategy_name='backtestnifty50v2',
                    source_name=BACKTEST_NIFTY50_V2_SOURCE,
                    symbol=symbol,
                    direction='LONG',
                    entry_date=bar.trade_date,
                    entry_price=close_price,
                    signal_score=round(signal_score, 2),
                    atr=atr_value,
                    breakout_flag='STRUCTURE_BREAKOUT',
                    trend_direction='UPTREND',
                    setup_type='EMA20>EMA50 | RSI>55 | MACD>0 | ADX>25 | SR Breakout',
                )
            )
    signals.sort(key=lambda item: (item.entry_date, item.symbol, item.source_name))
    return signals


def _load_backtestnifty50_dataset(conn, params: Dict[str, Any], strategy_name: str = 'backtestnifty50') -> Tuple[List[TradeSignal], Dict[str, List[DailyBar]], Dict[str, Dict[date, float]], Dict[str, Dict[date, float]]]:
    if not _to_bool(params.get('enabled'), True):
        return [], {}, {}, {}
    start_date = _to_date(params.get('start_date')) or date(1998, 1, 1)
    universe_table = _resolve_table_with_schema(conn, 'NIFTY50_UNIVERSE_TABLE', 'NSE_NIFTY50_LARGECAP', ('NIFTY50_SCHEMA', 'ORACLE_SCHEMA'))
    price_table = _resolve_table_with_schema(conn, 'NIFTY50_PRICE_TABLE', 'NSE_NIFTY500_DAILY_RAW_DATA_DEV', ('NIFTY50_PRICE_SCHEMA', 'ORACLE_SCHEMA'))
    symbols = _load_universe_symbols(conn, universe_table)
    bars_by_symbol = _load_price_bars_for_universe(conn, price_table, symbols, start_date)
    atr_lookup = {symbol: _build_atr_lookup(bars) for symbol, bars in bars_by_symbol.items()}
    volume_ratio_lookup = {symbol: _build_volume_ratio_lookup(bars) for symbol, bars in bars_by_symbol.items()}
    strategy_key = (strategy_name or 'backtestnifty50').strip().lower()
    if strategy_key == 'backtestnifty50v2':
        signals = _build_backtestnifty50_v2_signals(bars_by_symbol, params, atr_lookup)
    else:
        signals = _build_backtestnifty50_signals(bars_by_symbol, params, atr_lookup)
    return signals, bars_by_symbol, atr_lookup, volume_ratio_lookup


def _load_bars_for_symbols(signals: Iterable[TradeSignal], lookback_days: int) -> Tuple[Dict[str, List[DailyBar]], Dict[str, Dict[date, float]], Dict[str, Dict[date, float]]]:
    signal_list = list(signals)
    if not signal_list:
        return {}, {}, {}
    earliest = min(item.entry_date for item in signal_list) - timedelta(days=40)
    months = max(6, int(math.ceil((lookback_days + 90) / 30.0)))
    raw_series = fetch_ohlc_series_from_oracle(months=months, cutoff_anchor='latest')
    wanted = {item.symbol for item in signal_list}
    bars_by_symbol: Dict[str, List[DailyBar]] = {}
    atr_lookup: Dict[str, Dict[date, float]] = {}
    volume_ratio_lookup: Dict[str, Dict[date, float]] = {}

    for symbol in wanted:
        raw_rows = raw_series.get(symbol) or raw_series.get(symbol.upper()) or raw_series.get(symbol.lower()) or []
        bars: List[DailyBar] = []
        for row in raw_rows:
            trade_date = _to_date(row.get('date'))
            if not trade_date or trade_date < earliest:
                continue
            bars.append(DailyBar(
                trade_date=trade_date,
                open_price=_to_float(row.get('open')),
                high_price=_to_float(row.get('high')),
                low_price=_to_float(row.get('low')),
                close_price=_to_float(row.get('close')),
                volume=_to_float(row.get('volume')),
            ))
        bars.sort(key=lambda item: item.trade_date)
        if not bars:
            continue
        bars_by_symbol[symbol] = bars
        atr_lookup[symbol] = _build_atr_lookup(bars)
        volume_ratio_lookup[symbol] = _build_volume_ratio_lookup(bars)
    return bars_by_symbol, atr_lookup, volume_ratio_lookup


def _build_atr_lookup(bars: List[DailyBar], period: int = 14) -> Dict[date, float]:
    atrs: Dict[date, float] = {}
    true_ranges: List[float] = []
    prev_close: Optional[float] = None
    for bar in bars:
        if bar.high_price is None or bar.low_price is None:
            prev_close = bar.close_price if bar.close_price is not None else prev_close
            continue
        if prev_close is None:
            tr = bar.high_price - bar.low_price
        else:
            tr = max(
                bar.high_price - bar.low_price,
                abs(bar.high_price - prev_close),
                abs(bar.low_price - prev_close),
            )
        true_ranges.append(max(tr, 0.0))
        if len(true_ranges) >= period:
            atrs[bar.trade_date] = sum(true_ranges[-period:]) / float(period)
        prev_close = bar.close_price if bar.close_price is not None else prev_close
    return atrs


def _build_volume_ratio_lookup(bars: List[DailyBar], period: int = 20) -> Dict[date, float]:
    ratios: Dict[date, float] = {}
    prior_volumes: List[float] = []
    for bar in bars:
        volume = _to_float(bar.volume)
        if len(prior_volumes) >= period and volume is not None and volume > 0:
            avg_volume = sum(prior_volumes[-period:]) / float(period)
            if avg_volume > 0:
                ratios[bar.trade_date] = volume / avg_volume
        if volume is not None and volume > 0:
            prior_volumes.append(volume)
    return ratios


def _resolve_risk(signal: TradeSignal, params: Dict[str, Any], atr_lookup: Dict[str, Dict[date, float]], volume_ratio_lookup: Dict[str, Dict[date, float]]) -> Tuple[float, str, Optional[float], Optional[float]]:
    stop_mode = _normalize_text(params.get('stop_mode') or 'PCT').upper() or 'PCT'
    stop_pct = max(0.0, _to_float(params.get('stop_pct')) or 0.05)
    stop_buffer_pct = max(0.0, _to_float(params.get('stop_buffer_pct')) or 0.0)
    atr_mult = max(0.0, _to_float(params.get('atr_mult')) or 1.0)
    atr_buffer_mult = max(0.0, _to_float(params.get('atr_buffer_mult')) or 0.0)
    volume_min_ratio = max(1.0, _to_float(params.get('volume_min_ratio')) or 1.5)
    volume_buffer_pct = max(0.0, _to_float(params.get('volume_buffer_pct')) or 0.0)
    atr_value = signal.atr
    if atr_value is None:
        atr_value = (atr_lookup.get(signal.symbol) or {}).get(signal.entry_date)
    volume_ratio = (volume_ratio_lookup.get(signal.symbol) or {}).get(signal.entry_date)
    pct_risk = signal.entry_price * stop_pct
    atr_risk = atr_value * atr_mult if atr_value is not None and atr_value > 0 else None
    risk = None
    mode_used = stop_mode
    if stop_mode == 'ATR' and atr_risk is not None and atr_risk > 0:
        risk = atr_risk
    elif stop_mode == 'HYBRID':
        risk = max(pct_risk, atr_risk or 0.0)
        mode_used = 'HYBRID'
    if risk is None or risk <= 0:
        mode_used = 'PCT'
        risk = pct_risk
    buffer_risk = signal.entry_price * stop_buffer_pct
    if atr_value is not None and atr_value > 0 and atr_buffer_mult > 0:
        buffer_risk += atr_value * atr_buffer_mult
    if volume_ratio is not None and volume_ratio >= volume_min_ratio and volume_buffer_pct > 0:
        spike_scale = min(volume_ratio / volume_min_ratio, 2.5)
        buffer_risk += signal.entry_price * volume_buffer_pct * spike_scale
    risk += buffer_risk
    return max(risk, signal.entry_price * 0.0025), mode_used, atr_value, volume_ratio


def _directional_return_pct(direction: str, entry_price: float, exit_price: float) -> float:
    if direction == 'SHORT':
        return ((entry_price - exit_price) / entry_price) * 100.0
    return ((exit_price - entry_price) / entry_price) * 100.0


def _find_bar_index(bars: List[DailyBar], entry_date: date) -> int:
    for idx, bar in enumerate(bars):
        if bar.trade_date > entry_date:
            return idx
    return len(bars)

def simulate_trade(signal: TradeSignal, bars: List[DailyBar], params: Dict[str, Any], atr_lookup: Dict[str, Dict[date, float]], volume_ratio_lookup: Dict[str, Dict[date, float]]) -> Optional[Dict[str, Any]]:
    if signal.entry_price <= 0:
        return None
    rr1 = _to_float(params.get('target1_rr')) or 2.0
    rr2 = _to_float(params.get('target2_rr')) or 3.0
    max_holding_days = max(1, _to_int(params.get('max_holding_days'), 30))
    risk, risk_mode, atr_value, volume_ratio = _resolve_risk(signal, params, atr_lookup, volume_ratio_lookup)
    if risk <= 0:
        return None

    if signal.direction == 'SHORT':
        stop_loss = signal.entry_price + risk
        target1 = signal.entry_price - risk * rr1
        target2 = signal.entry_price - risk * rr2
    else:
        stop_loss = signal.entry_price - risk
        target1 = signal.entry_price + risk * rr1
        target2 = signal.entry_price + risk * rr2

    start_index = _find_bar_index(bars, signal.entry_date)
    if start_index >= len(bars):
        return None

    t1_date: Optional[date] = None
    t2_date: Optional[date] = None
    exit_date: Optional[date] = None
    exit_price: Optional[float] = None
    exit_reason = 'OPEN_AT_CUTOFF'
    trading_days = 0
    trail_active = False
    trail_stop = stop_loss
    cutoff_index = min(len(bars), start_index + max_holding_days)

    for idx in range(start_index, cutoff_index):
        bar = bars[idx]
        if bar.high_price is None or bar.low_price is None or bar.close_price is None:
            continue
        trading_days += 1
        high_val = bar.high_price
        low_val = bar.low_price

        if signal.direction == 'SHORT':
            if not trail_active:
                if high_val >= stop_loss and low_val <= target1:
                    exit_reason = 'STOP_LOSS_AMBIGUOUS'
                    exit_price = stop_loss
                    exit_date = bar.trade_date
                    break
                if high_val >= stop_loss:
                    exit_reason = 'STOP_LOSS'
                    exit_price = stop_loss
                    exit_date = bar.trade_date
                    break
                if low_val <= target1:
                    t1_date = bar.trade_date
                    trail_active = True
                    trail_stop = target1
                    if low_val <= target2:
                        t2_date = bar.trade_date
                        exit_reason = 'TARGET2_HIT'
                        exit_price = target2
                        exit_date = bar.trade_date
                        break
            else:
                if high_val >= trail_stop and low_val <= target2:
                    exit_reason = 'TRAIL_STOP_T1_AMBIGUOUS'
                    exit_price = trail_stop
                    exit_date = bar.trade_date
                    break
                if high_val >= trail_stop:
                    exit_reason = 'TRAIL_STOP_T1'
                    exit_price = trail_stop
                    exit_date = bar.trade_date
                    break
                if low_val <= target2:
                    t2_date = bar.trade_date
                    exit_reason = 'TARGET2_HIT'
                    exit_price = target2
                    exit_date = bar.trade_date
                    break
        else:
            if not trail_active:
                if low_val <= stop_loss and high_val >= target1:
                    exit_reason = 'STOP_LOSS_AMBIGUOUS'
                    exit_price = stop_loss
                    exit_date = bar.trade_date
                    break
                if low_val <= stop_loss:
                    exit_reason = 'STOP_LOSS'
                    exit_price = stop_loss
                    exit_date = bar.trade_date
                    break
                if high_val >= target1:
                    t1_date = bar.trade_date
                    trail_active = True
                    trail_stop = target1
                    if high_val >= target2:
                        t2_date = bar.trade_date
                        exit_reason = 'TARGET2_HIT'
                        exit_price = target2
                        exit_date = bar.trade_date
                        break
            else:
                if low_val <= trail_stop and high_val >= target2:
                    exit_reason = 'TRAIL_STOP_T1_AMBIGUOUS'
                    exit_price = trail_stop
                    exit_date = bar.trade_date
                    break
                if low_val <= trail_stop:
                    exit_reason = 'TRAIL_STOP_T1'
                    exit_price = trail_stop
                    exit_date = bar.trade_date
                    break
                if high_val >= target2:
                    t2_date = bar.trade_date
                    exit_reason = 'TARGET2_HIT'
                    exit_price = target2
                    exit_date = bar.trade_date
                    break

    if exit_price is None or exit_date is None:
        close_index = min(len(bars) - 1, max(start_index, cutoff_index - 1))
        bar = bars[close_index]
        exit_date = bar.trade_date
        exit_price = bar.close_price if bar.close_price is not None else signal.entry_price
        exit_reason = 'TIME_EXIT'

    return_pct = _directional_return_pct(signal.direction, signal.entry_price, exit_price)
    return_rr = (return_pct / 100.0 * signal.entry_price) / risk
    success_flag = 1 if return_rr > SUCCESS_EPSILON else 0
    fail_flag = 1 if return_rr < -SUCCESS_EPSILON else 0
    result_flag = 'SUCCESS' if success_flag else ('FAIL' if fail_flag else 'NEUTRAL')

    days_to_t1 = None
    if t1_date:
        days_to_t1 = max(1, sum(1 for bar in bars[start_index:] if bar.trade_date <= t1_date))
    days_to_t2 = None
    if t2_date:
        days_to_t2 = max(1, sum(1 for bar in bars[start_index:] if bar.trade_date <= t2_date))

    direction_label = 'long' if signal.direction == 'LONG' else 'short'
    why_trade = f'{signal.source_name} {direction_label} setup {exit_reason.lower().replace("_", " ")}; return {return_pct:.2f}%.'
    if t1_date and not t2_date and exit_reason.startswith('TRAIL_STOP_T1'):
        why_trade = f'{signal.source_name} {direction_label} setup locked target1 on {_date_to_iso(t1_date)} and trailed out afterward.'
    elif t2_date:
        why_trade = f'{signal.source_name} {direction_label} setup reached target2 on {_date_to_iso(t2_date)}.'
    elif exit_reason.startswith('STOP_LOSS'):
        why_trade = f'{signal.source_name} {direction_label} setup hit stop before any reward target.'
    elif exit_reason == 'TIME_EXIT':
        why_trade = f'{signal.source_name} {direction_label} setup timed out after {trading_days} trading days.'

    return {
        'source_name': signal.source_name,
        'symbol': signal.symbol,
        'direction': signal.direction,
        'entry_date': signal.entry_date,
        'entry_price': round(signal.entry_price, 4),
        'stop_loss': round(stop_loss, 4),
        'target1': round(target1, 4),
        'target2': round(target2, 4),
        'target1_date': t1_date,
        'target2_date': t2_date,
        'exit_date': exit_date,
        'exit_price': round(exit_price, 4),
        'exit_reason': exit_reason,
        'result_flag': result_flag,
        'success_flag': success_flag,
        'fail_flag': fail_flag,
        'trading_days': trading_days,
        'days_to_t1': days_to_t1,
        'days_to_t2': days_to_t2,
        'return_pct': round(return_pct, 4),
        'return_rr': round(return_rr, 6),
        'why_trade': why_trade[:400],
        'risk_mode': risk_mode,
        'atr_value': round(atr_value, 6) if atr_value is not None else None,
        'volume_ratio': round(volume_ratio, 6) if volume_ratio is not None else None,
        'signal_score': signal.signal_score,
        'breakout_flag': signal.breakout_flag,
        'trend_direction': signal.trend_direction,
        'setup_type': signal.setup_type,
        'percentage': signal.percentage,
        'points': signal.points,
    }


def _apply_symbol_cooldown(signals: List[TradeSignal], cooldown_days: int) -> List[TradeSignal]:
    if cooldown_days <= 0:
        return list(signals)
    filtered: List[TradeSignal] = []
    last_entry_by_symbol: Dict[str, date] = {}
    for signal in sorted(signals, key=lambda item: (item.entry_date, item.symbol, item.source_name)):
        last_entry = last_entry_by_symbol.get(signal.symbol)
        if last_entry and signal.entry_date <= (last_entry + timedelta(days=cooldown_days)):
            continue
        filtered.append(signal)
        last_entry_by_symbol[signal.symbol] = signal.entry_date
    return filtered


def summarize_backtests(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    success = sum(int(row.get('success_flag') or 0) for row in rows)
    fail = sum(int(row.get('fail_flag') or 0) for row in rows)
    avg_days = sum(int(row.get('trading_days') or 0) for row in rows) / total if total else 0.0
    avg_rr = sum(float(row.get('return_rr') or 0.0) for row in rows) / total if total else 0.0
    avg_return_pct = sum(float(row.get('return_pct') or 0.0) for row in rows) / total if total else 0.0
    target2_hits = sum(1 for row in rows if row.get('exit_reason') == 'TARGET2_HIT')
    target1_locked = sum(1 for row in rows if str(row.get('exit_reason') or '').startswith('TRAIL_STOP_T1'))
    stop_hits = sum(1 for row in rows if str(row.get('exit_reason') or '').startswith('STOP_LOSS'))
    return {
        'total_trades': total,
        'success_count': success,
        'fail_count': fail,
        'success_rate': round((success / total) * 100.0, 2) if total else 0.0,
        'fail_rate': round((fail / total) * 100.0, 2) if total else 0.0,
        'avg_trading_days': round(avg_days, 2) if total else 0.0,
        'avg_return_rr': round(avg_rr, 4) if total else 0.0,
        'avg_return_pct': round(avg_return_pct, 4) if total else 0.0,
        'target2_hits': target2_hits,
        'target1_locks': target1_locked,
        'stop_hits': stop_hits,
    }


def _generate_candidate_param_sets(strategy_name: str, base_params: Dict[str, Any]) -> List[Dict[str, Any]]:
    strategy = strategy_name.lower()
    candidates: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add_candidate(**updates: Any) -> None:
        params = dict(base_params)
        params.update(updates)
        key = json.dumps(_serialize_params(params), sort_keys=True)
        if key in seen:
            return
        seen.add(key)
        candidates.append(params)

    def add_stop_buffer_candidates() -> None:
        for stop_pct in (0.04, 0.05, 0.06, 0.07):
            for stop_buffer_pct in (0.0, 0.0025, 0.005, 0.0075):
                add_candidate(stop_mode='PCT', stop_pct=stop_pct, stop_buffer_pct=round(stop_buffer_pct, 4))
        for atr_mult in (1.0, 1.25, 1.5, 1.75):
            for atr_buffer_mult in (0.0, 0.25, 0.5):
                add_candidate(stop_mode='ATR', atr_mult=round(atr_mult, 2), atr_buffer_mult=round(atr_buffer_mult, 2))
        for volume_min_ratio in (1.25, 1.5, 1.75, 2.0, 3.0):
            for volume_buffer_pct in (0.0, 0.0025, 0.005):
                add_candidate(volume_min_ratio=round(volume_min_ratio, 2), volume_buffer_pct=round(volume_buffer_pct, 4))
        add_candidate(stop_mode='PCT', stop_pct=0.05, stop_buffer_pct=0.005, atr_buffer_mult=0.25)
        add_candidate(stop_mode='ATR', atr_mult=1.5, atr_buffer_mult=0.25, volume_buffer_pct=0.0025)
        add_candidate(stop_mode='HYBRID', stop_pct=0.05, atr_mult=1.25, stop_buffer_pct=0.0025, atr_buffer_mult=0.25)

    add_candidate()
    if strategy == 'backtestnifty50':
        return candidates
    if strategy == 'backtestnifty50v2':
        add_candidate(adx_threshold=30.0, breakout_lookback=20, breakout_margin_atr_mult=0.15, support_buffer_atr_mult=0.05, breakout_body_atr_min=0.25, close_to_high_max_pct=0.35, trendline_min_rise_pct=0.75, rsi_threshold=55.0, max_holding_days=30, success_target_pct=60.0, min_trade_retention_ratio=0.02)
        add_candidate(adx_threshold=30.0, breakout_lookback=20, breakout_margin_atr_mult=0.15, support_buffer_atr_mult=0.05, breakout_body_atr_min=0.25, close_to_high_max_pct=0.20, trendline_min_rise_pct=0.75, rsi_threshold=55.0, max_holding_days=25, success_target_pct=60.0, min_trade_retention_ratio=0.02)
        add_candidate(adx_threshold=27.5, breakout_lookback=30, breakout_margin_atr_mult=0.25, support_buffer_atr_mult=0.10, breakout_body_atr_min=0.35, close_to_high_max_pct=0.25, trendline_min_rise_pct=0.50, rsi_threshold=55.0, max_holding_days=35, success_target_pct=65.0, min_trade_retention_ratio=0.05)
        add_candidate(adx_threshold=32.5, breakout_lookback=55, breakout_margin_atr_mult=0.35, support_buffer_atr_mult=0.15, breakout_body_atr_min=0.50, close_to_high_max_pct=0.25, trendline_min_rise_pct=1.00, rsi_threshold=58.0, max_holding_days=35, success_target_pct=70.0, min_trade_retention_ratio=0.10)
        return candidates
    if strategy in ('asura', 'yamuna'):
        add_stop_buffer_candidates()
    if strategy == 'asura':
        min_signal = _to_float(base_params.get('min_signal')) or 60.0
        min_adx = _to_float(base_params.get('min_adx')) or 20.0
        for value in (max(45.0, min_signal - 5.0), min_signal + 5.0, min_signal + 10.0):
            add_candidate(min_signal=round(value, 2))
        for value in (max(10.0, min_adx - 5.0), min_adx + 5.0):
            add_candidate(min_adx=round(value, 2))
        add_candidate(breakout_only=0 if _to_bool(base_params.get('breakout_only')) else 1)
        add_candidate(bull_stack_only=1)
        for value in (1.25, 1.5):
            add_candidate(entry_min_volume_ratio=round(value, 2))
        for value in (40.0, 50.0, 60.0):
            add_candidate(entry_min_level_score=round(value, 2))
        add_candidate(entry_min_rsi=52.0, entry_max_rsi=65.0)
        add_candidate(entry_min_rsi=55.0, entry_max_rsi=68.0)
        add_candidate(macd_positive_only=1)
        add_candidate(bull_stack_only=1, entry_min_level_score=40.0)
        add_candidate(bull_stack_only=1, entry_min_level_score=50.0)
        add_candidate(entry_min_level_score=40.0, entry_min_rsi=52.0, entry_max_rsi=65.0)
        add_candidate(entry_min_level_score=50.0, entry_min_rsi=52.0, entry_max_rsi=65.0)
        add_candidate(entry_min_level_score=50.0, entry_min_volume_ratio=1.25)
        add_candidate(entry_min_level_score=60.0, entry_min_volume_ratio=1.25)
        for success_target in (70.0, 75.0, 80.0):
            add_candidate(success_target_pct=success_target)
        for retention_ratio in (0.1, 0.15, 0.2, 0.25, 0.35):
            add_candidate(min_trade_retention_ratio=retention_ratio)
        add_candidate(entry_min_level_score=50.0, entry_min_rsi=52.0, entry_max_rsi=65.0, min_trade_retention_ratio=0.15, success_target_pct=80.0)
        add_candidate(entry_min_level_score=60.0, entry_min_volume_ratio=1.25, min_trade_retention_ratio=0.05, success_target_pct=80.0)
    else:
        for holding_days in (20, 30, 45):
            add_candidate(max_holding_days=holding_days)
        add_candidate(include_volume=0 if _to_bool(base_params.get('include_volume'), True) else 1)
        add_candidate(include_gainers=0 if _to_bool(base_params.get('include_gainers'), True) else 1)
        add_candidate(include_losers=0 if _to_bool(base_params.get('include_losers'), True) else 1)
        for success_target in (65.0, 70.0, 75.0):
            add_candidate(success_target_pct=success_target)
        for retention_ratio in (0.15, 0.25, 0.35):
            add_candidate(min_trade_retention_ratio=retention_ratio)
    return candidates


def _is_candidate_better(baseline: Dict[str, Any], candidate: Dict[str, Any], threshold_pct: float, success_target_pct: float = 0.0, min_trade_retention_ratio: float = 0.0) -> bool:
    candidate_total = candidate.get('total_trades', 0) or 0
    if candidate_total <= 0:
        return False
    baseline_total = baseline.get('total_trades', 0) or 0
    if baseline_total > 0:
        min_required_trades = max(1, int(math.ceil(baseline_total * max(0.0, min(1.0, min_trade_retention_ratio)))))
        if candidate_total < min_required_trades:
            return False
    else:
        return True
    baseline_success = float(baseline.get('success_rate') or 0.0)
    candidate_success = float(candidate.get('success_rate') or 0.0)
    baseline_fail = float(baseline.get('fail_rate') or 0.0)
    candidate_fail = float(candidate.get('fail_rate') or 0.0)
    success_delta = candidate_success - baseline_success
    rr_delta = float(candidate.get('avg_return_rr') or 0.0) - float(baseline.get('avg_return_rr') or 0.0)
    fail_delta = candidate_fail - baseline_fail
    if success_target_pct > 0:
        baseline_gap = abs(success_target_pct - baseline_success)
        candidate_gap = abs(success_target_pct - candidate_success)
        if candidate_success >= success_target_pct and rr_delta >= -0.25 and fail_delta <= 0.0:
            return True
        if candidate_success >= baseline_success and candidate_gap + 0.05 < baseline_gap and rr_delta >= -0.20 and fail_delta <= 0.0:
            return True
        if success_delta >= max(0.25, threshold_pct * 0.8) and rr_delta >= -0.20:
            return True
    if success_delta >= threshold_pct and rr_delta >= -0.10:
        return True
    if success_delta >= 0.20 and rr_delta > 0.05 and fail_delta <= 0.0:
        return True
    return False


def _build_reason(strategy_name: str, baseline_params: Dict[str, Any], selected_params: Dict[str, Any], baseline_summary: Dict[str, Any], selected_summary: Dict[str, Any]) -> str:
    changed = []
    for key in sorted(selected_params.keys()):
        if baseline_params.get(key) == selected_params.get(key):
            continue
        changed.append(f'{key}={selected_params.get(key)}')
    if not changed:
        return (
            f'No better {strategy_name} candidate was found. '
            f'Baseline success stayed at {baseline_summary.get("success_rate", 0.0):.2f}% over {baseline_summary.get("total_trades", 0)} trades.'
        )
    return (
        f'{strategy_name.title()} success rate improved from {baseline_summary.get("success_rate", 0.0):.2f}% '
        f'to {selected_summary.get("success_rate", 0.0):.2f}% across {selected_summary.get("total_trades", 0)} trades '
        f'using {", ".join(changed)}.'
    )


def _serialize_trade_row(row: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'sourceName': row.get('source_name'),
        'symbol': row.get('symbol'),
        'direction': row.get('direction'),
        'buyingDate': _date_to_iso(row.get('entry_date')),
        'sellingDate': _date_to_iso(row.get('exit_date')),
        'entryPrice': row.get('entry_price'),
        'stopLoss': row.get('stop_loss'),
        'target1': row.get('target1'),
        'target2': row.get('target2'),
        'sellingOrExit': row.get('exit_reason'),
        'whyTrade': row.get('why_trade'),
        'successPct': summary.get('success_rate', 0.0),
        'failPct': summary.get('fail_rate', 0.0),
        'total': summary.get('total_trades', 0),
        'tradingDays': row.get('trading_days'),
        'daysToTarget1': row.get('days_to_t1'),
        'daysToTarget2': row.get('days_to_t2'),
        'exitPrice': row.get('exit_price'),
        'resultFlag': row.get('result_flag'),
        'returnPct': row.get('return_pct'),
        'returnRr': row.get('return_rr'),
    }


def _serialize_summary_payload(summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'successRate': summary.get('success_rate', 0.0),
        'failRate': summary.get('fail_rate', 0.0),
        'totalTrades': summary.get('total_trades', 0),
        'avgTradingDays': summary.get('avg_trading_days', 0.0),
        'avgReturnRr': summary.get('avg_return_rr', 0.0),
        'avgReturnPct': summary.get('avg_return_pct', 0.0),
        'target2Hits': summary.get('target2_hits', 0),
        'target1Locks': summary.get('target1_locks', 0),
        'stopHits': summary.get('stop_hits', 0),
    }


def _sort_backtest_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def _row_key(row: Dict[str, Any]) -> Tuple[int, str]:
        entry_date = _to_date(row.get('entry_date')) or date.min
        return (-entry_date.toordinal(), _normalize_text(row.get('symbol')).upper())

    return sorted(list(rows), key=_row_key)


def _normalize_run_source_for_storage(run_source: str | None) -> str:
    value = (str(run_source or 'manual').strip().lower() or 'manual')
    if len(value) <= _RUN_SOURCE_MAX_LENGTH:
        return value
    truncated = value[:_RUN_SOURCE_MAX_LENGTH]
    _logger.warning(
        'Truncating strategy agent run source from %s to %s characters: %s -> %s',
        len(value),
        _RUN_SOURCE_MAX_LENGTH,
        value,
        truncated,
    )
    return truncated


def _build_backtest_preview_payload(conn, strategy_name: str, params: Dict[str, Any], fetch_limit: int) -> Dict[str, Any]:
    preview_rows, preview_summary = _backtest_strategy(conn, strategy_name, params)
    ordered_rows = _sort_backtest_rows(preview_rows)[:fetch_limit]
    return {
        'strategy': strategy_name,
        'runId': None,
        'preview': True,
        'summary': _serialize_summary_payload(preview_summary),
        'rows': [_serialize_trade_row(row, preview_summary) for row in ordered_rows],
    }

def _persist_run(conn, strategy_name: str, run_source: str, status: str, applied: bool, baseline_summary: Dict[str, Any], selected_summary: Dict[str, Any], selected_params: Dict[str, Any], note: str, rows: List[Dict[str, Any]]) -> str:
    run_id = str(uuid.uuid4())
    stored_run_source = _normalize_run_source_for_storage(run_source)
    with conn.cursor() as cur:
        cur.execute(
            f'''
            INSERT INTO {RUNS_TABLE_SQL} (
              RUN_ID, STRATEGY_NAME, RUN_SOURCE, RUN_AT, STATUS, APPLIED_FLAG,
              BASELINE_SUCCESS_RATE, CANDIDATE_SUCCESS_RATE,
              BASELINE_FAIL_RATE, CANDIDATE_FAIL_RATE,
              BASELINE_TOTAL_TRADES, CANDIDATE_TOTAL_TRADES,
              BASELINE_AVG_RR, CANDIDATE_AVG_RR,
              PARAMS_JSON, NOTES
            ) VALUES (
              :run_id, :strategy_name, :run_source, SYSTIMESTAMP, :status, :applied_flag,
              :baseline_success_rate, :candidate_success_rate,
              :baseline_fail_rate, :candidate_fail_rate,
              :baseline_total_trades, :candidate_total_trades,
              :baseline_avg_rr, :candidate_avg_rr,
              :params_json, :notes
            )
            ''',
            {
                'run_id': run_id,
                'strategy_name': strategy_name,
                'run_source': stored_run_source,
                'status': status,
                'applied_flag': 'Y' if applied else 'N',
                'baseline_success_rate': baseline_summary.get('success_rate'),
                'candidate_success_rate': selected_summary.get('success_rate'),
                'baseline_fail_rate': baseline_summary.get('fail_rate'),
                'candidate_fail_rate': selected_summary.get('fail_rate'),
                'baseline_total_trades': baseline_summary.get('total_trades'),
                'candidate_total_trades': selected_summary.get('total_trades'),
                'baseline_avg_rr': baseline_summary.get('avg_return_rr'),
                'candidate_avg_rr': selected_summary.get('avg_return_rr'),
                'params_json': json.dumps(_serialize_params(selected_params), sort_keys=True),
                'notes': note,
            },
        )
        if rows:
            payloads = []
            for idx, row in enumerate(rows, 1):
                payloads.append({
                    'backtest_id': f'{run_id}:{idx}',
                    'run_id': run_id,
                    'strategy_name': strategy_name,
                    'source_name': row.get('source_name'),
                    'symbol': row.get('symbol'),
                    'direction': row.get('direction'),
                    'entry_date': row.get('entry_date'),
                    'exit_date': row.get('exit_date'),
                    'entry_price': row.get('entry_price'),
                    'exit_price': row.get('exit_price'),
                    'stop_loss': row.get('stop_loss'),
                    'target1': row.get('target1'),
                    'target2': row.get('target2'),
                    'target1_date': row.get('target1_date'),
                    'target2_date': row.get('target2_date'),
                    'exit_reason': row.get('exit_reason'),
                    'result_flag': row.get('result_flag'),
                    'success_flag': row.get('success_flag'),
                    'fail_flag': row.get('fail_flag'),
                    'trading_days': row.get('trading_days'),
                    'days_to_t1': row.get('days_to_t1'),
                    'days_to_t2': row.get('days_to_t2'),
                    'return_pct': row.get('return_pct'),
                    'return_rr': row.get('return_rr'),
                    'why_trade': row.get('why_trade'),
                })
            cur.executemany(
                f'''
                INSERT INTO {BACKTEST_TABLE_SQL} (
                  BACKTEST_ID, RUN_ID, STRATEGY_NAME, SOURCE_NAME, SYMBOL, DIRECTION,
                  ENTRY_DATE, EXIT_DATE, ENTRY_PRICE, EXIT_PRICE,
                  STOP_LOSS, TARGET1, TARGET2, TARGET1_DATE, TARGET2_DATE,
                  EXIT_REASON, RESULT_FLAG, SUCCESS_FLAG, FAIL_FLAG,
                  TRADING_DAYS, DAYS_TO_T1, DAYS_TO_T2,
                  RETURN_PCT, RETURN_RR, WHY_TRADE, CREATED_AT
                ) VALUES (
                  :backtest_id, :run_id, :strategy_name, :source_name, :symbol, :direction,
                  :entry_date, :exit_date, :entry_price, :exit_price,
                  :stop_loss, :target1, :target2, :target1_date, :target2_date,
                  :exit_reason, :result_flag, :success_flag, :fail_flag,
                  :trading_days, :days_to_t1, :days_to_t2,
                  :return_pct, :return_rr, :why_trade, SYSTIMESTAMP
                )
                ''',
                payloads,
            )
    conn.commit()
    return run_id


def _write_latest_summary_params(conn, strategy_name: str, summary: Dict[str, Any], note: str) -> None:
    _upsert_param(conn, strategy_name, 'last_success_rate', summary.get('success_rate'), note, updated_by='agent-summary')
    _upsert_param(conn, strategy_name, 'last_fail_rate', summary.get('fail_rate'), note, updated_by='agent-summary')
    _upsert_param(conn, strategy_name, 'last_total_trades', summary.get('total_trades'), note, updated_by='agent-summary')
    _upsert_param(conn, strategy_name, 'last_avg_rr', summary.get('avg_return_rr'), note, updated_by='agent-summary')
    _upsert_param(conn, strategy_name, 'last_run_at', _datetime_to_iso(datetime.utcnow()), note, updated_by='agent-summary')
    _upsert_param(conn, strategy_name, 'last_run_note', note, note, updated_by='agent-summary')


def _upsert_selected_params(conn, strategy_name: str, params: Dict[str, Any], note: str) -> None:
    for key, value in params.items():
        if key not in _PARAM_TYPES:
            continue
        _upsert_param(conn, strategy_name, key, value, note, updated_by='strategy-agent')


def _check_strategy_agent_cancellation(cancel_check: Optional[Callable[[], None]] = None) -> None:
    if callable(cancel_check):
        cancel_check()


def _emit_strategy_agent_progress(
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    **payload: Any,
) -> None:
    if callable(progress_callback):
        progress_callback(payload)


def _backtest_strategy(
    conn,
    strategy_name: str,
    params: Dict[str, Any],
    cancel_check: Optional[Callable[[], None]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    progress_label: str = '',
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    strategy = strategy_name.lower()
    label = progress_label or strategy.upper()
    _check_strategy_agent_cancellation(cancel_check)
    _emit_strategy_agent_progress(progress_callback, stage='LOADING_DATA', message=f'{label}: loading signals and bars...')
    if strategy == 'asura':
        raw_signals = _load_asura_signals(conn, params)
        cooldown_days = max(0, _to_int(params.get('cooldown_days'), 0))
        signals = _apply_symbol_cooldown(raw_signals, cooldown_days)
        lookback_days = max(30, _to_int(params.get('lookback_days'), 365))
        bars_by_symbol, atr_lookup, volume_ratio_lookup = _load_bars_for_symbols(signals, lookback_days)
    elif strategy == 'yamuna':
        raw_signals = _load_yamuna_signals(conn, params)
        cooldown_days = max(0, _to_int(params.get('cooldown_days'), 0))
        signals = _apply_symbol_cooldown(raw_signals, cooldown_days)
        lookback_days = max(30, _to_int(params.get('lookback_days'), 365))
        bars_by_symbol, atr_lookup, volume_ratio_lookup = _load_bars_for_symbols(signals, lookback_days)
    elif strategy == 'bhramhastra':
        raw_signals = _load_bhramhastra_signals(conn, params)
        cooldown_days = max(0, _to_int(params.get('cooldown_days'), 0))
        signals = _apply_symbol_cooldown(raw_signals, cooldown_days)
        lookback_days = max(30, _to_int(params.get('lookback_days'), 365))
        bars_by_symbol, atr_lookup, volume_ratio_lookup = _load_bars_for_symbols(signals, lookback_days)
    elif strategy in ('backtestnifty50', 'backtestnifty50v2'):
        raw_signals, bars_by_symbol, atr_lookup, volume_ratio_lookup = _load_backtestnifty50_dataset(conn, params, strategy_name=strategy)
        cooldown_days = max(0, _to_int(params.get('cooldown_days'), 0))
        signals = _apply_symbol_cooldown(raw_signals, cooldown_days)
    else:
        raise ValueError(f'Unsupported strategy {strategy_name!r}')
    results: List[Dict[str, Any]] = []
    occupied_until: Dict[Tuple[str, str], date] = {}
    total_signals = len(signals)
    _emit_strategy_agent_progress(
        progress_callback,
        stage='BACKTESTING',
        message=f'{label}: processing {total_signals} signals...',
        totalSignals=total_signals,
        processedSignals=0,
    )

    for index, signal in enumerate(signals, 1):
        _check_strategy_agent_cancellation(cancel_check)
        if total_signals and (index == 1 or index % 25 == 0 or index == total_signals):
            _emit_strategy_agent_progress(
                progress_callback,
                stage='BACKTESTING',
                message=f'{label}: processed {index - 1}/{total_signals} signals...',
                totalSignals=total_signals,
                processedSignals=index - 1,
            )
        bars = bars_by_symbol.get(signal.symbol)
        if not bars:
            continue
        key = (signal.symbol, signal.strategy_name)
        if occupied_until.get(key) and signal.entry_date <= occupied_until[key]:
            continue
        result = simulate_trade(signal, bars, params, atr_lookup, volume_ratio_lookup)
        if not result:
            continue
        results.append(result)
        exit_date = result.get('exit_date')
        if isinstance(exit_date, date):
            occupied_until[key] = exit_date

    _emit_strategy_agent_progress(
        progress_callback,
        stage='BACKTESTING',
        message=f'{label}: processed {total_signals}/{total_signals} signals.',
        totalSignals=total_signals,
        processedSignals=total_signals,
        completedTrades=len(results),
    )
    summary = summarize_backtests(results)
    return results, summary


def run_strategy_agent_cycle(
    strategy_name: str,
    run_source: str = 'manual',
    cancel_check: Optional[Callable[[], None]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    strategy = (strategy_name or '').strip().lower()
    if strategy not in DEFAULT_STRATEGY_PARAMS:
        raise ValueError(f'Unsupported strategy {strategy_name!r}')

    _check_strategy_agent_cancellation(cancel_check)
    _emit_strategy_agent_progress(progress_callback, stage='INITIALIZING', message=f'{strategy.upper()}: loading runtime state...')
    with pool.acquire() as conn:
        _check_strategy_agent_cancellation(cancel_check)
        ensure_strategy_agent_runtime(conn)
        baseline_params = get_strategy_params(strategy, conn=conn)
        _emit_strategy_agent_progress(progress_callback, stage='BASELINE', message=f'{strategy.upper()}: running baseline backtest...')
        baseline_rows, baseline_summary = _backtest_strategy(
            conn,
            strategy,
            baseline_params,
            cancel_check=cancel_check,
            progress_callback=progress_callback,
            progress_label=f'{strategy.upper()} baseline',
        )
        selected_params = dict(baseline_params)
        selected_rows = baseline_rows
        selected_summary = baseline_summary
        threshold_pct = _to_float(baseline_params.get('apply_threshold_pct')) or 0.5
        success_target_pct = max(0.0, _to_float(baseline_params.get('success_target_pct')) or 0.0)
        min_trade_retention_ratio = max(0.0, min(1.0, _to_float(baseline_params.get('min_trade_retention_ratio')) or 0.0))
        candidates = _generate_candidate_param_sets(strategy, baseline_params)
        total_candidates = len(candidates)
        _emit_strategy_agent_progress(
            progress_callback,
            stage='SEARCHING',
            message=f'{strategy.upper()}: evaluating {max(total_candidates - 1, 0)} candidate parameter sets...',
            candidateIndex=0,
            candidateCount=max(total_candidates - 1, 0),
        )

        for candidate_index, candidate_params in enumerate(candidates, 1):
            _check_strategy_agent_cancellation(cancel_check)
            if candidate_params == baseline_params:
                continue
            _emit_strategy_agent_progress(
                progress_callback,
                stage='SEARCHING',
                message=f'{strategy.upper()}: candidate {candidate_index}/{total_candidates} in progress...',
                candidateIndex=candidate_index,
                candidateCount=total_candidates,
            )
            candidate_rows, candidate_summary = _backtest_strategy(
                conn,
                strategy,
                candidate_params,
                cancel_check=cancel_check,
                progress_callback=progress_callback,
                progress_label=f'{strategy.upper()} candidate {candidate_index}/{total_candidates}',
            )
            candidate_success_target_pct = max(0.0, _to_float(candidate_params.get('success_target_pct')) or success_target_pct)
            candidate_retention_ratio = max(0.0, min(1.0, _to_float(candidate_params.get('min_trade_retention_ratio')) or min_trade_retention_ratio))
            if _is_candidate_better(selected_summary, candidate_summary, threshold_pct, success_target_pct=candidate_success_target_pct, min_trade_retention_ratio=candidate_retention_ratio):
                selected_params = candidate_params
                selected_rows = candidate_rows
                selected_summary = candidate_summary

        selected_success_target_pct = max(0.0, _to_float(selected_params.get('success_target_pct')) or success_target_pct)
        selected_retention_ratio = max(0.0, min(1.0, _to_float(selected_params.get('min_trade_retention_ratio')) or min_trade_retention_ratio))
        applied = selected_params != baseline_params and _is_candidate_better(baseline_summary, selected_summary, threshold_pct, success_target_pct=selected_success_target_pct, min_trade_retention_ratio=selected_retention_ratio)
        note = _build_reason(strategy, baseline_params, selected_params, baseline_summary, selected_summary)
        summary_to_publish = selected_summary if applied else baseline_summary
        summary_note = note
        if not applied and selected_params != baseline_params:
            summary_note = (
                f'Best {strategy} candidate reached {selected_summary.get("success_rate", 0.0):.2f}% '
                f'across {selected_summary.get("total_trades", 0)} trades but was not applied because '
                f'the active retention guard kept the {baseline_summary.get("total_trades", 0)}-trade baseline in force.'
            )
        _check_strategy_agent_cancellation(cancel_check)
        _emit_strategy_agent_progress(progress_callback, stage='PERSISTING', message=f'{strategy.upper()}: saving agent results...')
        if applied:
            _upsert_selected_params(conn, strategy, selected_params, note)
        _write_latest_summary_params(conn, strategy, summary_to_publish, summary_note)
        run_id = _persist_run(
            conn,
            strategy,
            run_source,
            status='APPLIED' if applied else 'NO_CHANGE',
            applied=applied,
            baseline_summary=baseline_summary,
            selected_summary=selected_summary,
            selected_params=selected_params,
            note=note,
            rows=selected_rows,
        )
        conn.commit()

    _emit_strategy_agent_progress(
        progress_callback,
        stage='COMPLETED',
        message=f'{strategy.upper()}: run completed.',
        runId=run_id,
        applied=applied,
        rowsStored=len(selected_rows),
    )
    return {
        'runId': run_id,
        'strategy': strategy,
        'applied': applied,
        'baselineSummary': baseline_summary,
        'selectedSummary': selected_summary,
        'params': _serialize_params(selected_params),
        'note': note,
        'rowsStored': len(selected_rows),
    }


def run_all_strategy_agent_cycles(
    run_source: str = 'manual',
    cancel_check: Optional[Callable[[], None]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    strategy_order = ['asura', 'yamuna', 'bhramhastra', 'backtestnifty50', 'backtestnifty50v2']
    results: Dict[str, Any] = {}
    total_strategies = len([name for name in strategy_order if name in DEFAULT_STRATEGY_PARAMS])
    progress_index = 0
    for strategy_name in strategy_order:
        if strategy_name not in DEFAULT_STRATEGY_PARAMS:
            continue
        progress_index += 1
        _check_strategy_agent_cancellation(cancel_check)
        _emit_strategy_agent_progress(
            progress_callback,
            stage='BATCH',
            message=f'Running strategy {progress_index}/{total_strategies}: {strategy_name.upper()}...',
            strategyIndex=progress_index,
            strategyCount=total_strategies,
            currentStrategy=strategy_name,
        )
        results[strategy_name] = run_strategy_agent_cycle(
            strategy_name,
            run_source=run_source,
            cancel_check=cancel_check,
            progress_callback=progress_callback,
        )
    return results


def _read_latest_run(conn, strategy_name: str) -> Optional[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            f'''
            SELECT RUN_ID, STRATEGY_NAME, RUN_SOURCE, RUN_AT, STATUS, APPLIED_FLAG,
                   BASELINE_SUCCESS_RATE, CANDIDATE_SUCCESS_RATE,
                   BASELINE_FAIL_RATE, CANDIDATE_FAIL_RATE,
                   BASELINE_TOTAL_TRADES, CANDIDATE_TOTAL_TRADES,
                   BASELINE_AVG_RR, CANDIDATE_AVG_RR,
                   PARAMS_JSON, NOTES
            FROM {RUNS_TABLE_SQL}
            WHERE STRATEGY_NAME = :strategy_name
            ORDER BY RUN_AT DESC
            FETCH FIRST 1 ROWS ONLY
            ''',
            {'strategy_name': strategy_name},
        )
        row = cur.fetchone()
        if not row:
            return None
        columns = [
            'run_id', 'strategy_name', 'run_source', 'run_at', 'status', 'applied_flag',
            'baseline_success_rate', 'candidate_success_rate', 'baseline_fail_rate', 'candidate_fail_rate',
            'baseline_total_trades', 'candidate_total_trades', 'baseline_avg_rr', 'candidate_avg_rr',
            'params_json', 'notes',
        ]
        return dict(zip(columns, row))


def get_strategy_agent_status(strategy_name: str) -> Dict[str, Any]:
    strategy = (strategy_name or '').strip().lower()
    if strategy not in DEFAULT_STRATEGY_PARAMS:
        raise ValueError(f'Unsupported strategy {strategy_name!r}')
    fallback_params = dict(DEFAULT_STRATEGY_PARAMS.get(strategy, {}))
    fallback_summary = {
        'successRate': 0.0,
        'failRate': 0.0,
        'totalTrades': 0,
        'avgReturnRr': 0.0,
        'lastRunAt': None,
        'lastNote': '',
    }
    with pool.acquire() as conn:
        try:
            ensure_strategy_agent_runtime(conn)
            params = get_strategy_params(strategy, conn=conn)
            latest_run = _read_latest_run(conn, strategy)
        except Exception as exc:
            _logger.exception('Strategy agent status fallback for %s', strategy)
            return {
                'strategy': strategy,
                'summary': fallback_summary,
                'params': _serialize_params(fallback_params),
                'lastRun': None,
                'detail': str(exc),
            }

        summary = {
            'successRate': _to_float(params.get('last_success_rate')) or 0.0,
            'failRate': _to_float(params.get('last_fail_rate')) or 0.0,
            'totalTrades': _to_int(params.get('last_total_trades')),
            'avgReturnRr': _to_float(params.get('last_avg_rr')) or 0.0,
            'lastRunAt': params.get('last_run_at') or None,
            'lastNote': params.get('last_run_note') or '',
        }
        latest_payload = None
        if latest_run:
            params_json = latest_run.get('params_json')
            parsed_params = {}
            if params_json:
                try:
                    parsed_params = json.loads(params_json.read() if hasattr(params_json, 'read') else params_json)
                except Exception:
                    parsed_params = {}
            latest_payload = {
                'runId': latest_run.get('run_id'),
                'runAt': _datetime_to_iso(latest_run.get('run_at')),
                'status': latest_run.get('status'),
                'applied': _normalize_text(latest_run.get('applied_flag')).upper() == 'Y',
                'baselineSuccessRate': _to_float(latest_run.get('baseline_success_rate')) or 0.0,
                'candidateSuccessRate': _to_float(latest_run.get('candidate_success_rate')) or 0.0,
                'baselineFailRate': _to_float(latest_run.get('baseline_fail_rate')) or 0.0,
                'candidateFailRate': _to_float(latest_run.get('candidate_fail_rate')) or 0.0,
                'baselineTotalTrades': _to_int(latest_run.get('baseline_total_trades')),
                'candidateTotalTrades': _to_int(latest_run.get('candidate_total_trades')),
                'baselineAvgRr': _to_float(latest_run.get('baseline_avg_rr')) or 0.0,
                'candidateAvgRr': _to_float(latest_run.get('candidate_avg_rr')) or 0.0,
                'params': parsed_params,
                'notes': latest_run.get('notes') if not hasattr(latest_run.get('notes'), 'read') else latest_run.get('notes').read(),
            }
        return {
            'strategy': strategy,
            'summary': summary,
            'params': _serialize_params(params),
            'lastRun': latest_payload,
        }


def get_strategy_agent_backtests(strategy_name: str, limit: int = 50) -> Dict[str, Any]:
    strategy = (strategy_name or '').strip().lower()
    if strategy not in DEFAULT_STRATEGY_PARAMS:
        raise ValueError(f'Unsupported strategy {strategy_name!r}')
    fetch_limit = max(1, min(int(limit or 50), MAX_BACKTEST_ROWS))
    with pool.acquire() as conn:
        try:
            ensure_strategy_agent_runtime(conn)
            params = get_strategy_params(strategy, conn=conn)
            latest_run = _read_latest_run(conn, strategy)
            if not latest_run:
                preview_payload = _build_backtest_preview_payload(conn, strategy, params, fetch_limit)
                return preview_payload
            run_id = latest_run.get('run_id')
            with conn.cursor() as cur:
                cur.execute(
                    f'''
                    SELECT SOURCE_NAME, SYMBOL, DIRECTION, ENTRY_DATE, EXIT_DATE, ENTRY_PRICE, EXIT_PRICE,
                           STOP_LOSS, TARGET1, TARGET2, EXIT_REASON, RESULT_FLAG,
                           SUCCESS_FLAG, FAIL_FLAG, TRADING_DAYS, DAYS_TO_T1, DAYS_TO_T2,
                           RETURN_PCT, RETURN_RR, WHY_TRADE
                    FROM {BACKTEST_TABLE_SQL}
                    WHERE RUN_ID = :run_id
                    ORDER BY ENTRY_DATE DESC, SYMBOL
                    FETCH FIRST {fetch_limit} ROWS ONLY
                    ''',
                    {'run_id': run_id},
                )
                rows = []
                columns = [
                    'source_name', 'symbol', 'direction', 'entry_date', 'exit_date', 'entry_price', 'exit_price',
                    'stop_loss', 'target1', 'target2', 'exit_reason', 'result_flag',
                    'success_flag', 'fail_flag', 'trading_days', 'days_to_t1', 'days_to_t2',
                    'return_pct', 'return_rr', 'why_trade',
                ]
                for record in cur.fetchall() or []:
                    rows.append(dict(zip(columns, record)))
            summary = summarize_backtests(rows)
            serialized_rows = [_serialize_trade_row(row, summary) for row in rows]
            return {
                'strategy': strategy,
                'runId': run_id,
                'summary': _serialize_summary_payload(summary),
                'rows': serialized_rows,
            }
        except Exception as exc:
            _logger.exception('Strategy agent backtests fallback for %s', strategy)
            return {
                'strategy': strategy,
                'runId': None,
                'summary': {'successRate': 0.0, 'failRate': 0.0, 'totalTrades': 0},
                'rows': [],
                'detail': str(exc),
            }


__all__ = [
    'ensure_strategy_agent_tables',
    'ensure_default_strategy_params',
    'get_strategy_params',
    'get_strategy_agent_status',
    'get_strategy_agent_backtests',
    'run_strategy_agent_cycle',
    'run_all_strategy_agent_cycles',
    'simulate_trade',
    'summarize_backtests',
]




















