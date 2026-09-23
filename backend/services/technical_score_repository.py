from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime
from typing import Any, Iterable

try:
    from services.technical_score_engine import (
        ENGINE_SOURCE,
        calculate_master_score,
        calculate_master_trend,
        dumps_json,
    )
except ImportError:  # pragma: no cover
    from .technical_score_engine import (  # type: ignore
        ENGINE_SOURCE,
        calculate_master_score,
        calculate_master_trend,
        dumps_json,
    )

logger = logging.getLogger(__name__)

_IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*(?:\.[A-Za-z][A-Za-z0-9_$#]*)?$")

TECHNICAL_SCORE_LATEST_TABLE = (
    os.getenv("TECHNICAL_SCORE_LATEST_TABLE") or "TECHNICAL_SCORE_LATEST"
).strip()
TECHNICAL_SCORE_HISTORY_TABLE = (
    os.getenv("TECHNICAL_SCORE_HISTORY_TABLE") or "TECHNICAL_SCORE_HISTORY"
).strip()
TECHNICAL_SCORE_CONFIG_TABLE = (
    os.getenv("TECHNICAL_SCORE_CONFIG_TABLE") or "TECHNICAL_SCORE_CONFIG"
).strip()


def _safe_identifier(value: str) -> str:
    text = str(value or "").strip().upper()
    if not text or not _IDENT_RE.fullmatch(text):
        raise ValueError(f"Invalid Oracle identifier: {value!r}")
    return text


def _to_date(value: Any) -> date | datetime | str | None:
    if isinstance(value, (datetime, date)):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    token = text[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(token, fmt).date()
        except Exception:
            continue
    return text


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def _get(row: dict[str, Any], *keys: str) -> Any:
    normalized = {
        "".join(ch for ch in str(key).lower() if ch.isalnum()): value
        for key, value in (row or {}).items()
    }
    for key in keys:
        if key in row:
            return row.get(key)
        token = "".join(ch for ch in str(key).lower() if ch.isalnum())
        if token in normalized:
            return normalized[token]
    return None


def load_active_config(conn: Any) -> dict[str, Any]:
    table = _safe_identifier(TECHNICAL_SCORE_CONFIG_TABLE)
    config: dict[str, Any] = {}
    sql = f"""
SELECT CONFIG_KEY, CONFIG_VALUE
FROM {table}
WHERE IS_ACTIVE = 'Y'
"""
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            for key, value in cur.fetchall() or []:
                config[str(key)] = value
    except Exception:
        logger.exception("technical_score_config_load_failed table=%s", table)
    return config


def build_latest_record(
    row: dict[str, Any],
    *,
    sr_context: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trend_result = calculate_master_trend(row, sr_context=sr_context, config=config)
    score_result = calculate_master_score(row, trend_result, sr_context=sr_context, config=config)
    breakdown = score_result.get("scoreBreakdown") if isinstance(score_result.get("scoreBreakdown"), dict) else {}
    debug = trend_result.get("debug") if isinstance(trend_result.get("debug"), dict) else {}

    symbol = str(_get(row, "symbol", "stock") or debug.get("symbol") or "").strip().upper()
    trading_date = _to_date(_get(row, "tradingDate", "tradeDate", "ltcDate", "ltc_date") or debug.get("tradingDate"))
    if not symbol:
        raise ValueError("TECHNICAL_SCORE_LATEST requires symbol")
    if trading_date is None:
        raise ValueError(f"TECHNICAL_SCORE_LATEST requires trading date for {symbol}")

    return {
        "symbol": symbol,
        "trading_date": trading_date,
        "price": _num(_get(row, "price", "close", "closePrice", "close_price") or debug.get("close")),
        "open_price": _num(_get(row, "open", "openPrice", "open_price") or debug.get("open")),
        "high_price": _num(_get(row, "high", "highPrice", "high_price") or debug.get("high")),
        "low_price": _num(_get(row, "low", "lowPrice", "low_price") or debug.get("low")),
        "close_price": _num(_get(row, "close", "closePrice", "close_price", "price") or debug.get("close")),
        "volume": _num(_get(row, "volume") or debug.get("volume")),
        "trend": trend_result.get("trend"),
        "trend_sort": _num(trend_result.get("trendSort")),
        "trend_decision_reason": trend_result.get("trendDecisionReason"),
        "trend_source": trend_result.get("trendSource") or ENGINE_SOURCE,
        "score": _num(score_result.get("score")),
        "score_sort": _num(score_result.get("scoreSort")),
        "score_grade": score_result.get("scoreGrade"),
        "score_source": score_result.get("scoreSource") or ENGINE_SOURCE,
        "score_breakdown_json": dumps_json(breakdown),
        "ema20": _num(_get(row, "ema20") or debug.get("ema20")),
        "ema50": _num(_get(row, "ema50") or debug.get("ema50")),
        "ema100": _num(_get(row, "ema100") or debug.get("ema100")),
        "ema200": _num(_get(row, "ema200") or debug.get("ema200")),
        "ema20_slope_pct": _num(debug.get("ema20SlopePct") or _get(row, "ema20SlopePct")),
        "ema50_slope_pct": _num(debug.get("ema50SlopePct") or _get(row, "ema50SlopePct")),
        "rsi14": _num(debug.get("rsi") or _get(row, "rsi", "rsi14")),
        "macd_hist": _num(debug.get("macdHist") or _get(row, "macdHist", "macd_hist")),
        "macd_hist_slope": _num(debug.get("macdHistSlope") or _get(row, "macdHistSlope", "macd_hist_slope")),
        "adx14": _num(debug.get("adx14") or _get(row, "adx14", "adx")),
        "adx14_slope": _num(debug.get("adx14Slope") or _get(row, "adx14Slope", "adx_slope")),
        "plus_di14": _num(debug.get("plusDi14") or _get(row, "plusDi14", "diPlus14", "plus_di14")),
        "minus_di14": _num(debug.get("minusDi14") or _get(row, "minusDi14", "diMinus14", "minus_di14")),
        "atr14": _num(debug.get("atr14") or _get(row, "atr14", "atr")),
        "volume_ratio_20": _num(debug.get("volumeRatio20") or _get(row, "volumeRatio20", "volume_ratio20")),
        "delivery_pct": _num(debug.get("deliveryPct") or _get(row, "deliveryPct", "delivery_pct")),
        "delivery_rel_20": _num(debug.get("deliveryRel20") or _get(row, "deliveryRel20", "delivery_rel20")),
        "deliverable_value": _num(debug.get("deliverableValue") or _get(row, "deliverableValue")),
        "deliverable_value_rel_20": _num(debug.get("deliverableValueRel20") or _get(row, "deliverableValueRel20")),
        "ath": _num(debug.get("ath") or _get(row, "ath")),
        "high_52w": _num(debug.get("high52w") or _get(row, "high52w", "high_52w")),
        "low_52w": _num(debug.get("low52w") or _get(row, "low52w", "low_52w")),
        "support_level": _num(debug.get("support") or _get(row, "supportPrice", "support")),
        "resistance_level": _num(debug.get("resistance") or _get(row, "resistancePrice", "resistance")),
        "dist_to_support_pct": _num(debug.get("distanceToSupportPct") or _get(row, "distToSupportPct", "distanceToSupportPct")),
        "dist_to_resistance_pct": _num(debug.get("distanceToResistancePct") or _get(row, "distToResistancePct", "distanceToResistancePct")),
        "breakout_flag": debug.get("breakoutFlag") or _get(row, "breakoutFlag", "breakout_flag"),
        "breakdown_flag": debug.get("breakdownFlag") or _get(row, "breakdownFlag", "breakdown_flag"),
        "close_location_pct": _num(debug.get("closeLocationPct") or _get(row, "closeLocationPct")),
        "risk_flags_json": dumps_json(breakdown.get("riskFlags") or trend_result.get("riskFlags") or []),
        "missing_inputs_json": dumps_json(breakdown.get("missingInputs") or trend_result.get("missingInputs") or []),
    }


_LATEST_COLUMNS = (
    "symbol",
    "trading_date",
    "price",
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "volume",
    "trend",
    "trend_sort",
    "trend_decision_reason",
    "trend_source",
    "score",
    "score_sort",
    "score_grade",
    "score_source",
    "score_breakdown_json",
    "ema20",
    "ema50",
    "ema100",
    "ema200",
    "ema20_slope_pct",
    "ema50_slope_pct",
    "rsi14",
    "macd_hist",
    "macd_hist_slope",
    "adx14",
    "adx14_slope",
    "plus_di14",
    "minus_di14",
    "atr14",
    "volume_ratio_20",
    "delivery_pct",
    "delivery_rel_20",
    "deliverable_value",
    "deliverable_value_rel_20",
    "ath",
    "high_52w",
    "low_52w",
    "support_level",
    "resistance_level",
    "dist_to_support_pct",
    "dist_to_resistance_pct",
    "breakout_flag",
    "breakdown_flag",
    "close_location_pct",
    "risk_flags_json",
    "missing_inputs_json",
)


def _latest_merge_sql() -> str:
    table = _safe_identifier(TECHNICAL_SCORE_LATEST_TABLE)
    select_cols = ",\n        ".join(f":{col} AS {col}" for col in _LATEST_COLUMNS)
    update_cols = [col for col in _LATEST_COLUMNS if col not in {"symbol", "trading_date"}]
    update_set = ",\n        ".join(f"tgt.{col.upper()} = src.{col}" for col in update_cols)
    insert_cols = ", ".join(col.upper() for col in _LATEST_COLUMNS)
    insert_values = ", ".join(f"src.{col}" for col in _LATEST_COLUMNS)
    return f"""
MERGE INTO {table} tgt
USING (
    SELECT
        {select_cols}
    FROM dual
) src
ON (tgt.SYMBOL = src.symbol AND tgt.TRADING_DATE = src.trading_date)
WHEN MATCHED THEN UPDATE SET
        {update_set},
        tgt.UPDATED_AT = SYSTIMESTAMP
WHEN NOT MATCHED THEN INSERT (
        {insert_cols}
) VALUES (
        {insert_values}
)
"""


def upsert_latest_score(conn: Any, record: dict[str, Any]) -> None:
    started_at = datetime.utcnow()
    sql = _latest_merge_sql()
    with conn.cursor() as cur:
        cur.execute(sql, record)
    logger.info(
        "technical_score_latest_upsert symbol=%s trading_date=%s score=%s trend=%s elapsed_ms=%s",
        record.get("symbol"),
        record.get("trading_date"),
        record.get("score"),
        record.get("trend"),
        int((datetime.utcnow() - started_at).total_seconds() * 1000),
    )


def upsert_latest_scores(conn: Any, records: Iterable[dict[str, Any]], *, commit: bool = True) -> int:
    count = 0
    for record in records:
        upsert_latest_score(conn, record)
        count += 1
    if commit and count:
        conn.commit()
    logger.info("technical_score_latest_batch_upsert rows=%s", count)
    return count


def calculate_and_upsert_latest_scores(
    conn: Any,
    rows: Iterable[dict[str, Any]],
    *,
    config: dict[str, Any] | None = None,
    commit: bool = True,
) -> int:
    effective_config = config if config is not None else load_active_config(conn)
    records = [build_latest_record(row, config=effective_config) for row in rows]
    return upsert_latest_scores(conn, records, commit=commit)
