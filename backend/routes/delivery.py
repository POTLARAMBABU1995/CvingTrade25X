from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from flask import Blueprint, g, jsonify, request

from services.delivery_service import fetch_delivery_page
from .request_validators import parse_int, parse_sort_dir, parse_sort_key
from services import nse_mcap_service as nse_mcap_svc


bp = Blueprint("delivery", __name__)
_logger = logging.getLogger(__name__)


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().lower()
    if token in {"1", "true", "yes", "y", "on"}:
        return True
    if token in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _parse_date(value: Optional[str], field_name: str = "date") -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except Exception:
            continue
    raise ValueError(f"{field_name} must be in YYYY-MM-DD format.")


def _parse_int(value: object, default: Optional[int] = None) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return int(text)
    except Exception:
        raise ValueError(f"Invalid integer value: {value}")


def _parse_float(value: object, default: Optional[float] = None) -> Optional[float]:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        raise ValueError(f"Invalid decimal value: {value}")


@bp.get("/api/technicals/delivery")
def api_delivery():
    try:
        symbol = (request.args.get("symbol") or "").strip() or None
        trading_date = _parse_date(request.args.get("trading_date"), "trading_date")
        start_date = _parse_date(request.args.get("start_date"), "start_date")
        end_date = _parse_date(request.args.get("end_date"), "end_date")
        if start_date and end_date and start_date > end_date:
            raise ValueError("start_date must be on or before end_date.")
        td = _parse_int(request.args.get("td"), None)
        min_delivery_pct = _parse_float(request.args.get("min_delivery_pct"), None)
        delivery_pct_eq_100 = _as_bool(request.args.get("delivery_pct_eq_100"), False)
        min_delivery_score = _parse_float(request.args.get("min_delivery_score"), None)
        latest_only = _as_bool(request.args.get("latest_only"), True)
        strong_only = _as_bool(request.args.get("strong_only"), False)
        delivery_status = (request.args.get("delivery_status") or "").strip() or None
        page = parse_int(request.args.get("page"), 1, min_value=1, max_value=10000, field="page")
        page_size = parse_int(request.args.get("page_size"), 25, min_value=1, max_value=200, field="page_size")
        sort_by_raw = (request.args.get("sort_by") or "").strip()
        sort_by = parse_sort_key(
            sort_by_raw,
            default="TRADING_DATE",
            allowed={
                "SYMBOL",
                "PRICE",
                "TRADING_DATE",
                "LTC_DATE",
                "T_D",
                "DELIVERY_QTY",
                "DELIVERY_PCT",
                "DELIVERY_SCORE",
                "DELIVERY_STATUS",
            },
            field="sort_by",
        ) if sort_by_raw else None
        sort_dir = parse_sort_dir(request.args.get("sort_dir"), default="DESC", field="sort_dir")

        payload = fetch_delivery_page(
            symbol=symbol,
            trading_date=trading_date,
            start_date=start_date,
            end_date=end_date,
            td=td,
            min_delivery_pct=min_delivery_pct,
            delivery_pct_eq_100=delivery_pct_eq_100,
            min_delivery_score=min_delivery_score,
            latest_only=latest_only,
            strong_only=strong_only,
            delivery_status=delivery_status,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
            request_id=getattr(g, "request_id", ""),
        )
        return jsonify(nse_mcap_svc.enrich_payload_marketcap_index(payload, row_keys=("data",)))
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        _logger.exception("Delivery API failed")
        return jsonify({"status": "error", "message": "Failed to load delivery data."}), 500
