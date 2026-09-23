from pathlib import Path
import importlib
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sector_rotation = importlib.import_module('routes.sector_rotation')
sector_rotation_service = importlib.import_module('services.sector_rotation_service')


def test_service_normalization_keeps_agriculture_sector():
    rows = sector_rotation_service._normalize_sector_rows([
        {
            'sectorCode': 'AGRICULTURE',
            'sectorName': 'Agriculture',
            'indexCode': 'NIFTY_AGRICULTURE',
            'asOfDate': '2026-06-06',
            'totalSymbols': 19,
            'rsi55Pct': 42.0,
            'rsi50Pct': 47.0,
            'sma20Pct': 53.0,
            'sma50Pct': 58.0,
            'sma100Pct': 63.0,
            'breadthComposite': 0.44,
            'confirmedStocks': 8,
            'screenedStocks': 19,
            'stockConfirmationScoreAvg': 0.42,
        }
    ])

    assert len(rows) == 1
    assert rows[0]['sectorCode'] == 'AGRICULTURE'
    assert rows[0]['sectorName'] == 'Agriculture'


def test_route_maps_agriculture_to_strict_table():
    assert sector_rotation._strict_sector_table_name('AGRICULTURE') == 'NSE_NIFTY_AGRICULTURE_STAGING'
    assert sector_rotation._resolve_display_sector_name('AGRICULTURE') == 'Agriculture'


def test_route_maps_alcohol_breweries_to_strict_table():
    assert sector_rotation._strict_sector_table_name('ALCOHOL_BREWERIES') == 'NSE_NIFTY_ALCOHOL_BREWERIES_STAGING'
    assert sector_rotation._resolve_display_sector_name('ALCOHOL_BREWERIES') == 'Alcohol Breweries'


def test_route_maps_auto_mobile_and_auto_ancillaries_to_strict_tables():
    assert sector_rotation._strict_sector_table_name('AUTO') == 'NSE_NIFTY_AUTO_STAGING'
    assert sector_rotation._resolve_display_sector_name('AUTO') == 'Auto Mobile'
    assert sector_rotation._strict_sector_table_name('AUTO_ANCILLARIES') == 'NSE_NIFTY_AUTO_ANCILLARIES_STAGING'
    assert sector_rotation._resolve_display_sector_name('AUTO_ANCILLARIES') == 'Auto Ancillaries'


def test_service_normalization_renames_auto_to_auto_mobile():
    rows = sector_rotation_service._normalize_sector_rows([
        {
            'sectorCode': 'AUTO',
            'sectorName': 'Auto',
            'indexCode': 'NIFTY_AUTO',
            'asOfDate': '2026-06-06',
            'totalSymbols': 18,
            'rsi55Pct': 50.0,
            'rsi50Pct': 55.0,
            'sma20Pct': 60.0,
            'sma50Pct': 65.0,
            'sma100Pct': 70.0,
            'breadthComposite': 0.62,
            'confirmedStocks': 11,
            'screenedStocks': 18,
            'stockConfirmationScoreAvg': 0.58,
        }
    ])

    assert len(rows) == 1
    assert rows[0]['sectorCode'] == 'AUTO'
    assert rows[0]['sectorName'] == 'Auto Mobile'


def test_breadth_supplement_adds_agriculture_row(monkeypatch):
    monkeypatch.setattr(sector_rotation, '_latest_raw_trading_date', lambda: None)
    monkeypatch.setattr(
        sector_rotation,
        '_discover_sector_staging_tables',
        lambda: [
            {
                'sectorCode': 'AGRICULTURE',
                'sectorName': 'Agriculture',
                'tableName': 'NSE_NIFTY_AGRICULTURE_STAGING',
                'stockCount': 19,
            }
        ],
    )
    monkeypatch.setattr(
        sector_rotation,
        '_load_sector_rotation_summary_from_sector_tables',
        lambda: {
            'AGRICULTURE': {
                'sectorCode': 'AGRICULTURE',
                'sectorName': 'Agriculture',
                'totalSymbols': 19,
                'rsi55Pct': 36.84,
                'rsi50Pct': 42.11,
                'sma20Pct': 47.37,
                'sma50Pct': 52.63,
                'sma100Pct': 57.89,
                'breadthComposite': 0.47,
                'confirmedStocks': 9,
                'screenedStocks': 19,
                'stockConfirmationScoreAvg': 0.48,
                'stockConfirmationLabel': 'Moderate',
                'stockConfirmationScreening': 'Moderate (9/19)',
            }
        },
    )

    rows = sector_rotation._supplement_breadth_rows_with_sector_tables([])

    assert len(rows) == 1
    assert rows[0]['sectorCode'] == 'AGRICULTURE'
    assert rows[0]['sectorName'] == 'Agriculture'
    assert rows[0]['tableName'] == 'NSE_NIFTY_AGRICULTURE_STAGING'
    assert rows[0]['totalSymbols'] == 19


