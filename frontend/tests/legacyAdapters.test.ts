import { describe, expect, test } from 'vitest';
import {
  adaptDeliveryWireRow,
  adaptMarketCapWireRow,
  adaptTechnicalIndicatorWireRow,
} from '../src/services/marketdata/legacyAdapters';

describe('legacy market-data adapters', () => {
  test('adapts market-cap wire rows without renaming backend keys in the contract layer', () => {
    const row = adaptMarketCapWireRow({
      SYMBOL: 'RELIANCE',
      INDEX: 'LARGE',
      MCAP: '1985420',
      MCAP_RANK: '1',
      FFMC: 1450000,
      LTC_DATE: '2026-05-12',
      PRICE: '2948.55',
      VOLUME: '1823400',
    });

    expect(row).toEqual({
      symbol: 'RELIANCE',
      companyName: null,
      sector: null,
      index: 'LARGE',
      tradingDate: null,
      price: 2948.55,
      change: null,
      changePct: null,
      volume: 1823400,
      ltcDate: '2026-05-12',
      totalMcap: 1985420,
      freeFloatMcap: 1450000,
      mcapRank: 1,
      sharesOutstanding: null,
    });
  });

  test('adapts technical indicator wire rows to a typed view model', () => {
    const row = adaptTechnicalIndicatorWireRow({
      SYMBOL: 'TCS',
      TRADING_DATE: '2026-05-12',
      PRICE: 4102.2,
      EMA20: 4020.4,
      EMA50: 3955.1,
      EMA100: 3820.8,
      EMA200: 3610.2,
      RSI50: 57.2,
      ADX14: 28.4,
      ATR14: 82.5,
      TREND_DIRECTION: 'UP',
      SCORE: 86,
      SIGNALSCORE: 91,
    });

    expect(row.symbol).toBe('TCS');
    expect(row.tradingDate).toBe('2026-05-12');
    expect(row.ema20).toBe(4020.4);
    expect(row.rsi50).toBe(57.2);
    expect(row.trendDirection).toBe('UP');
    expect(row.signalScore).toBe(91);
  });

  test('adapts delivery wire rows and preserves nullable values', () => {
    const row = adaptDeliveryWireRow({
      SYMBOL: 'NTPC',
      LTC_DATE: '2026-05-12',
      DELIVERY_QTY: '445000',
      DELIVERY_PCT: '58.4',
      DELIVERY_SCORE: null,
      PRICE: '421.9',
      VOLUME: '901200',
    });

    expect(row.deliveryQty).toBe(445000);
    expect(row.deliveryPct).toBe(58.4);
    expect(row.deliveryScore).toBeNull();
    expect(row.price).toBe(421.9);
  });
});
