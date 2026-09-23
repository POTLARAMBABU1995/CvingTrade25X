from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, g, jsonify, request

try:
    from ..services import chart_service as chart_svc
    from ..services import marketdata_service as marketdata_svc
    from ..db_pool import pool
except ImportError:  # pragma: no cover
    from services import chart_service as chart_svc  # type: ignore
    from services import marketdata_service as marketdata_svc  # type: ignore
    from db_pool import pool  # type: ignore


bp = Blueprint("chart_compat", __name__, url_prefix="/api")
_logger = logging.getLogger(__name__)


def _json_error(message: str, status: int = 400):
    return jsonify({
        "status": "error",
        "message": "Internal server error." if status >= 500 else str(message or "Invalid request parameter"),
        "request_id": getattr(g, "request_id", ""),
    }), status


def _tf_to_chart_timeframe(tf: Any) -> str:
    token = str(tf or "1D").strip().upper()
    if token == "1W":
        return "weekly"
    if token == "1M":
        return "monthly"
    return "daily"


def _time_to_epoch(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt_value = datetime.fromisoformat(text[:10]).replace(tzinfo=timezone.utc)
        return int(dt_value.timestamp())
    except Exception:
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _candle_to_bar(candle: dict[str, Any], volume_row: dict[str, Any] | None = None) -> dict[str, float] | None:
    ts = _time_to_epoch(candle.get("time"))
    open_value = _as_float(candle.get("open"))
    high_value = _as_float(candle.get("high"))
    low_value = _as_float(candle.get("low"))
    close_value = _as_float(candle.get("close"))
    if ts is None or open_value is None or high_value is None or low_value is None or close_value is None:
        return None
    volume_value = _as_float((volume_row or {}).get("value")) or 0.0
    return {
        "t": ts,
        "o": open_value,
        "h": high_value,
        "l": low_value,
        "c": close_value,
        "v": volume_value,
    }


def _load_bars(symbol: str, tf: str) -> list[dict[str, float]]:
    payload = chart_svc.fetch_ohlcv_payload(symbol, _tf_to_chart_timeframe(tf))
    candles = [item for item in payload.get("candles", []) if isinstance(item, dict)]
    volume = [item for item in payload.get("volume", []) if isinstance(item, dict)]
    bars: list[dict[str, float]] = []
    for index, candle in enumerate(candles):
        bar = _candle_to_bar(candle, volume[index] if index < len(volume) else None)
        if bar:
            bars.append(bar)
    return bars


def _slice_bars(
    bars: list[dict[str, float]],
    *,
    cursor: str | None,
    from_value: str | None,
    limit: int,
    to_value: str | None,
) -> tuple[list[dict[str, float]], str | None]:
    from_epoch = _time_to_epoch(from_value)
    to_epoch = _time_to_epoch(to_value)
    cursor_epoch = _time_to_epoch(cursor)
    filtered = [
        bar for bar in bars
        if (from_epoch is None or bar["t"] >= from_epoch)
        and (to_epoch is None or bar["t"] <= to_epoch)
        and (cursor_epoch is None or bar["t"] < cursor_epoch)
    ]
    page_limit = max(1, min(int(limit or 800), 2000))
    has_more = len(filtered) > page_limit
    page = filtered[-page_limit:]
    next_cursor = None
    if has_more and page:
        next_cursor = datetime.fromtimestamp(page[0]["t"], tz=timezone.utc).date().isoformat()
    return page, next_cursor


def _ema(values: list[float], period: int) -> list[float | None]:
    if period <= 0:
        return [None for _ in values]
    result: list[float | None] = []
    multiplier = 2 / (period + 1)
    current: float | None = None
    for index, value in enumerate(values):
        if index + 1 < period:
            result.append(None)
            continue
        if current is None:
            current = sum(values[index + 1 - period:index + 1]) / period
        else:
            current = (value - current) * multiplier + current
        result.append(current)
    return result


def _rsi(values: list[float], period: int = 14) -> list[float | None]:
    result: list[float | None] = [None for _ in values]
    if len(values) <= period:
        return result
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, period + 1):
        change = values[index] - values[index - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    result[period] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + (avg_gain / avg_loss)))
    for index in range(period + 1, len(values)):
        change = values[index] - values[index - 1]
        avg_gain = ((avg_gain * (period - 1)) + max(change, 0)) / period
        avg_loss = ((avg_loss * (period - 1)) + abs(min(change, 0))) / period
        result[index] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + (avg_gain / avg_loss)))
    return result


