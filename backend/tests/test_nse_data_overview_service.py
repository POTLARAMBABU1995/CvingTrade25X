import datetime as dt
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SERVICES_ROOT = BACKEND_ROOT / 'services'
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICES_ROOT))

import services.nse_data_overview_service as service


def test_build_overview_returns_hierarchical_counts():
    selected_date = dt.date(2026, 3, 19)

    class FakeCursor:
        def __init__(self):
            self.description = []
            self._rows = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            normalized = ' '.join(str(sql).split())
            if 'COUNT(*) total_records' in normalized:
                self.description = [('TOTAL_RECORDS',), ('TOTAL_SYMBOLS',), ('TOTAL_TRADE_DATES',), ('EARLIEST_TRADE_DATE',), ('LATEST_TRADE_DATE',), ('LATEST_FETCH_TS',)]
                self._rows = [(120, 6, 10, dt.date(2020, 1, 1), selected_date, dt.datetime(2026, 3, 19, 15, 30, 0))]
                return
            if 'COUNT(*) daily_records' in normalized:
                self.description = [('DAILY_RECORDS',), ('DAILY_STOCKS',)]
                self._rows = [(12, 6)]
                return
            if "GROUP BY EXTRACT(YEAR FROM trade_date)" in normalized:
                self.description = [('BUCKET_YEAR',), ('TRADE_DAYS',), ('RECORDS_COUNT',), ('STOCKS_COUNT',), ('LATEST_TRADE_DATE',)]
                self._rows = [
                    (2026, 10, 120, 6, selected_date),
                    (2025, 4, 50, 5, dt.date(2025, 12, 31)),
                ]
                return
            if "GROUP BY EXTRACT(MONTH FROM trade_date)" in normalized:
                self.description = [('BUCKET_MONTH',), ('FIRST_TRADE_DATE',), ('TRADE_DAYS',), ('RECORDS_COUNT',), ('STOCKS_COUNT',), ('LATEST_TRADE_DATE',)]
                self._rows = [
                    (3, dt.date(2026, 3, 3), 8, 96, 6, selected_date),
                    (2, dt.date(2026, 2, 3), 2, 24, 6, dt.date(2026, 2, 28)),
                ]
                return
            if "GROUP BY TRUNC(trade_date, 'IW')" in normalized:
                self.description = [('WEEK_START',), ('FIRST_TRADE_DATE',), ('LATEST_TRADE_DATE',), ('TRADE_DAYS',), ('RECORDS_COUNT',), ('STOCKS_COUNT',)]
                self._rows = [
                    (dt.date(2026, 3, 16), dt.date(2026, 3, 16), selected_date, 4, 48, 6),
                    (dt.date(2026, 3, 9), dt.date(2026, 3, 9), dt.date(2026, 3, 13), 5, 60, 6),
                ]
                return
            if 'WHERE trade_date BETWEEN :week_start AND :week_end' in normalized:
                self.description = [('TRADE_DATE',), ('RECORDS_COUNT',), ('STOCKS_COUNT',)]
                self._rows = [
                    (selected_date, 12, 6),
                    (dt.date(2026, 3, 18), 12, 6),
                ]
                return
            raise AssertionError(f'Unexpected SQL: {sql}')

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return list(self._rows)

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    result = service.build_overview(FakeConn(), 'CVING_NSE_MARKET_CAP_HIST', selected_date)

    assert result['stocksCount'] == 6
    assert result['recordsCount'] == 120
    assert result['earliestTradeDate'] == '2020-01-01'
    assert result['latestTradeDate'] == '2026-03-19'
    assert result['tableStocksCount'] == 6
    assert result['tableRecordsCount'] == 120
    assert result['tableFromDate'] == '2020-01-01'
    assert result['tableToDate'] == '2026-03-19'
    assert result['yearlyData'] == 2
    assert result['monthlyData'] == 2
    assert result['weeklyData'] == 2
    assert result['dailyData'] == 12
    assert result['selectedDateHasData'] is True
    assert result['years'][0]['isSelected'] is True
    assert result['months'][0]['label'] == 'Mar 2026'
    assert result['weeks'][0]['label'] == '16 Mar - 19 Mar'
    assert result['days'][0]['isSelected'] is True


