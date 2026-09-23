from pathlib import Path
import importlib
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sector_rotation = importlib.import_module('routes.sector_rotation')
sector_rotation_service = importlib.import_module('services.sector_rotation_service')


def test_service_normalization_keeps_rubber_products_tyres_sector():
    rows = sector_rotation_service._normalize_sector_rows([
        {
            'sectorCode': 'RUBBER_PRODUCTS_TYRES',
            'sectorName': 'Rubber Products Tyres',
            'indexCode': 'NIFTY_RUBBER_PRODUCTS_TYRES',
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
    assert rows[0]['sectorCode'] == 'RUBBER_PRODUCTS_TYRES'
    assert rows[0]['sectorName'] == 'Rubber Products Tyres'


def test_route_maps_rubber_products_tyres_to_strict_table():
    assert sector_rotation._strict_sector_table_name('RUBBER_PRODUCTS_TYRES') == 'NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING'
    assert sector_rotation._resolve_display_sector_name('RUBBER_PRODUCTS_TYRES') == 'Rubber Products Tyres'


def test_breadth_supplement_adds_rubber_products_tyres_row(monkeypatch):
    monkeypatch.setattr(sector_rotation, '_latest_raw_trading_date', lambda: None)
    monkeypatch.setattr(
        sector_rotation,
        '_discover_sector_staging_tables',
        lambda: [
            {
                'sectorCode': 'RUBBER_PRODUCTS_TYRES',
                'sectorName': 'Rubber Products Tyres',
                'tableName': 'NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING',
                'stockCount': 19,
            }
        ],
    )
    monkeypatch.setattr(
        sector_rotation,
        '_load_sector_rotation_summary_from_sector_tables',
        lambda: {
            'RUBBER_PRODUCTS_TYRES': {
                'sectorCode': 'RUBBER_PRODUCTS_TYRES',
                'sectorName': 'Rubber Products Tyres',
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
    assert rows[0]['sectorCode'] == 'RUBBER_PRODUCTS_TYRES'
    assert rows[0]['sectorName'] == 'Rubber Products Tyres'
    assert rows[0]['tableName'] == 'NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING'
    assert rows[0]['totalSymbols'] == 19

