from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from services import sector_rotation_v3_repository as repository


class _Cursor:
    def __init__(self):
        self.execute_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _sql, _binds):
        self.execute_count += 1

    def fetchone(self):
        return (
            "run-1",
            date(2026, 7, 15),
            "NIFTY500",
            datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc),
            125.5,
            2,
        )

    def fetchall(self):
        return [
            (json.dumps({"sectorCode": "AUTO", "finalRotationScore": 72.5}),),
            (json.dumps({"sectorCode": "IT", "finalRotationScore": 65.0}),),
        ]


class _Connection:
    def __init__(self):
        self.cursor_instance = _Cursor()
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_schema_probe_uses_the_deployed_component_table_name(monkeypatch):
    executed: list[str] = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql):
            executed.append(str(sql))

        def fetchone(self):
            return (4,)

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            return None

    monkeypatch.setattr(repository, "get_oracle_connection", Connection)

    assert repository.is_sector_rotation_v3_schema_available() is True
    assert "NSE_SECTOR_ROT_COMP_V3" in executed[0]


def test_read_latest_published_v3_snapshot_returns_envelope(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(repository, "get_oracle_connection", lambda: connection)

    payload = repository.read_latest_published_v3_snapshot(date(2026, 7, 15))

    assert payload is not None
    assert payload["version"] == "v3"
    assert payload["modelVersion"] == "SECTOR_ROTATION_V3"
    assert payload["runId"] == "run-1"
    assert payload["asOfDate"] == "2026-07-15"
    assert [row["sectorCode"] for row in payload["rows"]] == ["AUTO", "IT"]
    assert connection.closed is True


def test_component_rows_persist_six_independent_factor_records():
    row = {
        "sectorCode": "AUTO",
        "eligibleStockCount": 10,
        "validIndicatorCount": 8,
        "momentumScore": 72,
        "breadthScore": 68,
        "trendScore": 75,
        "moneyFlowScore": None,
        "riskScore": 62,
        "dataQualityScore": 80,
        "configuredWeights": {
            "momentum": 0.30,
            "breadth": 0.25,
            "trend": 0.20,
            "moneyFlow": 0.10,
            "risk": 0.10,
            "dataQuality": 0.05,
        },
        "effectiveWeights": {
            "momentum": 0.3375,
            "breadth": 0.28125,
            "trend": 0.225,
            "moneyFlow": 0,
            "risk": 0.1125,
            "dataQuality": 0.05,
        },
        "weightRedistributionApplied": True,
    }

    records = repository._component_rows("run-1", "config-1", date(2026, 7, 15), row)

    assert {record["component_code"] for record in records} == {
        "MOMENTUM",
        "BREADTH",
        "TREND",
        "MONEY_FLOW",
        "RISK",
        "DATA_QUALITY",
    }
    money_flow = next(record for record in records if record["component_code"] == "MONEY_FLOW")
    assert money_flow["is_required"] == "N"
    assert money_flow["is_available"] == "N"
    assert money_flow["effective_weight"] == 0.0
    assert all(record["redistribution_applied"] == "Y" for record in records)


def test_publish_rejects_empty_envelope_without_opening_oracle(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_oracle_connection",
        lambda: pytest.fail("Oracle must not be opened for invalid input"),
    )

    with pytest.raises(ValueError, match="non-empty V3 envelope"):
        repository.publish_sector_rotation_v3_snapshot({"version": "v3", "rows": []})


def test_local_snapshot_is_atomic_and_readable(monkeypatch, tmp_path):
    snapshot_path = tmp_path / "sector_rotation_v3_latest.json"
    monkeypatch.setattr(repository, "_LOCAL_V3_SNAPSHOT_PATH", snapshot_path)
    weights = {
        "momentum": 0.30,
        "breadth": 0.25,
        "trend": 0.20,
        "moneyFlow": 0.10,
        "risk": 0.10,
        "dataQuality": 0.05,
    }
    row = {
        "modelVersion": "SECTOR_ROTATION_V3",
        "sectorCode": "AUTO",
        "sectorName": "Auto",
        "momentumScore": 70,
        "breadthScore": 68,
        "trendScore": 72,
        "moneyFlowScore": 60,
        "riskScore": 65,
        "dataQualityScore": 90,
        "finalRotationScore": 69.7,
        "configuredWeights": weights,
        "effectiveWeights": weights,
    }

    run_id = repository.publish_local_sector_rotation_v3_snapshot(
        {"asOfDate": "2026-07-22", "rows": [row]}
    )
    payload = repository._read_local_v3_snapshot(date(2026, 7, 22))

    assert run_id.startswith("local-2026-07-22-")
    assert payload is not None
    assert payload["asOfDate"] == "2026-07-22"
    assert payload["cacheStatus"] == "LOCAL_V3_SNAPSHOT"
    assert payload["isStale"] is False
    assert payload["rows"][0]["sectorCode"] == "AUTO"
    assert not list(tmp_path.glob("*.tmp"))


class _PublishCursor:
    def __init__(self):
        self.last_sql = ""
        self.executed: list[tuple[str, dict]] = []
        self.executed_many: list[tuple[str, list[dict]]] = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, binds):
        self.last_sql = sql
        self.executed.append((sql, dict(binds)))
        self.rowcount = 1 if "UPDATE nse_sector_rot_run_v3" in sql else 0

    def fetchone(self):
        if "FROM nse_sector_rot_config_v3" in self.last_sql:
            return ("hash-1", "NIFTY500", "NIFTY500_SOURCE_CURRENT", "UNIVERSE_V1")
        return None

    def setinputsizes(self, **_kwargs):
        return None

    def executemany(self, sql, records):
        self.executed_many.append((sql, [dict(record) for record in records]))


