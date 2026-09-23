from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.sector_rotation_v3_factors import (
    classify_phase,
    compute_hhi,
    compute_participation_percent,
    rotation_band,
    score_final_rotation,
    score_money_flow,
    score_trend,
)
from services.sector_rotation_v3_service import (
    V3FeatureDisabledError,
    build_sector_rotation_v3_envelope,
)


def _row(
    sector_code: str,
    strength: float,
    *,
    include_money_flow: bool = True,
) -> dict:
    is_strong = strength >= 50
    close = 120.0 if is_strong else 80.0
    row = {
        "sectorCode": sector_code,
        "sectorName": sector_code.title(),
        "asOfDate": "2026-07-14",
        "latestDataDate": "2026-07-14",
        "totalSymbols": 20,
        "eligibleStockCount": 20,
        "validPriceCount": 19,
        "validIndicatorCount": 19,
        "coveragePercent": 95,
        "historyCoveragePercent": 96,
        "liquidityCoveragePercent": 94,
        "nullOutlierQualityScore": 98,
        "relativeReturn21": 0.08 if is_strong else -0.08,
        "relativeReturn63": 0.14 if is_strong else -0.14,
        "relativeReturn126": 0.20 if is_strong else -0.20,
        "relativeReturn252": 0.28 if is_strong else -0.28,
        "realizedVolatility21": 0.12,
        "realizedVolatility63": 0.16,
        "realizedVolatility126": 0.20,
        "realizedVolatility252": 0.24,
        "momentumAccelerationRaw": 8 if is_strong else -8,
        "relativeStrengthLevel": 70 if is_strong else 30,
        "sectorIndexClose": close,
        "sectorSMA20": 110,
        "sectorSMA50": 105,
        "sectorSMA100": 100,
        "sectorSMA200": 95,
        "sectorSMA50Slope": 1 if is_strong else -1,
        "sectorSMA100Slope": 0.5 if is_strong else -0.5,
        "sectorReturn252": 0.25 if is_strong else -0.25,
        "rsi55Percent": strength,
        "rsi50Percent": min(strength + 5, 100),
        "sma20Percent": strength,
        "sma50Percent": strength,
        "sma100Percent": strength,
        "sma200Percent": strength,
        "bullishStackPercent": strength,
        "breadthDelta5D": 4 if is_strong else -4,
        "breadthDelta21D": 6 if is_strong else -6,
        "volatility63": 0.12 if is_strong else 0.42,
        "downsideVolatility126": 0.10 if is_strong else 0.48,
        "maxDrawdown126": -0.08 if is_strong else -0.38,
        "maxDrawdown252": -0.12 if is_strong else -0.52,
        "betaInstability": 0.08 if is_strong else 0.40,
        "concentrationHhi": 0.10 if is_strong else 0.32,
        "liquidityRisk": 0.06 if is_strong else 0.45,
    }
    if include_money_flow:
        row.update(
            {
                "volumeRatio20": 1.6 if is_strong else 0.6,
                "deliveryParticipationScore": strength,
                "obvSlopeScore": strength,
                "accumulationScore": strength,
                "upDownVolumeScore": strength,
                "breadthVolumeScore": strength,
            }
        )
    return row


def _build(rows: list[dict]) -> dict:
    return build_sector_rotation_v3_envelope(
        rows,
        engine_version="v3",
        generated_at="2026-07-15T00:00:00+00:00",
        calculation_duration_ms=1.25,
    )


def test_v3_feature_gate_is_opt_in_and_input_rows_are_not_mutated():
    rows = [_row("IT", 80)]
    original = deepcopy(rows)

    with pytest.raises(V3FeatureDisabledError):
        build_sector_rotation_v3_envelope(rows, engine_version="v2")

    assert rows == original


def test_participation_uses_metric_specific_valid_denominators_and_ffmc_weights():
    assert compute_participation_percent([True, False, None]) == 50.0
    assert compute_participation_percent([True, False, None], [80, 20, 1000]) == 80.0
    assert compute_participation_percent([None, None]) is None
    assert compute_hhi([50, 30, 20]) == pytest.approx(0.38)


def test_independent_factors_ignore_legacy_rotation_and_final_rotation_values():
    rows = [_row("STRONG", 82), _row("WEAK", 25)]
    rows[0].update({"rotationScore": -9999, "finalRotation": -9999})
    rows[1].update({"rotationScore": 9999, "finalRotation": 9999})

    first = _build(rows)
    second_rows = deepcopy(rows)
    second_rows[0].update({"rotationScore": 9999, "finalRotation": 9999})
    second_rows[1].update({"rotationScore": -9999, "finalRotation": -9999})
    second = _build(second_rows)

    first_scores = {row["sectorCode"]: row["finalRotationScore"] for row in first["rows"]}
    second_scores = {row["sectorCode"]: row["finalRotationScore"] for row in second["rows"]}
    assert first_scores == second_scores
    assert first["rows"][0]["sectorCode"] == "STRONG"
    assert all(0 <= row["finalRotationScore"] <= 100 for row in first["rows"])


