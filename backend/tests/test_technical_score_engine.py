from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.technical_score_engine import (  # noqa: E402
    calculate_master_score,
    calculate_master_trend,
    enrich_row_with_master_score_fields,
)


def test_master_score_strong_uptrend_with_confirmation():
    row = {
        "symbol": "RELIANCE",
        "tradingDate": "2026-05-05",
        "price": 1000,
        "open": 990,
        "high": 1010,
        "low": 980,
        "ema20": 960,
        "ema50": 930,
        "ema100": 900,
        "ema200": 850,
        "ema20SlopePct": 1.2,
        "ema50SlopePct": 0.8,
        "rsi14": 62,
        "macdHist": 2.5,
        "macdHistSlope": 0.4,
        "adx14": 31,
        "adx14Slope": 1.0,
        "plusDi14": 30,
        "minusDi14": 15,
        "volumeRatio20": 1.6,
        "deliveryRel20": 1.15,
        "deliverableValueRel20": 1.25,
        "ath": 1020,
        "high52w": 1020,
        "low52w": 600,
        "resistance": 990,
        "breakoutFlag": "BREAKOUT",
        "closeLocationPct": 66,
    }
    trend = calculate_master_trend(row)
    score = calculate_master_score(row, trend)

    assert trend["trend"] == "Strong Uptrend"
    assert trend["trendSort"] == 1
    assert score["score"] >= 80
    assert score["scoreGrade"] in {"A", "A+"}


def test_downtrend_score_is_capped_at_30():
    row = {
        "symbol": "ABC",
        "tradingDate": "2026-05-05",
        "price": 80,
        "ema20": 90,
        "ema50": 100,
        "ema100": 110,
        "ema200": 120,
        "adx14": 38,
        "minusDi14": 35,
        "plusDi14": 10,
        "support": 85,
        "breakdownFlag": "BREAKDOWN",
        "volumeRatio20": 2.0,
        "rsi14": 42,
        "macdHist": -1.2,
    }
    trend = calculate_master_trend(row)
    score = calculate_master_score(row, trend)

    assert trend["trend"] == "Downtrend"
    assert score["score"] <= 30


def test_missing_inputs_do_not_crash_and_are_reported():
    row = {"symbol": "MISSING", "tradingDate": "2026-05-05", "price": 100}
    trend = calculate_master_trend(row)
    score = calculate_master_score(row, trend)

    assert trend["trend"] in {"Consolidation", "Unknown / Insufficient Data"}
    assert isinstance(score["scoreBreakdown"]["missingInputs"], list)
    assert "ema20" in score["scoreBreakdown"]["missingInputs"]


def test_enrichment_preserves_legacy_signal_fields_when_not_replacing():
    row = {
        "symbol": "ASURA",
        "price": 100,
        "ema20": 95,
        "ema50": 90,
        "ema100": 85,
        "ema200": 80,
        "trendDirection": "UPTREND",
        "signalScore": 80,
    }
    enriched = enrich_row_with_master_score_fields(row, replace_existing=False)

    assert enriched["signalScore"] == 80
    assert enriched["trendDirection"] == "UPTREND"
    assert "masterScore" in enriched
    assert "masterTrend" in enriched