def test_build_overview_handles_empty_tables():
    class FakeCursor:
        def __init__(self):
            self.description = []
            self._rows = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            self.description = [('TOTAL_RECORDS',), ('TOTAL_SYMBOLS',), ('TOTAL_TRADE_DATES',), ('EARLIEST_TRADE_DATE',), ('LATEST_TRADE_DATE',), ('LATEST_FETCH_TS',)]
            self._rows = [(0, 0, 0, None, None, None)]

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return list(self._rows)

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    result = service.build_overview(FakeConn(), 'CVING_NSE_MARKET_CAP_HIST', dt.date(2026, 3, 19))

    assert result['stocksCount'] == 0
    assert result['recordsCount'] == 0
    assert result['earliestTradeDate'] == ''
    assert result['tableStocksCount'] == 0
    assert result['tableRecordsCount'] == 0
    assert result['tableFromDate'] == ''
    assert result['tableToDate'] == ''
    assert result['yearlyData'] == 0
    assert result['months'] == []
    assert result['selectedDateHasData'] is False


def test_build_overview_accepts_string_dates_from_db_and_inputs():
    selected_date = '2026-03-19'

    class FakeCursor:
        def __init__(self):
            self.description = []
            self._rows = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            normalized = ' '.join(str(sql).split())
            if 'COUNT(*) total_records' in normalized and 'WHERE trade_date BETWEEN :start_date AND :end_date' not in normalized:
                self.description = [('TOTAL_RECORDS',), ('TOTAL_SYMBOLS',), ('TOTAL_TRADE_DATES',), ('EARLIEST_TRADE_DATE',), ('LATEST_TRADE_DATE',), ('LATEST_FETCH_TS',)]
                self._rows = [(120, 6, 10, '2020-01-01', '2026-03-19', '2026-03-19 15:30:00')]
                return
            if 'COUNT(*) total_records' in normalized and 'WHERE trade_date BETWEEN :start_date AND :end_date' in normalized:
                self.description = [('TOTAL_RECORDS',), ('TOTAL_SYMBOLS',), ('TOTAL_TRADE_DATES',), ('EARLIEST_TRADE_DATE',), ('LATEST_TRADE_DATE',), ('LATEST_FETCH_TS',)]
                self._rows = [(96, 6, 8, '2026-03-03', '2026-03-19', '2026-03-19 15:30:00')]
                return
            if 'COUNT(*) daily_records' in normalized:
                self.description = [('DAILY_RECORDS',), ('DAILY_STOCKS',)]
                self._rows = [(12, 6)]
                return
            if "GROUP BY EXTRACT(YEAR FROM trade_date)" in normalized:
                self.description = [('BUCKET_YEAR',), ('TRADE_DAYS',), ('RECORDS_COUNT',), ('STOCKS_COUNT',), ('LATEST_TRADE_DATE',)]
                self._rows = [(2026, 10, 120, 6, '2026-03-19')]
                return
            if "GROUP BY EXTRACT(MONTH FROM trade_date)" in normalized:
                self.description = [('BUCKET_MONTH',), ('FIRST_TRADE_DATE',), ('TRADE_DAYS',), ('RECORDS_COUNT',), ('STOCKS_COUNT',), ('LATEST_TRADE_DATE',)]
                self._rows = [(3, '2026-03-03', 8, 96, 6, '2026-03-19')]
                return
            if "GROUP BY TRUNC(trade_date, 'IW')" in normalized:
                self.description = [('WEEK_START',), ('FIRST_TRADE_DATE',), ('LATEST_TRADE_DATE',), ('TRADE_DAYS',), ('RECORDS_COUNT',), ('STOCKS_COUNT',)]
                self._rows = [('2026-03-16', '2026-03-16', '2026-03-19', 4, 48, 6)]
                return
            if 'trade_date BETWEEN :week_start AND :week_end' in normalized:
                self.description = [('TRADE_DATE',), ('RECORDS_COUNT',), ('STOCKS_COUNT',)]
                self._rows = [('2026-03-19', 12, 6)]
                return
            raise AssertionError(f'Unexpected SQL: {sql}')

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return list(self._rows)

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    result = service.build_overview(FakeConn(), 'CVING_NSE_MARKET_CAP_HIST', selected_date, start_date='2026-03-01', end_date='2026-03-31')

    assert result['stocksCount'] == 6
    assert result['recordsCount'] == 96
    assert result['earliestTradeDate'] == '2026-03-03'
    assert result['latestTradeDate'] == '2026-03-19'
    assert result['tableStocksCount'] == 6
    assert result['tableRecordsCount'] == 120
    assert result['tableFromDate'] == '2020-01-01'
    assert result['tableToDate'] == '2026-03-19'
    assert result['selectedTradeDate'] == '2026-03-19'
    assert result['weeks'][0]['label'] == '16 Mar - 19 Mar'
