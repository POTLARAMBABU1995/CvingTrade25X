from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from ..db_pool import pool
except ImportError:  # pragma: no cover
    from db_pool import pool  # type: ignore


ASURA_DEFAULT_MIN_SIGNAL = float(os.getenv("ASURA_DEFAULT_MIN_SIGNAL", "60"))
ASURA_DEFAULT_MIN_ADX = float(os.getenv("ASURA_DEFAULT_MIN_ADX", "20"))
ASURA_MIXED_ADX_MIN = float(os.getenv("ASURA_MIXED_ADX_MIN", "30"))

ASURA_STOP_PCT = float(os.getenv("ASURA_STOP_PCT", "0.05"))
ASURA_TARGET1_PCT = float(os.getenv("ASURA_TARGET1_PCT", "0.10"))
ASURA_TARGET2_PCT = float(os.getenv("ASURA_TARGET2_PCT", "0.15"))

ASURA_BULLISH_TREND_TABLE = (
    os.getenv("ASURA_BULLISH_TREND_TABLE") or "ASURA_BULLISH_TREND_STRATEGY_TESTING"
).strip()
_ASURA_SCHEMA = (os.getenv("ASURA_SCHEMA") or os.getenv("ORACLE_SCHEMA") or "").strip()
if _ASURA_SCHEMA and "." not in ASURA_BULLISH_TREND_TABLE:
    ASURA_BULLISH_TREND_TABLE = f"{_ASURA_SCHEMA}.{ASURA_BULLISH_TREND_TABLE}"

VALID_TIMEFRAMES = ("daily", "weekly")


_IDENT_RE = re.compile(r"^[A-Za-z0-9_.$#]+$")

_REQUIRED_SIGNAL_COLUMNS = {
    "SIGNAL_SCORE",
    "ADX14",
    "EMA_STACK",
    "BREAKOUT_FLAG",
    "TREND_DIRECTION",
}

_SIGNAL_OPTIONAL_COLUMNS: List[Tuple[str, Tuple[str, ...]]] = [
    ("signal_score", ("SIGNAL_SCORE",)),
    ("volume_ratio20", ("VOLUME_RATIO20", "VOLUME_RATIO")),
    ("ema20", ("EMA20",)),
    ("ema50", ("EMA50",)),
    ("ema100", ("EMA100",)),
    ("ema200", ("EMA200",)),
    ("rsi", ("RSI14", "RSI")),
    ("macd", ("MACD_HIST", "MACD")),
    ("volume", ("VOLUME",)),
    ("atr", ("ATR14", "ATR")),
    ("adx14", ("ADX14", "ADX")),
    ("support", ("SUPPORT_PRICE", "SUPPORT")),
    ("resistance", ("RESISTANCE_PRICE", "RESISTANCE")),
    ("trend_direction", ("TREND_DIRECTION",)),
    ("ema_stack", ("EMA_STACK",)),
    ("support_strength", ("SUPPORT_STRENGTH", "S_STRENGTH")),
    ("resistance_strength", ("RESISTANCE_STRENGTH", "R_STRENGTH")),
    ("level_score", ("LEVEL_SCORE",)),
    ("bo_flag", ("BREAKOUT_FLAG", "BO_FLAG")),
    ("retest_ready", ("RETEST_READY", "RETESTREADY")),
    ("setup_type", ("SETUP_TYPE", "SETUPTYPE")),
    ("status", ("STATUS",)),
    ("bt_date", ("BT_DATE", "BACKTESTING_DATE", "RUN_DATE")),
    ("entry_price", ("ENTRY_PRICE", "ENTRYPRICE")),
    ("stop_loss", ("STOP_LOSS", "STOPLOSS", "SL")),
    ("target1", ("TARGET1", "T1")),
    ("target2", ("TARGET2", "T2")),
    ("rr1", ("RR_1", "RRR1", "RR1")),
    ("rr2", ("RR_2", "RRR2", "RR2")),
]