class _PublishConnection:
    def __init__(self):
        self.cursor_instance = _PublishCursor()
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_publish_binds_required_benchmark_version_and_nullable_rank(monkeypatch):
    connection = _PublishConnection()
    monkeypatch.setattr(repository, "get_oracle_connection", lambda: connection)
    weights = {
        "momentum": 0.30,
        "breadth": 0.25,
        "trend": 0.20,
        "moneyFlow": 0.10,
        "risk": 0.10,
        "dataQuality": 0.05,
    }
    row = {
        "modelVersion": "SECTOR_ROTATION_V3",
        "sectorCode": "AUTO",
        "sectorName": "Auto",
        "latestDataDate": "2026-07-15",
        "eligibleStockCount": 10,
        "validIndicatorCount": 10,
        "momentumScore": 70,
        "breadthScore": 68,
        "trendScore": 72,
        "moneyFlowScore": 60,
        "riskScore": 65,
        "dataQualityScore": 90,
        "finalRotationScore": 69.7,
        "rotationBand": "POSITIVE",
        "rotationPhase": "LEADING",
        "currentRank": None,
        "confidence": "MEDIUM",
        "configuredWeights": weights,
        "effectiveWeights": weights,
    }

    run_id = repository.publish_sector_rotation_v3_snapshot(
        {
            "asOfDate": "2026-07-15",
            "generatedAt": "2026-07-15T18:00:00+00:00",
            "calculationDurationMs": 12.5,
            "rows": [row],
        }
    )

    assert run_id
    run_insert = next(item for item in connection.cursor_instance.executed if "INSERT INTO nse_sector_rot_run_v3" in item[0])
    assert "benchmark_version" in run_insert[0].lower()
    assert run_insert[1]["benchmark_version"] == "NIFTY500_SOURCE_CURRENT"
    snapshot_insert = next(item for item in connection.cursor_instance.executed_many if "nse_sector_rotation_snap_v3" in item[0])
    assert "benchmark_version" in snapshot_insert[0].lower()
    assert snapshot_insert[1][0]["benchmark_version"] == "NIFTY500_SOURCE_CURRENT"
    assert snapshot_insert[1][0]["current_rank"] is None
    assert connection.committed is True
    assert connection.rolled_back is False
    assert connection.closed is True
