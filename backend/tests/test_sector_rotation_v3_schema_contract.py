from __future__ import annotations

from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _sql(name: str) -> str:
    return (BACKEND_ROOT / "sql" / name).read_text(encoding="utf-8").upper()


def test_v3_schema_is_additive_and_covers_publisher_required_columns():
    create_sql = _sql("create_sector_rotation_v3_schema.sql")
    rollback_sql = _sql("rollback_sector_rotation_v3_schema.sql")

    assert "BENCHMARK_VERSION" in create_sql
    assert "MISSING_MONEY_FLOW_PENALTY" in create_sql
    assert "'DATA_WEAK'" in create_sql
    assert "CURRENT_RANK IS NULL OR CURRENT_RANK > 0" in create_sql
    assert "DROP_TABLE_IF_EXISTS('NSE_SECTOR_ROTATION_SNAP_V3')" in rollback_sql
    assert "NSE_SECTOR_ROTATION_SNAP_V2" not in create_sql
    assert "NSE_SECTOR_ROTATION_SNAP_V2" not in rollback_sql
    assert "TRUNCATE TABLE" not in create_sql
    assert "DELETE FROM" not in create_sql


def test_v3_validation_accounts_for_required_factors_and_flow_penalty():
    validate_sql = _sql("validate_sector_rotation_v3_schema.sql")

    assert "CFG.MISSING_MONEY_FLOW_PENALTY" in validate_sql
    assert "'MOMENTUM', 'BREADTH', 'TREND', 'RISK', 'DATA_QUALITY'" in validate_sql
    assert "NON-POSITIVE CURRENT RANK" in validate_sql
    assert "DUPLICATE CURRENT RANKS WITHIN ONE RUN" in validate_sql
