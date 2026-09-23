from pathlib import Path
import importlib
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sector_hierarchy_service = importlib.import_module('services.sector_hierarchy_service')


def setup_function(_):
    sector_hierarchy_service.clear_cache()


def test_get_parents_returns_healthcare_and_cache_hit(monkeypatch):
    calls = {'count': 0}

    def _fake_fetch_rows(_sql, _binds=None):
        calls['count'] += 1
        return [
            {'parent_sector': 'Healthcare', 'stock_count': 56},
            {'parent_sector': 'Utilities', 'stock_count': 20},
        ]

    monkeypatch.setattr(sector_hierarchy_service, '_fetch_rows', _fake_fetch_rows)

    first = sector_hierarchy_service.get_parents(refresh=False)
    second = sector_hierarchy_service.get_parents(refresh=False)

    assert first['metadata']['cached'] is False
    assert first['metadata']['totalParents'] == 2
    assert first['data'][0]['parentSector'] == 'Healthcare'
    assert second['metadata']['cached'] is True
    assert calls['count'] == 1


def test_get_parents_refresh_bypasses_cache(monkeypatch):
    calls = {'count': 0}

    def _fake_fetch_rows(_sql, _binds=None):
        calls['count'] += 1
        return [{'parent_sector': 'Healthcare', 'stock_count': 56}]

    monkeypatch.setattr(sector_hierarchy_service, '_fetch_rows', _fake_fetch_rows)

    sector_hierarchy_service.get_parents(refresh=False)
    refreshed = sector_hierarchy_service.get_parents(refresh=True)

    assert refreshed['metadata']['cached'] is False
    assert calls['count'] == 2


def test_get_industries_for_healthcare(monkeypatch):
    monkeypatch.setattr(
        sector_hierarchy_service,
        '_fetch_rows',
        lambda _sql, _binds=None: [
            {
                'parent_sector': 'Healthcare',
                'industry_sector': 'Pharmaceuticals',
                'stock_count': 36,
            }
        ],
    )

    payload = sector_hierarchy_service.get_industries(parent_sector='Healthcare', refresh=False)

    assert payload['metadata']['cached'] is False
    assert payload['data'][0]['industrySector'] == 'Pharmaceuticals'
    assert payload['data'][0]['stockCount'] == 36


def test_get_sub_sectors_for_healthcare_pharma(monkeypatch):
    monkeypatch.setattr(
        sector_hierarchy_service,
        '_fetch_rows',
        lambda _sql, _binds=None: [
            {
                'parent_sector': 'Healthcare',
                'industry_sector': 'Pharmaceuticals',
                'sub_sector': 'Formulations & Generics',
                'stock_count': 16,
            }
        ],
    )

    payload = sector_hierarchy_service.get_sub_sectors(
        parent_sector='Healthcare',
        industry_sector='Pharmaceuticals',
        refresh=False,
    )

    assert payload['data'][0]['subSector'] == 'Formulations & Generics'
    assert payload['data'][0]['stockCount'] == 16


def test_get_stocks_filter_combination(monkeypatch):
    monkeypatch.setattr(
        sector_hierarchy_service,
        '_fetch_rows',
        lambda _sql, _binds=None: [
            {
                'parent_sector': 'Healthcare',
                'industry_sector': 'Pharmaceuticals',
                'sub_sector': 'Formulations & Generics',
                'symbol': 'SUNPHARMA',
                'exchange': 'NSE',
            },
            {
                'parent_sector': 'Healthcare',
                'industry_sector': 'Pharmaceuticals',
                'sub_sector': 'Formulations & Generics',
                'symbol': 'CIPLA',
                'exchange': 'NSE',
            },
        ],
    )

    payload = sector_hierarchy_service.get_stocks(
        parent_sector='Healthcare',
        industry_sector='Pharmaceuticals',
        sub_sector='Formulations & Generics',
        refresh=False,
    )

    assert payload['data']['totalStocks'] == 2
    assert payload['data']['stocks'][0]['symbol'] == 'SUNPHARMA'


