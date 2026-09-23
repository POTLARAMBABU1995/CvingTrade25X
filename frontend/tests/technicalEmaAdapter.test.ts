import { describe, expect, test } from 'vitest';
import {
  adaptEmaTrendPayload,
  adaptEmaTrendRow,
  buildEmaColumns,
  buildTenureOptions,
  filterEmaRowsBySymbol,
  getLatestLtcDateKey,
} from '../src/adapters/technicalEmaAdapter';
import type { EmaTrendPayloadWire, EmaTrendWireRow } from '../src/types/api/technical';

describe('technical EMA adapter', () => {
  test('maps wire row values into legacy-safe display cells', () => {
    const row: EmaTrendWireRow = {
      SYMBOL: '360ONE',
      INDEX: null,
      MCAP: null,
      MCAP_RANK: null,
      ATH: 1318,
      PRICE: 1115.3,
      GAP: '-15.38%',
      TRADING_DATE: '2019-09-19',
      LTC_DATE: '11-05-2026',
      tradingDays: 1653,
      d5: '4.58%',
      d5Sort: 4.5757,
      y1: '-2.10%',
      y1Sort: -2.1,
    };

    const adapted = adaptEmaTrendRow(row, 0);

    expect(adapted.symbol).toBe('360ONE');
    expect(adapted.cells.sNo.text).toBe('1');
    expect(adapted.cells.index.text).toBe('-');
    expect(adapted.cells.mcap.text).toBe('-');
    expect(adapted.cells.mcapRank.text).toBe('-');
    expect(adapted.cells.ath.text).toBe('1,318');
    expect(adapted.cells.price.sort).toBe(1115.3);
    expect(adapted.cells.price.tone).toBe('positive');
    expect(adapted.cells.gap.text).toBe('-15.38%');
    expect(adapted.cells.gap.tone).toBe('negative');
    expect(adapted.cells.tradingDate.text).toBe('19-09-2019');
    expect(adapted.cells.ltcDate.text).toBe('11-05-2026');
    expect(adapted.cells.tradingDays.text).toBe('1653');
    expect(adapted.cells.d5.text).toBe('4.58%');
    expect(adapted.cells.d5.sort).toBe(4.5757);
    expect(adapted.cells.d5.tone).toBe('positive');
    expect(adapted.cells.y1.tone).toBe('negative');
  });

  test('formats market-cap fields with index tone and dash fallbacks', () => {
    const adapted = adaptEmaTrendRow({
      symbol: 'MIDCAPCO',
      index: 'Nifty Midcap 150',
      totalMcap: '123456.789',
      mcap_rank: '42.4',
    }, 4);

    expect(adapted.cells.index.text).toBe('MID');
    expect(adapted.cells.index.tone).toBe('mid');
    expect(adapted.cells.mcap.text).toBe('1,23,456.79');
    expect(adapted.cells.mcap.sort).toBe(123456.789);
    expect(adapted.cells.mcapRank.text).toBe('42');
  });

  test('adapts exact EMA table keys and filters by symbol only', () => {
    const payload: EmaTrendPayloadWire = {
      timeframe: 'weekly',
      ema20: [{ symbol: 'RELIANCE', companyName: 'Different text' }],
      ema50: [{ symbol: 'TCS' }],
      ema200: [],
      ema200100: [],
      ema20010050: [],
      ema2001005020: [],
    };

    const adapted = adaptEmaTrendPayload(payload);
    expect(adapted.timeframe).toBe('weekly');
    expect(adapted.tables.ema20).toHaveLength(1);
    expect(adapted.tables.ema50).toHaveLength(1);
    expect(filterEmaRowsBySymbol(adapted.tables.ema20, 'rel')).toHaveLength(1);
    expect(filterEmaRowsBySymbol(adapted.tables.ema20, 'Different')).toHaveLength(0);
  });

  test('derives latest LTC date and tenure counts from legacy row fields', () => {
    const payload: EmaTrendPayloadWire = {
      ema20: [
        { symbol: 'AAA', tradingDate: '2019-09-19', ltcDate: '11-05-2026' },
        { symbol: 'BBB', tradingDate: '2023-01-02', ltcDate: '10-05-2026' },
      ],
    };

    expect(getLatestLtcDateKey(payload)).toBe('2026-05-11');
    const options = buildTenureOptions(payload);
    expect(options.find((option) => option.value === 6)?.count).toBe(1);
    expect(options.find((option) => option.value === 3)?.count).toBe(1);
  });

  test('builds dynamic year return columns from backend payload metadata and row keys', () => {
    const payload: EmaTrendPayloadWire = {
      yearReturnColumns: [
        { key: 'y1', label: '1Y', years: 1 },
        { key: 'y28', label: '28Y', years: 28 },
      ],
      yearReturnMaxYear: 28,
      ema20: [
        { symbol: 'ABB', y27: '150.00%', y27Sort: 150, y28: '175.00%', y28Sort: 175 },
      ],
    };

    const columns = buildEmaColumns(payload);
    const adapted = adaptEmaTrendPayload(payload);

    expect(columns.some((column) => column.key === 'y28' && column.label === '28Y')).toBe(true);
    expect(adapted.tables.ema20[0].cells.y27.text).toBe('150.00%');
    expect(adapted.tables.ema20[0].cells.y28.text).toBe('175.00%');
    expect(adapted.tables.ema20[0].cells.y28.sort).toBe(175);
    expect(buildTenureOptions(payload).some((option) => option.value === 28)).toBe(true);
  });
});