def test_breadth_supplement_adds_alcohol_breweries_row(monkeypatch):
    monkeypatch.setattr(sector_rotation, '_latest_raw_trading_date', lambda: None)
    monkeypatch.setattr(
        sector_rotation,
        '_discover_sector_staging_tables',
        lambda: [
            {
                'sectorCode': 'ALCOHOL_BREWERIES',
                'sectorName': 'Alcohol Breweries',
                'tableName': 'NSE_NIFTY_ALCOHOL_BREWERIES_STAGING',
                'stockCount': 18,
            }
        ],
    )
    monkeypatch.setattr(
        sector_rotation,
        '_load_sector_rotation_summary_from_sector_tables',
        lambda: {
            'ALCOHOL_BREWERIES': {
                'sectorCode': 'ALCOHOL_BREWERIES',
                'sectorName': 'Alcohol Breweries',
                'totalSymbols': 18,
                'rsi55Pct': 38.89,
                'rsi50Pct': 44.44,
                'sma20Pct': 50.0,
                'sma50Pct': 55.56,
                'sma100Pct': 61.11,
                'breadthComposite': 0.49,
                'confirmedStocks': 8,
                'screenedStocks': 18,
                'stockConfirmationScoreAvg': 0.44,
                'stockConfirmationLabel': 'Moderate',
                'stockConfirmationScreening': 'Moderate (8/18)',
            }
        },
    )

    rows = sector_rotation._supplement_breadth_rows_with_sector_tables([])

    assert len(rows) == 1
    assert rows[0]['sectorCode'] == 'ALCOHOL_BREWERIES'
    assert rows[0]['sectorName'] == 'Alcohol Breweries'
    assert rows[0]['tableName'] == 'NSE_NIFTY_ALCOHOL_BREWERIES_STAGING'
    assert rows[0]['totalSymbols'] == 18


def test_breadth_supplement_adds_auto_ancillaries_row(monkeypatch):
    monkeypatch.setattr(sector_rotation, '_latest_raw_trading_date', lambda: None)
    monkeypatch.setattr(
        sector_rotation,
        '_discover_sector_staging_tables',
        lambda: [
            {
                'sectorCode': 'AUTO_ANCILLARIES',
                'sectorName': 'Auto Ancillaries',
                'tableName': 'NSE_NIFTY_AUTO_ANCILLARIES_STAGING',
                'stockCount': 25,
            }
        ],
    )
    monkeypatch.setattr(
        sector_rotation,
        '_load_sector_rotation_summary_from_sector_tables',
        lambda: {
            'AUTO_ANCILLARIES': {
                'sectorCode': 'AUTO_ANCILLARIES',
                'sectorName': 'Auto Ancillaries',
                'totalSymbols': 25,
                'rsi55Pct': 36.0,
                'rsi50Pct': 44.0,
                'sma20Pct': 52.0,
                'sma50Pct': 56.0,
                'sma100Pct': 60.0,
                'breadthComposite': 0.48,
                'confirmedStocks': 11,
                'screenedStocks': 25,
                'stockConfirmationScoreAvg': 0.44,
                'stockConfirmationLabel': 'Moderate',
                'stockConfirmationScreening': 'Moderate (11/25)',
            }
        },
    )

    rows = sector_rotation._supplement_breadth_rows_with_sector_tables([])

    assert len(rows) == 1
    assert rows[0]['sectorCode'] == 'AUTO_ANCILLARIES'
    assert rows[0]['sectorName'] == 'Auto Ancillaries'
    assert rows[0]['tableName'] == 'NSE_NIFTY_AUTO_ANCILLARIES_STAGING'
    assert rows[0]['totalSymbols'] == 25


