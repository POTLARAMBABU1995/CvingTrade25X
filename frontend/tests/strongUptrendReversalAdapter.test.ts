import { describe, expect, test } from 'vitest';
import {
  adaptStrongUptrendReversalPayload,
  buildStrongUptrendReversalCsv,
  classifySignalFromScore,
  filterStrongUptrendReversalRows,
  formatStrongUptrendValue,
  mergeStrongUptrendMarketCapPayload,
} from '../src/adapters/strongUptrendReversalAdapter';
import { normalizeStrongUptrendReversalError } from '../src/services/api/strongUptrendReversalApi';

const baseRow = {
  SYMBOL: 'RELIANCE',
  INDEX: 'LARGE',
  MCAP: 1900000.25,
  MCAP_RANK: 1,
  TRADING_DATE: '2026-05-14',
  CLOSE: 2948.65,
  EMA20: 2876.2,
  EMA50: 2764.8,
  RSI14: 61.8,
  ADX14: 29.4,
  MACD: 22.45,
  DELIVERY_PCT: 47.8,
  VOLUME: 7854200,
  HH_HL_STRUCTURE: true,
  SUPPORT_CONFIRMED: true,
  BULLISH_REVERSAL_CANDLE: true,
  BREAKOUT_OK: true,
  SCORE: 90,
  SIGNAL: 'STRONG_BUY_SETUP',
  ENTRY_TRIGGER: true,
  ENTRY_PRICE: 2951.6,
  STOP_LOSS: 2844.2,
  TARGET_1: 3025,
  TARGET_2: 3166.4,
  REJECT_REASON: '',
};

describe('strong uptrend reversal adapter', () => {
  test('accepts direct array and nested data.rows payload shapes', () => {
    const direct = adaptStrongUptrendReversalPayload([baseRow]);
    const nested = adaptStrongUptrendReversalPayload({ data: { rows: [baseRow] }, meta: { tradingDate: '2026-05-14' } });

    expect(direct.rows).toHaveLength(1);
    expect(nested.rows).toHaveLength(1);
    expect(nested.meta.tradingDate).toBe('2026-05-14');
  });

  test('keeps optional delivery as null and renders dash formatting', () => {
    const payload = adaptStrongUptrendReversalPayload({
      data: [{ ...baseRow, DELIVERY_PCT: null, SIGNAL: '', SCORE: 72 }],
    });

    expect(payload.rows[0].DELIVERY_PCT).toBeNull();
    expect(payload.rows[0].SIGNAL).toBe('WATCHLIST');
    expect(formatStrongUptrendValue(payload.rows[0].DELIVERY_PCT, { kind: 'percent' })).toBe('-');
  });

  test('normalizes market-cap aliases with dash fallbacks', () => {
    const payload = adaptStrongUptrendReversalPayload({
      data: [
        { ...baseRow, INDEX: undefined, MCAP: undefined, MCAP_RANK: undefined, market_cap_index: 'Mid Cap', marketCapCrores: '1,23,456.78', mcap_rank: '42' },
        { ...baseRow, SYMBOL: 'NO_MCAP', INDEX: '', MCAP: '', MCAP_RANK: '' },
      ],
    });

    expect(payload.rows[0].INDEX).toBe('MID');
    expect(payload.rows[0].MCAP).toBe(123456.78);
    expect(payload.rows[0].MCAP_RANK).toBe(42);
    expect(payload.rows[1].INDEX).toBe('-');
    expect(payload.rows[1].MCAP).toBeNull();
    expect(payload.rows[1].MCAP_RANK).toBeNull();
  });

  test('fills missing market-cap fields from existing market-cap index payload', () => {
    const merged = mergeStrongUptrendMarketCapPayload(
      { data: [{ ...baseRow, SYMBOL: 'NSE:FORTIS-EQ', INDEX: '', MCAP: '', MCAP_RANK: '' }] },
      { data: [{ symbol: 'FORTIS', INDEX: 'MID', MCAP: 73347.958869, MCAP_RANK: 148 }] },
    );
    const payload = adaptStrongUptrendReversalPayload(merged);

    expect(payload.rows[0].SYMBOL).toBe('NSE:FORTIS-EQ');
    expect(payload.rows[0].INDEX).toBe('MID');
    expect(payload.rows[0].MCAP).toBe(73347.958869);
    expect(payload.rows[0].MCAP_RANK).toBe(148);
  });

  test('maps score bands to strategy signals', () => {
    expect(classifySignalFromScore(82)).toBe('STRONG_BUY_SETUP');
    expect(classifySignalFromScore(70)).toBe('WATCHLIST');
    expect(classifySignalFromScore(55)).toBe('WEAK_SETUP');
    expect(classifySignalFromScore(40)).toBe('AVOID');
  });

  test('filters rows by search, signal, and minimum score', () => {
    const rows = adaptStrongUptrendReversalPayload({
      data: [
        baseRow,
        { ...baseRow, SYMBOL: 'TCS', SCORE: 68, SIGNAL: 'WATCHLIST' },
        { ...baseRow, SYMBOL: 'INFY', SCORE: 48, SIGNAL: 'AVOID' },
      ],
    }).rows;

    const filtered = filterStrongUptrendReversalRows(rows, {
      entryTriggerOnly: false,
      search: 'TC',
      signal: 'WATCHLIST',
      minimumScore: '65',
      strongBuyOnly: false,
    });

    expect(filtered).toHaveLength(1);
    expect(filtered[0].SYMBOL).toBe('TCS');
  });

  test('builds CSV from filtered rows only', () => {
    const csv = buildStrongUptrendReversalCsv([
      adaptStrongUptrendReversalPayload({ data: [{ ...baseRow, SYMBOL: 'RELIANCE' }, { ...baseRow, SYMBOL: 'TCS' }] }).rows[1],
    ]);

    expect(csv).toContain('S.NO,SYMBOL,INDEX,MCAP,MCAP_RANK,TRADING_DATE');
    expect(csv).toContain('1,TCS,LARGE,1900000.25,1,2026-05-14');
    expect(csv).not.toContain('RELIANCE');
  });

  test('normalizes non-json transport errors to a friendly message', () => {
    expect(normalizeStrongUptrendReversalError(new SyntaxError('Unexpected token < in JSON at position 0'))).toBe(
      'Strong uptrend scanner is unavailable right now. Please try again.',
    );
  });
});
