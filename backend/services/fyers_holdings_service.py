from __future__ import annotations

import csv
import base64
import concurrent.futures
import hashlib
import io
import json
import logging
import os
import re
import threading
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from cache import TTLCache
from db import get_oracle_connection

try:  # pragma: no cover - supports package and direct script execution
    from .technical_score_engine import enrich_row_with_master_score_fields
    from .technical_utils import calculate_adx, calculate_ema, calculate_macd, calculate_rsi
except ImportError:  # pragma: no cover
    from services.technical_score_engine import enrich_row_with_master_score_fields  # type: ignore
    from services.technical_utils import calculate_adx, calculate_ema, calculate_macd, calculate_rsi  # type: ignore

try:  # pragma: no cover
    import oracledb  # type: ignore
except Exception:  # pragma: no cover
    oracledb = None  # type: ignore


FYERS_HOLDINGS_SCHEMA = (os.getenv("FYERS_HOLDINGS_SCHEMA") or os.getenv("ORACLE_SCHEMA") or "").strip().upper()
FYERS_HOLDINGS_IMPORT_TABLE = (
    os.getenv("FYERS_HOLDINGS_IMPORT_TABLE", "FYERS_HOLDINGS_IMPORTS").strip().upper()
)
FYERS_HOLDINGS_CURRENT_TABLE = (
    os.getenv("FYERS_HOLDINGS_CURRENT_TABLE", "FYERS_HOLDINGS_CURRENT").strip().upper()
)
FYERS_HOLDINGS_AUDIT_TABLE = (
    os.getenv("FYERS_HOLDINGS_AUDIT_TABLE", "FYERS_HOLDINGS_AUDIT").strip().upper()
)
FYERS_HOLDINGS_ASURA_TABLE = (
    os.getenv("FYERS_HOLDINGS_ASURA_TABLE")
    or os.getenv("ASURA_BULLISH_TREND_TABLE")
    or "ASURA_BULLISH_TREND_STRATEGY_TESTING"
).strip().upper()
FYERS_HOLDINGS_MANUAL_SR_TABLE = (
    os.getenv("FYERS_HOLDINGS_MANUAL_SR_TABLE")
    or os.getenv("PRICE_ACTION_SR_LEVELS_MANUALLY_TABLE")
    or "PRICE_ACTION_SR_LEVELS_MANUALLY"
).strip().upper()
_logger = logging.getLogger(__name__)

STATIC_REPORT_FIELDS: tuple[str, ...] = (
    "reportTitle",
    "reportDate",
    "clientName",
    "clientId",
    "pan",
    "downloadTimestamp",
    "totalInvested",
    "totalCurrent",
    "profitLoss",
    "unrealisedPnlPct",
)

_SUMMARY_TOTAL_TO_LIVE_TOTAL_KEY = {
    "totalInvested": "totalInvested",
    "totalCurrent": "totalCurrent",
    "profitLoss": "profitLoss",
    "unrealisedPnlPct": "unrealisedPnlPct",
}

_REPORT_LABELS = {
    "Report Title": "reportTitle",
    "Date": "reportDate",
    "Client Name": "clientName",
    "Client ID": "clientId",
    "PAN": "pan",
    "Download Timestamp": "downloadTimestamp",
    "Total Invested": "totalInvested",
    "Total Current": "totalCurrent",
    "Profit & loss": "profitLoss",
    "Unrealised P&L %": "unrealisedPnlPct",
}

_REPORT_FIELD_LABELS = {
    "reportTitle": "Report Title",
    "reportDate": "Date",
    "clientName": "Client Name",
    "clientId": "Client ID",
    "pan": "PAN",
    "downloadTimestamp": "Download Timestamp",
    "totalInvested": "Total Invested",
    "totalCurrent": "Total Current",
    "profitLoss": "Profit & Loss",
    "unrealisedPnlPct": "Unrealised P&L %",
}

_HOLDING_HEADER_MAP = {
    "name": "symbolRaw",
    "qty": "quantity",
    "buy price": "buyPrice",
    "buy_price": "buyPrice",
    "buyprice": "buyPrice",
    "average price": "buyPrice",
    "avg price": "buyPrice",
    "avg_price": "buyPrice",
    "purchase price": "buyPrice",
    "cost price": "buyPrice",
    "invested": "investedValue",
    "invested value": "investedValue",
    "current": "currentValue",
    "current value": "currentValue",
    "unrealised p&l": "unrealisedPnl",
    "unrealised p&l %": "unrealisedPnlPct",
    "previous close": "previousClose",
    "isin": "isin",
}

_NUMERIC_ROW_FIELDS = (
    "quantity",
    "buyPrice",
    "investedValue",
    "currentValue",
    "unrealisedPnl",
    "unrealisedPnlPct",
    "previousClose",
)

_BUSINESS_COMPARE_FIELDS = (
    "quantity",
    "buyPrice",
    "investedValue",
    "currentValue",
    "unrealisedPnl",
    "unrealisedPnlPct",
    "previousClose",
)

_WRITE_LOCK = threading.Lock()
_LIST_CACHE_TTL_SECONDS = max(1, int(os.getenv("FYERS_HOLDINGS_LIST_CACHE_TTL_SECONDS", "30")))
_SNAPSHOT_COLUMNS_CACHE_LOCK = threading.Lock()
_SNAPSHOT_COLUMNS_CACHE: set[str] | None = None
_SOURCE_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_$#]*(?:\.[A-Z][A-Z0-9_$#]*)?$")
_MONEY_QUANT = Decimal("0.01")
_PERCENT_QUANT = Decimal("0.01")
_P_AND_L_MONEY_TOLERANCE = Decimal("0.05")
_P_AND_L_PERCENT_TOLERANCE = Decimal("0.05")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None else int(default)
    except Exception:
        value = int(default)
    return max(int(minimum), value)


FYERS_HOLDINGS_LIVE_QUOTES_ENABLED = _env_bool("FYERS_HOLDINGS_LIVE_QUOTES_ENABLED", True)
FYERS_HOLDINGS_LIVE_QUOTES_TIMEOUT_SECONDS = _env_int("FYERS_HOLDINGS_LIVE_QUOTES_TIMEOUT_SECONDS", 4, 1)
FYERS_HOLDINGS_LIVE_QUOTES_CACHE_TTL_SECONDS = _env_int("FYERS_HOLDINGS_LIVE_QUOTES_CACHE_TTL_SECONDS", 15, 1)
FYERS_PROJECT_DIR = os.getenv("FYERS_PROJECT_DIR", r"D:\fyers_api_integration").strip()
_LIST_CACHE = TTLCache(
    ttl_seconds=_LIST_CACHE_TTL_SECONDS,
    max_items=_env_int("FYERS_HOLDINGS_LIST_CACHE_MAX_ITEMS", 64, 1),
    max_bytes=_env_int("FYERS_HOLDINGS_LIST_CACHE_MAX_MEMORY_MB", 32, 1) * 1024 * 1024,
)
_FYERS_LIVE_QUOTE_CACHE = TTLCache(
    ttl_seconds=FYERS_HOLDINGS_LIVE_QUOTES_CACHE_TTL_SECONDS,
    max_items=_env_int("FYERS_HOLDINGS_LIVE_QUOTES_CACHE_MAX_ITEMS", 16, 1),
    max_bytes=_env_int("FYERS_HOLDINGS_LIVE_QUOTES_CACHE_MAX_MEMORY_MB", 16, 1) * 1024 * 1024,
)


def _table_name(table: str) -> str:
    return f"{FYERS_HOLDINGS_SCHEMA}.{table}" if FYERS_HOLDINGS_SCHEMA else table


def _qualified_raw_ohlc_table() -> str:
    schema = _to_text(os.getenv("ORACLE_SCHEMA")).upper()
    table = _to_text(os.getenv("ORACLE_TABLE") or "NSE_NIFTY500_DAILY_RAW_DATA_DEV").upper()
    qualified = table if "." in table or not schema else f"{schema}.{table}"
    if not _SOURCE_NAME_PATTERN.fullmatch(qualified):
        raise RuntimeError("Invalid ORACLE_SCHEMA/ORACLE_TABLE configured for holdings technical enrichment.")
    return qualified