def test_breadth_supplement_rebuilds_stale_summary_for_new_sector(monkeypatch):
    calls: list[bool] = []

    monkeypatch.setattr(sector_rotation, '_latest_raw_trading_date', lambda: None)
    monkeypatch.setattr(
        sector_rotation,
        '_discover_sector_staging_tables',
        lambda: [
            {
                'sectorCode': 'AGRICULTURE',
                'sectorName': 'Agriculture',
                'tableName': 'NSE_NIFTY_AGRICULTURE_STAGING',
                'stockCount': 47,
            }
        ],
    )

    def fake_summary_loader(force_refresh: bool = False):
        calls.append(force_refresh)
        if not force_refresh:
            return {
                'AUTO': {
                    'sectorCode': 'AUTO',
                    'sectorName': 'Auto',
                    'totalSymbols': 15,
                }
            }
        return {
            'AGRICULTURE': {
                'sectorCode': 'AGRICULTURE',
                'sectorName': 'Agriculture',
                'totalSymbols': 47,
                'rsi55Pct': 23.53,
                'rsi50Pct': 41.18,
                'sma20Pct': 6.38,
                'sma50Pct': 17.02,
                'sma100Pct': 12.77,
                'breadthComposite': 0.25,
                'confirmedStocks': 3,
                'screenedStocks': 47,
                'stockConfirmationScoreAvg': 0.06,
                'stockConfirmationLabel': 'Weak',
                'stockConfirmationScreening': 'Weak (3/47)',
            }
        }

    monkeypatch.setattr(sector_rotation, '_load_sector_rotation_summary_from_sector_tables', fake_summary_loader)

    rows = sector_rotation._supplement_breadth_rows_with_sector_tables([])

    assert calls == [False, True]
    assert len(rows) == 1
    assert rows[0]['sectorCode'] == 'AGRICULTURE'
    assert rows[0]['totalSymbols'] == 47


class _SummaryCursor:
    def __init__(self, rows):
        self._rows = rows
        self.description = [
            ('stock',),
            ('tradingDate',),
            ('closePrice',),
            ('closeLag55',),
            ('sma20',),
            ('sma50',),
            ('sma100',),
            ('rsi14',),
        ]
        self.arraysize = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _sql, _binds):
        return None

    def fetchall(self):
        return list(self._rows)


class _SummaryConnection:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _SummaryCursor(self._rows)

    def close(self):
        return None


def test_sector_rotation_summary_uses_staging_totals_for_totalstocks(monkeypatch):
    monkeypatch.setattr(
        sector_rotation,
        '_discover_sector_staging_tables',
        lambda: [
            {
                'sectorCode': 'AGRICULTURE',
                'sectorName': 'Agriculture',
                'tableName': 'NSE_NIFTY_AGRICULTURE_STAGING',
                'stockCount': 3,
            }
        ],
    )
    monkeypatch.setattr(sector_rotation, '_raw_sma_source', lambda: ('NSE_NIFTY500_DAILY_RAW_DATA_DEV', 'CLOSE_PRICE'))
    monkeypatch.setattr(sector_rotation, '_load_strict_sector_symbols', lambda _sector: ['AAA', 'BBB', 'CCC'])
    monkeypatch.setattr(sector_rotation, '_load_strict_sector_symbol_lookups', lambda _sector: set())
    monkeypatch.setattr(sector_rotation, '_symbol_variants', lambda symbols: list(symbols))
    monkeypatch.setattr(
        sector_rotation,
        'get_oracle_connection',
        lambda: _SummaryConnection([
            ('AAA', '2026-06-30', 100.0, 90.0, 95.0, 94.0, 93.0, 60.0),
            ('BBB', '2026-06-30', 110.0, 100.0, 105.0, 104.0, 103.0, 58.0),
        ]),
    )

    summary = sector_rotation._load_sector_rotation_summary_from_sector_tables(force_refresh=True)

    agriculture = summary['AGRICULTURE']
    assert agriculture['totalSymbols'] == 3
    assert agriculture['totalStocks'] == 3
    assert agriculture['availableSymbols'] == 2