_INSERT_FIELD_MAP: List[Tuple[str, Tuple[str, ...]]] = [
    ("stock", ("STOCK", "SYMBOL")),
    ("buying_date", ("BUYING_DATE", "TRADE_DATE", "TRADING_DATE")),
    ("buying_price", ("BUYING_PRICE", "PRICE", "CLOSE_PRICE", "ENTRY_PRICE", "ENTRYPRICE")),
    ("entry_price", ("ENTRY_PRICE", "ENTRYPRICE")),
    ("signal_score", ("SIGNAL_SCORE", "SIGNALSCORE")),
    ("volume_ratio20", ("VOLUME_RATIO20", "VOLUMERATIO20", "VOLUME_RATIO")),
    ("ema20", ("EMA20", "EMA_20")),
    ("ema50", ("EMA50", "EMA_50")),
    ("ema100", ("EMA100", "EMA_100")),
    ("ema200", ("EMA200", "EMA_200")),
    ("rsi", ("RSI14", "RSI")),
    ("macd", ("MACD_HIST", "MACD")),
    ("volume", ("VOLUME",)),
    ("atr", ("ATR14", "ATR")),
    ("adx14", ("ADX14", "ADX")),
    ("support", ("SUPPORT_PRICE", "SUPPORT")),
    ("resistance", ("RESISTANCE_PRICE", "RESISTANCE")),
    ("trend_direction", ("TREND_DIRECTION", "TRENDIRECTION")),
    ("ema_stack", ("EMA_STACK",)),
    ("support_strength", ("SUPPORT_STRENGTH", "S_STRENGTH")),
    ("resistance_strength", ("RESISTANCE_STRENGTH", "R_STRENGTH")),
    ("level_score", ("LEVEL_SCORE", "LEVELSCORE")),
    ("bo_flag", ("BREAKOUT_FLAG", "BO_FLAG")),
    ("retest_ready", ("RETEST_READY", "RETESTREADY")),
    ("setup_type", ("SETUP_TYPE", "SETUPTYPE")),
    ("status", ("STATUS",)),
    ("bt_date", ("BT_DATE", "BACKTESTING_DATE")),
    ("stop_loss", ("STOP_LOSS", "STOPLOSS", "SL")),
    ("target1", ("TARGET1", "T1")),
    ("target2", ("TARGET2", "T2")),
    ("rr1", ("RR_1", "RRR1", "RR1")),
    ("rr2", ("RR_2", "RRR2", "RR2")),
]

_INSERT_KEYS = [key for key, _ in _INSERT_FIELD_MAP]


def _pick_available_column(available: set[str], candidates: Tuple[str, ...]) -> Optional[str]:
    for cand in candidates:
        if cand in available:
            return cand
    return None


