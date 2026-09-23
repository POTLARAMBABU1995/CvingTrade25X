from pathlib import Path
import sys
import types
from datetime import date


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

db_pool_stub = types.ModuleType('db_pool')
db_pool_stub.pool = types.SimpleNamespace(acquire=lambda: None)
db_pool_stub.fetchall_dict = lambda _cur: []
sys.modules['db_pool'] = db_pool_stub

cache_stub = types.ModuleType('cache')


class _DummyTTLCache:
    def __init__(self, *args, **kwargs):
        self._store = {}

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value):
        self._store[key] = value


cache_stub.TTLCache = _DummyTTLCache
sys.modules['cache'] = cache_stub

import services.delivery_service as delivery_service
sys.modules.pop('cache', None)


def test_resolve_ltc_date_falls_back_to_trading_date():
    row = {'ltc_date': None, 'trading_date': date(2026, 4, 23)}
    assert delivery_service._resolve_ltc_date_iso(row) == '2026-04-23'


def test_build_cte_sql_uses_filtered_date_rank_for_snapshot_path():
    projection = {
        'symbol_col': 'SYMBOL',
        'date_col': 'TRADING_DATE',
        'qty_col': 'DELIVERY_QTY',
        'pct_col': 'DELIVERY_PCT',
        'price_col': None,
        'status_col': None,
        'fetch_ts_col': None,
        'updated_ts_col': None,
        'id_col': None,
        'table_sql': 'CVING_NSE_DELIVERY_HIST',
    }

    cte_sql = delivery_service._build_cte_sql(
        projection=projection,
        price_source=None,
        filter_sql='',
        source_filter_sql='',
        recent_td_limit=None,
        use_filtered_date_rank=True,
    )

    normalized = ' '.join(cte_sql.split()).upper()
    assert 'FROM DELIVERY_BASE DB_DATES' in normalized
    assert 'FROM CVING_NSE_DELIVERY_HIST SRC_DATE' not in normalized


def test_build_cte_sql_limits_delivery_raw_for_recent_latest_path():
    projection = {
        'symbol_col': 'SYMBOL',
        'date_col': 'TRADING_DATE',
        'qty_col': 'DELIVERY_QTY',
        'pct_col': 'DELIVERY_PCT',
        'price_col': None,
        'status_col': None,
        'fetch_ts_col': None,
        'updated_ts_col': None,
        'id_col': None,
        'table_sql': 'CVING_NSE_DELIVERY_HIST',
    }

    cte_sql = delivery_service._build_cte_sql(
        projection=projection,
        price_source=None,
        filter_sql='',
        source_filter_sql='',
        recent_td_limit=25,
        use_filtered_date_rank=False,
    )

    normalized = ' '.join(cte_sql.split()).upper()
    assert 'CAST(SRC.TRADING_DATE AS DATE) >=' in normalized
    assert 'FROM CVING_NSE_DELIVERY_HIST SRC_RECENT' in normalized
    assert 'RECENT_DATES.T_D <= :RECENT_TD_LIMIT' in normalized


def test_inline_latest_summary_is_only_for_unfiltered_latest_page():
    assert delivery_service._should_inline_latest_summary(
        snapshot_enabled=False,
        latest_only=True,
        symbol=None,
        min_delivery_pct=None,
        min_delivery_score=None,
        strong_only=False,
        delivery_status=None,
    ) is True

    assert delivery_service._should_inline_latest_summary(
        snapshot_enabled=False,
        latest_only=True,
        symbol='RELIANCE',
        min_delivery_pct=None,
        min_delivery_score=None,
        strong_only=False,
        delivery_status=None,
    ) is False

    assert delivery_service._should_inline_latest_summary(
        snapshot_enabled=False,
        latest_only=True,
        symbol=None,
        min_delivery_pct=None,
        min_delivery_score=70,
        strong_only=False,
        delivery_status=None,
    ) is False