def test_breadth_supplement_uses_summary_totalstocks_for_display(monkeypatch):
    monkeypatch.setattr(sector_rotation, '_latest_raw_trading_date', lambda: None)
    monkeypatch.setattr(
        sector_rotation,
        '_discover_sector_staging_tables',
        lambda: [
            {
                'sectorCode': 'AGRICULTURE',
                'sectorName': 'Agriculture',
                'tableName': 'NSE_NIFTY_AGRICULTURE_STAGING',
                'stockCount': 47,
            }
        ],
    )
    monkeypatch.setattr(
        sector_rotation,
        '_load_sector_rotation_summary_from_sector_tables',
        lambda force_refresh=False: {
            'AGRICULTURE': {
                'sectorCode': 'AGRICULTURE',
                'sectorName': 'Agriculture',
                'totalSymbols': 47,
                'totalStocks': 47,
                'availableSymbols': 5,
                'rsi55Pct': 23.53,
                'rsi50Pct': 41.18,
                'sma20Pct': 6.38,
                'sma50Pct': 17.02,
                'sma100Pct': 12.77,
                'breadthComposite': 0.25,
                'confirmedStocks': 3,
                'screenedStocks': 47,
                'stockConfirmationScoreAvg': 0.06,
                'stockConfirmationLabel': 'Weak',
                'stockConfirmationScreening': 'Weak (3/47)',
            }
        },
    )

    rows = sector_rotation._supplement_breadth_rows_with_sector_tables([])

    assert len(rows) == 1
    assert rows[0]['sectorCode'] == 'AGRICULTURE'
    assert rows[0]['totalSymbols'] == 47
    assert rows[0]['totalStocks'] == 47
    assert rows[0]['availableSymbols'] == 5


def test_breadth_supplement_prefers_staging_count_when_summary_is_partial(monkeypatch):
    monkeypatch.setattr(sector_rotation, '_latest_raw_trading_date', lambda: None)
    monkeypatch.setattr(
        sector_rotation,
        '_discover_sector_staging_tables',
        lambda: [
            {
                'sectorCode': 'PSU_BANK',
                'sectorName': 'PSU Bank',
                'tableName': 'NSE_NIFTY_PSU_BANK_STAGING',
                'stockCount': 12,
            }
        ],
    )
    monkeypatch.setattr(
        sector_rotation,
        '_load_sector_rotation_summary_from_sector_tables',
        lambda force_refresh=False: {
            'PSU_BANK': {
                'sectorCode': 'PSU_BANK',
                'sectorName': 'PSU Bank',
                'totalSymbols': 1,
                'totalStocks': 1,
                'availableSymbols': 1,
                'rsi55Pct': 0,
                'rsi50Pct': 100,
                'sma20Pct': 100,
                'sma50Pct': 0,
                'sma100Pct': 0,
                'breadthComposite': 0.25,
                'confirmedStocks': 0,
                'screenedStocks': 1,
                'stockConfirmationScoreAvg': 0,
                'stockConfirmationLabel': 'Weak',
                'stockConfirmationScreening': 'Weak (0/1)',
            }
        },
    )

    rows = sector_rotation._supplement_breadth_rows_with_sector_tables([
        {'sectorCode': 'PSU_BANK', 'sectorName': 'PSU Bank', 'totalStocks': 1, 'totalSymbols': 1}
    ])

    assert len(rows) == 1
    assert rows[0]['sectorCode'] == 'PSU_BANK'
    assert rows[0]['tableName'] == 'NSE_NIFTY_PSU_BANK_STAGING'
    assert rows[0]['totalStocks'] == 12
    assert rows[0]['totalSymbols'] == 12
    assert rows[0]['availableSymbols'] == 1
    assert rows[0]['screenedStocks'] == 12
