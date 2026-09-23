import datetime as dt
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SERVICES_ROOT = BACKEND_ROOT / 'services'
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICES_ROOT))

import services.nse_existing_csv_symbol_service as svc


def test_parse_requested_symbols_normalizes_and_dedupes():
    parsed = svc.parse_requested_symbols('NSE:ITC-EQ, reliance ,ITC,INFY.NS')
    assert parsed == ['ITC', 'RELIANCE', 'INFY']


def test_load_valid_symbols_supports_path_without_extension(tmp_path):
    symbol_file = tmp_path / 'symbols_nifty500.csv'
    symbol_file.write_text('symbol\nNSE:ITC-EQ\nRELIANCE\n', encoding='utf-8')

    loaded = svc.load_valid_symbols(str(tmp_path / 'symbols_nifty500'))

    assert loaded == {'ITC', 'RELIANCE'}


def test_process_existing_csv_for_symbols_builds_expected_summary(tmp_path):
    csv_one = tmp_path / 'mcap23042026.csv'
    csv_two = tmp_path / 'mcap24042026.csv'
    csv_one.write_text('SYMBOL,MARKETCAPRS\nITC,10\n', encoding='utf-8')
    csv_two.write_text('SYMBOL,MARKETCAPRS\nRELIANCE,20\n', encoding='utf-8')

    symbol_file = tmp_path / 'symbols_nifty500.csv'
    symbol_file.write_text('symbol\nITC\nRELIANCE\n', encoding='utf-8')

    def parse_trade_date(path: Path):
        if '23042026' in path.name:
            return dt.date(2026, 4, 23)
        if '24042026' in path.name:
            return dt.date(2026, 4, 24)
        return None

    def inspect_csv(csv_path, trade_date, eq_only=True, allowed_symbols=None):
        symbol = 'ITC' if '23042026' in csv_path.name else 'RELIANCE'
        matched = bool(allowed_symbols and symbol in allowed_symbols)
        return {
            'matchedRows': 1 if matched else 0,
            'matchedSymbols': [symbol] if matched else [],
        }

    def load_csv(csv_path, trade_date, eq_only=True, allowed_symbols=None, line_logger=None):
        return {
            'loadedCount': 2,
            'alreadyLoadedCount': 1,
        }

    config = svc.ExistingCsvDatasetConfig(
        dataset_type='market_cap',
        download_dir=tmp_path,
        parse_trade_date=parse_trade_date,
        inspect_csv=inspect_csv,
        load_csv=load_csv,
    )

    result = svc.process_existing_csv_for_symbols(
        'ITC,RELIANCE,INVALID',
        config,
        symbol_file_path=str(symbol_file),
    )

    assert result['status'] == 'success'
    assert result['requested_count'] == 3
    assert result['valid_symbols'] == ['ITC', 'RELIANCE']
    assert result['invalid_symbols'] == ['INVALID']
    assert result['symbols_found_in_csv'] == ['ITC', 'RELIANCE']
    assert result['records_inserted'] == 4
    assert result['records_skipped_existing'] == 2


def test_process_existing_csv_for_symbols_supports_load_result_matching(tmp_path):
    csv_one = tmp_path / 'delivery_23042026.csv'
    csv_two = tmp_path / 'delivery_24042026.csv'
    csv_one.write_text('SYMBOL,DELIV_QTY\nITC,10\n', encoding='utf-8')
    csv_two.write_text('SYMBOL,DELIV_QTY\nRELIANCE,20\n', encoding='utf-8')

    symbol_file = tmp_path / 'symbols_nifty500.csv'
    symbol_file.write_text('symbol\nITC\nRELIANCE\n', encoding='utf-8')

    def parse_trade_date(path: Path):
        if '23042026' in path.name:
            return dt.date(2026, 4, 23)
        if '24042026' in path.name:
            return dt.date(2026, 4, 24)
        return None

    def inspect_csv(*args, **kwargs):
        raise AssertionError('inspect_csv should not be called when load-result matching is enabled')

    def load_csv(csv_path, trade_date, eq_only=True, allowed_symbols=None, line_logger=None):
        symbol = 'ITC' if '23042026' in csv_path.name else 'RELIANCE'
        matched = bool(allowed_symbols and symbol in allowed_symbols)
        return {
            'matchedRows': 1 if matched else 0,
            'matchedSymbols': [symbol] if matched else [],
            'loadedCount': 3,
            'alreadyLoadedCount': 2,
        }

    config = svc.ExistingCsvDatasetConfig(
        dataset_type='delivery_data',
        download_dir=tmp_path,
        parse_trade_date=parse_trade_date,
        inspect_csv=inspect_csv,
        load_csv=load_csv,
        use_load_result_for_matching=True,
    )

    result = svc.process_existing_csv_for_symbols(
        ['ITC', 'RELIANCE', 'INVALID'],
        config,
        symbol_file_path=str(symbol_file),
    )

    assert result['status'] == 'success'
    assert result['valid_symbols'] == ['ITC', 'RELIANCE']
    assert result['invalid_symbols'] == ['INVALID']
    assert result['symbols_found_in_csv'] == ['ITC', 'RELIANCE']
    assert result['records_inserted'] == 6
    assert result['records_skipped_existing'] == 4
