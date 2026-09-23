import { describe, expect, test } from 'vitest';
import {
  adaptMarketCapIndexPayload,
  buildNseAutomationView,
  formatLegacyDate,
  formatLegacyNumber,
} from '../src/adapters/databasePageAdapter';
import { NSE_AUTOMATION_PAGE_CONFIGS } from '../src/pages/ops/nseAutomationConfigs';

describe('database page adapters', () => {
  test('formats legacy missing and numeric values without blank table cells', () => {
    expect(formatLegacyNumber(null)).toBe('-');
    expect(formatLegacyNumber('')).toBe('-');
    expect(formatLegacyNumber(1234567.891)).toBe('12,34,567.89');
    expect(formatLegacyDate('2026-05-12T10:30:00Z')).toBe('12-05-2026 10:30:00');
  });

  test('maps NSE Market Cap Index aliases and preserves INDEX/MCAP/MCAP_RANK fallbacks', () => {
    const view = adaptMarketCapIndexPayload({
      status: 'success',
      latestDate: '2026-05-11',
      summary: {
        totalSymbols: 2,
        totalMarketCapCrores: 1250,
        largeSymbols: 1,
        midSymbols: 1,
        smallSymbols: 0,
      },
      data: [
        {
          SYMBOL: 'RELIANCE',
          INDEX: 'LARGE',
          MCAP: 1000.5,
          MCAP_RANK: 1,
          LTC_DATE: '2026-05-11',
          SECURITY_NAME: 'Reliance Industries',
          MCAP_SERIES: 'EQ',
        },
        {
          symbol: 'MISSING',
          securityName: 'Missing Fields Ltd',
        },
      ],
    });

    expect(view.latestDate).toBe('2026-05-11');
    expect(view.rows[0]).toMatchObject({
      index: 'LARGE',
      mcap: '1,000.5',
      mcapRank: '1',
      securityName: 'Reliance Industries',
    });
    expect(view.rows[1]).toMatchObject({
      index: '-',
      mcap: '-',
      mcapRank: '-',
      ltcDate: '-',
    });
  });

  test('keeps NSE Market Cap Index KPI order explicit for the 5x2 grid', () => {
    const view = adaptMarketCapIndexPayload({
      summary: {},
      data: [],
    });

    expect(view.kpis.map((item) => item.label)).toEqual([
      'Total Symbols Count',
      'Total MCap in Crores',
      'Large Cap Total Symbols Count',
      'Mid Cap Total Symbols Count',
      'Small Cap Total Symbols Count',
      'Index Wise Total Symbols Count',
      'Index Wise Total MCap in Crores',
      'Large Cap Total MCap in Crores',
      'Mid Cap Total MCap in Crores',
      'Small Cap Total MCap in Crores',
    ]);
    expect(view.kpis[0]?.value).toBe('-');
    expect(view.kpis[5]?.value).toBe('L:- | M:- | S:-');
  });

  test('builds NSE automation page rows from existing summary payloads without changing endpoint semantics', () => {
    const view = buildNseAutomationView(NSE_AUTOMATION_PAGE_CONFIGS.delivery, {
      data: {
        tradeDateLabel: '12-05-2026',
        mode: 'MANUAL',
        summary: {
          totalRows: 10,
          successRows: 9,
          insertedRows: 8,
          deliveryRows: 7,
          deliveryPctAvg: 55.125,
        },
        rows: [
          {
            symbol: 'TCS',
            status: 'SUCCESS',
            delivery_qty: 12345,
            fetched_timestamp: '2026-05-12T09:15:00Z',
            insertion_source: 'automation',
            inserted_rows: 1,
            series: 'EQ',
            close_price: 3500.25,
            delivery_pct: 62.5,
            traded_qty: 20000,
          },
        ],
      },
    });

    expect(view.kpis.find((item) => item.label === 'Trade Date')?.value).toBe('12-05-2026');
    expect(view.kpis.find((item) => item.label === 'Manual Rows')?.value).toBe('Y');
    expect(view.kpis.find((item) => item.label === 'Automation Rows')?.value).toBe('N');
    expect(view.kpis.find((item) => item.label === 'Delivery Rows')?.value).toBe('7');
    expect(view.rows).toHaveLength(1);
    expect(view.rows[0].cells).toEqual([
      'TCS',
      'SUCCESS',
      '12,345',
      '12-05-2026',
      'AUTOMATION',
      '1',
      'EQ',
      '3,500.25',
      '62.5',
      '20,000',
    ]);
  });

  test('aligns NSE automation card trade date and fetched column to latest row trade date', () => {
    const view = buildNseAutomationView(NSE_AUTOMATION_PAGE_CONFIGS.marketCap, {
      data: {
        tradeDateLabel: '10-06-2026 to 16-06-2026',
        latest_trade_date: '2026-06-16',
        summary: {
          successRows: 947,
          insertedRows: 947,
        },
        rows: [
          {
            symbol: 'ZYDUSWELL',
            status: 'SUCCESS',
            total_mcap_cr: 16720.94,
            trade_date: '2026-06-24',
            fetched_timestamp: '2026-06-25 08:00:00',
            insertion_source: 'NSE_MCAP_FILE',
            inserted_rows: 1,
          },
        ],
      },
    });

    expect(view.kpis.find((item) => item.label === 'Trade Date')?.value).toBe('24-06-2026');
    expect(view.rows[0].cells[3]).toBe('24-06-2026');
  });

  test('uses per-row insertion evidence for NSE automation status cells', () => {
    const mcapView = buildNseAutomationView(NSE_AUTOMATION_PAGE_CONFIGS.marketCap, {
      data: {
        rows: [
          {
            symbol: 'ZYDUSWELL',
            fetch_status: 'FAILED',
            total_mcap_cr: 15317.85,
            inserted_rows: 1,
          },
          {
            symbol: 'SCHNEIDER-BE',
            fetch_status: 'FAILED',
            inserted_rows: 0,
          },
        ],
      },
    });

    const deliveryView = buildNseAutomationView(NSE_AUTOMATION_PAGE_CONFIGS.delivery, {
      data: {
        rows: [
          {
            symbol: 'TCS',
            fetch_status: 'PARTIAL',
            delivery_qty: 12345,
            inserted_rows: 1,
          },
        ],
      },
    });

    expect(mcapView.rows[0].cells[1]).toBe('SUCCESS');
    expect(mcapView.rows[1].cells[1]).toBe('FAILED');
    expect(deliveryView.rows[0].cells[1]).toBe('SUCCESS');
  });
});