def test_trend_is_an_independent_weighted_model_and_missing_inputs_are_not_zero_filled():
    complete = score_trend(
        {
            "aboveSma20": 100,
            "aboveSma50": 100,
            "aboveSma100": 100,
            "aboveSma200": 100,
            "bullishStructure": 100,
            "positiveSma50Slope": 100,
            "positiveSma100Slope": 100,
            "positiveReturn252": 100,
        }
    )
    insufficient = score_trend({"aboveSma20": 100, "aboveSma50": 100})

    assert complete.score == 100
    assert complete.state == "STRONG_UPTREND"
    assert insufficient.score is None
    assert insufficient.state == "DATA_WEAK"


def test_breadth_count_aliases_keep_independent_denominators():
    row = _row("COUNTS", 80)
    for key in (
        "rsi55Percent",
        "rsi50Percent",
        "sma20Percent",
        "sma50Percent",
        "sma100Percent",
        "sma200Percent",
        "bullishStackPercent",
    ):
        row.pop(key)
    row.update(
        {
            "rsi55Count": 8,
            "rsi55ValidCount": 10,
            "rsi50Count": 9,
            "rsi50ValidCount": 10,
            "sma20Count": 5,
            "sma20ValidCount": 5,
            "sma50Count": 4,
            "sma50ValidCount": 8,
            "sma100Count": 3,
            "sma100ValidCount": 6,
            "sma200Count": 2,
            "sma200ValidCount": 4,
            "bullishStackCount": 1,
            "bullishStackValidCount": 4,
        }
    )

    result = _build([row])["rows"][0]

    assert result["rsi55Percent"] == 80
    assert result["sma20Percent"] == 100
    assert result["sma50Percent"] == 50
    assert result["sma200Percent"] == 50
    assert result["breadthScore"] is not None


def test_missing_money_flow_is_null_then_redistributed_with_penalty_and_confidence_cap():
    result = _build([_row("AUTO", 78, include_money_flow=False)])["rows"][0]

    assert result["moneyFlowScore"] is None
    assert result["moneyFlow"] is None
    assert result["finalRotationScore"] is not None
    assert result["weightRedistributionApplied"] is True
    assert result["effectiveWeights"]["moneyFlow"] == 0
    assert result["effectiveWeights"]["dataQuality"] == 0.05
    assert sum(result["effectiveWeights"].values()) == pytest.approx(1.0)
    assert result["confidence"] == "MEDIUM"
    assert "MONEY_FLOW_DATA_INCOMPLETE" in result["reasonCodes"]


def test_source_five_day_rank_delta_is_preserved_in_v3_snapshot():
    row = _row("RANKED", 78)
    row["rankChange5"] = 4

    result = _build([row])["rows"][0]

    assert result["rankChange1W"] == 4
    assert result["rankMovement"] == "UP"


def test_risk_score_is_inverse_risk_and_concentration_warning_is_explainable():
    result = _build([_row("CONTROLLED", 80), _row("RISKY", 20)])
    by_code = {row["sectorCode"]: row for row in result["rows"]}

    assert by_code["CONTROLLED"]["riskScore"] > by_code["RISKY"]["riskScore"]
    assert by_code["CONTROLLED"]["riskRegime"] == "LOW"
    assert "CONCENTRATION_HIGH" in by_code["RISKY"]["riskWarnings"]
    assert "HIGH_CONCENTRATION_DEPENDENCY" in by_code["RISKY"]["divergenceCodes"]


def test_final_score_requires_core_factors_and_preserves_legacy_aliases_as_nulls():
    row = {
        "sectorCode": "DATA_WEAK",
        "sectorName": "Data Weak",
        "asOfDate": "2026-07-14",
        "totalSymbols": 10,
        "rsi55Pct": 60,
        "rsi50Pct": 70,
        "sma20Pct": 55,
        "sma50Pct": 50,
        "sma100Pct": 45,
    }

    result = _build([row])["rows"][0]

    assert result["finalRotationScore"] is None
    assert result["rotation"] is None
    assert result["rotationPhase"] == "DATA_WEAK"
    assert result["confidence"] == "LOW"
    assert result["score"] == 56
    assert result["rsi55"] == 60
    assert result["phase"] == "DATA_WEAK"