def test_get_stocks_includes_enriched_marketcap_fields(monkeypatch):
    monkeypatch.setattr(
        sector_hierarchy_service,
        '_fetch_rows',
        lambda _sql, _binds=None: [
            {
                'parent_sector': 'Healthcare',
                'industry_sector': 'Pharmaceuticals',
                'sub_sector': 'Pharma Segment',
                'symbol': 'SUNPHARMA',
                'exchange': 'NSE',
            }
        ],
    )
    monkeypatch.setattr(
        sector_hierarchy_service,
        '_enrich_stock_rows_with_marketcap',
        lambda rows: [
            {
                **rows[0],
                'index': 'LARGE',
                'mcap': 12345.67,
                'mcapRank': 11,
            }
        ],
    )

    payload = sector_hierarchy_service.get_stocks(
        parent_sector='Healthcare',
        industry_sector='Pharmaceuticals',
        sub_sector='Pharma Segment',
        refresh=True,
    )

    first = payload['data']['stocks'][0]
    assert first['index'] == 'LARGE'
    assert first['mcap'] == 12345.67
    assert first['mcapRank'] == 11


def test_primary_hierarchy_queries_dedupe_parent_symbol_before_counts():
    normalized_cte = ' '.join(sector_hierarchy_service._SQL_ACTIVE_BASE_CTE.split())
    assert 'ROW_NUMBER() OVER' in normalized_cte
    assert 'PARTITION BY PARENT_SECTOR, SYMBOL' in normalized_cte
    assert 'BUCKET_PRIORITY DESC' in normalized_cte
    assert "LIKE '%PHARMA%'" in normalized_cte

    for sql in [
        sector_hierarchy_service._SQL_PARENTS,
        sector_hierarchy_service._SQL_INDUSTRIES,
        sector_hierarchy_service._SQL_SUB_SECTORS,
        sector_hierarchy_service._SQL_STOCKS,
        sector_hierarchy_service._SQL_TOTAL_BY_PARENT,
        sector_hierarchy_service._SQL_SUMMARY_ROWS,
        sector_hierarchy_service._SQL_TREE_ROWS,
    ]:
        normalized_sql = ' '.join(sql.split())
        assert 'FROM active_data' in normalized_sql
        assert 'FROM VW_NSE_SECTOR_HIERARCHY_ACTIVE' not in normalized_sql.split('active_data AS', 1)[-1]


def test_fallback_cte_uses_merged_healthcare_sources_and_pharma_priority():
    cte = sector_hierarchy_service._SQL_FB_BASE_CTE
    assert 'NSE_NIFTY_HEALTHCARE_INDEX_STAGING' in cte
    assert 'NSE_NIFTY500_HEALTHCARE_STAGING' in cte
    assert 'NSE_NIFTY_MIDSMALL_HEALTHCARE_STAGING' in cte
    assert 'NSE_NIFTY_PHARMA_STAGING' in cte
    assert '100 AS SOURCE_PRIORITY' in cte
    assert 'MARKSANS' not in cte


def test_get_summary_builds_expected_structure(monkeypatch):
    monkeypatch.setattr(
        sector_hierarchy_service,
        '_fetch_single_value',
        lambda _sql, _binds: 56,
    )
    monkeypatch.setattr(
        sector_hierarchy_service,
        '_fetch_rows',
        lambda _sql, _binds=None: [
            {
                'industry_sector': 'Pharmaceuticals',
                'sub_sector': 'Formulations & Generics',
                'stock_count': 16,
            },
            {
                'industry_sector': 'Pharmaceuticals',
                'sub_sector': 'API / CDMO',
                'stock_count': 8,
            },
        ],
    )

    payload = sector_hierarchy_service.get_summary(parent_sector='Healthcare', refresh=False)

    assert payload['data']['parentSector'] == 'Healthcare'
    assert payload['data']['totalStocks'] == 56
    assert payload['data']['industries'][0]['industrySector'] == 'Pharmaceuticals'


def test_sql_injection_like_input_is_passed_as_bind(monkeypatch):
    observed_binds = {}

    def _fake_fetch_rows(_sql, binds=None):
        observed_binds.update(binds or {})
        return []

    monkeypatch.setattr(sector_hierarchy_service, '_fetch_rows', _fake_fetch_rows)

    payload = sector_hierarchy_service.get_stocks(
        parent_sector="Healthcare' OR 1=1 --",
        industry_sector=None,
        sub_sector=None,
        refresh=False,
    )

    assert payload['data']['totalStocks'] == 0
    assert observed_binds['parent_sector'] == "Healthcare' OR 1=1 --"


def test_missing_hierarchy_view_degrades_to_empty_payload(monkeypatch):
    def _raise_missing_object(_sql, _binds=None):
        raise Exception('ORA-00942: table or view does not exist')

    monkeypatch.setattr(sector_hierarchy_service, '_fetch_rows', _raise_missing_object)

    payload = sector_hierarchy_service.get_parents(refresh=True)

    assert payload['metadata']['cached'] is False
    assert payload['metadata']['totalParents'] == 0
    assert payload['data'] == []