def _atr(bars: list[dict[str, float]], period: int = 14) -> list[float | None]:
    true_ranges: list[float] = []
    previous_close: float | None = None
    for bar in bars:
        high = bar["h"]
        low = bar["l"]
        true_range = high - low if previous_close is None else max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(true_range)
        previous_close = bar["c"]
    return _ema(true_ranges, period)


def _points(bars: list[dict[str, float]], values: list[float | None]) -> list[dict[str, float]]:
    return [
        {"t": bar["t"], "v": round(value, 4)}
        for bar, value in zip(bars, values)
        if value is not None
    ]


@bp.get("/symbols")
def symbols_endpoint():
    q = request.args.get("q")
    limit = request.args.get("limit", default=50, type=int)
    try:
        rows = marketdata_svc.list_symbols(q, limit)
        symbols = [
            {
                "symbol": str(row.get("symbol") or "").strip().upper(),
                "name": row.get("name") or row.get("symbol"),
                "exchange": row.get("exchange") or "NSE",
                "sector": row.get("sector"),
            }
            for row in rows
            if str(row.get("symbol") or "").strip()
        ]
        return jsonify({"version": "v1", "q": q, "symbols": symbols})
    except Exception:
        _logger.exception("chart_compat.symbols_failed")
        return _json_error("Unable to fetch symbols.", 500)


@bp.get("/bars")
def bars_endpoint():
    symbol = request.args.get("symbol", "", type=str)
    tf = request.args.get("tf", "1D", type=str)
    try:
        limit = request.args.get("limit", default=800, type=int)
        bars = _load_bars(symbol, tf)
        page, next_cursor = _slice_bars(
            bars,
            cursor=request.args.get("cursor"),
            from_value=request.args.get("from"),
            limit=limit,
            to_value=request.args.get("to"),
        )
        return jsonify({"version": "v1", "symbol": symbol.strip().upper(), "tf": tf.strip().upper() or "1D", "nextCursor": next_cursor, "bars": page})
    except chart_svc.InvalidChartParameter as exc:
        return _json_error(str(exc), 400)
    except Exception:
        _logger.exception("chart_compat.bars_failed")
        return _json_error("Unable to fetch bars.", 500)


@bp.get("/indicators")
def indicators_endpoint():
    symbol = request.args.get("symbol", "", type=str)
    tf = request.args.get("tf", "1D", type=str)
    requested = {
        item.strip()
        for item in str(request.args.get("names") or "").split(",")
        if item.strip()
    } or {"ema20", "ema50", "ema200", "rsi14", "macd", "atr14"}
    try:
        bars = _load_bars(symbol, tf)
        closes = [bar["c"] for bar in bars]
        series: dict[str, list[dict[str, float]]] = {}
        if "ema20" in requested:
            series["ema20"] = _points(bars, _ema(closes, 20))
        if "ema50" in requested:
            series["ema50"] = _points(bars, _ema(closes, 50))
        if "ema200" in requested:
            series["ema200"] = _points(bars, _ema(closes, 200))
        if "rsi14" in requested or "rsi" in requested:
            series["rsi14"] = _points(bars, _rsi(closes, 14))
        if "atr14" in requested or "atr" in requested:
            series["atr14"] = _points(bars, _atr(bars, 14))
        if "macd" in requested:
            ema12 = _ema(closes, 12)
            ema26 = _ema(closes, 26)
            macd_values = [
                (fast - slow) if fast is not None and slow is not None else None
                for fast, slow in zip(ema12, ema26)
            ]
            signal_values = _ema([value or 0 for value in macd_values], 9)
            hist_values = [
                (macd - signal) if macd is not None and signal is not None else None
                for macd, signal in zip(macd_values, signal_values)
            ]
            series["macd"] = _points(bars, macd_values)
            series["macdSignal"] = _points(bars, signal_values)
            series["macdHist"] = _points(bars, hist_values)
        return jsonify({"version": "v1", "symbol": symbol.strip().upper(), "tf": tf.strip().upper() or "1D", "series": series})
    except chart_svc.InvalidChartParameter as exc:
        return _json_error(str(exc), 400)
    except Exception:
        _logger.exception("chart_compat.indicators_failed")
        return _json_error("Unable to fetch indicators.", 500)


