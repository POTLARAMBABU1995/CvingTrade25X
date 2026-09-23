from pathlib import Path
import importlib
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sector_rotation = importlib.import_module('routes.sector_rotation')


class _DummyCache:
    def __init__(self):
        self._store = {}

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value):
        self._store[key] = value


def test_sector_rotation_supplement_keeps_pharma_separate_from_healthcare(monkeypatch):
    monkeypatch.setattr(sector_rotation, '_latest_raw_trading_date', lambda: None)
    monkeypatch.setattr(
        sector_rotation,
        '_discover_sector_staging_tables',
        lambda: [
            {
                'sectorCode': 'HEALTHCARE_INDEX',
                'sectorName': 'Healthcare Index',
                'tableName': 'NSE_NIFTY_HEALTHCARE_INDEX_STAGING',
                'stockCount': 71,
            },
            {
                'sectorCode': 'NIFTY500_HEALTHCARE',
                'sectorName': 'Nifty500 Healthcare',
                'tableName': 'NSE_NIFTY500_HEALTHCARE_STAGING',
                'stockCount': 50,
            },
            {
                'sectorCode': 'MIDSMALL_HEALTHCARE',
                'sectorName': 'Midsmall Healthcare',
                'tableName': 'NSE_NIFTY_MIDSMALL_HEALTHCARE_STAGING',
                'stockCount': 30,
            },
            {
                'sectorCode': 'POWER',
                'sectorName': 'Power',
                'tableName': 'NSE_NIFTY_POWER_STAGING',
                'stockCount': 21,
            },
            {
                'sectorCode': 'FIN_SERV',
                'sectorName': 'Fin Serv',
                'tableName': 'NSE_NIFTY_FINANCIAL_SERVICES_STAGING',
                'stockCount': 121,
            },
            {
                'sectorCode': 'OIL_GAS',
                'sectorName': 'Oil Gas',
                'tableName': 'NSE_NIFTY_OIL_AND_GAS_STAGING',
                'stockCount': 20,
            },
            {
                'sectorCode': 'PHARMA',
                'sectorName': 'Pharma',
                'tableName': 'NSE_NIFTY_PHARMA_STAGING',
                'stockCount': 20,
            },
            {
                'sectorCode': 'TELECOM',
                'sectorName': 'Telecom',
                'tableName': 'NSE_NIFTY_TELECOMMUNICATION_STAGING',
                'stockCount': 13,
            },
        ],
    )
    monkeypatch.setattr(
        sector_rotation,
        '_load_sector_rotation_summary_from_sector_tables',
        lambda: {
            'HEALTHCARE': {
                'sectorCode': 'HEALTHCARE',
                'sectorName': 'Healthcare',
                'totalSymbols': 52,
                'rsi55Pct': 90.28,
                'rsi50Pct': 93.06,
                'sma20Pct': 84.72,
                'sma50Pct': 98.61,
                'sma100Pct': 87.5,
                'breadthComposite': 0.636667,
                'confirmedStocks': 40,
                'screenedStocks': 52,
                'stockConfirmationScoreAvg': 0.769231,
                'stockConfirmationLabel': 'Strong',
                'stockConfirmationScreening': 'Strong (40/52)',
            },
            'PHARMA': {
                'sectorCode': 'PHARMA',
                'sectorName': 'Pharma',
                'totalSymbols': 20,
                'rsi55Pct': 88.0,
                'rsi50Pct': 84.0,
                'sma20Pct': 81.0,
                'sma50Pct': 79.0,
                'sma100Pct': 76.0,
                'breadthComposite': 0.55,
                'confirmedStocks': 16,
                'screenedStocks': 20,
                'stockConfirmationScoreAvg': 0.8,
                'stockConfirmationLabel': 'Strong',
                'stockConfirmationScreening': 'Strong (16/20)',
            },
            'POWER': {
                'totalSymbols': 21,
                'breadthComposite': 0.5,
            },
            'FINANCIAL_SERVICES': {
                'totalSymbols': 121,
                'breadthComposite': 0.5,
            },
            'OIL_AND_GAS': {
                'totalSymbols': 20,
                'breadthComposite': 0.5,
            },
            'TELECOMMUNICATION': {
                'totalSymbols': 13,
                'breadthComposite': 0.5,
            },
        },
    )

    rows = sector_rotation._supplement_breadth_rows_with_sector_tables([
        {'sectorCode': 'AUTO', 'sectorName': 'Auto', 'asOfDate': '2026-05-15'},
        {'sectorCode': 'FIN_SERV', 'sectorName': 'Fin Serv', 'totalSymbols': 121},
        {'sectorCode': 'FINANCIAL_SERVICES', 'sectorName': 'Financial Services', 'totalSymbols': 121},
        {'sectorCode': 'HEALTHCARE', 'sectorName': 'Healthcare', 'totalSymbols': 36},
        {'sectorCode': 'HEALTHCARE_INDEX', 'sectorName': 'Healthcare Index', 'totalSymbols': 71},
        {'sectorCode': 'NIFTY500_HEALTHCARE', 'sectorName': 'Nifty500 Healthcare', 'totalSymbols': 50},
        {'sectorCode': 'MIDSMALL_HEALTHCARE', 'sectorName': 'Midsmall Healthcare', 'totalSymbols': 30},
        {'sectorCode': 'OIL_GAS', 'sectorName': 'Oil Gas', 'totalSymbols': 20},
        {'sectorCode': 'OIL_AND_GAS', 'sectorName': 'Oil & Gas', 'totalSymbols': 20},
        {'sectorCode': 'PHARMA', 'sectorName': 'Pharma', 'totalSymbols': 20},
        {'sectorCode': 'TELECOM', 'sectorName': 'Telecom', 'totalSymbols': 13},
        {'sectorCode': 'TELECOMMUNICATION', 'sectorName': 'Telecommunication', 'totalSymbols': 13},
    ])

    codes = [row['sectorCode'] for row in rows]
    assert codes.count('HEALTHCARE') == 1
    assert 'HEALTHCARE_INDEX' not in codes
    assert 'NIFTY500_HEALTHCARE' not in codes
    assert 'MIDSMALL_HEALTHCARE' not in codes
    assert codes.count('PHARMA') == 1
    assert codes.count('FINANCIAL_SERVICES') == 1
    assert 'FIN_SERV' not in codes
    assert codes.count('OIL_AND_GAS') == 1
    assert 'OIL_GAS' not in codes
    assert codes.count('TELECOMMUNICATION') == 1
    assert 'TELECOM' not in codes

    healthcare = next(row for row in rows if row['sectorCode'] == 'HEALTHCARE')
    assert healthcare['sectorName'] == 'Healthcare'
    assert healthcare['tableName'] == 'MERGED_HEALTHCARE_STAGING'
    assert healthcare['totalSymbols'] == 52
    assert healthcare['screenedStocks'] == 52

    pharma = next(row for row in rows if row['sectorCode'] == 'PHARMA')
    assert pharma['sectorName'] == 'Pharma'
    assert pharma['tableName'] == 'NSE_NIFTY_PHARMA_STAGING'
    assert pharma['totalSymbols'] == 20
    assert pharma['screenedStocks'] == 20


