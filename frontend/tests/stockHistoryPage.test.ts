import { describe, expect, test } from 'vitest';
import {
  buildStockHistorySyncCards,
  formatStockHistoryLtcDate,
  resolveStockHistoryTotalRows,
  resolveStockHistoryTotalStocks,
  resolveStockHistoryTotalTradingDays,
} from '../src/pages/ops/StockHistoryPage';

describe('StockHistoryPage sync KPI fallback', () => {
  test('uses total rows as synched rows when backend sync fields are not present and nothing is pending', () => {
    expect(buildStockHistorySyncCards({
      stock_eod_record_count: 2922,
      stock_eod_synched_rows: null,
      stock_eod_unsynched_rows: null,
      stock_eod_pending_dev_count: 0,
    })).toEqual({
      synchedRows: 2922,
      unsynchedRows: 0,
    });
  });

  test('derives synched and unsynched rows from pending count for older stats payloads', () => {
    expect(buildStockHistorySyncCards({
      stock_eod_record_count: 2922,
      stock_eod_pending_dev_count: 1235,
    })).toEqual({
      synchedRows: 1687,
      unsynchedRows: 1235,
    });
  });
});

describe('StockHistoryPage latest LTC date formatting', () => {
  test('formats backend HTTP date strings as DD-MM-YYYY only', () => {
    expect(formatStockHistoryLtcDate('Wed, 24 Jun 2026 00:00:00 GMT')).toBe('24-06-2026');
  });

  test('formats ISO latest dates as DD-MM-YYYY only', () => {
    expect(formatStockHistoryLtcDate('2026-06-24T00:00:00Z')).toBe('24-06-2026');
    expect(formatStockHistoryLtcDate('2026-06-24')).toBe('24-06-2026');
  });
});

describe('StockHistoryPage KPI resolution', () => {
  test('reads total stocks from stock-history stats payload keys', () => {
    expect(resolveStockHistoryTotalStocks({
      stock_eod_stock_count: 944,
    }, [
      { stocks: 4 },
    ])).toBe(944);
  });

  test('falls back to the latest table stock count when stats payload is wrapped or missing', () => {
    expect(resolveStockHistoryTotalStocks({}, [
      { stocks: 944, latest_trade_date: '2026-06-29' },
      { stocks: 940, latest_trade_date: '2026-06-28' },
    ])).toBe(944);
  });

  test('reads total rows from stock-history record count aliases', () => {
    expect(resolveStockHistoryTotalRows({
      stock_eod_record_count: 250869,
    })).toBe(250869);
  });

  test('falls back to table trading-day totals when stats payload is wrapped or missing', () => {
    expect(resolveStockHistoryTotalTradingDays({}, [
      { total_no_of_trading_days: 1 },
      { total_no_of_trading_days: 5 },
    ])).toBe(5);
  });
});
