from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Any

from flask import Blueprint, jsonify, request

try:
    from ..db_pool import pool
except ImportError:  # pragma: no cover
    from db_pool import pool  # type: ignore

bp = Blueprint("corporate_actions", __name__, url_prefix="/api/corporate-actions")
_logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 500
_MAX_LIMIT = 5000
_DEFAULT_MIN_DROP = 50.0


def _parse_date(value: object, field: str) -> dt.date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.strptime(text[:10], "%Y-%m-%d").date()
    except Exception as exc:
        raise ValueError(f"{field} must be in YYYY-MM-DD format") from exc


def _parse_limit(value: object) -> int:
    text = str(value or "").strip()
    if not text:
        return _DEFAULT_LIMIT
    try:
        parsed = int(text)
    except Exception as exc:
        raise ValueError("limit must be an integer") from exc
    if parsed < 1:
        raise ValueError("limit must be >= 1")
    return min(parsed, _MAX_LIMIT)


def _parse_min_drop_pct(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return _DEFAULT_MIN_DROP
    try:
        parsed = float(text)
    except Exception as exc:
        raise ValueError("min_drop_pct must be numeric") from exc
    if parsed < 0 or parsed > 100:
        raise ValueError("min_drop_pct must be between 0 and 100")
    return parsed


def _json_scalar(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return value


def _clean_symbol_query(value: object) -> str:
    return str(value or "").strip().upper()


def _normalize_symbols(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("symbols must be a list")
    symbols: list[str] = []
    seen: set[str] = set()
    for item in value:
        symbol = str(item or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        symbols.append(symbol)
        seen.add(symbol)
    if not symbols:
        raise ValueError("symbols is required")
    if len(symbols) > 500:
        raise ValueError("symbols limit is 500")
    return symbols


def _in_clause(prefix: str, values: list[str]) -> tuple[str, dict[str, str]]:
    placeholders: list[str] = []
    binds: dict[str, str] = {}
    for index, value in enumerate(values):
        key = f"{prefix}_{index}"
        placeholders.append(f":{key}")
        binds[key] = value
    return ", ".join(placeholders), binds


@bp.route("/split-bonus-candidates", methods=["GET"])
def split_bonus_candidates():
    q = _clean_symbol_query(request.args.get("q"))
    min_drop_pct_raw = request.args.get("min_drop_pct")
    from_date_raw = request.args.get("from_date")
    to_date_raw = request.args.get("to_date")
    limit_raw = request.args.get("limit")

    try:
        min_drop_pct = _parse_min_drop_pct(min_drop_pct_raw)
        from_date = _parse_date(from_date_raw, "from_date")
        to_date = _parse_date(to_date_raw, "to_date")
        if from_date and to_date and from_date > to_date:
            raise ValueError("from_date must be on or before to_date")
        limit = _parse_limit(limit_raw)

        q_bind = f"%{q}%" if q else None
        sql = """
            SELECT
                SYMBOL,
                TO_CHAR(PREV_TRADING_DATE, 'YYYY-MM-DD') AS PREV_TRADING_DATE,
                TO_CHAR(TRADING_DATE, 'YYYY-MM-DD') AS TRADING_DATE,
                PREV_PRICE,
                PRICE,
                DROP_PCT,
                ACTUAL_FACTOR,
                POSSIBLE_ACTIONS,
                EXPECTED_DROP_PCT,
                CONFIDENCE_SCORE,
                DETECTION_BUCKET
            FROM (
                SELECT
                    SYMBOL,
                    PREV_TRADING_DATE,
                    TRADING_DATE,
                    PREV_PRICE,
                    PRICE,
                    DROP_PCT,
                    ACTUAL_FACTOR,
                    POSSIBLE_ACTIONS,
                    EXPECTED_DROP_PCT,
                    CONFIDENCE_SCORE,
                    DETECTION_BUCKET
                FROM V_CORP_ACTION_CANDIDATES
                WHERE DROP_PCT >= :min_drop_pct
                  AND (:q_bind IS NULL OR UPPER(SYMBOL) LIKE :q_bind)
                  AND (:from_date IS NULL OR TRADING_DATE >= :from_date)
                  AND (:to_date IS NULL OR TRADING_DATE <= :to_date)
                ORDER BY TRADING_DATE DESC, DROP_PCT DESC, SYMBOL ASC
            )
            WHERE ROWNUM <= :limit_rows
        """

        payload_rows: list[dict[str, Any]] = []
        with pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    {
                        "min_drop_pct": min_drop_pct,
                        "q_bind": q_bind,
                        "from_date": from_date,
                        "to_date": to_date,
                        "limit_rows": limit,
                    },
                )
                columns = [str(col[0]).lower() for col in (cur.description or [])]
                for row in cur.fetchall():
                    item = {columns[idx]: _json_scalar(row[idx]) for idx in range(len(columns))}
                    payload_rows.append(
                        {
                            "symbol": item.get("symbol"),
                            "prev_trading_date": item.get("prev_trading_date"),
                            "trading_date": item.get("trading_date"),
                            "prev_price": item.get("prev_price"),
                            "price": item.get("price"),
                            "drop_pct": item.get("drop_pct"),
                            "actual_factor": item.get("actual_factor"),
                            "possible_actions": item.get("possible_actions"),
                            "expected_drop_pct": item.get("expected_drop_pct"),
                            "confidence_score": item.get("confidence_score"),
                            "detection_bucket": item.get("detection_bucket"),
                        }
                    )

        return jsonify(
            {
                "success": True,
                "count": len(payload_rows),
                "data": payload_rows,
                "filters": {
                    "q": q,
                    "min_drop_pct": min_drop_pct,
                    "from_date": from_date.isoformat() if from_date else "",
                    "to_date": to_date.isoformat() if to_date else "",
                    "limit": limit,
                },
            }
        )
    except ValueError as exc:
        return (
            jsonify(
                {
                    "success": False,
                    "message": str(exc),
                }
            ),
            400,
        )
    except Exception as exc:  # pragma: no cover
        _logger.exception("Failed to load split/bonus candidates")
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Failed to load split/bonus candidates",
                    "error": str(exc),
                }
            ),
            500,
        )