def test_phase_dead_band_and_two_of_three_hysteresis_are_deterministic():
    preserved = classify_phase(
        relative_strength_level=70,
        momentum_acceleration_raw=10,
        trend_score=80,
        breadth_delta_5d=5,
        previous_phase="LAGGING",
        recent_phase_candidates=["LAGGING"],
    )
    confirmed = classify_phase(
        relative_strength_level=70,
        momentum_acceleration_raw=10,
        trend_score=80,
        breadth_delta_5d=5,
        previous_phase="LAGGING",
        recent_phase_candidates=["LEADING"],
    )
    dead_band = classify_phase(
        relative_strength_level=70,
        momentum_acceleration_raw=0,
        trend_score=80,
        breadth_delta_5d=0,
        previous_phase="WEAKENING",
    )

    assert preserved.phase == "LAGGING"
    assert preserved.reason_codes == ("PHASE_HYSTERESIS_PRESERVED",)
    assert confirmed.phase == "LEADING"
    assert dead_band.phase == "WEAKENING"
    assert dead_band.reason_codes == ("PHASE_DEAD_BAND_PRESERVED",)


@pytest.mark.parametrize(
    ("score", "expected"),
    [(85, "VERY_STRONG"), (70, "STRONG"), (55, "POSITIVE"), (45, "NEUTRAL"), (30, "WEAK"), (0, "VERY_WEAK"), (None, "DATA_WEAK")],
)
def test_rotation_bands_are_separate_from_phase(score, expected):
    assert rotation_band(score) == expected


def test_final_score_redistributes_only_money_flow_weight():
    result = score_final_rotation(
        {
            "momentum": 80,
            "breadth": 75,
            "trend": 70,
            "moneyFlow": None,
            "risk": 65,
            "dataQuality": 90,
        }
    )

    assert result.score is not None
    assert result.redistribution_applied is True
    assert result.effective_weights["dataQuality"] == 0.05
    assert result.effective_weights["moneyFlow"] == 0
    assert sum(result.effective_weights.values()) == pytest.approx(1.0)


def test_route_friendly_envelope_has_canonical_metadata_ranking_and_aliases():
    result = _build([_row("BANK", 75), _row("IT", 88)])
    first = result["rows"][0]

    assert result == {
        **result,
        "version": "v3",
        "modelVersion": "SECTOR_ROTATION_V3",
        "benchmark": "NIFTY500",
        "asOfDate": "2026-07-14",
        "generatedAt": "2026-07-15T00:00:00+00:00",
        "calculationDurationMs": 1.25,
    }
    assert first["currentRank"] == 1
    assert first["rotation"] == first["finalRotationScore"]
    assert first["momentum"] == first["momentumScore"]
    assert first["breadth"] == first["breadthScore"]
    assert first["moneyFlow"] == first["moneyFlowScore"]
    assert first["risk"] == first["riskScore"]
    assert first["trend"] == first["trendScore"]
    assert first["phase"] == first["rotationPhase"]
    assert first["score"] == first["legacyDisplayScore"]
    assert first["summaryExplanation"]


def test_legacy_current_rows_use_flagged_proxies_without_scaled_duplicate_factors():
    rows = [
        {
            "sectorCode": "AUTO",
            "sectorName": "Auto",
            "asOfDate": "2026-07-14",
            "totalSymbols": 10,
            "screenedStocks": 9,
            "relativeMomentum": 1.2,
            "absoluteTrend": 0.8,
            "riskAdjustment": 0.4,
            "rsi55Pct": 70,
            "rsi50Pct": 75,
            "sma20Pct": 72,
            "sma50Pct": 68,
            "sma100Pct": 60,
        },
        {
            "sectorCode": "METAL",
            "sectorName": "Metal",
            "asOfDate": "2026-07-14",
            "totalSymbols": 10,
            "screenedStocks": 8,
            "relativeMomentum": -0.8,
            "absoluteTrend": 0.4,
            "riskAdjustment": -0.5,
            "rsi55Pct": 40,
            "rsi50Pct": 45,
            "sma20Pct": 42,
            "sma50Pct": 38,
            "sma100Pct": 35,
        },
    ]

    result = _build(rows)
    auto = next(row for row in result["rows"] if row["sectorCode"] == "AUTO")

    assert auto["momentumScore"] == 100
    assert auto["trendScore"] == 80
    assert auto["riskScore"] == 100
    assert auto["moneyFlowScore"] is None
    assert auto["finalRotationScore"] is not None
    assert "LEGACY_MOMENTUM_PROXY_USED" in auto["reasonCodes"]
    assert "LEGACY_TREND_PROXY_USED" in auto["reasonCodes"]
    assert "LEGACY_RISK_PROXY_USED" in auto["reasonCodes"]
    assert auto["confidence"] == "LOW"


def test_v3_envelope_is_strict_json_safe_for_non_finite_source_values():
    rows = [_row("AUTO", 80), _row("IT", 60)]
    rows[0]["diagnostic"] = float("nan")
    rows[1]["nestedDiagnostics"] = [float("inf"), -float("inf"), 0.0]

    payload = _build(rows)

    json.dumps(payload, allow_nan=False)
    auto = next(row for row in payload["rows"] if row["sectorCode"] == "AUTO")
    it_row = next(row for row in payload["rows"] if row["sectorCode"] == "IT")
    assert auto["diagnostic"] is None
    assert it_row["nestedDiagnostics"] == [None, None, 0.0]
