from __future__ import annotations

import json
import logging
import math
import os
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import oracledb

from db import get_oracle_connection

from services.sector_rotation_v3_factors import MODEL_VERSION


logger = logging.getLogger(__name__)

DEFAULT_CONFIG_VERSION = "V3_DEFAULT_20260715"
_LOCAL_V3_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[2] / "runtime" / "snapshots" / "sector_rotation_v3_latest.json"
)


def _json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    )


def _read_clob(value: Any) -> str:
    if value is None:
        return ""
    return str(value.read() if hasattr(value, "read") else value)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    token = str(value or "").strip()[:10]
    if not token:
        return None
    try:
        return date.fromisoformat(token)
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _integer(value: Any) -> int:
    parsed = _number(value)
    return max(int(round(parsed)), 0) if parsed is not None else 0


def _nullable_integer(value: Any) -> int | None:
    parsed = _number(value)
    return max(int(round(parsed)), 0) if parsed is not None else None


def _oracle_error_code(exc: Exception) -> int | None:
    detail = exc.args[0] if getattr(exc, "args", ()) else None
    code = getattr(detail, "code", None)
    if isinstance(code, int):
        return code
    return 942 if "ORA-00942" in str(exc).upper() else None


def _read_local_v3_snapshot(as_of_date: date | None = None) -> dict[str, Any] | None:
    try:
        payload = json.loads(_LOCAL_V3_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        logger.exception("sector_rotation_v3_local_snapshot_read_failed")
        return None
    if not isinstance(payload, dict):
        return None
    rows = [dict(row) for row in payload.get("rows", []) if isinstance(row, Mapping)]
    snapshot_day = _as_date(payload.get("asOfDate"))
    if not rows or snapshot_day is None:
        return None
    return {
        **payload,
        "version": "v3",
        "modelVersion": MODEL_VERSION,
        "asOfDate": snapshot_day.isoformat(),
        "cacheStatus": "LOCAL_V3_SNAPSHOT",
        "isStale": bool(as_of_date and snapshot_day < as_of_date),
        "rows": rows,
    }


def is_sector_rotation_v3_schema_available() -> bool:
    conn = None
    try:
        conn = get_oracle_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM user_tables
                WHERE table_name IN (
                    'NSE_SECTOR_ROT_CONFIG_V3',
                    'NSE_SECTOR_ROT_RUN_V3',
                    'NSE_SECTOR_ROTATION_SNAP_V3',
                    'NSE_SECTOR_ROT_COMP_V3'
                )
                """
            )
            row = cursor.fetchone()
            return bool(row and int(row[0] or 0) == 4)
    except Exception:
        logger.exception("sector_rotation_v3_schema_probe_failed")
        return False
    finally:
        if conn is not None:
            conn.close()


def read_latest_published_v3_snapshot(
    as_of_date: date | None = None,
) -> dict[str, Any] | None:
    """Read only the latest atomically published V3 run; return None before deployment."""

    conn = None
    try:
        conn = get_oracle_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT run_id, as_of_date, benchmark_code, completed_at,
                       calculation_duration_ms, row_count
                FROM (
                    SELECT run_id, as_of_date, benchmark_code, completed_at,
                           calculation_duration_ms, row_count
                    FROM nse_sector_rot_run_v3
                    WHERE model_version = :model_version
                      AND status = 'SUCCESS'
                      AND is_published = 'Y'
                      AND (:as_of_date IS NULL OR as_of_date <= :as_of_date)
                    ORDER BY as_of_date DESC, published_at DESC, run_id DESC
                )
                WHERE ROWNUM = 1
                """,
                {"model_version": MODEL_VERSION, "as_of_date": as_of_date},
            )
            run = cursor.fetchone()
            if not run:
                return _read_local_v3_snapshot(as_of_date)
            run_id, snapshot_date, benchmark, generated_at, duration_ms, expected_row_count = run
            cursor.execute(
                """
                SELECT payload_json
                FROM nse_sector_rotation_snap_v3
                WHERE run_id = :run_id
                ORDER BY final_rotation_score DESC NULLS LAST,
                         confidence_score DESC NULLS LAST,
                         coverage_percent DESC NULLS LAST,
                         sector_name
                """,
                {"run_id": run_id},
            )
            rows: list[dict[str, Any]] = []
            for (payload_json,) in cursor.fetchall():
                try:
                    payload = json.loads(_read_clob(payload_json))
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(f"Invalid V3 snapshot payload for run {run_id}") from exc
                if not isinstance(payload, dict):
                    raise ValueError(f"Non-object V3 snapshot payload for run {run_id}")
                rows.append(payload)
            if not rows or len(rows) != _integer(expected_row_count):
                raise RuntimeError(
                    f"Incomplete V3 snapshot run {run_id}: expected {expected_row_count}, read {len(rows)}"
                )
            snapshot_day = _as_date(snapshot_date)
            generated_text = (
                generated_at.isoformat()
                if hasattr(generated_at, "isoformat")
                else str(generated_at or "")
            )
            return {
                "version": "v3",
                "modelVersion": MODEL_VERSION,
                "benchmark": str(benchmark or "NIFTY500"),
                "asOfDate": snapshot_day.isoformat() if snapshot_day else None,
                "generatedAt": generated_text,
                "cacheStatus": "ORACLE_SNAPSHOT",
                "isStale": bool(as_of_date and snapshot_day and snapshot_day < as_of_date),
                "calculationDurationMs": _number(duration_ms) or 0.0,
                "runId": str(run_id),
                "rows": rows,
            }
    except Exception as exc:
        # The V3 schema is intentionally optional until its additive deployment is approved.
        if _oracle_error_code(exc) == 942:
            logger.info("sector_rotation_v3_snapshot_schema_not_deployed source=local_fallback")
            return _read_local_v3_snapshot(as_of_date)
        logger.exception("sector_rotation_v3_snapshot_read_failed error_type=%s", type(exc).__name__)
        raise
    finally:
        if conn is not None:
            conn.close()


