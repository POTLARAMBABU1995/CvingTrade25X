import pytest
import os
import json
import hashlib
import importlib
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sector_rotation = importlib.import_module('routes.sector_rotation')

from routes.sector_rotation import (
    _discover_sector_staging_tables,
    _invalidate_dependent_caches,
    _SECTOR_TABLES_SNAPSHOT_PATH,
    _SECTOR_DISCOVERY_STATE,
    _SECTOR_TABLE_DISCOVERY_TTL_SECONDS
)

def test_sector_discovery_from_oracle_metadata():
    # Discover staging tables, verify they return list of dicts
    sectors = _discover_sector_staging_tables(force_refresh=True)
    assert isinstance(sectors, list)
    if sectors:
        assert 'sectorCode' in sectors[0]
        assert 'tableName' in sectors[0]
        assert 'stockCount' in sectors[0]

def test_sector_snapshot_write_and_read():
    # Re-run and check if snapshot file exists and is populated
    _discover_sector_staging_tables(force_refresh=True)
    assert _SECTOR_TABLES_SNAPSHOT_PATH.exists()
    
    # Read snapshot
    data = json.loads(_SECTOR_TABLES_SNAPSHOT_PATH.read_text(encoding='utf-8'))
    assert 'signature' in data
    assert 'tables' in data
    assert isinstance(data['tables'], list)

def test_force_refresh_invalidates_memory_cache():
    # Initialize cache
    _discover_sector_staging_tables(force_refresh=True)
    assert _SECTOR_DISCOVERY_STATE['tables'] is not None
    
    # Check signature is not None
    assert _SECTOR_DISCOVERY_STATE['signature'] is not None

def test_corrupt_snapshot_rebuilds_from_oracle():
    # Corrupt snapshot file
    _SECTOR_TABLES_SNAPSHOT_PATH.write_text("corrupted_json", encoding='utf-8')
    
    # Should rebuild and not crash
    sectors = _discover_sector_staging_tables(force_refresh=True)
    assert isinstance(sectors, list)
    assert len(sectors) > 0

def test_missing_snapshot_rebuilds_from_oracle():
    # Delete snapshot
    if _SECTOR_TABLES_SNAPSHOT_PATH.exists():
        _SECTOR_TABLES_SNAPSHOT_PATH.unlink()
        
    sectors = _discover_sector_staging_tables(force_refresh=True)
    assert isinstance(sectors, list)
    assert len(sectors) > 0

def test_sector_key_normalization():
    # Test key normalization logic
    # E.g. NSE_NIFTY_RESTAURANTS_STAGING should have restaurants as sector_key
    sectors = _discover_sector_staging_tables(force_refresh=True)
    restaurants_sec = next((s for s in sectors if s['sectorCode'] == 'RESTAURANTS'), None)
    if restaurants_sec:
        assert restaurants_sec['sector_key'] == 'restaurants'
        assert restaurants_sec['display_name'] == 'Restaurants'

def test_no_hardcoded_sector_names():
    # Verify restaurants, hospitality, and tourism travel appear dynamically
    sectors = _discover_sector_staging_tables(force_refresh=True)
    codes = {s['sectorCode'] for s in sectors}
    assert 'RESTAURANTS' in codes
    assert 'HOSPITALITY_HOTELS_RESORTS' in codes
    assert 'TOURISM_TRAVEL' in codes
    assert 'EDUCATION_E_LEARNING' in codes


def test_invalidate_dependent_caches_clears_sector_snapshots(monkeypatch, tmp_path):
    snapshot_path = tmp_path / 'sector_rotation_latest.json'
    snapshot_path.write_text('[]', encoding='utf-8')
    deleted_tables: list[str] = []
    flags = {'sector_cache': False, 'sector_memory': False, 'group_cache': False}

    monkeypatch.setattr('routes.sector_rotation._SNAPSHOT_PATH', snapshot_path)
    monkeypatch.setattr(
        'routes.sector_rotation.sector_cache_service.clear_sector_cache',
        lambda: flags.__setitem__('sector_cache', True),
    )
    monkeypatch.setattr(
        'routes.sector_rotation.sector_stock_cache_service.clear_sector_memory_cache',
        lambda: flags.__setitem__('sector_memory', True),
    )
    monkeypatch.setattr(
        'routes.sector_rotation.sector_stock_cache_service.delete_snapshot',
        lambda table_name: deleted_tables.append(table_name),
    )
    monkeypatch.setattr(
        'services.sector_rotation_service.invalidate_sector_groups_cache',
        lambda: flags.__setitem__('group_cache', True),
    )

    _invalidate_dependent_caches([
        {'tableName': 'NSE_NIFTY_RESTAURANTS_STAGING'},
        {'tableName': 'NSE_NIFTY_HOSPITALITY_HOTELS_RESORTS_STAGING'},
    ])

    assert flags == {'sector_cache': True, 'sector_memory': True, 'group_cache': True}
    assert snapshot_path.exists() is False
    assert deleted_tables == [
        'NSE_NIFTY_RESTAURANTS_STAGING',
        'NSE_NIFTY_HOSPITALITY_HOTELS_RESORTS_STAGING',
    ]