def _qualified_optional_table(table: str, *, schema: str | None = None) -> str:
    table_name = _to_text(table).upper()
    schema_name = _to_text(schema if schema is not None else os.getenv("ORACLE_SCHEMA")).upper()
    qualified = table_name if "." in table_name or not schema_name else f"{schema_name}.{table_name}"
    if not _SOURCE_NAME_PATTERN.fullmatch(qualified):
        raise RuntimeError(f"Invalid Oracle object configured for holdings enrichment: {qualified}")
    return qualified


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _decimal_compare_token(value: Decimal) -> str:
    try:
        text = format(value.normalize(), "f")
    except Exception:
        text = str(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _numeric_compare_token(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_compare_token(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        try:
            return _decimal_compare_token(Decimal(str(value)))
        except Exception:
            return value
    return value


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\u2212", "-").replace("\xa0", " ")
    if text in {"-", "--"}:
        return None
    negative_from_parentheses = False
    if text.startswith("(") and text.endswith(")"):
        inner = text[1:-1].strip()
        if inner.startswith(("+", "-")):
            text = inner
        else:
            negative_from_parentheses = True
            text = inner
    text = (
        text.replace(",", "")
        .replace("₹", "")
        .replace("%", "")
        .replace("INR", "")
        .replace("inr", "")
        .replace("Rs.", "")
        .replace("rs.", "")
        .replace("Rs", "")
        .replace("rs", "")
    )
    text = re.sub(r"\s+", "", text)
    if text in {"", "-", "--", "+", "++"}:
        return None
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid numeric value: {value}") from exc
    if negative_from_parentheses and parsed > 0:
        parsed = -parsed
    return parsed


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        parsed = _decimal_or_none(value)
    except Exception:
        return None
    return float(parsed) if parsed is not None else None


def _safe_decimal(value: Any) -> Decimal | None:
    try:
        return _decimal_or_none(value)
    except ValueError:
        return None


def _round_money(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def _round_percent(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(_PERCENT_QUANT, rounding=ROUND_HALF_UP)


def _decimal_to_json_number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _parse_report_date(value: Any) -> date | None:
    text = _to_text(value)
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid report date: {value}")


def _parse_timestamp(value: Any) -> datetime | None:
    text = _to_text(value)
    if not text:
        return None
    text = text.replace(" IST", "").replace(" UTC", "")
    for fmt in (
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Invalid download timestamp: {value}") from exc


def _iso_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        text = value.strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}", text):
            return text[:10]
    return ""


def _iso_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    return ""


def _normalize_header(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _split_symbol(raw_symbol: Any) -> tuple[str, str, str, str]:
    symbol_raw = _to_text(raw_symbol).upper()
    if not symbol_raw:
        raise ValueError("Holding symbol is required.")
    exchange_code = ""
    remainder = symbol_raw
    if ":" in symbol_raw:
        exchange_code, remainder = symbol_raw.split(":", 1)
    series_code = ""
    symbol_code = remainder
    if "-" in remainder:
        symbol_code, series_code = remainder.rsplit("-", 1)
    return symbol_raw, exchange_code.strip(), symbol_code.strip(), series_code.strip()


def _normalize_symbol_token(raw_symbol: Any) -> str:
    text = _to_text(raw_symbol).upper()
    if not text:
        return ""
    if ":" in text:
        text = text.split(":", 1)[1]
    text = text.replace(".NS", "")
    if text.endswith("-EQ"):
        text = text[:-3]
    return text.strip()


def _build_symbol_aliases(raw_symbol: Any, symbol_code: Any) -> set[str]:
    aliases = set()
    for value in (raw_symbol, symbol_code):
        token = _normalize_symbol_token(value)
        if token:
            aliases.add(token)
    return aliases


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _to_number(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _serialize_state(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    return json.dumps(payload, default=_json_default, sort_keys=True, separators=(",", ":"))


def _file_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require_oracledb() -> None:
    if oracledb is None:
        raise RuntimeError("python-oracledb is not installed. Run: pip install -r backend/requirements.txt")


def _table_exists(conn: Any, table: str) -> bool:
    owner = FYERS_HOLDINGS_SCHEMA or ""
    sql = """
        SELECT COUNT(*)
        FROM ALL_TABLES
        WHERE TABLE_NAME = :table_name
          AND (:owner = '' OR OWNER = :owner)
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"table_name": table.upper(), "owner": owner.upper()})
        row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _ensure_tables_exist(conn: Any) -> None:
    missing = [
        table
        for table in (
            FYERS_HOLDINGS_IMPORT_TABLE,
            FYERS_HOLDINGS_CURRENT_TABLE,
            FYERS_HOLDINGS_AUDIT_TABLE,
        )
        if not _table_exists(conn, table)
    ]
    if missing:
        raise RuntimeError(
            "FYERS holdings tables are missing: "
            + ", ".join(missing)
            + ". Apply backend/sql/create_fyers_holdings_tables.sql before importing."
        )


def _stable_fields_from_metadata(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for key in STATIC_REPORT_FIELDS:
        value = metadata.get(key)
        if isinstance(value, Decimal):
            value = _to_number(value)
        elif isinstance(value, datetime):
            value = _iso_datetime(value)
        elif isinstance(value, date):
            value = _iso_date(value)
        fields.append({"key": key, "label": _REPORT_FIELD_LABELS.get(key, key), "value": value})
    return fields


def _apply_authoritative_totals_to_summary(
    summary: dict[str, Any],
    *,
    live_totals: dict[str, Any],
) -> None:
    for summary_key, live_key in _SUMMARY_TOTAL_TO_LIVE_TOTAL_KEY.items():
        if live_key in live_totals:
            summary[summary_key] = live_totals.get(live_key)

    stable_fields = summary.get("stableFields")
    if not isinstance(stable_fields, list):
        return
    for field in stable_fields:
        if not isinstance(field, dict):
            continue
        key = _to_text(field.get("key"))
        if key in _SUMMARY_TOTAL_TO_LIVE_TOTAL_KEY:
            live_key = _SUMMARY_TOTAL_TO_LIVE_TOTAL_KEY[key]
            if live_key in live_totals:
                field["value"] = live_totals.get(live_key)


def _row_to_response(row: dict[str, Any]) -> dict[str, Any]:
    previous_close_source = _to_text(row.get("previousCloseSource")) or (
        "NOT_AVAILABLE" if _to_number(row.get("previousClose")) is None else "CSV_PRICE"
    )
    score_value = _to_number(_coalesce(row.get("score"), row.get("techScore"), row.get("signalScore")))
    score_sort_value = _to_number(_coalesce(row.get("scoreSort"), row.get("techScoreSort"), score_value))
    support_display = _to_text(
        _coalesce(row.get("supportDisplay"), row.get("support"), row.get("supportLevel"), row.get("nearestSupport"))
    )
    resistance_display = _to_text(
        _coalesce(
            row.get("resistanceDisplay"),
            row.get("resistance"),
            row.get("resistanceLevel"),
            row.get("nearestResistance"),
        )
    )
    return {
        "holdingId": row.get("holdingId"),
        "importId": row.get("importId"),
        "clientId": row.get("clientId"),
        "clientName": row.get("clientName"),
        "pan": row.get("pan"),
        "reportDate": _iso_date(row.get("reportDate")),
        "downloadTimestamp": _iso_datetime(row.get("downloadTimestamp")),
        "symbol": row.get("symbolRaw"),
        "symbolRaw": row.get("symbolRaw"),
        "exchangeCode": row.get("exchangeCode"),
        "symbolCode": row.get("symbolCode"),
        "seriesCode": row.get("seriesCode"),
        "quantity": _to_number(row.get("quantity")),
        "buyPrice": _to_number(row.get("buyPrice")),
        "investedValue": _to_number(row.get("investedValue")),
        "currentValue": _to_number(row.get("currentValue")),
        "unrealisedPnl": _to_number(row.get("unrealisedPnl")),
        "unrealisedPnlPct": _to_number(row.get("unrealisedPnlPct")),
        "previousClose": _to_number(row.get("previousClose")),
        "previousCloseSource": previous_close_source,
        "buyPriceSource": "CSV",
        "lastUpdated": _iso_datetime(row.get("updatedAt")),
        "score": score_value,
        "scoreSort": score_sort_value,
        "techScore": score_value,
        "ema20": _to_number(row.get("ema20")),
        "ema50": _to_number(row.get("ema50")),
        "ema100": _to_number(row.get("ema100")),
        "ema200": _to_number(row.get("ema200")),
        "ema20Flag": _to_text(row.get("ema20Flag")).upper() or None,
        "ema50Flag": _to_text(row.get("ema50Flag")).upper() or None,
        "ema100Flag": _to_text(row.get("ema100Flag")).upper() or None,
        "ema200Flag": _to_text(row.get("ema200Flag")).upper() or None,
        "macdAboveZero": row.get("macdAboveZero"),
        "rsiAbove50": row.get("rsiAbove50"),
        "adxAbove25": row.get("adxAbove25"),
        "atrAbove14": row.get("atrAbove14"),
        "volumeAbove20": row.get("volumeAbove20"),
        "volume": _to_number(row.get("volume")),
        "volumeRatio20": _to_number(row.get("volumeRatio20")),
        "avgVolume20": _to_number(row.get("avgVolume20")),
        "fiftyTwoWeekLow": _to_number(row.get("fiftyTwoWeekLow")),
        "fiftyTwoWeekHigh": _to_number(row.get("fiftyTwoWeekHigh")),
        "low52w": _to_number(row.get("fiftyTwoWeekLow")),
        "high52w": _to_number(row.get("fiftyTwoWeekHigh")),
        "ath": _to_number(row.get("ath")),
        "athDate": _iso_date(row.get("athDate")),
        "supportDisplay": support_display or None,
        "resistanceDisplay": resistance_display or None,
        "support": support_display or None,
        "resistance": resistance_display or None,
        "trendDirection": _to_text(row.get("trendDirection")) or None,
        "isin": row.get("isin") or "",
        "sourceFilename": row.get("sourceFilename") or "",
        "sourcePath": row.get("sourcePath") or "",
        "sourceHash": row.get("sourceHash") or "",
        "createdAt": _iso_datetime(row.get("createdAt")),
        "updatedAt": _iso_datetime(row.get("updatedAt")),
    }


def _derive_ltp(row: dict[str, Any]) -> tuple[Decimal | None, str]:
    direct_candidates = (
        ("ltp", _to_text(row.get("ltpSource")) or "LTP"),
        ("lastPrice", "LAST_PRICE"),
        ("currentPrice", "CURRENT_PRICE"),
        ("price", _to_text(row.get("priceSource")) or "TECHNICAL_PRICE"),
        ("close", "CLOSE_PRICE"),
    )
    for key, source in direct_candidates:
        value = _safe_decimal(row.get(key))
        if value is not None:
            return value, source

    quantity = _safe_decimal(row.get("quantity"))
    current_value = _safe_decimal(_coalesce(row.get("appCurrentValue"), row.get("currentValue")))
    if quantity is not None and quantity != 0 and current_value is not None:
        return current_value / quantity, "CSV_CURRENT_VALUE_DERIVED"
    return None, "NOT_AVAILABLE"


def _value_date_for_reconciliation(row: dict[str, Any]) -> str:
    for key in ("tradingDate", "dataDate", "reportDate", "downloadTimestamp", "lastUpdated", "updatedAt"):
        text = _to_text(row.get(key))
        if text:
            return text
    return ""


def _is_stale_price(row: dict[str, Any]) -> bool:
    text = _value_date_for_reconciliation(row)
    if not text:
        return False
    token = text.split("T", 1)[0].split(" ", 1)[0]
    try:
        price_date = date.fromisoformat(token)
    except ValueError:
        return False
    return (date.today() - price_date).days > 5


def _status_for_reconciliation(
    *,
    symbol: str,
    quantity: Decimal | None,
    avg_price: Decimal | None,
    ltp: Decimal | None,
    previous_close: Decimal | None,
    difference_amount: Decimal | None,
    difference_percent: Decimal | None,
    stale_price: bool,
) -> tuple[str, list[str]]:
    details: list[str] = []
    if not symbol:
        details.append("Symbol could not be normalized.")
        return "SYMBOL_MAPPING_ISSUE", details
    if quantity is None:
        details.append("Quantity is missing.")
        return "MISSING_QTY", details
    if avg_price is None:
        details.append("Average price is missing.")
        return "MISSING_AVG_PRICE", details
    if ltp is None:
        details.append("LTP/current price is missing.")
        return "MISSING_LTP", details
    if previous_close is None:
        details.append("Previous close is missing; day P&L is neutral.")
    if stale_price:
        details.append("Price date is older than the freshness threshold.")

    abs_amount = abs(difference_amount) if difference_amount is not None else Decimal("0")
    abs_percent = abs(difference_percent) if difference_percent is not None else Decimal("0")
    has_mismatch = abs_amount > _P_AND_L_MONEY_TOLERANCE or abs_percent > _P_AND_L_PERCENT_TOLERANCE
    if has_mismatch:
        if abs_amount <= Decimal("0.10") and abs_percent <= Decimal("0.10"):
            return "ROUNDING_ONLY_DIFF", details
        return "MISMATCH", details
    if stale_price:
        return "STALE_PRICE", details
    if previous_close is None:
        return "MISSING_PREVIOUS_CLOSE", details
    return "MATCHED", details


def recalculate_holding_pnl(row: dict[str, Any]) -> dict[str, Any]:
    symbol = _to_text(_coalesce(row.get("symbolCode"), row.get("symbol"), row.get("symbolRaw"))).upper()
    quantity = _safe_decimal(row.get("quantity"))
    avg_price = _safe_decimal(row.get("buyPrice"))
    invested_app = _round_money(_safe_decimal(_coalesce(row.get("appInvestedValue"), row.get("investedValue"))))
    current_app = _round_money(_safe_decimal(_coalesce(row.get("appCurrentValue"), row.get("currentValue"))))
    pnl_app = _round_money(_safe_decimal(_coalesce(row.get("appUnrealisedPnl"), row.get("unrealisedPnl"), row.get("profitLoss"))))
    pnl_pct_app = _round_percent(_safe_decimal(_coalesce(row.get("appUnrealisedPnlPct"), row.get("unrealisedPnlPct"))))
    day_pnl_app = _round_money(_safe_decimal(row.get("appDayPnl")))
    day_pnl_pct_app = _round_percent(_safe_decimal(row.get("appDayPnlPct")))
    previous_close = _safe_decimal(row.get("previousClose"))
    ltp, ltp_source = _derive_ltp(row)

    invested_recalc = _round_money(quantity * avg_price) if quantity is not None and avg_price is not None else None
    current_recalc = _round_money(quantity * ltp) if quantity is not None and ltp is not None else None
    total_pnl_recalc = (
        _round_money(current_recalc - invested_recalc)
        if current_recalc is not None and invested_recalc is not None
        else None
    )
    total_pnl_pct_recalc = (
        _round_percent((total_pnl_recalc / invested_recalc) * Decimal("100"))
        if total_pnl_recalc is not None and invested_recalc not in (None, Decimal("0"))
        else None
    )
    day_pnl_recalc = (
        _round_money(quantity * (ltp - previous_close))
        if quantity is not None and ltp is not None and previous_close is not None
        else None
    )
    day_pnl_pct_recalc = (
        _round_percent(((ltp - previous_close) / previous_close) * Decimal("100"))
        if ltp is not None and previous_close not in (None, Decimal("0"))
        else None
    )
    difference_amount = None
    if total_pnl_recalc is not None and pnl_app is not None:
        difference_amount = _round_money(total_pnl_recalc - pnl_app)
    elif current_recalc is not None and current_app is not None:
        difference_amount = _round_money(current_recalc - current_app)
    difference_percent = (
        _round_percent(total_pnl_pct_recalc - pnl_pct_app)
        if total_pnl_pct_recalc is not None and pnl_pct_app is not None
        else None
    )
    stale_price = _is_stale_price(row)
    status, status_details = _status_for_reconciliation(
        symbol=symbol,
        quantity=quantity,
        avg_price=avg_price,
        ltp=ltp,
        previous_close=previous_close,
        difference_amount=difference_amount,
        difference_percent=difference_percent,
        stale_price=stale_price,
    )
    data_source = ";".join(
        [
            f"AVG:{_to_text(row.get('buyPriceSource')) or 'CSV'}",
            f"LTP:{ltp_source}",
            f"PREVIOUS_CLOSE:{_to_text(row.get('previousCloseSource')) or 'NOT_AVAILABLE'}",
        ]
    )
    return {
        "symbol": symbol,
        "symbolRaw": row.get("symbolRaw") or row.get("symbol"),
        "qty": _decimal_to_json_number(quantity),
        "avgPrice": _decimal_to_json_number(avg_price),
        "investedValueApp": _decimal_to_json_number(invested_app),
        "investedValueRecalculated": _decimal_to_json_number(invested_recalc),
        "ltp": _decimal_to_json_number(_round_money(ltp) if ltp is not None else None),
        "ltpSource": ltp_source,
        "previousClose": _decimal_to_json_number(_round_money(previous_close) if previous_close is not None else None),
        "currentValueApp": _decimal_to_json_number(current_app),
        "currentValueRecalculated": _decimal_to_json_number(current_recalc),
        "totalPnlApp": _decimal_to_json_number(pnl_app),
        "totalPnlRecalculated": _decimal_to_json_number(total_pnl_recalc),
        "totalPnlPercentApp": _decimal_to_json_number(pnl_pct_app),
        "totalPnlPercentRecalculated": _decimal_to_json_number(total_pnl_pct_recalc),
        "dayPnlApp": _decimal_to_json_number(day_pnl_app),
        "dayPnlRecalculated": _decimal_to_json_number(day_pnl_recalc),
        "dayPnlPercentApp": _decimal_to_json_number(day_pnl_pct_app),
        "dayPnlPercentRecalculated": _decimal_to_json_number(day_pnl_pct_recalc),
        "differenceAmount": _decimal_to_json_number(difference_amount),
        "differencePercent": _decimal_to_json_number(difference_percent),
        "dataSourceUsed": data_source,
        "dataDate": _value_date_for_reconciliation(row),
        "lastUpdated": row.get("lastUpdated") or row.get("updatedAt") or "",
        "status": status,
        "statusDetails": status_details,
    }


def apply_recalculated_holding_values(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        row.setdefault("appInvestedValue", row.get("investedValue"))
        row.setdefault("appCurrentValue", row.get("currentValue"))
        row.setdefault("appUnrealisedPnl", row.get("unrealisedPnl"))
        row.setdefault("appUnrealisedPnlPct", row.get("unrealisedPnlPct"))
        reconciliation = recalculate_holding_pnl(row)
        row["ltp"] = reconciliation.get("ltp")
        row["ltpSource"] = reconciliation.get("ltpSource")
        row["dayPnl"] = reconciliation.get("dayPnlRecalculated")
        row["dayPnlPct"] = reconciliation.get("dayPnlPercentRecalculated")
        row["pnlStatus"] = reconciliation.get("status")
        row["pnlStatusDetails"] = reconciliation.get("statusDetails")
        row["pnlDifferenceAmount"] = reconciliation.get("differenceAmount")
        if reconciliation.get("investedValueRecalculated") is not None:
            row["investedValue"] = reconciliation["investedValueRecalculated"]
        if reconciliation.get("currentValueRecalculated") is not None:
            row["currentValue"] = reconciliation["currentValueRecalculated"]
        if reconciliation.get("totalPnlRecalculated") is not None:
            row["unrealisedPnl"] = reconciliation["totalPnlRecalculated"]
        if reconciliation.get("totalPnlPercentRecalculated") is not None:
            row["unrealisedPnlPct"] = reconciliation["totalPnlPercentRecalculated"]
    return rows


def _cache_key_for_list(client_id: str, symbol_query: str) -> str:
    return f"{client_id}|{symbol_query}"


def _get_cached_list(cache_key: str) -> dict[str, Any] | None:
    cached = _LIST_CACHE.get(cache_key)
    return cached if isinstance(cached, dict) else None


def _set_cached_list(cache_key: str, payload: dict[str, Any]) -> None:
    _LIST_CACHE.set(cache_key, payload)


def _invalidate_list_cache() -> None:
    _LIST_CACHE.clear()


def _to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = _to_text(value).upper()
    if text in {"Y", "YES", "TRUE", "1", "ABOVE", "UP"}:
        return True
    if text in {"N", "NO", "FALSE", "0", "BELOW", "DOWN"}:
        return False
    num = _to_number(value)
    if num is None:
        return None
    return num > 0


def _load_snapshot_columns(conn: Any) -> set[str]:
    global _SNAPSHOT_COLUMNS_CACHE
    with _SNAPSHOT_COLUMNS_CACHE_LOCK:
        if _SNAPSHOT_COLUMNS_CACHE is not None:
            return _SNAPSHOT_COLUMNS_CACHE
    cols: set[str] = set()
    sql = """
        SELECT COLUMN_NAME
        FROM ALL_TAB_COLUMNS
        WHERE UPPER(TABLE_NAME) = 'MV_NSE_SECTOR_UI_SNAPSHOT'
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        for (column_name,) in cur.fetchall() or []:
            col = _to_text(column_name).upper()
            if col:
                cols.add(col)
    with _SNAPSHOT_COLUMNS_CACHE_LOCK:
        _SNAPSHOT_COLUMNS_CACHE = cols
    return cols


def _pick_snapshot_col(columns: set[str], *candidates: str) -> str | None:
    for name in candidates:
        candidate = name.upper()
        if candidate in columns:
            return candidate
    return None


def _fetch_latest_ema_previous_close_map(conn: Any, symbols: list[str]) -> dict[str, float]:
    cleaned = sorted({s for s in symbols if s})
    if not cleaned:
        return {}
    binds = {f"s{idx}": value for idx, value in enumerate(cleaned)}
    in_clause = ", ".join(f":{name}" for name in binds.keys())
    sql = f"""
        SELECT symbol_norm, price_for_ema
        FROM (
            SELECT
                UPPER(TRIM(symbol)) AS symbol_norm,
                price_for_ema,
                ROW_NUMBER() OVER (
                    PARTITION BY UPPER(TRIM(symbol))
                    ORDER BY trading_date DESC NULLS LAST
                ) AS rn
            FROM V_NSE500_EMA_DAILY
            WHERE UPPER(TRIM(symbol)) IN ({in_clause})
        )
        WHERE rn = 1
    """
    out: dict[str, float] = {}
    with conn.cursor() as cur:
        cur.execute(sql, binds)
        for symbol_norm, price_for_ema in cur.fetchall() or []:
            price = _to_number(price_for_ema)
            if symbol_norm and price is not None:
                out[str(symbol_norm).upper()] = price
    return out


def _fetch_raw_technical_range_map(conn: Any, symbols: list[str]) -> dict[str, dict[str, Any]]:
    cleaned = sorted({s for s in symbols if s})
    if not cleaned:
        return {}

    expanded_symbols: set[str] = set()
    for symbol in cleaned:
        token = _to_text(symbol).upper()
        if not token:
            continue
        expanded_symbols.update({token, f"{token}-EQ", f"{token}.NS", f"NSE:{token}-EQ"})
    if not expanded_symbols:
        return {}

    binds = {f"s{idx}": value for idx, value in enumerate(sorted(expanded_symbols))}
    in_clause = ", ".join(f":{name}" for name in binds.keys())
    table_name = _qualified_raw_ohlc_table()
    symbol_expr = "REGEXP_REPLACE(REGEXP_REPLACE(UPPER(TRIM(symbol)), '^.*:', ''), '(\\.NS|-EQ)$', '')"
    sql = f"""
        SELECT
            symbol_norm,
            latest_volume,
            avg_volume20,
            low52w,
            high52w,
            ath,
            ath_date
        FROM (
            SELECT
                symbol_norm,
                MAX(CASE WHEN rn_desc = 1 THEN volume_val END) AS latest_volume,
                AVG(CASE WHEN rn_desc <= 20 THEN volume_val END) AS avg_volume20,
                MIN(CASE WHEN trading_date >= latest_trading_date - 365 THEN low_val END) AS low52w,
                MAX(CASE WHEN trading_date >= latest_trading_date - 365 THEN high_val END) AS high52w,
                MAX(high_val) AS ath,
                MAX(trading_date) KEEP (DENSE_RANK LAST ORDER BY high_val) AS ath_date
            FROM (
                SELECT
                    {symbol_expr} AS symbol_norm,
                    trading_date,
                    high AS high_val,
                    low AS low_val,
                    volume AS volume_val,
                    MAX(trading_date) OVER (PARTITION BY {symbol_expr}) AS latest_trading_date,
                    ROW_NUMBER() OVER (
                        PARTITION BY {symbol_expr}
                        ORDER BY trading_date DESC NULLS LAST
                    ) AS rn_desc
                FROM {table_name}
                WHERE symbol IS NOT NULL
                  AND UPPER(TRIM(symbol)) IN ({in_clause})
            )
            GROUP BY symbol_norm
        )
    """

    out: dict[str, dict[str, Any]] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(sql, binds)
            for symbol_norm, latest_volume, avg_volume20, low52w, high52w, ath, ath_date in cur.fetchall() or []:
                symbol_key = _to_text(symbol_norm).upper()
                if not symbol_key:
                    continue
                latest_volume_num = _to_number(latest_volume)
                avg_volume20_num = _to_number(avg_volume20)
                volume_ratio20 = (
                    latest_volume_num / avg_volume20_num
                    if latest_volume_num is not None and avg_volume20_num and avg_volume20_num > 0
                    else None
                )
                out[symbol_key] = {
                    "volume": latest_volume_num,
                    "avgVolume20": avg_volume20_num,
                    "volumeRatio20": volume_ratio20,
                    "volumeAbove20": (
                        latest_volume_num >= avg_volume20_num
                        if latest_volume_num is not None and avg_volume20_num and avg_volume20_num > 0
                        else None
                    ),
                    "fiftyTwoWeekLow": _to_number(low52w),
                    "fiftyTwoWeekHigh": _to_number(high52w),
                    "ath": _to_number(ath),
                    "athDate": _iso_date(ath_date),
                }
    except Exception as exc:
        _logger.warning("FYERS holdings technical range enrichment skipped: %s", exc)
        return {}
    return out


def _indicator_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return None


def _date_from_any(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _to_text(value)
    if not text:
        return None
    token = text.split("T", 1)[0].split(" ", 1)[0]
    try:
        return date.fromisoformat(token)
    except ValueError:
        return None


def _fetch_computed_technical_map(conn: Any, symbols: list[str]) -> dict[str, dict[str, Any]]:
    cleaned = sorted({s for s in symbols if s})
    if not cleaned:
        return {}

    expanded_symbols: set[str] = set()
    for symbol in cleaned:
        token = _to_text(symbol).upper()
        if not token:
            continue
        expanded_symbols.update({token, f"{token}-EQ", f"{token}.NS", f"NSE:{token}-EQ"})
    if not expanded_symbols:
        return {}

    binds = {f"s{idx}": value for idx, value in enumerate(sorted(expanded_symbols))}
    in_clause = ", ".join(f":{name}" for name in binds.keys())
    symbol_expr = "REGEXP_REPLACE(REGEXP_REPLACE(UPPER(TRIM(symbol)), '^.*:', ''), '(\\.NS|-EQ)$', '')"
    sql = f"""
        SELECT
            {symbol_expr} AS symbol_norm,
            trading_date,
            price_for_ema,
            open,
            high,
            low,
            volume
        FROM V_NSE500_EMA_DAILY
        WHERE symbol IS NOT NULL
          AND UPPER(TRIM(symbol)) IN ({in_clause})
        ORDER BY {symbol_expr}, trading_date
    """
    candles_by_symbol: dict[str, list[dict[str, Any]]] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(sql, binds)
            for symbol_norm, trading_date, price, open_price, high, low, volume in cur.fetchall() or []:
                symbol_key = _to_text(symbol_norm).upper()
                close = _to_number(price)
                if not symbol_key or close is None:
                    continue
                candle_date = _indicator_datetime(trading_date)
                if candle_date is None:
                    continue
                candles_by_symbol.setdefault(symbol_key, []).append(
                    {
                        "date": candle_date,
                        "tradingDate": _iso_date(trading_date),
                        "open": _to_number(open_price) if _to_number(open_price) is not None else close,
                        "high": _to_number(high) if _to_number(high) is not None else close,
                        "low": _to_number(low) if _to_number(low) is not None else close,
                        "close": close,
                        "volume": _to_number(volume),
                    }
                )
    except Exception as exc:
        _logger.warning("FYERS holdings computed technical enrichment skipped: %s", exc)
        return {}

    out: dict[str, dict[str, Any]] = {}
    for symbol_key, candles in candles_by_symbol.items():
        candles.sort(key=lambda item: item["date"])
        closes = [float(candle["close"]) for candle in candles if _to_number(candle.get("close")) is not None]
        if not closes:
            continue
        latest = candles[-1]
        price = _to_number(latest.get("close"))
        ema_values = {period: calculate_ema(closes, period) for period in (20, 50, 100, 200)}
        rsi = calculate_rsi(closes, 14)
        macd_state = calculate_macd(closes)
        adx_state = calculate_adx(candles, 14)
        volume_values = [_to_number(candle.get("volume")) for candle in candles[-21:-1]]
        prior_volumes = [value for value in volume_values if value is not None and value > 0]
        latest_volume = _to_number(latest.get("volume"))
        avg_volume20 = sum(prior_volumes) / len(prior_volumes) if prior_volumes else None
        volume_ratio20 = (
            latest_volume / avg_volume20
            if latest_volume is not None and avg_volume20 is not None and avg_volume20 > 0
            else None
        )
        out[symbol_key] = {
            "price": price,
            "tradingDate": latest.get("tradingDate"),
            "open": _to_number(latest.get("open")),
            "high": _to_number(latest.get("high")),
            "low": _to_number(latest.get("low")),
            "volume": latest_volume,
            "avgVolume20": avg_volume20,
            "volumeRatio20": volume_ratio20,
            "volumeAbove20": (volume_ratio20 >= 1) if volume_ratio20 is not None else None,
            "ema20": ema_values[20],
            "ema50": ema_values[50],
            "ema100": ema_values[100],
            "ema200": ema_values[200],
            "ema20Flag": "Y" if price is not None and ema_values[20] is not None and price > ema_values[20] else (
                "N" if price is not None and ema_values[20] is not None else None
            ),
            "ema50Flag": "Y" if price is not None and ema_values[50] is not None and price > ema_values[50] else (
                "N" if price is not None and ema_values[50] is not None else None
            ),
            "ema100Flag": "Y" if price is not None and ema_values[100] is not None and price > ema_values[100] else (
                "N" if price is not None and ema_values[100] is not None else None
            ),
            "ema200Flag": "Y" if price is not None and ema_values[200] is not None and price > ema_values[200] else (
                "N" if price is not None and ema_values[200] is not None else None
            ),
            "rsi": rsi,
            "rsiAbove50": (rsi > 50) if rsi is not None else None,
            "macd": macd_state.get("macd"),
            "macdHist": macd_state.get("hist"),
            "macdAboveZero": (macd_state.get("hist") > 0) if macd_state.get("hist") is not None else None,
            "adx14": adx_state.get("adx"),
            "adxAbove25": (adx_state.get("adx") > 25) if adx_state.get("adx") is not None else None,
            "plusDi14": adx_state.get("plusDi"),
            "minusDi14": adx_state.get("minusDi"),
            "atr14": adx_state.get("atr"),
            "atrAbove14": (adx_state.get("atr") > 14) if adx_state.get("atr") is not None else None,
        }
    return out


def _fetch_latest_raw_ltp_map(
    conn: Any,
    symbols: list[str],
    *,
    min_trading_date: date | None = None,
) -> dict[str, dict[str, Any]]:
    cleaned = sorted({s for s in symbols if s})
    if not cleaned:
        return {}

    table_name = _qualified_optional_table(
        os.getenv("FYERS_HOLDINGS_LTP_TABLE") or "NSE_NIFTY500_DAILY_RAW_DATA_VIEW",
        schema=os.getenv("FYERS_HOLDINGS_LTP_SCHEMA") or os.getenv("ORACLE_SCHEMA"),
    )
    expanded_symbols: set[str] = set()
    for symbol in cleaned:
        token = _to_text(symbol).upper()
        if not token:
            continue
        expanded_symbols.update({token, f"{token}-EQ", f"{token}.NS", f"NSE:{token}-EQ"})
    if not expanded_symbols:
        return {}

    binds: dict[str, Any] = {f"s{idx}": value for idx, value in enumerate(sorted(expanded_symbols))}
    in_clause = ", ".join(f":{name}" for name in binds.keys())
    min_date_filter = ""
    if min_trading_date is not None:
        binds["min_trading_date"] = min_trading_date
        min_date_filter = "AND TRADING_DATE >= :min_trading_date"
    symbol_expr = "REGEXP_REPLACE(REGEXP_REPLACE(UPPER(TRIM(SYMBOL)), '^.*:', ''), '(\\.NS|-EQ)$', '')"
    sql = f"""
        SELECT symbol_norm, trading_date, ltp
        FROM (
            SELECT
                {symbol_expr} AS symbol_norm,
                TRADING_DATE AS trading_date,
                LTP AS ltp,
                ROW_NUMBER() OVER (
                    PARTITION BY {symbol_expr}
                    ORDER BY TRADING_DATE DESC NULLS LAST
                ) AS rn
            FROM {table_name}
            WHERE SYMBOL IS NOT NULL
              AND LTP IS NOT NULL
              {min_date_filter}
              AND UPPER(TRIM(SYMBOL)) IN ({in_clause})
        )
        WHERE rn = 1
    """
    out: dict[str, dict[str, Any]] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(sql, binds)
            for symbol_norm, trading_date, ltp in cur.fetchall() or []:
                symbol_key = _to_text(symbol_norm).upper()
                ltp_value = _to_number(ltp)
                if not symbol_key or ltp_value is None:
                    continue
                out[symbol_key] = {
                    "price": ltp_value,
                    "tradingDate": _iso_date(trading_date),
                    "priceSource": "NSE_RAW_LTP",
                }
    except Exception as exc:
        _logger.warning("FYERS holdings raw LTP enrichment skipped: %s", exc)
        return {}
    return out


def _is_ltp_price_source(source: Any) -> bool:
    return _to_text(source).upper() in {"FYERS_LIVE_QUOTE", "NSE_RAW_LTP"}


def _fyers_symbol_from_token(symbol: str) -> str:
    token = _normalize_symbol_token(symbol)
    return f"NSE:{token}-EQ" if token else ""


def _load_fyers_quote_token() -> tuple[str, str] | None:
    full_token = _to_text(os.getenv("FYERS_ACCESS_TOKEN") or os.getenv("FYERS_TOKEN"))
    token_paths = [
        _to_text(os.getenv("FYERS_TOKEN_FILE")),
        str(Path(FYERS_PROJECT_DIR) / "src" / "token.json") if FYERS_PROJECT_DIR else "",
        str(Path(FYERS_PROJECT_DIR) / "token.json") if FYERS_PROJECT_DIR else "",
    ]
    if not full_token:
        for raw_path in token_paths:
            if not raw_path:
                continue
            path = Path(raw_path).expanduser()
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            full_token = _to_text(payload.get("access_token") or payload.get("token"))
            raw_token = _to_text(payload.get("raw_access_token"))
            client_id = _to_text(payload.get("client_id") or payload.get("app_id") or payload.get("FYERS_APP_ID"))
            if full_token:
                break
            if raw_token and client_id:
                return client_id, raw_token
    if not full_token:
        return None
    if ":" in full_token:
        client_id, token = full_token.split(":", 1)
        return _to_text(client_id), _to_text(token)

    config_paths = [
        _to_text(os.getenv("FYERS_CONFIG_FILE")),
        str(Path(FYERS_PROJECT_DIR) / "src" / "config.json") if FYERS_PROJECT_DIR else "",
        str(Path(FYERS_PROJECT_DIR) / "config.json") if FYERS_PROJECT_DIR else "",
    ]
    for raw_path in config_paths:
        if not raw_path:
            continue
        path = Path(raw_path).expanduser()
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        client_id = _to_text(payload.get("FYERS_APP_ID") or payload.get("client_id") or payload.get("app_id"))
        if client_id:
            return client_id, full_token
    return None


def _is_jwt_expired(token: str, *, skew_seconds: int = 60) -> bool:
    parts = str(token or "").split(".")
    if len(parts) < 2:
        return False
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
        exp = int(data.get("exp") or 0)
    except Exception:
        return False
    return bool(exp and exp <= int(time.time()) + int(skew_seconds))


def _has_active_fyers_quote_auth() -> bool:
    try:
        try:
            from . import marketdata_service as marketdata_svc
        except ImportError:  # pragma: no cover
            import services.marketdata_service as marketdata_svc  # type: ignore
        status = marketdata_svc.fyers_auth_status()
    except Exception:
        return True
    if not isinstance(status, dict):
        return True
    if status.get("authExpired") is True:
        return False
    if status.get("authenticated") is False and status.get("authenticatedToday") is False:
        return False
    return True


def _parse_fyers_quote_response(response: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(response, dict) or str(response.get("s") or "").lower() != "ok":
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in response.get("d") or []:
        if not isinstance(item, dict):
            continue
        values = item.get("v") if isinstance(item.get("v"), dict) else {}
        name = _to_text(_coalesce(item.get("n"), values.get("symbol"), values.get("original_name"))).upper()
        symbol_key = _normalize_symbol_token(name)
        lp = _safe_decimal(_coalesce(values.get("lp"), values.get("last_price"), values.get("ltp"), item.get("lp")))
        previous_close = _safe_decimal(
            _coalesce(
                values.get("prev_close_price"),
                values.get("previous_close"),
                values.get("prevClose"),
                values.get("pc"),
            )
        )
        if not symbol_key or lp is None:
            continue
        out[symbol_key] = {
            "price": lp,
            "previousClose": previous_close,
            "priceSource": "FYERS_LIVE_QUOTE",
            "tradingDate": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    return out


def _fetch_fyers_live_quote_map(symbols: list[str]) -> dict[str, dict[str, Any]]:
    if not FYERS_HOLDINGS_LIVE_QUOTES_ENABLED:
        return {}
    fyers_symbols = sorted({_fyers_symbol_from_token(symbol) for symbol in symbols if _fyers_symbol_from_token(symbol)})
    if not fyers_symbols:
        return {}
    cache_key = ",".join(fyers_symbols)
    cached = _FYERS_LIVE_QUOTE_CACHE.get(cache_key)
    if isinstance(cached, dict):
        return cached

    if not _has_active_fyers_quote_auth():
        _logger.info("FYERS holdings live quote skipped because FYERS authentication is not active")
        _FYERS_LIVE_QUOTE_CACHE.set(cache_key, {})
        return {}

    token_pair = _load_fyers_quote_token()
    if not token_pair:
        return {}
    if _is_jwt_expired(token_pair[1]):
        _logger.info("FYERS holdings live quote skipped because the FYERS access token is expired")
        _FYERS_LIVE_QUOTE_CACHE.set(cache_key, {})
        return {}

    def _call_quotes() -> dict[str, dict[str, Any]]:
        from fyers_apiv3 import fyersModel  # type: ignore

        client_id, token = token_pair
        repo_root = Path(__file__).resolve().parents[2]
        log_dir = Path(os.getenv("FYERS_HOLDINGS_QUOTE_LOG_DIR") or repo_root / "backend" / "logs" / "fyers_quotes")
        log_dir.mkdir(parents=True, exist_ok=True)
        fyers = fyersModel.FyersModel(client_id=client_id, token=token, log_path=str(log_dir))
        response = fyers.quotes({"symbols": ",".join(fyers_symbols)})
        return _parse_fyers_quote_response(response)

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_call_quotes)
        quote_map = future.result(timeout=FYERS_HOLDINGS_LIVE_QUOTES_TIMEOUT_SECONDS)
    except Exception as exc:
        executor.shutdown(wait=False, cancel_futures=True)
        _logger.info("FYERS holdings live quote fallback active: %s", exc)
        _FYERS_LIVE_QUOTE_CACHE.set(cache_key, {})
        return {}
    executor.shutdown(wait=False, cancel_futures=False)

    _FYERS_LIVE_QUOTE_CACHE.set(cache_key, quote_map)
    return quote_map


def _format_level_number(value: Any) -> str:
    num = _to_number(value)
    if num is None:
        return ""
    text = f"{num:,.2f}"
    return text.rstrip("0").rstrip(".")


def _format_level_label(prefix: str, levels: list[float]) -> str | None:
    cleaned = [level for level in levels if _to_number(level) is not None]
    if not cleaned:
        return None
    parts = []
    for idx, level in enumerate(cleaned[:2], start=1):
        formatted = _format_level_number(level)
        if formatted:
            parts.append(f"{prefix}{idx}:{formatted}")
    return ", ".join(parts) or None


def _fetch_asura_signal_map(conn: Any, symbols: list[str]) -> dict[str, dict[str, Any]]:
    cleaned = sorted({s for s in symbols if s})
    if not cleaned:
        return {}
    binds = {f"s{idx}": value for idx, value in enumerate(cleaned)}
    in_clause = ", ".join(f":{name}" for name in binds.keys())
    table_name = _qualified_optional_table(
        FYERS_HOLDINGS_ASURA_TABLE,
        schema=os.getenv("ASURA_SCHEMA") or os.getenv("ORACLE_SCHEMA"),
    )
    symbol_expr = "REGEXP_REPLACE(REGEXP_REPLACE(UPPER(TRIM(STOCK)), '^.*:', ''), '(\\.NS|-EQ)$', '')"
    sql = f"""
        SELECT
            symbol_norm,
            signal_score,
            ema20,
            ema50,
            ema100,
            ema200,
            rsi14,
            macd_hist,
            atr14,
            adx14,
            support_price,
            resistance_price,
            trend_direction
        FROM (
            SELECT
                {symbol_expr} AS symbol_norm,
                SIGNAL_SCORE AS signal_score,
                EMA20 AS ema20,
                EMA50 AS ema50,
                EMA100 AS ema100,
                EMA200 AS ema200,
                RSI14 AS rsi14,
                MACD_HIST AS macd_hist,
                ATR14 AS atr14,
                ADX14 AS adx14,
                SUPPORT_PRICE AS support_price,
                RESISTANCE_PRICE AS resistance_price,
                TREND_DIRECTION AS trend_direction,
                ROW_NUMBER() OVER (
                    PARTITION BY {symbol_expr}
                    ORDER BY NVL(BUYING_DATE, DATE '1900-01-01') DESC, NVL(S_NO, 0) DESC
                ) AS rn
            FROM {table_name}
            WHERE STOCK IS NOT NULL
              AND {symbol_expr} IN ({in_clause})
        )
        WHERE rn = 1
    """
    out: dict[str, dict[str, Any]] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(sql, binds)
            for record in cur.fetchall() or []:
                symbol_key = _to_text(record[0]).upper()
                if not symbol_key:
                    continue
                support = _to_number(record[10])
                resistance = _to_number(record[11])
                out[symbol_key] = {
                    "score": _to_number(record[1]),
                    "scoreSort": _to_number(record[1]),
                    "ema20": _to_number(record[2]),
                    "ema50": _to_number(record[3]),
                    "ema100": _to_number(record[4]),
                    "ema200": _to_number(record[5]),
                    "ema20Flag": None,
                    "ema50Flag": None,
                    "ema100Flag": None,
                    "ema200Flag": None,
                    "rsiAbove50": (_to_number(record[6]) > 50) if _to_number(record[6]) is not None else None,
                    "macdAboveZero": (_to_number(record[7]) > 0) if _to_number(record[7]) is not None else None,
                    "atrAbove14": (_to_number(record[8]) > 14) if _to_number(record[8]) is not None else None,
                    "adxAbove25": (_to_number(record[9]) > 25) if _to_number(record[9]) is not None else None,
                    "supportDisplay": _format_level_label("S", [support]) if support is not None else None,
                    "resistanceDisplay": _format_level_label("R", [resistance]) if resistance is not None else None,
                    "trendDirection": _to_text(record[12]) or None,
                }
    except Exception as exc:
        _logger.warning("FYERS holdings Asura enrichment skipped: %s", exc)
        return {}
    return out


def _fetch_manual_sr_display_map(
    conn: Any,
    symbols: list[str],
    price_by_symbol: dict[str, float | None],
) -> dict[str, dict[str, Any]]:
    cleaned = sorted({s for s in symbols if s})
    if not cleaned:
        return {}
    binds = {f"s{idx}": value for idx, value in enumerate(cleaned)}
    in_clause = ", ".join(f":{name}" for name in binds.keys())
    table_name = _qualified_optional_table(
        FYERS_HOLDINGS_MANUAL_SR_TABLE,
        schema=os.getenv("PRICE_ACTION_SR_SCHEMA") or os.getenv("ORACLE_SCHEMA"),
    )
    symbol_expr = "REGEXP_REPLACE(REGEXP_REPLACE(UPPER(TRIM(SYMBOL)), '^.*:', ''), '(\\.NS|-EQ)$', '')"
    sql = f"""
        SELECT {symbol_expr} AS symbol_norm,
               SR_LEVEL
        FROM {table_name}
        WHERE SYMBOL IS NOT NULL
          AND SR_LEVEL IS NOT NULL
          AND {symbol_expr} IN ({in_clause})
          AND UPPER(TRIM(NVL(TF, '1D'))) IN ('1D', 'D', 'DAILY')
        ORDER BY {symbol_expr}, SR_LEVEL
    """
    levels_by_symbol: dict[str, list[float]] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(sql, binds)
            for symbol_norm, sr_level in cur.fetchall() or []:
                symbol_key = _to_text(symbol_norm).upper()
                level = _to_number(sr_level)
                if not symbol_key or level is None:
                    continue
                levels_by_symbol.setdefault(symbol_key, []).append(level)
    except Exception as exc:
        _logger.warning("FYERS holdings manual SR enrichment skipped: %s", exc)
        return {}

    out: dict[str, dict[str, Any]] = {}
    for symbol_key, raw_levels in levels_by_symbol.items():
        levels = sorted({round(float(level), 6) for level in raw_levels})
        price = price_by_symbol.get(symbol_key)
        if price is None:
            supports = levels[:2]
            resistances: list[float] = []
        else:
            supports = sorted((level for level in levels if level <= price), reverse=True)[:2]
            resistances = [level for level in levels if level > price][:2]
        out[symbol_key] = {
            "supportDisplay": _format_level_label("S", supports),
            "resistanceDisplay": _format_level_label("R", resistances),
        }
    return out


def _fetch_sector_snapshot_map(conn: Any, symbols: list[str]) -> dict[str, dict[str, Any]]:
    cleaned = sorted({s for s in symbols if s})
    if not cleaned:
        return {}
    binds = {f"s{idx}": value for idx, value in enumerate(cleaned)}
    in_clause = ", ".join(f":{name}" for name in binds.keys())
    cols = _load_snapshot_columns(conn)

    symbol_col = _pick_snapshot_col(cols, "SYMBOL")
    if not symbol_col:
        return {}

    order_date_col = _pick_snapshot_col(cols, "LTC_DATE", "TRADING_DATE", "AS_OF_DATE", "UPDATED_AT", "CREATED_AT")
    close_col = _pick_snapshot_col(cols, "CLOSE_PRICE", "PRICE", "CLOSE")
    ema20_col = _pick_snapshot_col(cols, "EMA20", "EMA_20")
    ema50_col = _pick_snapshot_col(cols, "EMA50", "EMA_50")
    ema100_col = _pick_snapshot_col(cols, "EMA100", "EMA_100")
    ema200_col = _pick_snapshot_col(cols, "EMA200", "EMA_200")
    ema20_flag_col = _pick_snapshot_col(cols, "EMA20_FLAG", "EMA_20_FLAG")
    ema50_flag_col = _pick_snapshot_col(cols, "EMA50_FLAG", "EMA_50_FLAG")
    ema100_flag_col = _pick_snapshot_col(cols, "EMA100_FLAG", "EMA_100_FLAG")
    ema200_flag_col = _pick_snapshot_col(cols, "EMA200_FLAG", "EMA_200_FLAG")
    macd_flag_col = _pick_snapshot_col(cols, "MACD_FLAG", "MACD_ABOVE_ZERO")
    rsi_flag_col = _pick_snapshot_col(cols, "RSI_FLAG", "RSI_ABOVE_50")
    adx_flag_col = _pick_snapshot_col(cols, "ADX_FLAG", "ADX_ABOVE_25")
    atr_flag_col = _pick_snapshot_col(cols, "ATR_FLAG", "ATR_ABOVE_14")
    volume_flag_col = _pick_snapshot_col(cols, "VOLUME_FLAG", "VOLUME_ABOVE_20")
    low52_col = _pick_snapshot_col(cols, "LOW52W", "LOW_52W", "FIFTY_TWO_WEEK_LOW", "WEEK52_LOW")
    high52_col = _pick_snapshot_col(cols, "HIGH52W", "HIGH_52W", "FIFTY_TWO_WEEK_HIGH", "WEEK52_HIGH")
    ath_col = _pick_snapshot_col(cols, "ATH", "ALL_TIME_HIGH")
    ath_date_col = _pick_snapshot_col(cols, "ATH_DATE")
    score_col = _pick_snapshot_col(cols, "TECH_SCORE", "SCORE", "SIGNAL_SCORE", "MASTER_SCORE")
    score_sort_col = _pick_snapshot_col(
        cols,
        "TECH_SCORE_SORT",
        "SCORE_SORT",
        "SIGNAL_SCORE_SORT",
        "MASTER_SCORE_SORT",
        "TECH_SCORE",
        "SCORE",
        "SIGNAL_SCORE",
        "MASTER_SCORE",
    )
    support_col = _pick_snapshot_col(
        cols,
        "SUPPORT_DISPLAY",
        "NEAREST_SUPPORT",
        "SUPPORT_LEVEL",
        "SUPPORT_PRICE",
        "SUPPORT",
        "S1",
    )
    resistance_col = _pick_snapshot_col(
        cols,
        "RESISTANCE_DISPLAY",
        "NEAREST_RESISTANCE",
        "RESISTANCE_LEVEL",
        "RESISTANCE_PRICE",
        "RESISTANCE",
        "R1",
    )

    def _sel(col: str | None) -> str:
        return f"{col}" if col else "NULL"

    order_expr = f"{order_date_col} DESC NULLS LAST" if order_date_col else "ROWID DESC"
    sql = f"""
        SELECT
            symbol_norm,
            close_price,
            ema20,
            ema50,
            ema100,
            ema200,
            ema20_flag,
            ema50_flag,
            ema100_flag,
            ema200_flag,
            macd_flag,
            rsi_flag,
            adx_flag,
            atr_flag,
            volume_flag,
            low52w,
            high52w,
            ath,
            ath_date,
            score,
            score_sort,
            support_display,
            resistance_display
        FROM (
            SELECT
                UPPER(TRIM({symbol_col})) AS symbol_norm,
                {_sel(close_col)} AS close_price,
                {_sel(ema20_col)} AS ema20,
                {_sel(ema50_col)} AS ema50,
                {_sel(ema100_col)} AS ema100,
                {_sel(ema200_col)} AS ema200,
                {_sel(ema20_flag_col)} AS ema20_flag,
                {_sel(ema50_flag_col)} AS ema50_flag,
                {_sel(ema100_flag_col)} AS ema100_flag,
                {_sel(ema200_flag_col)} AS ema200_flag,
                {_sel(macd_flag_col)} AS macd_flag,
                {_sel(rsi_flag_col)} AS rsi_flag,
                {_sel(adx_flag_col)} AS adx_flag,
                {_sel(atr_flag_col)} AS atr_flag,
                {_sel(volume_flag_col)} AS volume_flag,
                {_sel(low52_col)} AS low52w,
                {_sel(high52_col)} AS high52w,
                {_sel(ath_col)} AS ath,
                {_sel(ath_date_col)} AS ath_date,
                {_sel(score_col)} AS score,
                {_sel(score_sort_col)} AS score_sort,
                {_sel(support_col)} AS support_display,
                {_sel(resistance_col)} AS resistance_display,
                ROW_NUMBER() OVER (
                    PARTITION BY UPPER(TRIM({symbol_col}))
                    ORDER BY {order_expr}, {_sel(close_col)} DESC NULLS LAST
                ) AS rn
            FROM (
                SELECT * FROM mv_nse_sector_ui_snapshot
            ) snap
            WHERE UPPER(TRIM({symbol_col})) IN ({in_clause})
        )
        WHERE rn = 1
    """
    out: dict[str, dict[str, Any]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, binds)
        for record in cur.fetchall() or []:
            symbol_key = _to_text(record[0]).upper()
            if not symbol_key:
                continue
            out[symbol_key] = {
                "price": _to_number(record[1]),
                "ema20": _to_number(record[2]),
                "ema50": _to_number(record[3]),
                "ema100": _to_number(record[4]),
                "ema200": _to_number(record[5]),
                "ema20Flag": _to_text(record[6]).upper() or None,
                "ema50Flag": _to_text(record[7]).upper() or None,
                "ema100Flag": _to_text(record[8]).upper() or None,
                "ema200Flag": _to_text(record[9]).upper() or None,
                "macdAboveZero": _to_bool(record[10]),
                "rsiAbove50": _to_bool(record[11]),
                "adxAbove25": _to_bool(record[12]),
                "atrAbove14": _to_bool(record[13]),
                "volumeAbove20": _to_bool(record[14]),
                "fiftyTwoWeekLow": _to_number(record[15]),
                "fiftyTwoWeekHigh": _to_number(record[16]),
                "ath": _to_number(record[17]),
                "athDate": _iso_date(record[18]),
                "score": _to_number(record[19]),
                "scoreSort": _to_number(record[20]),
                "supportDisplay": _to_text(record[21]) or None,
                "resistanceDisplay": _to_text(record[22]) or None,
            }
    return out


def _apply_previous_close_priority(
    conn: Any,
    rows: list[dict[str, Any]],
    *,
    include_live_quotes: bool = False,
) -> tuple[int, int, int]:
    row_aliases: list[list[str]] = [
        _build_symbol_aliases(row.get("symbolRaw"), row.get("symbolCode"))
        for row in rows
    ]
    symbol_keys = sorted({alias for aliases in row_aliases for alias in aliases})
    if not hasattr(conn, "cursor"):
        return 0, 0, len(rows)
    report_dates = [
        candidate
        for candidate in (_date_from_any(row.get("reportDate")) for row in rows)
        if candidate is not None
    ]
    min_raw_ltp_date = max(report_dates) if report_dates else None
    live_quote_map = _fetch_fyers_live_quote_map(symbol_keys) if include_live_quotes else {}
    raw_ltp_map = _fetch_latest_raw_ltp_map(conn, symbol_keys, min_trading_date=min_raw_ltp_date)
    snapshot_map = _fetch_sector_snapshot_map(conn, symbol_keys)
    asura_signal_map = _fetch_asura_signal_map(conn, symbol_keys)
    ema_map = _fetch_latest_ema_previous_close_map(conn, symbol_keys)
    fallback_symbol_keys: set[str] = set()
    for aliases in row_aliases:
        snapshot_row = next((snapshot_map.get(alias) for alias in aliases if alias in snapshot_map), None)
        asura_row = next((asura_signal_map.get(alias) for alias in aliases if alias in asura_signal_map), None)
        if not isinstance(snapshot_row, dict):
            fallback_symbol_keys.update(aliases)
            continue
        if any(
            snapshot_row.get(key) is None
            for key in ("volumeAbove20", "fiftyTwoWeekLow", "fiftyTwoWeekHigh", "ath")
        ):
            fallback_symbol_keys.update(aliases)
            continue
        if all(
            _to_number(snapshot_row.get(key)) is None
            for key in ("ema20", "ema50", "ema100", "ema200")
        ) and not isinstance(asura_row, dict):
            fallback_symbol_keys.update(aliases)
    fallback_symbols = sorted(fallback_symbol_keys)
    technical_range_map = _fetch_raw_technical_range_map(conn, fallback_symbols) if fallback_symbols else {}
    computed_technical_map = _fetch_computed_technical_map(conn, symbol_keys)
    ema_matches = 0
    csv_matches = 0
    missing = 0
    for row, aliases in zip(rows, row_aliases):
        snapshot_row = next((snapshot_map.get(alias) for alias in aliases if alias in snapshot_map), None)
        technical_range_row = next(
            (technical_range_map.get(alias) for alias in aliases if alias in technical_range_map),
            None,
        )
        computed_row = next(
            (computed_technical_map.get(alias) for alias in aliases if alias in computed_technical_map),
            None,
        )
        live_quote_row = next((live_quote_map.get(alias) for alias in aliases if alias in live_quote_map), None)
        raw_ltp_row = next((raw_ltp_map.get(alias) for alias in aliases if alias in raw_ltp_map), None)
        asura_row = next((asura_signal_map.get(alias) for alias in aliases if alias in asura_signal_map), None)
        ema_price = next((ema_map.get(alias) for alias in aliases if alias in ema_map), None)
        snapshot_price = _to_number(snapshot_row.get("price")) if isinstance(snapshot_row, dict) else None
        if isinstance(live_quote_row, dict):
            live_price = _safe_decimal(live_quote_row.get("price"))
            if live_price is not None:
                row["price"] = live_price
                row["priceSource"] = "FYERS_LIVE_QUOTE"
                row["tradingDate"] = live_quote_row.get("tradingDate")
        if not _is_ltp_price_source(row.get("priceSource")) and isinstance(raw_ltp_row, dict):
            raw_ltp_price = _safe_decimal(raw_ltp_row.get("price"))
            if raw_ltp_price is not None:
                row["price"] = raw_ltp_price
                row["priceSource"] = "NSE_RAW_LTP"
                row["tradingDate"] = raw_ltp_row.get("tradingDate")
        if isinstance(snapshot_row, dict):
            if snapshot_price is not None and row.get("price") in (None, ""):
                row["price"] = snapshot_price
                row["priceSource"] = "SECTOR_SNAPSHOT_PRICE"
            row["ema20"] = snapshot_row.get("ema20")
            row["ema50"] = snapshot_row.get("ema50")
            row["ema100"] = snapshot_row.get("ema100")
            row["ema200"] = snapshot_row.get("ema200")
            row["ema20Flag"] = snapshot_row.get("ema20Flag")
            row["ema50Flag"] = snapshot_row.get("ema50Flag")
            row["ema100Flag"] = snapshot_row.get("ema100Flag")
            row["ema200Flag"] = snapshot_row.get("ema200Flag")
            row["macdAboveZero"] = snapshot_row.get("macdAboveZero")
            row["rsiAbove50"] = snapshot_row.get("rsiAbove50")
            row["adxAbove25"] = snapshot_row.get("adxAbove25")
            row["atrAbove14"] = snapshot_row.get("atrAbove14")
            row["volumeAbove20"] = snapshot_row.get("volumeAbove20")
            row["fiftyTwoWeekLow"] = snapshot_row.get("fiftyTwoWeekLow")
            row["fiftyTwoWeekHigh"] = snapshot_row.get("fiftyTwoWeekHigh")
            row["low52w"] = row.get("fiftyTwoWeekLow")
            row["high52w"] = row.get("fiftyTwoWeekHigh")
            row["ath"] = snapshot_row.get("ath")
            row["athDate"] = snapshot_row.get("athDate")
            row["score"] = snapshot_row.get("score")
            row["scoreSort"] = snapshot_row.get("scoreSort")
            row["techScore"] = snapshot_row.get("score")
            row["supportDisplay"] = snapshot_row.get("supportDisplay")
            row["resistanceDisplay"] = snapshot_row.get("resistanceDisplay")
        if isinstance(asura_row, dict):
            for key in ("score", "scoreSort", "ema20", "ema50", "ema100", "ema200"):
                if _to_number(row.get(key)) is None:
                    row[key] = asura_row.get(key)
            if _to_number(row.get("techScore")) is None:
                row["techScore"] = asura_row.get("score")
            for key in (
                "macdAboveZero",
                "rsiAbove50",
                "adxAbove25",
                "atrAbove14",
            ):
                if row.get(key) is None:
                    row[key] = asura_row.get(key)
            if not _to_text(row.get("supportDisplay")):
                row["supportDisplay"] = asura_row.get("supportDisplay")
            if not _to_text(row.get("resistanceDisplay")):
                row["resistanceDisplay"] = asura_row.get("resistanceDisplay")
            if not _to_text(row.get("trendDirection")):
                row["trendDirection"] = asura_row.get("trendDirection")
        if isinstance(computed_row, dict):
            for key in ("price", "tradingDate", "open", "high", "low", "volume", "avgVolume20", "volumeRatio20"):
                if key == "price" and not _is_ltp_price_source(row.get("priceSource")):
                    row[key] = computed_row.get(key)
                    if computed_row.get(key) is not None:
                        row["priceSource"] = "COMPUTED_TECHNICAL_PRICE"
                    continue
                if row.get(key) in (None, ""):
                    row[key] = computed_row.get(key)
                    if key == "price" and computed_row.get(key) is not None:
                        row["priceSource"] = "COMPUTED_TECHNICAL_PRICE"
            for key in ("ema20", "ema50", "ema100", "ema200", "rsi", "macd", "macdHist", "adx14", "plusDi14", "minusDi14", "atr14"):
                if _to_number(row.get(key)) is None:
                    row[key] = computed_row.get(key)
            for key in (
                "ema20Flag",
                "ema50Flag",
                "ema100Flag",
                "ema200Flag",
                "macdAboveZero",
                "rsiAbove50",
                "adxAbove25",
                "atrAbove14",
                "volumeAbove20",
            ):
                if row.get(key) is None or not _to_text(row.get(key)):
                    row[key] = computed_row.get(key)
        if isinstance(technical_range_row, dict):
            if row.get("volumeAbove20") is None:
                row["volumeAbove20"] = technical_range_row.get("volumeAbove20")
            row["volume"] = technical_range_row.get("volume")
            row["volumeRatio20"] = technical_range_row.get("volumeRatio20")
            row["avgVolume20"] = technical_range_row.get("avgVolume20")
            if _to_number(row.get("fiftyTwoWeekLow")) is None:
                row["fiftyTwoWeekLow"] = technical_range_row.get("fiftyTwoWeekLow")
            row["low52w"] = row.get("fiftyTwoWeekLow")
            if _to_number(row.get("fiftyTwoWeekHigh")) is None:
                row["fiftyTwoWeekHigh"] = technical_range_row.get("fiftyTwoWeekHigh")
            row["high52w"] = row.get("fiftyTwoWeekHigh")
            if _to_number(row.get("ath")) is None:
                row["ath"] = technical_range_row.get("ath")
            if not row.get("athDate"):
                row["athDate"] = technical_range_row.get("athDate")
        live_previous_close = _safe_decimal(live_quote_row.get("previousClose")) if isinstance(live_quote_row, dict) else None
        csv_prev = _safe_decimal(row.get("previousClose"))
        if live_previous_close is not None:
            row["previousClose"] = live_previous_close
            row["previousCloseSource"] = "FYERS_LIVE_QUOTE"
            ema_matches += 1
        elif csv_prev is not None:
            row["previousClose"] = csv_prev
            row["previousCloseSource"] = "CSV_PRICE"
            csv_matches += 1
            if _to_number(row.get("price")) is None and ema_price is not None:
                row["price"] = ema_price
                row["priceSource"] = "EMA_PRICE"
            elif _to_number(row.get("price")) is None and snapshot_price is not None:
                row["price"] = snapshot_price
                row["priceSource"] = "SECTOR_SNAPSHOT_PRICE"
        elif snapshot_price is not None:
            row["previousClose"] = None
            row["previousCloseSource"] = "NOT_AVAILABLE"
            if _to_number(row.get("price")) is None:
                row["price"] = snapshot_price
                row["priceSource"] = "SECTOR_SNAPSHOT_PRICE"
            ema_matches += 1
        elif ema_price is not None:
            row["previousClose"] = None
            row["previousCloseSource"] = "NOT_AVAILABLE"
            row["price"] = ema_price
            row["priceSource"] = "EMA_PRICE"
            ema_matches += 1
        else:
            row["previousClose"] = None
            row["previousCloseSource"] = "NOT_AVAILABLE"
            missing += 1
        price = _to_number(row.get("price")) or _to_number(row.get("previousClose"))
        for period in (20, 50, 100, 200):
            ema_value = _to_number(row.get(f"ema{period}"))
            flag_key = f"ema{period}Flag"
            if _to_text(row.get(flag_key)):
                continue
            if price is not None and ema_value is not None:
                row[flag_key] = "Y" if price > ema_value else "N"

    price_by_symbol: dict[str, float | None] = {}
    for row in rows:
        price = _to_number(row.get("price"))
        if price is None:
            price = _to_number(row.get("previousClose"))
        if price is None:
            price = _to_number(row.get("buyPrice"))
        for alias in _build_symbol_aliases(row.get("symbolRaw"), row.get("symbolCode")):
            price_by_symbol[alias] = price
    manual_sr_map = _fetch_manual_sr_display_map(conn, symbol_keys, price_by_symbol)
    for row in rows:
        aliases = _build_symbol_aliases(row.get("symbolRaw"), row.get("symbolCode"))
        manual_sr_row = next((manual_sr_map.get(alias) for alias in aliases if alias in manual_sr_map), None)
        if isinstance(manual_sr_row, dict) and not _to_text(row.get("supportDisplay")):
            row["supportDisplay"] = manual_sr_row.get("supportDisplay")
        if isinstance(manual_sr_row, dict) and not _to_text(row.get("resistanceDisplay")):
            row["resistanceDisplay"] = manual_sr_row.get("resistanceDisplay")
        if not _to_text(row.get("supportDisplay")):
            low52 = _to_number(row.get("fiftyTwoWeekLow"))
            row["supportDisplay"] = _format_level_label("S", [low52]) if low52 is not None else None
        if not _to_text(row.get("resistanceDisplay")):
            high52 = _to_number(row.get("fiftyTwoWeekHigh"))
            row["resistanceDisplay"] = _format_level_label("R", [high52]) if high52 is not None else None
        price = _to_number(row.get("price")) or _to_number(row.get("previousClose")) or _to_number(row.get("buyPrice"))
        if price is not None:
            row["close"] = price
        if _to_number(row.get("score")) is None or not _to_text(row.get("trendDirection")):
            enrich_row_with_master_score_fields(row, replace_existing=False)
    return ema_matches, csv_matches, missing


def parse_holdings_csv_text(
    csv_text: str,
    *,
    source_filename: str = "",
    source_path: str = "",
) -> dict[str, Any]:
    text = str(csv_text or "").lstrip("\ufeff")
    if not text.strip():
        raise ValueError("CSV content is required.")

    reader = csv.reader(io.StringIO(text), skipinitialspace=True)
    rows = [[_to_text(cell) for cell in row] for row in reader]
    header_index = -1
    for idx, row in enumerate(rows):
        normalized = [_normalize_header(cell) for cell in row if _to_text(cell)]
        if len(normalized) >= 2 and normalized[0] == "name" and normalized[1] == "qty":
            header_index = idx
            break
    if header_index < 0:
        raise ValueError("Unable to locate the holdings table in the CSV.")

    metadata: dict[str, Any] = {}
    for row in rows[:header_index]:
        if not row:
            continue
        key = _to_text(row[0])
        if key not in _REPORT_LABELS:
            continue
        field = _REPORT_LABELS[key]
        value = row[1] if len(row) > 1 else ""
        if field == "reportDate":
            metadata[field] = _parse_report_date(value)
        elif field == "downloadTimestamp":
            metadata[field] = _parse_timestamp(value)
        elif field in {"totalInvested", "totalCurrent", "profitLoss", "unrealisedPnlPct"}:
            metadata[field] = _decimal_or_none(value)
        else:
            metadata[field] = _to_text(value)

    header_row = rows[header_index]
    field_indexes: dict[str, int] = {}
    for idx, name in enumerate(header_row):
        mapped = _HOLDING_HEADER_MAP.get(_normalize_header(name))
        if mapped:
            field_indexes[mapped] = idx

    missing_required = [
        field
        for field in (
            "symbolRaw",
            "quantity",
            "buyPrice",
            "investedValue",
            "currentValue",
            "unrealisedPnl",
            "unrealisedPnlPct",
            "previousClose",
            "isin",
        )
        if field not in field_indexes
    ]
    if missing_required:
        raise ValueError("CSV holdings header is missing columns: " + ", ".join(missing_required))

    holding_rows: list[dict[str, Any]] = []
    duplicates: set[str] = set()
    seen_symbols: set[str] = set()
    for row in rows[header_index + 1 :]:
        if not any(_to_text(cell) for cell in row):
            continue
        symbol_raw = row[field_indexes["symbolRaw"]] if field_indexes["symbolRaw"] < len(row) else ""
        if not _to_text(symbol_raw):
            continue
        raw_symbol, exchange_code, symbol_code, series_code = _split_symbol(symbol_raw)
        if symbol_code in seen_symbols:
            duplicates.add(symbol_code)
        seen_symbols.add(symbol_code)
        parsed_row: dict[str, Any] = {
            "symbolRaw": raw_symbol,
            "exchangeCode": exchange_code,
            "symbolCode": symbol_code,
            "seriesCode": series_code,
            "isin": _to_text(row[field_indexes["isin"]]) if field_indexes["isin"] < len(row) else "",
        }
        for field in _NUMERIC_ROW_FIELDS:
            idx = field_indexes[field]
            parsed_row[field] = _decimal_or_none(row[idx] if idx < len(row) else "")
        holding_rows.append(parsed_row)

    if duplicates:
        raise ValueError("Duplicate symbols found in holdings CSV: " + ", ".join(sorted(duplicates)))

    return {
        "metadata": metadata,
        "rows": holding_rows,
        "rowCount": len(holding_rows),
        "stableFields": _stable_fields_from_metadata(metadata),
        "stableFieldKeys": list(STATIC_REPORT_FIELDS),
        "file": {
            "sourceFilename": _to_text(source_filename),
            "sourcePath": _to_text(source_path),
            "sourceHash": _file_hash(text),
            "sourceSize": len(text.encode("utf-8")),
        },
    }


def _current_row_key(row: dict[str, Any]) -> str:
    return _to_text(row.get("symbolCode")).upper()


def _business_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    values: list[Any] = []
    for field in _BUSINESS_COMPARE_FIELDS:
        value = _numeric_compare_token(row.get(field))
        if isinstance(value, (datetime, date)):
            value = _json_default(value)
        values.append(value)
    return tuple(values)


def plan_current_holding_changes(
    existing_rows: list[dict[str, Any]],
    imported_rows: list[dict[str, Any]],
    *,
    replace_missing: bool = True,
) -> dict[str, Any]:
    existing_map = {_current_row_key(row): row for row in existing_rows}
    imported_map = {_current_row_key(row): row for row in imported_rows}

    inserts: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    deletes: list[dict[str, Any]] = []

    for symbol_code, new_row in imported_map.items():
        existing = existing_map.get(symbol_code)
        if existing is None:
            inserts.append({"after": new_row})
            continue
        if _business_signature(existing) == _business_signature(new_row):
            unchanged.append({"before": existing, "after": new_row})
            continue
        updates.append({"before": existing, "after": new_row})

    if replace_missing:
        for symbol_code, existing in existing_map.items():
            if symbol_code not in imported_map:
                deletes.append({"before": existing})

    return {
        "insert": inserts,
        "update": updates,
        "unchanged": unchanged,
        "delete": deletes,
        "stats": {
            "inserted": len(inserts),
            "updated": len(updates),
            "unchanged": len(unchanged),
            "deleted": len(deletes),
            "errors": 0,
            "rows": len(imported_rows),
        },
    }


def _current_rows_match_import_metadata(
    existing_rows: list[dict[str, Any]],
    metadata: dict[str, Any],
    file_info: dict[str, Any],
) -> bool:
    if not existing_rows:
        return False
    expected_hash = _to_text(file_info.get("sourceHash"))
    expected_filename = _to_text(file_info.get("sourceFilename"))
    expected_report_date = _iso_date(metadata.get("reportDate"))
    expected_download_ts = _iso_datetime(metadata.get("downloadTimestamp"))
    for row in existing_rows:
        if expected_hash and _to_text(row.get("sourceHash")) != expected_hash:
            return False
        if expected_filename and _to_text(row.get("sourceFilename")) != expected_filename:
            return False
        if expected_report_date and _iso_date(row.get("reportDate")) != expected_report_date:
            return False
        if expected_download_ts and _iso_datetime(row.get("downloadTimestamp")) != expected_download_ts:
            return False
    return True

def _read_csv_payload(payload: dict[str, Any]) -> tuple[str, str, str]:
    csv_text = _coalesce(payload.get("csvText"), payload.get("csvContent"), payload.get("fileContent"))
    filename = _to_text(_coalesce(payload.get("filename"), payload.get("sourceFilename")))
    source_path = _to_text(_coalesce(payload.get("filePath"), payload.get("sourcePath")))
    if csv_text is not None:
        return str(csv_text), filename, source_path
    if not source_path:
        raise ValueError("Provide either csvText/fileContent or filePath.")
    path = Path(source_path).expanduser()
    if not path.exists():
        raise ValueError(f"CSV file not found: {path}")
    return path.read_text(encoding="utf-8-sig"), filename or path.name, str(path)


def _fetch_current_rows(conn: Any, client_id: str) -> list[dict[str, Any]]:
    sql = f"""
        SELECT
            HOLDING_ID,
            IMPORT_ID,
            CLIENT_ID,
            CLIENT_NAME,
            PAN,
            REPORT_DATE,
            DOWNLOAD_TIMESTAMP,
            SYMBOL_RAW,
            EXCHANGE_CODE,
            SYMBOL_CODE,
            SERIES_CODE,
            QUANTITY,
            BUY_PRICE,
            INVESTED_VALUE,
            CURRENT_VALUE,
            UNREALISED_PNL,
            UNREALISED_PNL_PCT,
            PREVIOUS_CLOSE,
            ISIN,
            SOURCE_FILENAME,
            SOURCE_PATH,
            SOURCE_HASH,
            CREATED_AT,
            UPDATED_AT
        FROM {_table_name(FYERS_HOLDINGS_CURRENT_TABLE)}
        WHERE CLIENT_ID = :client_id
        ORDER BY SYMBOL_CODE
    """
    rows: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        cur.execute(sql, {"client_id": client_id})
        for record in cur.fetchall() or []:
            rows.append(
                {
                    "holdingId": int(record[0]),
                    "importId": int(record[1]) if record[1] is not None else None,
                    "clientId": record[2],
                    "clientName": record[3],
                    "pan": record[4],
                    "reportDate": record[5],
                    "downloadTimestamp": record[6],
                    "symbolRaw": record[7],
                    "exchangeCode": record[8],
                    "symbolCode": record[9],
                    "seriesCode": record[10],
                    "quantity": record[11],
                    "buyPrice": record[12],
                    "investedValue": record[13],
                    "currentValue": record[14],
                    "unrealisedPnl": record[15],
                    "unrealisedPnlPct": record[16],
                    "previousClose": record[17],
                    "isin": record[18],
                    "sourceFilename": record[19],
                    "sourcePath": record[20],
                    "sourceHash": record[21],
                    "createdAt": record[22],
                    "updatedAt": record[23],
                }
            )
    return rows


def _import_row_to_state(
    row: dict[str, Any],
    *,
    holding_id: int | None,
    import_id: int | None,
    metadata: dict[str, Any],
    file_info: dict[str, Any],
) -> dict[str, Any]:
    merged = {
        "holdingId": holding_id,
        "importId": import_id,
        "clientId": metadata.get("clientId"),
        "clientName": metadata.get("clientName"),
        "pan": metadata.get("pan"),
        "reportDate": metadata.get("reportDate"),
        "downloadTimestamp": metadata.get("downloadTimestamp"),
        "sourceFilename": file_info.get("sourceFilename"),
        "sourcePath": file_info.get("sourcePath"),
        "sourceHash": file_info.get("sourceHash"),
    }
    merged.update(row)
    return _row_to_response(merged)


def _insert_import_row(
    conn: Any,
    parsed: dict[str, Any],
    *,
    import_mode: str,
    replace_missing: bool,
    stats: dict[str, Any],
    message: str,
) -> int:
    metadata = parsed["metadata"]
    file_info = parsed["file"]
    sql = f"""
        INSERT INTO {_table_name(FYERS_HOLDINGS_IMPORT_TABLE)} (
            REPORT_TITLE,
            REPORT_DATE,
            CLIENT_NAME,
            CLIENT_ID,
            PAN,
            DOWNLOAD_TIMESTAMP,
            TOTAL_INVESTED,
            TOTAL_CURRENT,
            PROFIT_LOSS,
            UNREALISED_PNL_PCT,
            SOURCE_FILENAME,
            SOURCE_PATH,
            SOURCE_HASH,
            IMPORT_MODE,
            STATUS,
            ROW_COUNT,
            INSERTED_COUNT,
            UPDATED_COUNT,
            DELETED_COUNT,
            UNCHANGED_COUNT,
            ERROR_COUNT,
            MESSAGE,
            CREATED_AT,
            COMPLETED_AT,
            REPLACE_MISSING
        ) VALUES (
            :report_title,
            :report_date,
            :client_name,
            :client_id,
            :pan,
            :download_ts,
            :total_invested,
            :total_current,
            :profit_loss,
            :unrealised_pnl_pct,
            :source_filename,
            :source_path,
            :source_hash,
            :import_mode,
            'COMPLETED',
            :row_count,
            :inserted_count,
            :updated_count,
            :deleted_count,
            :unchanged_count,
            :error_count,
            :message,
            SYSTIMESTAMP,
            SYSTIMESTAMP,
            :replace_missing
        ) RETURNING IMPORT_ID INTO :out_import_id
    """
    with conn.cursor() as cur:
        out_import_id = cur.var(oracledb.NUMBER)
        cur.execute(
            sql,
            {
                "report_title": metadata.get("reportTitle"),
                "report_date": metadata.get("reportDate"),
                "client_name": metadata.get("clientName"),
                "client_id": metadata.get("clientId"),
                "pan": metadata.get("pan"),
                "download_ts": metadata.get("downloadTimestamp"),
                "total_invested": metadata.get("totalInvested"),
                "total_current": metadata.get("totalCurrent"),
                "profit_loss": metadata.get("profitLoss"),
                "unrealised_pnl_pct": metadata.get("unrealisedPnlPct"),
                "source_filename": file_info.get("sourceFilename"),
                "source_path": file_info.get("sourcePath"),
                "source_hash": file_info.get("sourceHash"),
                "import_mode": import_mode,
                "row_count": int(stats.get("rows") or 0),
                "inserted_count": int(stats.get("inserted") or 0),
                "updated_count": int(stats.get("updated") or 0),
                "deleted_count": int(stats.get("deleted") or 0),
                "unchanged_count": int(stats.get("unchanged") or 0),
                "error_count": int(stats.get("errors") or 0),
                "message": message,
                "replace_missing": "Y" if replace_missing else "N",
                "out_import_id": out_import_id,
            },
        )
        value = out_import_id.getvalue()
        if isinstance(value, list):
            value = value[0]
        return int(value)


def _insert_audit_row(
    conn: Any,
    *,
    holding_id: int | None,
    import_id: int | None,
    client_id: str,
    symbol_code: str,
    action_type: str,
    action_source: str,
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
) -> None:
    sql = f"""
        INSERT INTO {_table_name(FYERS_HOLDINGS_AUDIT_TABLE)} (
            HOLDING_ID,
            IMPORT_ID,
            CLIENT_ID,
            SYMBOL_CODE,
            ACTION_TYPE,
            ACTION_SOURCE,
            BEFORE_STATE,
            AFTER_STATE,
            CHANGED_AT
        ) VALUES (
            :holding_id,
            :import_id,
            :client_id,
            :symbol_code,
            :action_type,
            :action_source,
            :before_state,
            :after_state,
            SYSTIMESTAMP
        )
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                "holding_id": holding_id,
                "import_id": import_id,
                "client_id": client_id,
                "symbol_code": symbol_code,
                "action_type": action_type,
                "action_source": action_source,
                "before_state": _serialize_state(before_state),
                "after_state": _serialize_state(after_state),
            },
        )


def _insert_current_row(
    conn: Any,
    row: dict[str, Any],
    *,
    import_id: int | None,
    metadata: dict[str, Any],
    file_info: dict[str, Any],
) -> int:
    sql = f"""
        INSERT INTO {_table_name(FYERS_HOLDINGS_CURRENT_TABLE)} (
            IMPORT_ID,
            CLIENT_ID,
            CLIENT_NAME,
            PAN,
            REPORT_DATE,
            DOWNLOAD_TIMESTAMP,
            SYMBOL_RAW,
            EXCHANGE_CODE,
            SYMBOL_CODE,
            SERIES_CODE,
            QUANTITY,
            BUY_PRICE,
            INVESTED_VALUE,
            CURRENT_VALUE,
            UNREALISED_PNL,
            UNREALISED_PNL_PCT,
            PREVIOUS_CLOSE,
            ISIN,
            SOURCE_FILENAME,
            SOURCE_PATH,
            SOURCE_HASH,
            CREATED_AT,
            UPDATED_AT
        ) VALUES (
            :import_id,
            :client_id,
            :client_name,
            :pan,
            :report_date,
            :download_ts,
            :symbol_raw,
            :exchange_code,
            :symbol_code,
            :series_code,
            :quantity,
            :buy_price,
            :invested_value,
            :current_value,
            :unrealised_pnl,
            :unrealised_pnl_pct,
            :previous_close,
            :isin,
            :source_filename,
            :source_path,
            :source_hash,
            SYSTIMESTAMP,
            SYSTIMESTAMP
        ) RETURNING HOLDING_ID INTO :out_holding_id
    """
    with conn.cursor() as cur:
        out_holding_id = cur.var(oracledb.NUMBER)
        cur.execute(
            sql,
            {
                "import_id": import_id,
                "client_id": metadata.get("clientId"),
                "client_name": metadata.get("clientName"),
                "pan": metadata.get("pan"),
                "report_date": metadata.get("reportDate"),
                "download_ts": metadata.get("downloadTimestamp"),
                "symbol_raw": row.get("symbolRaw"),
                "exchange_code": row.get("exchangeCode"),
                "symbol_code": row.get("symbolCode"),
                "series_code": row.get("seriesCode"),
                "quantity": row.get("quantity"),
                "buy_price": row.get("buyPrice"),
                "invested_value": row.get("investedValue"),
                "current_value": row.get("currentValue"),
                "unrealised_pnl": row.get("unrealisedPnl"),
                "unrealised_pnl_pct": row.get("unrealisedPnlPct"),
                "previous_close": row.get("previousClose"),
                "isin": row.get("isin"),
                "source_filename": file_info.get("sourceFilename"),
                "source_path": file_info.get("sourcePath"),
                "source_hash": file_info.get("sourceHash"),
                "out_holding_id": out_holding_id,
            },
        )
        value = out_holding_id.getvalue()
        if isinstance(value, list):
            value = value[0]
        return int(value)


def _update_current_row(
    conn: Any,
    holding_id: int,
    row: dict[str, Any],
    *,
    import_id: int | None,
    metadata: dict[str, Any],
    file_info: dict[str, Any],
) -> None:
    sql = f"""
        UPDATE {_table_name(FYERS_HOLDINGS_CURRENT_TABLE)}
        SET IMPORT_ID = :import_id,
            CLIENT_NAME = :client_name,
            PAN = :pan,
            REPORT_DATE = :report_date,
            DOWNLOAD_TIMESTAMP = :download_ts,
            SYMBOL_RAW = :symbol_raw,
            EXCHANGE_CODE = :exchange_code,
            SERIES_CODE = :series_code,
            QUANTITY = :quantity,
            BUY_PRICE = :buy_price,
            INVESTED_VALUE = :invested_value,
            CURRENT_VALUE = :current_value,
            UNREALISED_PNL = :unrealised_pnl,
            UNREALISED_PNL_PCT = :unrealised_pnl_pct,
            PREVIOUS_CLOSE = :previous_close,
            ISIN = :isin,
            SOURCE_FILENAME = :source_filename,
            SOURCE_PATH = :source_path,
            SOURCE_HASH = :source_hash,
            UPDATED_AT = SYSTIMESTAMP
        WHERE HOLDING_ID = :holding_id
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                "holding_id": holding_id,
                "import_id": import_id,
                "client_name": metadata.get("clientName"),
                "pan": metadata.get("pan"),
                "report_date": metadata.get("reportDate"),
                "download_ts": metadata.get("downloadTimestamp"),
                "symbol_raw": row.get("symbolRaw"),
                "exchange_code": row.get("exchangeCode"),
                "series_code": row.get("seriesCode"),
                "quantity": row.get("quantity"),
                "buy_price": row.get("buyPrice"),
                "invested_value": row.get("investedValue"),
                "current_value": row.get("currentValue"),
                "unrealised_pnl": row.get("unrealisedPnl"),
                "unrealised_pnl_pct": row.get("unrealisedPnlPct"),
                "previous_close": row.get("previousClose"),
                "isin": row.get("isin"),
                "source_filename": file_info.get("sourceFilename"),
                "source_path": file_info.get("sourcePath"),
                "source_hash": file_info.get("sourceHash"),
            },
        )


def _delete_current_row(conn: Any, holding_id: int) -> None:
    sql = f"DELETE FROM {_table_name(FYERS_HOLDINGS_CURRENT_TABLE)} WHERE HOLDING_ID = :holding_id"
    with conn.cursor() as cur:
        cur.execute(sql, {"holding_id": holding_id})

def _fetch_latest_import_row(conn: Any, client_id: str | None = None) -> dict[str, Any] | None:
    where = ""
    params: dict[str, Any] = {}
    if client_id:
        where = "WHERE CLIENT_ID = :client_id"
        params["client_id"] = client_id
    sql = f"""
        SELECT *
        FROM (
            SELECT
                IMPORT_ID,
                REPORT_TITLE,
                REPORT_DATE,
                CLIENT_NAME,
                CLIENT_ID,
                PAN,
                DOWNLOAD_TIMESTAMP,
                TOTAL_INVESTED,
                TOTAL_CURRENT,
                PROFIT_LOSS,
                UNREALISED_PNL_PCT,
                SOURCE_FILENAME,
                SOURCE_PATH,
                SOURCE_HASH,
                IMPORT_MODE,
                STATUS,
                ROW_COUNT,
                INSERTED_COUNT,
                UPDATED_COUNT,
                DELETED_COUNT,
                UNCHANGED_COUNT,
                ERROR_COUNT,
                MESSAGE,
                CREATED_AT,
                COMPLETED_AT,
                REPLACE_MISSING
            FROM {_table_name(FYERS_HOLDINGS_IMPORT_TABLE)}
            {where}
            ORDER BY CREATED_AT DESC, IMPORT_ID DESC
        )
        WHERE ROWNUM = 1
    """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    if not row:
        return None
    return {
        "importId": int(row[0]),
        "reportTitle": row[1],
        "reportDate": row[2],
        "clientName": row[3],
        "clientId": row[4],
        "pan": row[5],
        "downloadTimestamp": row[6],
        "totalInvested": row[7],
        "totalCurrent": row[8],
        "profitLoss": row[9],
        "unrealisedPnlPct": row[10],
        "sourceFilename": row[11],
        "sourcePath": row[12],
        "sourceHash": row[13],
        "importMode": row[14],
        "status": row[15],
        "rowCount": int(row[16] or 0),
        "insertedCount": int(row[17] or 0),
        "updatedCount": int(row[18] or 0),
        "deletedCount": int(row[19] or 0),
        "unchangedCount": int(row[20] or 0),
        "errorCount": int(row[21] or 0),
        "message": row[22] or "",
        "createdAt": row[23],
        "completedAt": row[24],
        "replaceMissing": str(row[25] or "N").upper() == "Y",
    }


def _resolve_client_id(conn: Any, client_id: str | None) -> str | None:
    if _to_text(client_id):
        return _to_text(client_id)
    latest = _fetch_latest_import_row(conn)
    if latest and latest.get("clientId"):
        return _to_text(latest.get("clientId"))
    sql = f"""
        SELECT CLIENT_ID
        FROM (
            SELECT CLIENT_ID, MAX(UPDATED_AT) AS LAST_TS
            FROM {_table_name(FYERS_HOLDINGS_CURRENT_TABLE)}
            GROUP BY CLIENT_ID
            ORDER BY LAST_TS DESC
        )
        WHERE ROWNUM = 1
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    return _to_text(row[0]) if row and row[0] is not None else None


def _fetch_live_totals(conn: Any, client_id: str) -> dict[str, Any]:
    sql = f"""
        SELECT
            COUNT(*) AS row_count,
            NVL(SUM(INVESTED_VALUE), 0) AS total_invested,
            NVL(SUM(CURRENT_VALUE), 0) AS total_current,
            NVL(SUM(UNREALISED_PNL), 0) AS profit_loss,
            NVL(SUM(CASE WHEN PREVIOUS_CLOSE IS NOT NULL THEN QUANTITY * PREVIOUS_CLOSE ELSE 0 END), 0) AS prior_day_value,
            NVL(SUM(CASE WHEN PREVIOUS_CLOSE IS NOT NULL THEN CURRENT_VALUE - (QUANTITY * PREVIOUS_CLOSE) ELSE 0 END), 0) AS day_pnl,
            SUM(CASE WHEN PREVIOUS_CLOSE IS NOT NULL THEN 1 ELSE 0 END) AS day_row_count
        FROM {_table_name(FYERS_HOLDINGS_CURRENT_TABLE)}
        WHERE CLIENT_ID = :client_id
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"client_id": client_id})
        record = cur.fetchone()
    if not record:
        return {
            "rowCount": 0,
            "totalInvested": 0.0,
            "totalCurrent": 0.0,
            "profitLoss": 0.0,
            "unrealisedPnlPct": None,
            "dayPnl": None,
            "dayPnlPct": None,
        }
    row_count = int(record[0] or 0)
    invested = _safe_decimal(record[1]) or Decimal("0")
    current = _safe_decimal(record[2]) or Decimal("0")
    pnl = _safe_decimal(record[3]) or Decimal("0")
    prior_value = _safe_decimal(record[4]) or Decimal("0")
    day_pnl = _safe_decimal(record[5]) or Decimal("0")
    day_row_count = int(record[6] or 0)
    pnl_pct = (pnl / invested) * Decimal("100") if invested != 0 else None
    day_pnl_pct = (day_pnl / prior_value) * Decimal("100") if prior_value != 0 else None
    return {
        "rowCount": row_count,
        "totalInvested": _decimal_to_json_number(_round_money(invested)),
        "totalCurrent": _decimal_to_json_number(_round_money(current)),
        "profitLoss": _decimal_to_json_number(_round_money(pnl)),
        "unrealisedPnlPct": _decimal_to_json_number(_round_percent(pnl_pct)),
        "dayPnl": _decimal_to_json_number(_round_money(day_pnl)) if day_row_count else None,
        "dayPnlPct": _decimal_to_json_number(_round_percent(day_pnl_pct)) if day_row_count else None,
    }


def import_holdings(payload: dict[str, Any]) -> dict[str, Any]:
    _require_oracledb()
    csv_text, source_filename, source_path = _read_csv_payload(payload)
    try:
        parsed = parse_holdings_csv_text(csv_text, source_filename=source_filename, source_path=source_path)
    except Exception:
        _logger.exception(
            "FYERS holdings parser failed filename=%s sourcePath=%s",
            source_filename or "",
            source_path or "",
        )
        raise
    replace_missing = str(_coalesce(payload.get("replaceMissing"), True)).strip().lower() not in {"0", "false", "no", "off"}

    metadata = parsed["metadata"]
    client_id = _to_text(metadata.get("clientId"))
    if not client_id:
        raise ValueError("Client ID is required in the holdings CSV.")

    with _WRITE_LOCK:
        conn = get_oracle_connection()
        try:
            _ensure_tables_exist(conn)
            _apply_previous_close_priority(conn, parsed["rows"])
            existing_rows = _fetch_current_rows(conn, client_id)
            plan = plan_current_holding_changes(existing_rows, parsed["rows"], replace_missing=replace_missing)
            latest_import = _fetch_latest_import_row(conn, client_id)
            duplicate_import = (
                bool(existing_rows)
                and plan["stats"]["inserted"] == 0
                and plan["stats"]["updated"] == 0
                and plan["stats"]["deleted"] == 0
                and _current_rows_match_import_metadata(existing_rows, metadata, parsed["file"])
            )
            if duplicate_import:
                summary = get_holdings_summary({"clientId": client_id}, connection=conn)
                skipped_stats = {
                    "inserted": 0,
                    "updated": 0,
                    "unchanged": len(parsed["rows"]),
                    "deleted": 0,
                    "errors": 0,
                    "rows": len(parsed["rows"]),
                }
                _logger.info(
                    "FYERS holdings duplicate skipped clientId=%s filename=%s sourceHash=%s",
                    client_id,
                    parsed["file"].get("sourceFilename") or "",
                    parsed["file"].get("sourceHash") or "",
                )
                return {
                    "ok": True,
                    "message": "Already existing data, skipped",
                    "duplicateSkipped": True,
                    "importId": latest_import.get("importId") if latest_import else None,
                    "replaceMissing": replace_missing,
                    "stats": skipped_stats,
                    "stableFieldKeys": parsed["stableFieldKeys"],
                    "stableFields": parsed["stableFields"],
                    "created": [],
                    "updated": [],
                    "deleted": [],
                    "summary": summary.get("summary"),
                    "file": parsed["file"],
                }
            import_id = _insert_import_row(
                conn,
                parsed,
                import_mode="UPLOAD" if source_filename else "PATH",
                replace_missing=replace_missing,
                stats=plan["stats"],
                message="FYERS holdings import completed.",
            )

            created_rows: list[dict[str, Any]] = []
            updated_rows: list[dict[str, Any]] = []
            deleted_rows: list[dict[str, Any]] = []

            for item in plan["insert"]:
                row = item["after"]
                holding_id = _insert_current_row(conn, row, import_id=import_id, metadata=metadata, file_info=parsed["file"])
                after_state = _import_row_to_state(row, holding_id=holding_id, import_id=import_id, metadata=metadata, file_info=parsed["file"])
                _insert_audit_row(
                    conn,
                    holding_id=holding_id,
                    import_id=import_id,
                    client_id=client_id,
                    symbol_code=row["symbolCode"],
                    action_type="INSERT",
                    action_source="IMPORT",
                    before_state=None,
                    after_state=after_state,
                )
                created_rows.append(after_state)

            for item in plan["update"]:
                before_row = item["before"]
                row = item["after"]
                holding_id = int(before_row["holdingId"])
                before_state = _row_to_response(before_row)
                _update_current_row(conn, holding_id, row, import_id=import_id, metadata=metadata, file_info=parsed["file"])
                after_state = get_holding(holding_id, connection=conn)["holding"]
                _insert_audit_row(
                    conn,
                    holding_id=holding_id,
                    import_id=import_id,
                    client_id=client_id,
                    symbol_code=row["symbolCode"],
                    action_type="UPDATE",
                    action_source="IMPORT",
                    before_state=before_state,
                    after_state=after_state,
                )
                updated_rows.append(after_state)

            for item in plan["unchanged"]:
                before_row = item["before"]
                row = item["after"]
                _update_current_row(conn, int(before_row["holdingId"]), row, import_id=import_id, metadata=metadata, file_info=parsed["file"])

            for item in plan["delete"]:
                before_row = item["before"]
                before_state = _row_to_response(before_row)
                _insert_audit_row(
                    conn,
                    holding_id=int(before_row["holdingId"]),
                    import_id=import_id,
                    client_id=client_id,
                    symbol_code=_to_text(before_row.get("symbolCode")),
                    action_type="DELETE",
                    action_source="IMPORT",
                    before_state=before_state,
                    after_state=None,
                )
                _delete_current_row(conn, int(before_row["holdingId"]))
                deleted_rows.append(before_state)

            conn.commit()
            summary = get_holdings_summary({"clientId": client_id}, connection=conn)
            _logger.info(
                "FYERS holdings import clientId=%s importId=%s rows=%s inserted=%s updated=%s unchanged=%s deleted=%s",
                client_id,
                import_id,
                plan["stats"]["rows"],
                plan["stats"]["inserted"],
                plan["stats"]["updated"],
                plan["stats"]["unchanged"],
                plan["stats"]["deleted"],
            )
            _invalidate_list_cache()
            return {
                "ok": True,
                "message": "FYERS holdings import completed.",
                "importId": import_id,
                "replaceMissing": replace_missing,
                "stats": plan["stats"],
                "stableFieldKeys": parsed["stableFieldKeys"],
                "stableFields": parsed["stableFields"],
                "created": created_rows,
                "updated": updated_rows,
                "deleted": deleted_rows,
                "summary": summary.get("summary"),
                "file": parsed["file"],
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def list_holdings(payload: dict[str, Any] | None = None, *, connection: Any | None = None) -> dict[str, Any]:
    _require_oracledb()
    api_start = time.perf_counter()
    payload = payload or {}
    own_conn = connection is None
    conn = connection or get_oracle_connection()
    try:
        _ensure_tables_exist(conn)
        client_id = _resolve_client_id(conn, _coalesce(payload.get("clientId"), payload.get("client_id")))
        if not client_id:
            return {"ok": True, "clientId": "", "holdings": [], "count": 0}
        symbol_query = _to_text(_coalesce(payload.get("symbol"), payload.get("q"))).upper()
        cache_key = _cache_key_for_list(client_id, symbol_query) if own_conn else ""
        if cache_key:
            cached = _get_cached_list(cache_key)
            if cached is not None:
                duration_ms = round((time.perf_counter() - api_start) * 1000, 2)
                _logger.info(
                    "FYERS holdings list cache=HIT clientId=%s count=%s responseMs=%s",
                    client_id,
                    cached.get("count", 0),
                    duration_ms,
                )
                return cached
        params: dict[str, Any] = {"client_id": client_id}
        sql = f"""
            SELECT
                HOLDING_ID,
                IMPORT_ID,
                CLIENT_ID,
                CLIENT_NAME,
                PAN,
                REPORT_DATE,
                DOWNLOAD_TIMESTAMP,
                SYMBOL_RAW,
                EXCHANGE_CODE,
                SYMBOL_CODE,
                SERIES_CODE,
                QUANTITY,
                BUY_PRICE,
                INVESTED_VALUE,
                CURRENT_VALUE,
                UNREALISED_PNL,
                UNREALISED_PNL_PCT,
                PREVIOUS_CLOSE,
                ISIN,
                SOURCE_FILENAME,
                SOURCE_PATH,
                SOURCE_HASH,
                CREATED_AT,
                UPDATED_AT
            FROM {_table_name(FYERS_HOLDINGS_CURRENT_TABLE)}
            WHERE CLIENT_ID = :client_id
        """
        if symbol_query:
            sql += " AND (UPPER(SYMBOL_CODE) LIKE :symbol_like OR UPPER(SYMBOL_RAW) LIKE :symbol_like)"
            params["symbol_like"] = f"%{symbol_query}%"
        sql += " ORDER BY CURRENT_VALUE DESC NULLS LAST, SYMBOL_CODE"

        rows: list[dict[str, Any]] = []
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for record in cur.fetchall() or []:
                rows.append(
                    _row_to_response(
                        {
                            "holdingId": int(record[0]),
                            "importId": int(record[1]) if record[1] is not None else None,
                            "clientId": record[2],
                            "clientName": record[3],
                            "pan": record[4],
                            "reportDate": record[5],
                            "downloadTimestamp": record[6],
                            "symbolRaw": record[7],
                            "exchangeCode": record[8],
                            "symbolCode": record[9],
                            "seriesCode": record[10],
                            "quantity": record[11],
                            "buyPrice": record[12],
                            "investedValue": record[13],
                            "currentValue": record[14],
                            "unrealisedPnl": record[15],
                            "unrealisedPnlPct": record[16],
                            "previousClose": record[17],
                            "isin": record[18],
                            "sourceFilename": record[19],
                            "sourcePath": record[20],
                            "sourceHash": record[21],
                            "createdAt": record[22],
                            "updatedAt": record[23],
                        }
                    )
                )
        ema_matches, csv_matches, missing_prev = _apply_previous_close_priority(conn, rows, include_live_quotes=True)
        apply_recalculated_holding_values(rows)
        buy_missing = sum(1 for row in rows if _to_number(row.get("buyPrice")) is None)
        response = {"ok": True, "clientId": client_id, "count": len(rows), "holdings": rows}
        if cache_key:
            _set_cached_list(cache_key, response)
        duration_ms = round((time.perf_counter() - api_start) * 1000, 2)
        _logger.info(
            "FYERS holdings list cache=MISS clientId=%s holdings=%s emaMatched=%s csvMatched=%s missingPrev=%s missingBuy=%s responseMs=%s",
            client_id,
            len(rows),
            ema_matches,
            csv_matches,
            missing_prev,
            buy_missing,
            duration_ms,
        )
        return response
    finally:
        if own_conn:
            conn.close()


def get_holding(holding_id: int, *, connection: Any | None = None) -> dict[str, Any]:
    _require_oracledb()
    own_conn = connection is None
    conn = connection or get_oracle_connection()
    try:
        _ensure_tables_exist(conn)
        sql = f"""
            SELECT
                HOLDING_ID,
                IMPORT_ID,
                CLIENT_ID,
                CLIENT_NAME,
                PAN,
                REPORT_DATE,
                DOWNLOAD_TIMESTAMP,
                SYMBOL_RAW,
                EXCHANGE_CODE,
                SYMBOL_CODE,
                SERIES_CODE,
                QUANTITY,
                BUY_PRICE,
                INVESTED_VALUE,
                CURRENT_VALUE,
                UNREALISED_PNL,
                UNREALISED_PNL_PCT,
                PREVIOUS_CLOSE,
                ISIN,
                SOURCE_FILENAME,
                SOURCE_PATH,
                SOURCE_HASH,
                CREATED_AT,
                UPDATED_AT
            FROM {_table_name(FYERS_HOLDINGS_CURRENT_TABLE)}
            WHERE HOLDING_ID = :holding_id
        """
        with conn.cursor() as cur:
            cur.execute(sql, {"holding_id": int(holding_id)})
            row = cur.fetchone()
        if not row:
            raise ValueError(f"Holding {holding_id} was not found.")
        holding = _row_to_response(
            {
                "holdingId": int(row[0]),
                "importId": int(row[1]) if row[1] is not None else None,
                "clientId": row[2],
                "clientName": row[3],
                "pan": row[4],
                "reportDate": row[5],
                "downloadTimestamp": row[6],
                "symbolRaw": row[7],
                "exchangeCode": row[8],
                "symbolCode": row[9],
                "seriesCode": row[10],
                "quantity": row[11],
                "buyPrice": row[12],
                "investedValue": row[13],
                "currentValue": row[14],
                "unrealisedPnl": row[15],
                "unrealisedPnlPct": row[16],
                "previousClose": row[17],
                "isin": row[18],
                "sourceFilename": row[19],
                "sourcePath": row[20],
                "sourceHash": row[21],
                "createdAt": row[22],
                "updatedAt": row[23],
            }
        )
        _apply_previous_close_priority(conn, [holding], include_live_quotes=True)
        apply_recalculated_holding_values([holding])
        return {
            "ok": True,
            "holding": holding,
        }
    finally:
        if own_conn:
            conn.close()


def get_holdings_summary(payload: dict[str, Any] | None = None, *, connection: Any | None = None) -> dict[str, Any]:
    _require_oracledb()
    payload = payload or {}
    own_conn = connection is None
    conn = connection or get_oracle_connection()
    try:
        _ensure_tables_exist(conn)
        client_id = _resolve_client_id(conn, _coalesce(payload.get("clientId"), payload.get("client_id")))
        if not client_id:
            return {"ok": True, "summary": None}
        latest_import = _fetch_latest_import_row(conn, client_id)
        live_totals = _fetch_live_totals(conn, client_id)
        if latest_import is None:
            return {
                "ok": True,
                "summary": {
                    "clientId": client_id,
                    "stableFieldKeys": list(STATIC_REPORT_FIELDS),
                    "stableFields": [],
                    "liveTotals": live_totals,
                },
            }
        summary = {
            key: (
                _iso_datetime(value)
                if isinstance(value, datetime)
                else _iso_date(value)
                if isinstance(value, date)
                else _to_number(value)
                if isinstance(value, Decimal)
                else value
            )
            for key, value in latest_import.items()
        }
        summary["stableFieldKeys"] = list(STATIC_REPORT_FIELDS)
        summary["stableFields"] = _stable_fields_from_metadata(latest_import)
        summary["liveTotals"] = live_totals
        _apply_authoritative_totals_to_summary(summary, live_totals=live_totals)
        return {"ok": True, "summary": summary}
    finally:
        if own_conn:
            conn.close()


def reconcile_holdings(payload: dict[str, Any] | None = None, *, connection: Any | None = None) -> dict[str, Any]:
    _require_oracledb()
    payload = payload or {}
    own_conn = connection is None
    conn = connection or get_oracle_connection()
    try:
        _ensure_tables_exist(conn)
        client_id = _resolve_client_id(conn, _coalesce(payload.get("clientId"), payload.get("client_id")))
        if not client_id:
            return {
                "ok": True,
                "clientId": "",
                "generatedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "summary": {
                    "totalSymbolsChecked": 0,
                    "matchedSymbolsCount": 0,
                    "mismatchedSymbolsCount": 0,
                    "missingLtpCount": 0,
                    "missingPreviousCloseCount": 0,
                    "stalePriceCount": 0,
                    "totalInvestedValue": 0,
                    "totalCurrentValue": 0,
                    "totalPnl": 0,
                    "totalPnlPercent": None,
                    "todayPnl": None,
                    "todayPnlPercent": None,
                },
                "rows": [],
            }
        symbol_query = _to_text(_coalesce(payload.get("symbol"), payload.get("q"))).upper()
        rows = [_row_to_response(row) for row in _fetch_current_rows(conn, client_id)]
        if symbol_query:
            rows = [
                row
                for row in rows
                if symbol_query in _to_text(row.get("symbolCode")).upper()
                or symbol_query in _to_text(row.get("symbolRaw")).upper()
            ]
        _apply_previous_close_priority(conn, rows, include_live_quotes=True)
        apply_recalculated_holding_values(rows)

        report_rows: list[dict[str, Any]] = []
        total_invested = Decimal("0")
        total_current = Decimal("0")
        total_pnl = Decimal("0")
        total_day_pnl = Decimal("0")
        prior_day_value = Decimal("0")
        day_rows = 0
        missing_previous_close = 0
        missing_ltp = 0
        stale_price_count = 0
        for index, row in enumerate(rows, start=1):
            item = recalculate_holding_pnl(row)
            item["serialNumber"] = index
            report_rows.append(item)
            total_invested += _safe_decimal(item.get("investedValueRecalculated")) or Decimal("0")
            total_current += _safe_decimal(item.get("currentValueRecalculated")) or Decimal("0")
            total_pnl += _safe_decimal(item.get("totalPnlRecalculated")) or Decimal("0")
            day_pnl = _safe_decimal(item.get("dayPnlRecalculated"))
            if day_pnl is not None:
                total_day_pnl += day_pnl
                day_rows += 1
            qty = _safe_decimal(item.get("qty"))
            previous_close = _safe_decimal(item.get("previousClose"))
            if previous_close is None:
                missing_previous_close += 1
            elif qty is not None:
                prior_day_value += qty * previous_close
            if item.get("ltp") is None:
                missing_ltp += 1
            if item.get("status") == "STALE_PRICE":
                stale_price_count += 1

        total_pnl_pct = (total_pnl / total_invested) * Decimal("100") if total_invested != 0 else None
        today_pnl_pct = (total_day_pnl / prior_day_value) * Decimal("100") if prior_day_value != 0 else None
        summary = {
            "totalSymbolsChecked": len(report_rows),
            "matchedSymbolsCount": sum(1 for item in report_rows if item.get("status") == "MATCHED"),
            "mismatchedSymbolsCount": sum(1 for item in report_rows if item.get("status") == "MISMATCH"),
            "roundingOnlyDiffCount": sum(1 for item in report_rows if item.get("status") == "ROUNDING_ONLY_DIFF"),
            "missingLtpCount": missing_ltp,
            "missingPreviousCloseCount": missing_previous_close,
            "stalePriceCount": stale_price_count,
            "totalInvestedValue": _decimal_to_json_number(_round_money(total_invested)),
            "totalCurrentValue": _decimal_to_json_number(_round_money(total_current)),
            "totalPnl": _decimal_to_json_number(_round_money(total_pnl)),
            "totalPnlPercent": _decimal_to_json_number(_round_percent(total_pnl_pct)),
            "todayPnl": _decimal_to_json_number(_round_money(total_day_pnl)) if day_rows else None,
            "todayPnlPercent": _decimal_to_json_number(_round_percent(today_pnl_pct)) if day_rows else None,
        }
        return {
            "ok": True,
            "clientId": client_id,
            "generatedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "summary": summary,
            "rows": report_rows,
        }
    finally:
        if own_conn:
            conn.close()


def list_import_runs(payload: dict[str, Any] | None = None, *, connection: Any | None = None) -> dict[str, Any]:
    _require_oracledb()
    payload = payload or {}
    own_conn = connection is None
    conn = connection or get_oracle_connection()
    try:
        _ensure_tables_exist(conn)
        client_id = _to_text(_coalesce(payload.get("clientId"), payload.get("client_id")))
        limit = int(_coalesce(payload.get("limit"), 10) or 10)
        params: dict[str, Any] = {"limit_rows": max(1, min(limit, 100))}
        where = ""
        if client_id:
            where = "WHERE CLIENT_ID = :client_id"
            params["client_id"] = client_id
        sql = f"""
            SELECT *
            FROM (
                SELECT
                    IMPORT_ID,
                    REPORT_TITLE,
                    REPORT_DATE,
                    CLIENT_NAME,
                    CLIENT_ID,
                    PAN,
                    DOWNLOAD_TIMESTAMP,
                    TOTAL_INVESTED,
                    TOTAL_CURRENT,
                    PROFIT_LOSS,
                    UNREALISED_PNL_PCT,
                    SOURCE_FILENAME,
                    SOURCE_PATH,
                    SOURCE_HASH,
                    IMPORT_MODE,
                    STATUS,
                    ROW_COUNT,
                    INSERTED_COUNT,
                    UPDATED_COUNT,
                    DELETED_COUNT,
                    UNCHANGED_COUNT,
                    ERROR_COUNT,
                    MESSAGE,
                    CREATED_AT,
                    COMPLETED_AT,
                    REPLACE_MISSING
                FROM {_table_name(FYERS_HOLDINGS_IMPORT_TABLE)}
                {where}
                ORDER BY CREATED_AT DESC, IMPORT_ID DESC
            )
            WHERE ROWNUM <= :limit_rows
        """
        items: list[dict[str, Any]] = []
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall() or []:
                items.append(
                    {
                        "importId": int(row[0]),
                        "reportTitle": row[1],
                        "reportDate": _iso_date(row[2]),
                        "clientName": row[3],
                        "clientId": row[4],
                        "pan": row[5],
                        "downloadTimestamp": _iso_datetime(row[6]),
                        "totalInvested": _to_number(row[7]),
                        "totalCurrent": _to_number(row[8]),
                        "profitLoss": _to_number(row[9]),
                        "unrealisedPnlPct": _to_number(row[10]),
                        "sourceFilename": row[11] or "",
                        "sourcePath": row[12] or "",
                        "sourceHash": row[13] or "",
                        "importMode": row[14],
                        "status": row[15],
                        "rowCount": int(row[16] or 0),
                        "insertedCount": int(row[17] or 0),
                        "updatedCount": int(row[18] or 0),
                        "deletedCount": int(row[19] or 0),
                        "unchangedCount": int(row[20] or 0),
                        "errorCount": int(row[21] or 0),
                        "message": row[22] or "",
                        "createdAt": _iso_datetime(row[23]),
                        "completedAt": _iso_datetime(row[24]),
                        "replaceMissing": str(row[25] or "N").upper() == "Y",
                    }
                )
        return {"ok": True, "imports": items, "count": len(items)}
    finally:
        if own_conn:
            conn.close()

def _manual_row_from_payload(payload: dict[str, Any], latest_summary: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    symbol_value = _coalesce(payload.get("symbolRaw"), payload.get("symbol"))
    symbol_raw, exchange_code, symbol_code, series_code = _split_symbol(symbol_value)
    client_id = _to_text(_coalesce(payload.get("clientId"), latest_summary.get("clientId") if latest_summary else None))
    if not client_id:
        raise ValueError("Client ID is required to create or edit a holding.")

    metadata = {
        "clientId": client_id,
        "clientName": _to_text(_coalesce(payload.get("clientName"), latest_summary.get("clientName") if latest_summary else None)),
        "pan": _to_text(_coalesce(payload.get("pan"), latest_summary.get("pan") if latest_summary else None)),
        "reportDate": _parse_report_date(_coalesce(payload.get("reportDate"), latest_summary.get("reportDate") if latest_summary else None))
        if _coalesce(payload.get("reportDate"), latest_summary.get("reportDate") if latest_summary else None)
        else date.today(),
        "downloadTimestamp": _parse_timestamp(_coalesce(payload.get("downloadTimestamp"), latest_summary.get("downloadTimestamp") if latest_summary else None))
        if _coalesce(payload.get("downloadTimestamp"), latest_summary.get("downloadTimestamp") if latest_summary else None)
        else datetime.now(),
    }
    file_info = {
        "sourceFilename": _to_text(_coalesce(payload.get("sourceFilename"), latest_summary.get("sourceFilename") if latest_summary else None)),
        "sourcePath": _to_text(_coalesce(payload.get("sourcePath"), latest_summary.get("sourcePath") if latest_summary else None)),
        "sourceHash": _to_text(_coalesce(payload.get("sourceHash"), latest_summary.get("sourceHash") if latest_summary else None)),
    }
    row = {
        "symbolRaw": symbol_raw,
        "exchangeCode": exchange_code,
        "symbolCode": symbol_code,
        "seriesCode": series_code,
        "quantity": _decimal_or_none(payload.get("quantity")),
        "buyPrice": _decimal_or_none(payload.get("buyPrice")),
        "investedValue": _decimal_or_none(payload.get("investedValue")),
        "currentValue": _decimal_or_none(payload.get("currentValue")),
        "unrealisedPnl": _decimal_or_none(payload.get("unrealisedPnl")),
        "unrealisedPnlPct": _decimal_or_none(payload.get("unrealisedPnlPct")),
        "previousClose": _decimal_or_none(payload.get("previousClose")),
        "isin": _to_text(payload.get("isin")),
    }
    if row["quantity"] is None:
        raise ValueError("Quantity is required.")
    return row, metadata, file_info


def create_holding(payload: dict[str, Any]) -> dict[str, Any]:
    _require_oracledb()
    with _WRITE_LOCK:
        conn = get_oracle_connection()
        try:
            _ensure_tables_exist(conn)
            latest_summary = get_holdings_summary({"clientId": payload.get("clientId")}, connection=conn).get("summary") or {}
            row, metadata, file_info = _manual_row_from_payload(payload, latest_summary)
            existing_rows = _fetch_current_rows(conn, metadata["clientId"])
            if row["symbolCode"] in {_current_row_key(item) for item in existing_rows}:
                raise ValueError(f"Holding {row['symbolCode']} already exists for client {metadata['clientId']}.")
            holding_id = _insert_current_row(conn, row, import_id=None, metadata=metadata, file_info=file_info)
            holding = _import_row_to_state(row, holding_id=holding_id, import_id=None, metadata=metadata, file_info=file_info)
            _insert_audit_row(
                conn,
                holding_id=holding_id,
                import_id=None,
                client_id=metadata["clientId"],
                symbol_code=row["symbolCode"],
                action_type="INSERT",
                action_source="MANUAL",
                before_state=None,
                after_state=holding,
            )
            conn.commit()
            _invalidate_list_cache()
            return {"ok": True, "message": "Holding created.", "holding": holding}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def update_holding(holding_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    _require_oracledb()
    with _WRITE_LOCK:
        conn = get_oracle_connection()
        try:
            _ensure_tables_exist(conn)
            existing = get_holding(holding_id, connection=conn)["holding"]
            latest_summary = get_holdings_summary({"clientId": existing.get("clientId")}, connection=conn).get("summary") or {}
            raw_payload = payload or {}
            merged_payload = {**existing, **raw_payload, "clientId": _coalesce(raw_payload.get("clientId"), existing.get("clientId"))}
            merged_payload["symbol"] = existing.get("symbolRaw")
            merged_payload["symbolRaw"] = existing.get("symbolRaw")
            merged_payload["isin"] = existing.get("isin")
            merged_payload["clientId"] = existing.get("clientId")
            merged_payload["clientName"] = existing.get("clientName")
            merged_payload["pan"] = existing.get("pan")
            merged_payload["downloadTimestamp"] = existing.get("downloadTimestamp")
            row, metadata, file_info = _manual_row_from_payload(merged_payload, latest_summary)
            other_rows = [item for item in _fetch_current_rows(conn, metadata["clientId"]) if int(item["holdingId"]) != int(holding_id)]
            if row["symbolCode"] in {_current_row_key(item) for item in other_rows}:
                raise ValueError(f"Holding {row['symbolCode']} already exists for client {metadata['clientId']}.")
            _update_current_row(conn, int(holding_id), row, import_id=None, metadata=metadata, file_info=file_info)
            updated = get_holding(int(holding_id), connection=conn)["holding"]
            _insert_audit_row(
                conn,
                holding_id=int(holding_id),
                import_id=None,
                client_id=metadata["clientId"],
                symbol_code=row["symbolCode"],
                action_type="UPDATE",
                action_source="MANUAL",
                before_state=existing,
                after_state=updated,
            )
            conn.commit()
            _invalidate_list_cache()
            return {"ok": True, "message": "Holding updated.", "holding": updated}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def delete_holding(holding_id: int) -> dict[str, Any]:
    _require_oracledb()
    with _WRITE_LOCK:
        conn = get_oracle_connection()
        try:
            _ensure_tables_exist(conn)
            existing = get_holding(holding_id, connection=conn)["holding"]
            _insert_audit_row(
                conn,
                holding_id=int(holding_id),
                import_id=existing.get("importId"),
                client_id=_to_text(existing.get("clientId")),
                symbol_code=_to_text(existing.get("symbolCode")),
                action_type="DELETE",
                action_source="MANUAL",
                before_state=existing,
                after_state=None,
            )
            _delete_current_row(conn, int(holding_id))
            conn.commit()
            _invalidate_list_cache()
            return {"ok": True, "message": "Holding deleted.", "holding": existing}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