def _resolve_target_columns(conn, table: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {table} WHERE ROWNUM = 0")
        return {str(col[0]).upper() for col in (cur.description or []) if col and col[0]}


def _get_source_columns(conn, source: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {source} WHERE ROWNUM = 0")
        return {str(col[0]).upper() for col in (cur.description or []) if col and col[0]}


def _has_signal_columns(columns: set[str]) -> bool:
    if not columns:
        return False
    has_symbol = ("SYMBOL" in columns) or ("STOCK" in columns)
    has_date = ("TRADE_DATE" in columns) or ("TRADING_DATE" in columns)
    has_price = any(col in columns for col in ("CLOSE_PRICE", "PRICE", "BUYING_PRICE", "LTP", "LAST_PRICE", "CLOSE"))
    has_required = _REQUIRED_SIGNAL_COLUMNS.issubset(columns)
    return has_symbol and has_date and has_price and has_required


def _pick_column(columns: set[str], candidates: Sequence[str], label: str) -> str:
    for cand in candidates:
        if cand in columns:
            return cand
    raise RuntimeError(f"Missing {label} column in Asura signal source")


def _safe_identifier(value: str) -> str:
    candidate = (value or "").strip()
    if not candidate or not _IDENT_RE.match(candidate):
        raise ValueError("Invalid identifier")
    return candidate


@dataclass
class OhlcBar:
    trade_date: date
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]




def _to_date(value: Any) -> Optional[date]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None


def _build_signal_candidates(timeframe: str) -> list[str]:
    schema = (os.getenv("ASURA_SCHEMA") or os.getenv("ORACLE_SCHEMA") or "").strip()
    explicit = ""
    if timeframe == "weekly":
        explicit = (os.getenv("ASURA_SIGNAL_VIEW_WEEKLY") or os.getenv("ASURA_VIEW_WEEKLY") or "").strip()
    else:
        explicit = (os.getenv("ASURA_SIGNAL_VIEW_DAILY") or os.getenv("ASURA_VIEW") or "").strip()

    bases = (
        ["V_ASURA_SCAN_WEEKLY_LATEST", "MV_ASURA_SCAN_WEEKLY", "ASURA_SCAN_WEEKLY_FACT"]
        if timeframe == "weekly"
        else ["V_ASURA_SCAN_LATEST", "MV_ASURA_SCAN_DAILY", "ASURA_SCAN_DAILY_FACT"]
    )
    candidates: list[str] = []

    def add(name: str) -> None:
        name = name.strip()
        if not name:
            return
        try:
            name = _safe_identifier(name)
        except ValueError:
            return
        if name not in candidates:
            candidates.append(name)

    if explicit:
        add(explicit)
    for base in bases:
        add(base)
        if schema:
            add(f"{schema}.{base}")
    return candidates


def _resolve_signal_source(conn, timeframe: str) -> Tuple[str, set[str]]:
    candidates = _build_signal_candidates(timeframe)
    if not candidates:
        raise RuntimeError("No Asura signal source candidates configured")
    for name in candidates:
        try:
            cols = _get_source_columns(conn, name)
        except Exception as exc:
            if "ORA-00942" in str(exc):
                continue
            raise
        if not _has_signal_columns(cols):
            continue
        return name, cols
    raise RuntimeError(
        "Asura signal source not found (tried: %s)."
        % (", ".join(candidates))
    )


def _resolve_trade_date(conn, source: str, columns: set[str]) -> date:
    trade_col = _pick_column(columns, ("TRADE_DATE", "TRADING_DATE"), "trade date")
    with conn.cursor() as cur:
        cur.execute(f"SELECT MAX({trade_col}) FROM {source}")
        row = cur.fetchone()
        val = row[0] if row else None
    resolved = _to_date(val)
    if not resolved:
        raise RuntimeError("Unable to resolve cutoff date from Asura source")
    return resolved


def _ensure_bullish_strategy_table(conn) -> None:
    table = _safe_identifier(ASURA_BULLISH_TREND_TABLE)
    with conn.cursor() as cur:
        try:
            cur.execute(f"SELECT 1 FROM {table} WHERE ROWNUM = 1")
            return
        except Exception as exc:
            if "ORA-00942" not in str(exc):
                raise
        try:
            cur.execute(
                f"""
                CREATE TABLE {table}
                (
                    S_NO           NUMBER,
                    STOCK          VARCHAR2(50),
                    BUYING_PRICE   NUMBER(10,2),
                    BUYING_DATE    DATE,
                    SELLING_PRICE  NUMBER(10,2),
                    SELLING_DATE   DATE,
                    SL             NUMBER(10,2),
                    T1             NUMBER(10,2),
                    T2             NUMBER(10,2),
                    SIGNAL_SCORE   NUMBER(10,2),
                    VOLUME_RATIO20 NUMBER(10,2),
                    EMA20          NUMBER(10,2),
                    EMA50          NUMBER(10,2),
                    EMA100         NUMBER(10,2),
                    EMA200         NUMBER(10,2),
                    RSI14          NUMBER(10,2),
                    MACD_HIST      NUMBER(10,4),
                    VOLUME         NUMBER(18,2),
                    ATR14          NUMBER(10,2),
                    ADX14          NUMBER(10,2),
                    SUPPORT_PRICE  NUMBER(10,2),
                    RESISTANCE_PRICE NUMBER(10,2),
                    TREND_DIRECTION VARCHAR2(20),
                    EMA_STACK      VARCHAR2(20),
                    SUPPORT_STRENGTH NUMBER(10,2),
                    RESISTANCE_STRENGTH NUMBER(10,2),
                    LEVEL_SCORE    NUMBER(10,2),
                    BREAKOUT_FLAG  VARCHAR2(20),
                    RETEST_READY   NUMBER(1),
                    SETUP_TYPE     VARCHAR2(20),
                    STATUS         VARCHAR2(40),
                    BT_DATE        DATE,
                    ENTRY_PRICE    NUMBER(10,2),
                    STOP_LOSS      NUMBER(10,2),
                    TARGET1        NUMBER(10,2),
                    TARGET2        NUMBER(10,2),
                    RR_1           NUMBER(10,2),
                    RR_2           NUMBER(10,2)
                )
                """
            )
        except Exception as exc:
            if "ORA-00955" in str(exc):
                return
            raise


def _load_signal_rows(
    conn,
    source: str,
    source_columns: set[str],
    *,
    start_date: Optional[date],
    cutoff_date: Optional[date],
    apply_date_filter: bool,
    min_signal: float,
    min_adx: float,
    breakout_only: bool,
) -> Dict[str, List[Dict[str, Any]]]:
    rows_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    symbol_col = _pick_column(source_columns, ("SYMBOL", "STOCK"), "symbol")
    trade_col = _pick_column(source_columns, ("TRADE_DATE", "TRADING_DATE"), "trade date")
    close_col = _pick_column(source_columns, ("CLOSE_PRICE", "PRICE", "BUYING_PRICE", "LTP", "LAST_PRICE", "CLOSE"), "close price")
    date_filter = ""
    binds = {
        "min_signal": min_signal,
        "min_adx": min_adx,
        "mixed_adx_min": ASURA_MIXED_ADX_MIN,
        "breakout_only": 1 if breakout_only else 0,
    }
    if apply_date_filter:
        date_filter = f" AND {trade_col} >= :start_date AND {trade_col} <= :cutoff_date "
        binds["start_date"] = start_date
        binds["cutoff_date"] = cutoff_date

    select_parts = [
        f"{symbol_col} AS SYMBOL",
        f"{trade_col} AS TRADE_DATE",
        f"{close_col} AS CLOSE_PRICE",
    ]
    for key, candidates in _SIGNAL_OPTIONAL_COLUMNS:
        col = _pick_available_column(source_columns, candidates)
        if not col:
            continue
        select_parts.append(f"{col} AS {key.upper()}")

    select_sql = ",\n        ".join(select_parts)
    sql = f"""
      SELECT
        {select_sql}
      FROM {source}
      WHERE TREND_DIRECTION = 'UPTREND'
        AND NVL(SIGNAL_SCORE, 0) >= :min_signal
        AND NVL(ADX14, 0) >= :min_adx
        AND (EMA_STACK = 'BULL_STACK'
             OR (EMA_STACK = 'MIXED' AND NVL(ADX14, 0) >= :mixed_adx_min))
        AND (:breakout_only = 0 OR BREAKOUT_FLAG = 'BREAKOUT')
        {date_filter}
      ORDER BY SYMBOL, TRADE_DATE
    """
    with conn.cursor() as cur:
        cur.execute(sql, binds)
        cols = [str(col[0]).lower() for col in (cur.description or []) if col and col[0]]
        for record in cur:
            row = dict(zip(cols, record))
            symbol = row.get("symbol")
            if not symbol:
                continue
            trade_date = _to_date(row.get("trade_date"))
            price = _to_float(row.get("close_price"))
            if not trade_date or price is None:
                continue
            sym = str(symbol).strip().upper()
            item = {key: None for key in _INSERT_KEYS}
            item["stock"] = sym
            item["buying_date"] = trade_date
            item["buying_price"] = price

            entry_price_val = _to_float(row.get("entry_price"))
            item["entry_price"] = entry_price_val if entry_price_val is not None else price

            for key, _ in _SIGNAL_OPTIONAL_COLUMNS:
                raw_val = row.get(key)
                if raw_val is None:
                    continue
                if key in {
                    "signal_score",
                    "volume_ratio20",
                    "ema20",
                    "ema50",
                    "ema100",
                    "ema200",
                    "rsi",
                    "macd",
                    "volume",
                    "atr",
                    "adx14",
                    "support",
                    "resistance",
                    "support_strength",
                    "resistance_strength",
                    "level_score",
                    "entry_price",
                    "stop_loss",
                    "target1",
                    "target2",
                    "rr1",
                    "rr2",
                }:
                    item[key] = _to_float(raw_val)
                elif key == "retest_ready":
                    item[key] = 1 if _to_bool_flag(raw_val) else 0
                elif key == "bt_date":
                    item[key] = _to_date(raw_val)
                elif key in {"trend_direction", "ema_stack", "bo_flag"}:
                    item[key] = str(raw_val).strip().upper()
                elif key in {"setup_type", "status"}:
                    item[key] = str(raw_val).strip()
                else:
                    item[key] = raw_val

            if item.get("stop_loss") is None or item.get("target1") is None or item.get("target2") is None:
                target1, target2, stop_loss = _compute_targets(price)
                if item.get("stop_loss") is None:
                    item["stop_loss"] = stop_loss
                if item.get("target1") is None:
                    item["target1"] = target1
                if item.get("target2") is None:
                    item["target2"] = target2

            rows_by_symbol.setdefault(sym, []).append(item)
    return rows_by_symbol


def _resolve_available_columns(conn, schema: str, table: str) -> set[str]:
    qualified = f"{schema}.{table}" if schema else table
    with conn.cursor() as meta_cur:
        meta_cur.execute(f"SELECT * FROM {qualified} WHERE ROWNUM = 0")
        desc = meta_cur.description or []
        return {str(col[0]).upper() for col in desc if col and col[0]}


def _collect_candidates(available: set[str], candidates: List[str]) -> List[str]:
    out: List[str] = []
    for cand in candidates:
        name = cand.upper()
        if name in available and name not in out:
            out.append(name)
    return out


def _select_expr(columns: List[str], alias: str) -> str:
    if not columns:
        return f"NULL AS {alias}"
    if len(columns) == 1:
        return f"{columns[0]} AS {alias}"
    joined = ", ".join(columns)
    return f"COALESCE({joined}) AS {alias}"


def _fetch_ohlc_series(
    symbols: Iterable[str],
    start_date: date,
    cutoff_date: date,
) -> Dict[str, List[OhlcBar]]:
    symbol_list = [str(sym).strip().upper() for sym in symbols if sym]
    if not symbol_list:
        return {}

    schema = os.getenv("ORACLE_SCHEMA", "")
    table = os.getenv("ORACLE_TABLE", "NSE_NIFTY500_DAILY_RAW_DATA_DEV")
    qualified = f"{schema}.{table}" if schema else table

    series: Dict[str, List[OhlcBar]] = {}
    with pool.acquire() as conn:
        available = _resolve_available_columns(conn, schema, table)
        date_cols = _collect_candidates(available, ["TRADING_DATE", "TRADE_DATE", "DATE", "TRADE_DT"])
        if not date_cols:
            raise RuntimeError(f"No trade date column found for {qualified}")
        date_col = date_cols[0]

        high_cols = _collect_candidates(available, ["HIGH_PRICE", "HIGH", "H"])
        low_cols = _collect_candidates(available, ["LOW_PRICE", "LOW", "L"])
        close_candidates = [
            "CLOSE_PRICE", "CLOSE", "ADJ_CLOSE", "LTP",
            "LAST_PRICE", "LAST_TRADED_PRICE", "LASTTRADEPRICE",
            "CLOSING_PRICE", "CLOSE_RATE", "CLOSEVALUE", "CLOSE_VAL",
            "CLOSEPRICE", "CLOSEP",
        ]
        close_cols = _collect_candidates(available, close_candidates)
        if not close_cols and "LTP" in available:
            close_cols = ["LTP"]
        if not close_cols:
            fallback_close = [col for col in sorted(available) if any(key in col for key in ("CLOSE", "LTP", "LAST"))]
            if fallback_close:
                close_cols = fallback_close
        if not close_cols:
            raise RuntimeError(f"No close/ltp column detected for table {qualified}")

        high_expr = _select_expr(high_cols, "HIGH_VAL")
        low_expr = _select_expr(low_cols, "LOW_VAL")
        close_expr = _select_expr(close_cols, "CLOSE_VAL")

        chunk_size = 900
        for idx in range(0, len(symbol_list), chunk_size):
            chunk = symbol_list[idx:idx + chunk_size]
            binds: Dict[str, Any] = {
                "start_date": start_date,
                "cutoff_date": cutoff_date,
            }
            sym_binds = []
            for i, sym in enumerate(chunk):
                key = f"sym{i}"
                binds[key] = sym
                sym_binds.append(f":{key}")
            sym_clause = ", ".join(sym_binds)
            sql = f"""
                SELECT
                  SYMBOL,
                  {date_col} AS TRADE_DATE,
                  {high_expr},
                  {low_expr},
                  {close_expr}
                FROM {qualified}
                WHERE SYMBOL IS NOT NULL
                  AND {date_col} >= :start_date
                  AND {date_col} <= :cutoff_date
                  AND SYMBOL IN ({sym_clause})
                ORDER BY SYMBOL, {date_col}
            """
            with conn.cursor() as cur:
                cur.arraysize = 5000
                cur.execute(sql, binds)
                for sym, dt_val, high_val, low_val, close_val in cur:
                    if not sym:
                        continue
                    trade_dt = _to_date(dt_val)
                    if not trade_dt:
                        continue
                    bar = OhlcBar(
                        trade_date=trade_dt,
                        high=_to_float(high_val),
                        low=_to_float(low_val),
                        close=_to_float(close_val),
                    )
                    key = str(sym).strip().upper()
                    series.setdefault(key, []).append(bar)
    return series


def _aggregate_weekly(bars: List[OhlcBar]) -> List[OhlcBar]:
    buckets: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for bar in bars:
        iso = bar.trade_date.isocalendar()
        key = (iso[0], iso[1])
        bucket = buckets.get(key)
        if bucket is None:
            buckets[key] = {
                "date": bar.trade_date,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
            }
            continue
        if bar.high is not None:
            bucket["high"] = bar.high if bucket["high"] is None else max(bucket["high"], bar.high)
        if bar.low is not None:
            bucket["low"] = bar.low if bucket["low"] is None else min(bucket["low"], bar.low)
        bucket["close"] = bar.close
        bucket["date"] = bar.trade_date

    aggregated: List[OhlcBar] = []
    for bucket in sorted(buckets.values(), key=lambda b: b["date"]):
        aggregated.append(OhlcBar(
            trade_date=bucket["date"],
            high=bucket["high"],
            low=bucket["low"],
            close=bucket["close"],
        ))
    return aggregated


def _compute_targets(entry_price: float) -> Tuple[float, float, float]:
    target1 = entry_price * (1 + ASURA_TARGET1_PCT)
    target2 = entry_price * (1 + ASURA_TARGET2_PCT)
    stop_loss = entry_price * (1 - ASURA_STOP_PCT)
    return target1, target2, stop_loss


def _find_exit_hit(
    *,
    buying_date: date,
    buying_price: float,
    bars: List[OhlcBar],
    cutoff_date: date,
) -> Optional[Dict[str, Any]]:
    target1, target2, stop_loss = _compute_targets(buying_price)
    for bar in bars:
        if bar.trade_date < buying_date or bar.trade_date > cutoff_date:
            continue
        high = bar.high
        low = bar.low
        # Exit priority: target2, stop-loss, then target1.
        if high is not None and high >= target2:
            return {
                "exit_date": bar.trade_date,
                "exit_price": target2,
                "sl": None,
                "t1": None,
                "t2": target2,
            }
        if low is not None and low <= stop_loss:
            return {
                "exit_date": bar.trade_date,
                "exit_price": stop_loss,
                "sl": stop_loss,
                "t1": None,
                "t2": None,
            }
        if high is not None and high >= target1:
            return {
                "exit_date": bar.trade_date,
                "exit_price": target1,
                "sl": None,
                "t1": target1,
                "t2": None,
            }
    return None


def sync_asura_bullish_strategy(
    *,
    timeframe: str = "daily",
    min_signal: Optional[float] = None,
    min_adx: Optional[float] = None,
    breakout_only: bool = False,
) -> Dict[str, Any]:
    tf = (timeframe or "daily").strip().lower()
    if tf not in VALID_TIMEFRAMES:
        raise ValueError("Invalid timeframe (daily/weekly only)")

    with pool.acquire() as conn:
        _ensure_bullish_strategy_table(conn)
        try:
            source, source_columns = _resolve_signal_source(conn, tf)
        except Exception as exc:
            return {
                "cutoffDate": None,
                "candidates": 0,
                "signalCandidates": 0,
                "inserted": 0,
                "exitsUpdated": 0,
                "exitUpdateError": None,
                "skipped": True,
                "skipReason": str(exc),
            }
        use_latest = "LATEST" in source.upper()
        cutoff_dt = None if use_latest else _resolve_trade_date(conn, source, source_columns)

        existing_symbols: set[str] = set()
        open_positions: List[Dict[str, Any]] = []
        trade_candidates: List[Dict[str, Any]] = []
        max_s_no = 0
        table = _safe_identifier(ASURA_BULLISH_TREND_TABLE)
        available_cols = _resolve_target_columns(conn, table)
        stock_col = _pick_available_column(available_cols, ("STOCK", "SYMBOL")) or "STOCK"

        with conn.cursor() as cur:
            if "S_NO" in available_cols:
                cur.execute(f"SELECT NVL(MAX(S_NO), 0) FROM {table}")
                row = cur.fetchone()
                max_s_no = int(row[0] or 0) if row else 0

            cur.execute(f"SELECT DISTINCT {stock_col} FROM {table}")
            for (stock_val,) in cur.fetchall() or []:
                sym = str(stock_val).strip().upper() if stock_val else ""
                if sym:
                    existing_symbols.add(sym)

            cur.execute(
                f"""
                SELECT {stock_col}, BUYING_DATE, BUYING_PRICE
                FROM {table}
                WHERE SELLING_DATE IS NULL
                """
            )
            for stock, buying_date, buying_price in cur.fetchall() or []:
                sym = str(stock).strip().upper() if stock else ""
                buying_dt = _to_date(buying_date)
                price = _to_float(buying_price)
                if not sym or not buying_dt or price is None:
                    continue
                open_positions.append({
                    "stock": sym,
                    "buying_date": buying_dt,
                    "buying_price": price,
                })

        min_signal_val = ASURA_DEFAULT_MIN_SIGNAL if min_signal is None else float(min_signal)
        min_adx_val = ASURA_DEFAULT_MIN_ADX if min_adx is None else float(min_adx)
        signal_candidates = 0
        seen_signal_symbols: set[str] = set()
        signal_rows = _load_signal_rows(
            conn,
            source,
            source_columns,
            start_date=cutoff_dt,
            cutoff_date=cutoff_dt,
            apply_date_filter=not use_latest,
            min_signal=min_signal_val,
            min_adx=min_adx_val,
            breakout_only=bool(breakout_only),
        )
        for symbol, rows in signal_rows.items():
            if not rows:
                continue
            sym = str(symbol).strip().upper()
            if not sym or sym in seen_signal_symbols:
                continue
            rows_sorted = sorted(rows, key=lambda r: r.get("buying_date") or date.min)
            latest = rows_sorted[-1]
            buying_dt = latest.get("buying_date")
            buying_price = latest.get("buying_price")
            if not buying_dt or buying_price is None:
                continue
            trade_candidates.append(latest)
            seen_signal_symbols.add(sym)
            signal_candidates += 1

        inserted = 0
        inserts: List[Dict[str, Any]] = []
        next_s_no = max_s_no + 1
        seen_candidates: set[str] = set()
        for candidate in trade_candidates:
            symbol = candidate["stock"]
            if symbol in existing_symbols or symbol in seen_candidates:
                continue
            row_out = {key: candidate.get(key) for key in _INSERT_KEYS}
            row_out["s_no"] = next_s_no
            row_out["stock"] = symbol
            inserts.append(row_out)
            seen_candidates.add(symbol)
            next_s_no += 1

        updates: List[Dict[str, Any]] = []
        updated = 0
        update_error = None
        exit_positions = list(open_positions)
        if inserts:
            for row in inserts:
                exit_positions.append({
                    "stock": row["stock"],
                    "buying_date": row["buying_date"],
                    "buying_price": row["buying_price"],
                })

        if exit_positions:
            try:
                symbols = {row["stock"] for row in exit_positions}
                start_date = min(row["buying_date"] for row in exit_positions)
                ohlc = _fetch_ohlc_series(symbols, start_date, cutoff_dt)
                if tf == "weekly":
                    for sym, bars in list(ohlc.items()):
                        ohlc[sym] = _aggregate_weekly(bars)

                for position in exit_positions:
                    bars = ohlc.get(position["stock"], [])
                    hit = _find_exit_hit(
                        buying_date=position["buying_date"],
                        buying_price=position["buying_price"],
                        bars=bars,
                        cutoff_date=cutoff_dt,
                    )
                    if not hit:
                        continue
                    updates.append({
                        "stock": position["stock"],
                        "buying_date": position["buying_date"],
                        "selling_date": hit["exit_date"],
                        "selling_price": hit["exit_price"],
                        "sl": hit["sl"],
                        "t1": hit["t1"],
                        "t2": hit["t2"],
                    })
            except Exception as exc:
                update_error = str(exc)
                updates = []

        if inserts:
            with conn.cursor() as cur:
                columns: List[str] = []
                values: List[str] = []

                def _add(col: Optional[str], expr: str) -> None:
                    if not col or col in columns:
                        return
                    columns.append(col)
                    values.append(expr)

                if "S_NO" in available_cols:
                    _add("S_NO", ":s_no")
                for key, candidates in _INSERT_FIELD_MAP:
                    col = _pick_available_column(available_cols, candidates)
                    if not col:
                        continue
                    _add(col, f":{key}")

                insert_sql = f"""
                INSERT INTO {table} ({", ".join(columns)})
                SELECT {", ".join(values)}
                FROM dual
                WHERE NOT EXISTS (
                    SELECT 1 FROM {table} t WHERE t.{stock_col} = :stock
                )
                """
                cur.executemany(insert_sql, inserts)
                inserted = cur.rowcount or len(inserts)
            conn.commit()

        if updates:
            with conn.cursor() as cur:
                cur.executemany(
                    f"""
                    UPDATE {table}
                    SET SELLING_DATE = :selling_date,
                        SELLING_PRICE = :selling_price,
                        SL = :sl,
                        T1 = :t1,
                        T2 = :t2
                    WHERE STOCK = :stock
                      AND BUYING_DATE = :buying_date
                      AND SELLING_DATE IS NULL
                    """,
                    updates,
                )
                updated = cur.rowcount or len(updates)
            conn.commit()

    return {
        "cutoffDate": cutoff_dt.isoformat() if cutoff_dt else None,
        "candidates": len(trade_candidates),
        "signalCandidates": signal_candidates,
        "inserted": inserted,
        "exitsUpdated": updated,
        "exitUpdateError": update_error,
    }