def _component_rows(
    run_id: str,
    config_version: str,
    as_of_date: date,
    row: Mapping[str, Any],
) -> list[dict[str, Any]]:
    configured = dict(row.get("configuredWeights") or {})
    effective = dict(row.get("effectiveWeights") or {})
    eligible = _integer(row.get("eligibleStockCount"))
    valid = _integer(row.get("validIndicatorCount"))
    definitions = (
        ("MOMENTUM", "momentum", "momentumScore", "momentumDirection", "momentumAccelerationRaw", True),
        ("BREADTH", "breadth", "breadthScore", "breadthDirection", "breadthDelta5D", True),
        ("TREND", "trend", "trendScore", "trendState", "sectorReturn252", True),
        ("MONEY_FLOW", "moneyFlow", "moneyFlowScore", "moneyFlowDirection", "volumeRatio20", False),
        ("RISK", "risk", "riskScore", "riskRegime", "volatility63", True),
        ("DATA_QUALITY", "dataQuality", "dataQualityScore", "dataQualityStatus", "coveragePercent", True),
    )
    records: list[dict[str, Any]] = []
    for component_code, weight_key, score_key, direction_key, raw_key, required in definitions:
        score = _number(row.get(score_key))
        raw_value = _number(row.get(raw_key))
        records.append(
            {
                "run_id": run_id,
                "sector_code": str(row.get("sectorCode") or "").strip().upper(),
                "as_of_date": as_of_date,
                "model_version": MODEL_VERSION,
                "config_version": config_version,
                "component_code": component_code,
                "raw_value": raw_value,
                "normalized_score": score,
                "configured_weight": _number(configured.get(weight_key)) or 0.0,
                "effective_weight": _number(effective.get(weight_key)) or 0.0,
                "coverage_percent": _number(
                    row.get("moneyFlowCoveragePercent")
                    if component_code == "MONEY_FLOW"
                    else row.get("coveragePercent")
                ),
                "component_direction": str(row.get(direction_key) or "DATA_WEAK")[:24],
                "component_status": "AVAILABLE" if score is not None else "DATA_WEAK",
                "is_required": "Y" if required else "N",
                "is_available": "Y" if score is not None else "N",
                "redistribution_applied": "Y" if row.get("weightRedistributionApplied") else "N",
                "input_count": eligible,
                "valid_count": valid,
                "missing_count": max(eligible - valid, 0),
                "metrics_json": _json_text(
                    {
                        "rawField": raw_key,
                        "rawValue": raw_value,
                        "scoreField": score_key,
                        "normalizedScore": score,
                    }
                ),
                "reason_codes_json": _json_text(row.get("reasonCodes") or []),
                "warnings_json": _json_text(row.get("riskWarnings") or []),
            }
        )
    return records