@bp.route("/split-bonus-candidates/delete-symbols", methods=["POST"])
def delete_split_bonus_candidate_symbols():
    payload = request.get_json(silent=True) or {}
    try:
        confirm_text = str(payload.get("confirm_text") or "").strip()
        if confirm_text != "DELETE":
            raise ValueError("Delete confirmation failed")

        symbols = _normalize_symbols(payload.get("symbols") or [])
        in_sql, binds = _in_clause("sym", symbols)
        where_sql = f"UPPER(TRIM(SYMBOL)) IN ({in_sql})"
        count_sql = f"SELECT COUNT(*) AS MATCHED_ROWS FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV WHERE {where_sql}"
        delete_sql = f"DELETE FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV WHERE {where_sql}"

        matched_rows = 0
        deleted_rows = 0
        conn = None
        try:
            with pool.acquire() as conn:
                with conn.cursor() as cur:
                    cur.execute(count_sql, binds)
                    matched_rows = int((cur.fetchone() or [0])[0] or 0)
                    if matched_rows > 0:
                        cur.execute(delete_sql, binds)
                        deleted_rows = int(cur.rowcount or 0)
                conn.commit()
        except Exception:
            if conn is not None and hasattr(conn, "rollback"):
                try:
                    conn.rollback()
                except Exception:
                    _logger.exception("[CORPORATE_ACTIONS][ERROR] rollback failed symbols=%s", ",".join(symbols))
            raise

        _logger.info(
            "[CORPORATE_ACTIONS][DELETE] symbols=%s matched_rows=%s deleted_rows=%s",
            ",".join(symbols),
            matched_rows,
            deleted_rows,
        )
        return jsonify(
            {
                "success": True,
                "ok": True,
                "source_table": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
                "symbols": symbols,
                "deleted_symbols": len(symbols),
                "deletedSymbols": len(symbols),
                "matched_rows": matched_rows,
                "matchedRows": matched_rows,
                "deleted_rows": deleted_rows,
                "deletedRows": deleted_rows,
                "message": "Delete completed successfully",
            }
        )
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        _logger.exception("Failed to delete split/bonus candidate symbols")
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Failed to delete split/bonus candidate symbols",
                    "error": str(exc),
                }
            ),
            500,
        )