def test_merged_healthcare_payload_excludes_pharma_symbols(monkeypatch):
    monkeypatch.setattr(sector_rotation, '_popup_cache', _DummyCache())
    monkeypatch.setattr(
        sector_rotation,
        '_load_strict_sector_symbols',
        lambda sector: ['SUNPHARMA', 'CIPLA'] if str(sector).upper() == 'PHARMA' else [],
    )

    rows_by_sector = {
        'HEALTHCARE_INDEX': [
            {'stock': 'SUNPHARMA', 'ltcDate': '2026-05-21'},
            {'stock': 'APOLLOHOSP', 'ltcDate': '2026-05-21'},
        ],
        'NIFTY500_HEALTHCARE': [
            {'stock': 'CIPLA', 'ltcDate': '2026-05-21'},
            {'stock': 'FORTIS', 'ltcDate': '2026-05-21'},
        ],
        'MIDSMALL_HEALTHCARE': [
            {'stock': 'RAINBOW', 'ltcDate': '2026-05-21'},
            {'stock': 'SUNPHARMA', 'ltcDate': '2026-05-21'},
        ],
    }

    def _fake_sector_wise_payload(*, sector_code, **_kwargs):
        rows = rows_by_sector.get(str(sector_code).upper(), [])
        return {
            'rows': rows,
            'source': f'mock:{sector_code}',
            'totalCount': len(rows),
            'totalRows': len(rows),
            'totalPages': 1,
        }

    monkeypatch.setattr(sector_rotation, '_load_sector_wise_payload', _fake_sector_wise_payload)

    payload = sector_rotation._load_merged_sector_wise_payload(
        canonical_sector='HEALTHCARE',
        page=1,
        page_size=200,
        sort_key='STOCK',
        sort_dir='ASC',
        search_text='',
        force_refresh=False,
        allow_fast_path=False,
    )

    stocks = [row['stock'] for row in payload['rows']]
    assert stocks == ['APOLLOHOSP', 'FORTIS', 'RAINBOW']
    assert payload['totalCount'] == 3
    assert payload['sectorName'] == 'Healthcare'