def _validate_snapshot_rows(rows: list[dict[str, Any]]) -> None:
    sector_codes: set[str] = set()
    ranks: set[int] = set()
    required_scores = ("momentumScore", "breadthScore", "trendScore", "riskScore", "dataQualityScore")
    for row in rows:
        sector_code = str(row.get("sectorCode") or "").strip().upper()
        if not sector_code or sector_code in sector_codes:
            raise ValueError(f"V3 snapshot sector codes must be non-empty and unique: {sector_code or '<blank>'}")
        sector_codes.add(sector_code)
        _json_text(row)

        for field in ("configuredWeights", "effectiveWeights"):
            weights = row.get(field)
            if not isinstance(weights, Mapping):
                raise ValueError(f"{field} is required for sector {sector_code}")
            parsed = [_number(value) for value in weights.values()]
            if any(value is None or value < 0 for value in parsed):
                raise ValueError(f"{field} contains an invalid weight for sector {sector_code}")
            if abs(sum(value for value in parsed if value is not None) - 1.0) > 0.000001:
                raise ValueError(f"{field} must sum to 1.00 for sector {sector_code}")

        final_score = _number(row.get("finalRotationScore"))
        if final_score is not None and any(_number(row.get(field)) is None for field in required_scores):
            raise ValueError(f"Scored V3 row is missing a required factor for sector {sector_code}")
        rank = _nullable_integer(row.get("currentRank"))
        if rank is not None:
            if rank <= 0 or rank in ranks:
                raise ValueError(f"V3 current ranks must be positive and unique: {rank}")
            ranks.add(rank)