@bp.get("/overlays")
def overlays_endpoint():
    symbol = request.args.get("symbol", "", type=str).strip().upper()
    tf = request.args.get("tf", "1D", type=str).strip().upper() or "1D"
    return jsonify({"version": "v1", "symbol": symbol, "tf": tf, "annotations": []})


def _annotation_id(user_id: int, symbol: str, tf: str) -> str:
    return f"{user_id}:{symbol}:{tf}"


@bp.get("/user-annotations")
def get_user_annotations_endpoint():
    user_id = request.args.get("userId", default=1, type=int)
    symbol = request.args.get("symbol", "", type=str).strip().upper()
    tf = request.args.get("tf", "1D", type=str).strip().upper() or "1D"
    annotations: list[dict[str, Any]] = []
    try:
        with pool.acquire() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT PAYLOAD_JSON
                FROM USER_ANNOTATIONS
                WHERE USER_ID = :user_id AND SYMBOL = :symbol AND TF = :tf
                """,
                {"user_id": user_id, "symbol": symbol, "tf": tf},
            )
            row = cur.fetchone()
            if row and row[0]:
                payload = row[0].read() if hasattr(row[0], "read") else row[0]
                loaded = json.loads(payload)
                if isinstance(loaded, list):
                    annotations = [item for item in loaded if isinstance(item, dict)]
    except Exception:
        _logger.warning("chart_compat.annotations_read_fallback", exc_info=True)
    return jsonify({"version": "v1", "userId": user_id, "symbol": symbol, "tf": tf, "annotations": annotations})


@bp.post("/user-annotations")
def upsert_user_annotations_endpoint():
    payload = request.get_json(silent=True) or {}
    user_id = int(payload.get("userId") or 1)
    symbol = str(payload.get("symbol") or "").strip().upper()
    tf = str(payload.get("tf") or "1D").strip().upper()
    annotations = payload.get("annotations") if isinstance(payload.get("annotations"), list) else []
    try:
        with pool.acquire() as conn, conn.cursor() as cur:
            cur.execute(
                """
                MERGE INTO USER_ANNOTATIONS dst
                USING (
                  SELECT :annotation_id AS ANNOTATION_ID,
                         :user_id AS USER_ID,
                         :symbol AS SYMBOL,
                         :tf AS TF,
                         :payload AS PAYLOAD_JSON
                  FROM dual
                ) src
                ON (dst.ANNOTATION_ID = src.ANNOTATION_ID)
                WHEN MATCHED THEN UPDATE SET
                  dst.PAYLOAD_JSON = src.PAYLOAD_JSON,
                  dst.UPDATED_AT = SYSTIMESTAMP
                WHEN NOT MATCHED THEN INSERT (
                  ANNOTATION_ID, USER_ID, SYMBOL, TF, PAYLOAD_JSON
                ) VALUES (
                  src.ANNOTATION_ID, src.USER_ID, src.SYMBOL, src.TF, src.PAYLOAD_JSON
                )
                """,
                {
                    "annotation_id": _annotation_id(user_id, symbol, tf),
                    "user_id": user_id,
                    "symbol": symbol,
                    "tf": tf,
                    "payload": json.dumps(annotations, ensure_ascii=True),
                },
            )
            conn.commit()
    except Exception:
        _logger.warning("chart_compat.annotations_write_fallback", exc_info=True)
    return jsonify({"version": "v1", "userId": user_id, "symbol": symbol, "tf": tf, "annotations": annotations})
