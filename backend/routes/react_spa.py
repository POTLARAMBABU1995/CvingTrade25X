from __future__ import annotations

from pathlib import Path
from typing import Iterable

from flask import Flask, Response, jsonify, send_from_directory


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = REPO_ROOT / "frontend" / "dist"

MIGRATED_REACT_ROUTES = {
    "app/home",
    "home",
    "index",
    "login",
    "register",
    "app/dashboard",
    "dashboard",
    "portfolio",
    "trendindicator",
    "app/technical/ema",
    "technical/ema",
    "ema",
    "app/technical/rsi50",
    "technical/rsi50",
    "rsi50",
    "app/technical/macd",
    "technical/macd",
    "macd",
    "app/technical/atr14",
    "technical/atr14",
    "atr14",
    "app/technical/adx",
    "technical/adx",
    "adx",
    "app/technical/price-action",
    "technical/price-action",
    "price-action",
    "priceaction",
    "app/technical/price-action-analysis",
    "technical/price-action-analysis",
    "price-action-analysis",
    "priceactionanalysis",
    "app/technical/trendline",
    "technical/trendline",
    "trendline",
    "app/technical/breakout",
    "technical/breakout",
    "breakout",
    "app/technical/chart-patterns",
    "technical/chart-patterns",
    "chart-patterns",
    "chartpatterns",
    "app/technical/strong-technicals",
    "technical/strong-technicals",
    "strong-technicals",
    "strongtechnicals",
    "app/technical/support-resistance",
    "technical/support-resistance",
    "support-resistance",
    "sr_levels",
    "app/technical/volume",
    "technical/volume",
    "volume",
    "app/technical/delivery",
    "technical/delivery",
    "delivery",
    "app/database/stock-history",
    "database/stock-history",
    "database",
    "app/database/historical-data",
    "database/historical-data",
    "historical-data",
    "historical_data",
    "app/database/corporate-actions",
    "database/corporate-actions",
    "corporate-actions",
    "corporateactions",
    "app/database/nse-market-cap",
    "database/nse-market-cap",
    "nse-market-cap",
    "nse_market_cap",
    "app/database/nse-market-cap-index",
    "database/nse-market-cap-index",
    "nse-market-cap-index",
    "nse_marketcap_index",
    "app/database/nse-ffmc",
    "database/nse-ffmc",
    "nse-ffmc",
    "nse_ffmc",
    "app/database/nse-delivery-data",
    "database/nse-delivery-data",
    "nse-delivery-data",
    "nse_delivery_data",
    "app/database/server",
    "database/server",
    "server",
    "app/fyers/automation",
    "fyers/automation",
    "fyersapi",
    "app/fyers/failed-symbols",
    "fyers/failed-symbols",
    "failed-symbols",
    "app/fyers/holdings",
    "fyers/holdings",
    "holdings",
    "app/fyers/nifty500-sync",
    "fyers/nifty500-sync",
    "nifty500-sync",
    "niftyt500",
    "app/sector/rotation",
    "sector/rotation",
    "sectorrotation",
    "app/sector/stocks",
    "sector/stocks",
    "sector-wise-stocks",
    "sector-wise",
    "app/strategy",
    "strategy",
    "app/strategy/stock-chart",
    "strategy/stock-chart",
    "stock-chart",
    "stockchart",
    "app/strategy/asura",
    "strategy/asura",
    "asura",
    "app/strategy/asura-v3",
    "strategy/asura-v3",
    "asura-v3",
    "app/strategy/bhramhaputra",
    "strategy/bhramhaputra",
    "bhramhaputra",
    "app/strategy/bhramhastra",
    "strategy/bhramhastra",
    "bhramhastra",
    "app/strategy/ganga",
    "strategy/ganga",
    "ganga",
    "app/strategy/kaveri",
    "strategy/kaveri",
    "kaveri",
    "app/strategy/prudvi",
    "strategy/prudvi",
    "prudvi",
    "app/strategy/thrinethra",
    "strategy/thrinethra",
    "thrinethra",
    "app/strategy/thrisul",
    "strategy/thrisul",
    "thrisul",
    "app/strategy/yamuna",
    "strategy/yamuna",
    "yamuna",
}

REACT_ROUTE_PREFIXES = (
    "app",
    "fundamental",
)

RETIRED_LEGACY_STATIC_PREFIXES = (
    "assets/",
    "css/",
    "images/",
    "html/",
    "json/",
)


def _dist_index() -> Path:
    return FRONTEND_DIST_DIR / "index.html"


def _has_react_build() -> bool:
    return _dist_index().is_file()


def _serve_react_index() -> Response:
    return send_from_directory(FRONTEND_DIST_DIR, "index.html")


def _serve_react_missing_status(api_catalog: Iterable[str]):
    return jsonify({
        "name": "CvingTrade25X API",
        "status": "online",
        "frontend": "react_build_missing",
        "message": "React frontend build not found. Run npm.cmd run build in frontend.",
        "endpoints": list(api_catalog),
    })


def serve_frontend_root(api_catalog: Iterable[str]):
    if _has_react_build():
        return _serve_react_index()
    return _serve_react_missing_status(api_catalog)


def _is_react_route(path: str) -> bool:
    token = path.strip("/").lower()
    if token in MIGRATED_REACT_ROUTES:
        return True
    return any(token == prefix or token.startswith(f"{prefix}/") for prefix in REACT_ROUTE_PREFIXES)


def register_frontend_routes(app: Flask, api_catalog: Iterable[str]) -> None:
    @app.get("/react-assets/<path:filename>")
    def react_assets(filename: str):
        return send_from_directory(FRONTEND_DIST_DIR / "react-assets", filename)

    @app.get("/<path:request_path>")
    def frontend_or_legacy(request_path: str):
        normalized = request_path.strip("/")
        if normalized.startswith("api/"):
            return jsonify({"status": "error", "message": "API endpoint not found."}), 404

        dist_file = FRONTEND_DIST_DIR / normalized
        if dist_file.is_file():
            return send_from_directory(FRONTEND_DIST_DIR, normalized)

        if normalized.lower().startswith(RETIRED_LEGACY_STATIC_PREFIXES):
            return jsonify({"status": "error", "message": "Resource not found."}), 404

        if _is_react_route(normalized):
            if _has_react_build():
                return _serve_react_index()
            return jsonify({
                "status": "error",
                "message": "React frontend build not found. Run npm.cmd run build in frontend.",
            }), 503

        if _has_react_build() and ("/" in normalized or "." not in normalized):
            return _serve_react_index()

        return jsonify({"status": "error", "message": "Resource not found."}), 404