def publish_local_sector_rotation_v3_snapshot(envelope: Mapping[str, Any]) -> str:
    """Atomically publish a restart-safe V3 snapshot when Oracle V3 objects are absent."""

    rows = [dict(row) for row in envelope.get("rows", []) if isinstance(row, Mapping)]
    as_of_date = _as_date(envelope.get("asOfDate"))
    if not rows or as_of_date is None:
        raise ValueError("A non-empty V3 envelope with a valid asOfDate is required")
    _validate_snapshot_rows(rows)
    run_id = f"local-{as_of_date.isoformat()}-{uuid.uuid4().hex}"
    payload = {
        **dict(envelope),
        "version": "v3",
        "modelVersion": MODEL_VERSION,
        "asOfDate": as_of_date.isoformat(),
        "cacheStatus": "LOCAL_V3_SNAPSHOT",
        "isStale": False,
        "runId": run_id,
        "rows": rows,
    }
    _LOCAL_V3_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = _LOCAL_V3_SNAPSHOT_PATH.with_suffix(
        f"{_LOCAL_V3_SNAPSHOT_PATH.suffix}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary_path.write_text(_json_text(payload), encoding="utf-8")
        os.replace(temporary_path, _LOCAL_V3_SNAPSHOT_PATH)
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
    logger.info(
        "sector_rotation_v3_local_snapshot_published run_id=%s as_of_date=%s rows=%s path=%s",
        run_id,
        as_of_date,
        len(rows),
        _LOCAL_V3_SNAPSHOT_PATH,
    )
    return run_id


def publish_sector_rotation_v3_snapshot(
    envelope: Mapping[str, Any],
    *,
    config_version: str = DEFAULT_CONFIG_VERSION,
) -> str:
    """Persist and publish one completed envelope in a single Oracle transaction."""

    rows = [dict(row) for row in envelope.get("rows", []) if isinstance(row, Mapping)]
    as_of_date = _as_date(envelope.get("asOfDate"))
    if not rows or as_of_date is None:
        raise ValueError("A non-empty V3 envelope with a valid asOfDate is required")
    if any(str(row.get("modelVersion") or "").upper() != MODEL_VERSION for row in rows):
        raise ValueError("All snapshot rows must use SECTOR_ROTATION_V3")
    _validate_snapshot_rows(rows)

    run_id = uuid.uuid4().hex
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT config_hash, benchmark_code, benchmark_version, universe_version
                FROM nse_sector_rot_config_v3
                WHERE config_version = :config_version
                  AND status = 'ACTIVE'
                  AND effective_from <= :as_of_date
                  AND (effective_to IS NULL OR effective_to >= :as_of_date)
                """,
                {"config_version": config_version, "as_of_date": as_of_date},
            )
            config = cursor.fetchone()
            if not config:
                raise RuntimeError(f"Active V3 config not found: {config_version}")
            config_hash, benchmark, benchmark_version, universe_version = config
            cursor.execute(
                """
                INSERT INTO nse_sector_rot_run_v3 (
                    run_id, as_of_date, model_version, config_version, config_hash,
                    benchmark_code, benchmark_version, universe_version, source_max_trading_date,
                    status, is_published, row_count, input_symbol_count,
                    eligible_symbol_count, excluded_symbol_count,
                    calculation_duration_ms, run_metadata_json
                ) VALUES (
                    :run_id, :as_of_date, :model_version, :config_version, :config_hash,
                    :benchmark, :benchmark_version, :universe_version, :as_of_date,
                    'CALCULATING', 'N', :row_count, :input_count,
                    :eligible_count, :excluded_count, :duration_ms, :metadata_json
                )
                """,
                {
                    "run_id": run_id,
                    "as_of_date": as_of_date,
                    "model_version": MODEL_VERSION,
                    "config_version": config_version,
                    "config_hash": str(config_hash),
                    "benchmark": str(benchmark),
                    "benchmark_version": str(benchmark_version),
                    "universe_version": str(universe_version),
                    "row_count": len(rows),
                    "input_count": sum(_integer(row.get("totalStocks")) for row in rows),
                    "eligible_count": sum(_integer(row.get("eligibleStockCount")) for row in rows),
                    "excluded_count": sum(_integer(row.get("excludedStockCount")) for row in rows),
                    "duration_ms": _number(envelope.get("calculationDurationMs")) or 0.0,
                    "metadata_json": _json_text({"generatedAt": envelope.get("generatedAt")}),
                },
            )
            snapshot_records: list[dict[str, Any]] = []
            component_records: list[dict[str, Any]] = []
            for row in rows:
                configured_json = _json_text(row.get("configuredWeights") or {})
                effective_json = _json_text(row.get("effectiveWeights") or {})
                snapshot_records.append(
                    {
                        "run_id": run_id,
                        "sector_code": str(row.get("sectorCode") or "").strip().upper(),
                        "sector_name": str(row.get("sectorName") or row.get("sectorCode") or "")[:255],
                        "as_of_date": as_of_date,
                        "model_version": MODEL_VERSION,
                        "config_version": config_version,
                        "benchmark": str(benchmark),
                        "benchmark_version": str(benchmark_version),
                        "universe_version": str(universe_version),
                        "latest_data_date": _as_date(row.get("latestDataDate")),
                        "total_stocks": _integer(row.get("totalStocks")),
                        "eligible_count": _integer(row.get("eligibleStockCount")),
                        "valid_price_count": _integer(row.get("validPriceCount")),
                        "valid_indicator_count": _integer(row.get("validIndicatorCount")),
                        "coverage_percent": _number(row.get("coveragePercent")),
                        "history_coverage_percent": _number(row.get("historyCoveragePercent")),
                        "money_flow_coverage_percent": _number(row.get("moneyFlowCoveragePercent")),
                        "momentum_score": _number(row.get("momentumScore")),
                        "breadth_score": _number(row.get("breadthScore")),
                        "trend_score": _number(row.get("trendScore")),
                        "money_flow_score": _number(row.get("moneyFlowScore")),
                        "risk_score": _number(row.get("riskScore")),
                        "data_quality_score": _number(row.get("dataQualityScore")),
                        "final_score": _number(row.get("finalRotationScore")),
                        "rotation_band": str(row.get("rotationBand") or "") or None,
                        "rotation_phase": str(row.get("rotationPhase") or "DATA_WEAK"),
                        "current_rank": _nullable_integer(row.get("currentRank")),
                        "rank_change_1w": _number(row.get("rankChange1W")),
                        "confidence": str(row.get("confidence") or "LOW"),
                        "confidence_score": _number(row.get("confidenceScore")),
                        "redistributed": "Y" if row.get("weightRedistributionApplied") else "N",
                        "configured_json": configured_json,
                        "effective_json": effective_json,
                        "reasons_json": _json_text(row.get("reasonCodes") or []),
                        "warnings_json": _json_text(row.get("riskWarnings") or []),
                        "summary": str(row.get("summaryExplanation") or "")[:2000],
                        "payload_json": _json_text(row),
                    }
                )
                component_records.extend(_component_rows(run_id, config_version, as_of_date, row))
            if hasattr(cursor, "setinputsizes"):
                cursor.setinputsizes(
                    configured_json=oracledb.DB_TYPE_CLOB,
                    effective_json=oracledb.DB_TYPE_CLOB,
                    reasons_json=oracledb.DB_TYPE_CLOB,
                    warnings_json=oracledb.DB_TYPE_CLOB,
                    payload_json=oracledb.DB_TYPE_CLOB,
                )
            cursor.executemany(
                """
                INSERT INTO nse_sector_rotation_snap_v3 (
                    run_id, sector_code, sector_name, as_of_date, model_version,
                    config_version, benchmark_code, benchmark_version, universe_version, latest_data_date,
                    total_stocks, eligible_stock_count, valid_price_count,
                    valid_indicator_count, coverage_percent, history_coverage_percent,
                    money_flow_coverage_percent, momentum_score, breadth_score, trend_score,
                    money_flow_score, risk_score, data_quality_score, final_rotation_score,
                    rotation_band, rotation_phase, current_rank, rank_change_1w,
                    confidence, confidence_score, weight_redistribution_applied,
                    configured_weights_json, effective_weights_json, reason_codes_json,
                    risk_warnings_json, summary_explanation, payload_json
                ) VALUES (
                    :run_id, :sector_code, :sector_name, :as_of_date, :model_version,
                    :config_version, :benchmark, :benchmark_version, :universe_version, :latest_data_date,
                    :total_stocks, :eligible_count, :valid_price_count,
                    :valid_indicator_count, :coverage_percent, :history_coverage_percent,
                    :money_flow_coverage_percent, :momentum_score, :breadth_score, :trend_score,
                    :money_flow_score, :risk_score, :data_quality_score, :final_score,
                    :rotation_band, :rotation_phase, :current_rank, :rank_change_1w,
                    :confidence, :confidence_score, :redistributed,
                    :configured_json, :effective_json, :reasons_json,
                    :warnings_json, :summary, :payload_json
                )
                """,
                snapshot_records,
            )
            if hasattr(cursor, "setinputsizes"):
                cursor.setinputsizes(
                    metrics_json=oracledb.DB_TYPE_CLOB,
                    reason_codes_json=oracledb.DB_TYPE_CLOB,
                    warnings_json=oracledb.DB_TYPE_CLOB,
                )
            cursor.executemany(
                """
                INSERT INTO nse_sector_rot_comp_v3 (
                    run_id, sector_code, as_of_date, model_version, config_version,
                    component_code, raw_value, normalized_score, configured_weight,
                    effective_weight, coverage_percent, component_direction,
                    component_status, is_required, is_available, redistribution_applied,
                    input_count, valid_count, missing_count, metrics_json,
                    reason_codes_json, warnings_json
                ) VALUES (
                    :run_id, :sector_code, :as_of_date, :model_version, :config_version,
                    :component_code, :raw_value, :normalized_score, :configured_weight,
                    :effective_weight, :coverage_percent, :component_direction,
                    :component_status, :is_required, :is_available, :redistribution_applied,
                    :input_count, :valid_count, :missing_count, :metrics_json,
                    :reason_codes_json, :warnings_json
                )
                """,
                component_records,
            )
            cursor.execute(
                """
                UPDATE nse_sector_rot_run_v3
                SET status = 'SUCCESS', is_published = 'Y',
                    completed_at = SYSTIMESTAMP, published_at = SYSTIMESTAMP,
                    updated_at = SYSTIMESTAMP
                WHERE run_id = :run_id
                  AND status = 'CALCULATING'
                  AND is_published = 'N'
                """,
                {"run_id": run_id},
            )
            if cursor.rowcount != 1:
                raise RuntimeError("V3 snapshot publication gate was not updated")
        conn.commit()
        logger.info(
            "sector_rotation_v3_snapshot_published run_id=%s as_of_date=%s rows=%s",
            run_id,
            as_of_date,
            len(rows),
        )
        return run_id
    except Exception:
        conn.rollback()
        logger.exception("sector_rotation_v3_snapshot_publish_failed run_id=%s", run_id)
        raise
    finally:
        conn.close()


__all__ = [
    "DEFAULT_CONFIG_VERSION",
    "is_sector_rotation_v3_schema_available",
    "publish_local_sector_rotation_v3_snapshot",
    "publish_sector_rotation_v3_snapshot",
    "read_latest_published_v3_snapshot",
]
