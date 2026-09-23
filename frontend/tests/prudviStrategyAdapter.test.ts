import { describe, expect, test } from 'vitest';
import {
  adaptPrudviStrategyPayload,
  calculatePrudviKpiCounts,
  filterPrudviRows,
  isPrudviTrendQualifiedRow,
  isStrongPrudviUptrendRow,
  PRUDVI_CONDITION_KPI_FLAGS,
  PRUDVI_COLUMNS,
  prioritizePrudviRowsForDisplay,
  prudviScoreTone,
} from '../src/adapters/prudviStrategyAdapter';

const requiredColumnOrder = [
  'S.NO',
  'SYMBOL',
  'INDEX',
  'MCAP',
  'MCAP_RANK',
  'ATH',
  'PRICE',
  'GAP',
  'LTC_DATE',
  'SUPPORT',
  'RESISTANCE',
  'SUPPORT_REACTION',
  'SUPPORT_CANDLE',
  'CANDLE_DIRECTION',
  'SUPPORT_REVERSAL',
  'BULLISH_CANDLE',
  'EMA>20',
  'EMA>50',
  'RSI>50',
  'ADX>25',
  'MACD>0',
  'VOLUME>20',
  'DELIVERY%>60',
  'TREND',
  'TREND_SCORE',
];

describe('prudvi strategy adapter', () => {
  test('keeps the required column order exactly', () => {
    expect(PRUDVI_COLUMNS.map((column) => column.label)).toEqual(requiredColumnOrder);
  });

  test('normalizes market-cap aliases and Y/N/- flags', () => {
    const payload = adaptPrudviStrategyPayload({
      data: [
        {
          SYMBOL: 'RELIANCE',
          marketCapCategory: 'Mid Cap',
          marketCapCrores: '1,23,456.78',
          mcap_rank: '42',
          ATH: '3025.50',
          PRICE: '2948.65',
          GAP: '-2.54%',
          LTC_DATE: '2026-05-15',
          SUPPORT: '2850',
          RESISTANCE: '3025',
          SUPPORT_REACTION: 'bounce',
          SUPPORT_CANDLE: 'hammer',
          CANDLE_DIRECTION: 'bullish',
          SUPPORT_REVERSAL: 'Y',
          BULLISH_CANDLE: true,
          EMA_GT_20: 'Y',
          EMA_GT_50: 'N',
          RSI_GT_50: '',
          ADX_GT_25: '1',
          MACD_GT_0: '0',
          VOLUME_GT_20: 'yes',
          DELIVERY_GT_60: 'no',
          TREND: 'Strong Uptrend',
          TREND_SCORE: 92,
        },
      ],
      meta: { rows: 1, tradingDate: '2026-05-14' },
    });

    expect(payload.rows[0]).toMatchObject({
      SYMBOL: 'RELIANCE',
      INDEX: 'MID',
      MCAP: 123456.78,
      MCAP_RANK: 42,
      ATH: 3025.5,
      PRICE: 2948.65,
      GAP: -2.54,
      LTC_DATE: '15-05-2026',
      SUPPORT: '2850',
      RESISTANCE: '3025',
      SUPPORT_REACTION: 'BOUNCE',
      SUPPORT_CANDLE: 'HAMMER',
      CANDLE_DIRECTION: 'BULLISH',
      SUPPORT_REVERSAL: 'Y',
      BULLISH_CANDLE: 'Y',
      EMA_GT_20: 'Y',
      EMA_GT_50: 'N',
      RSI_GT_50: '-',
      ADX_GT_25: 'Y',
      MACD_GT_0: 'N',
      VOLUME_GT_20: 'Y',
      DELIVERY_GT_60: 'N',
      TREND: 'UPTREND',
      TREND_SCORE: 92,
    });
  });

  test('filters by symbol, trend, and minimum score', () => {
    const rows = adaptPrudviStrategyPayload({
      data: [
        { SYMBOL: 'RELIANCE', TREND: 'UPTREND', TREND_SCORE: 92 },
        { SYMBOL: 'TCS', TREND: 'CONSOLIDATION', TREND_SCORE: 66 },
      ],
    }).rows;

    expect(filterPrudviRows(rows, { search: 'rel', trend: 'UPTREND', minimumScore: '80' })).toHaveLength(1);
    expect(filterPrudviRows(rows, { search: '', trend: 'UPTREND', minimumScore: '95' })).toHaveLength(0);
  });

  test('keeps condition KPI cards in the required order', () => {
    expect(PRUDVI_CONDITION_KPI_FLAGS.map((item) => item.label)).toEqual([
      'BULLISH_CANDLE',
      'EMA>20',
      'EMA>50',
      'RSI>50',
      'ADX>25',
      'MACD>0',
      'VOLUME>20',
      'DELIVERY%>60',
    ]);
  });

  test('applies mandatory trend flag qualification before display filtering', () => {
    const rows = adaptPrudviStrategyPayload({
      data: [
        { SYMBOL: 'PASS', EMA_GT_20: 'Y', EMA_GT_50: 'Y', RSI_GT_50: 'Y', ADX_GT_25: 'Y', MACD_GT_0: 'Y' },
        { SYMBOL: 'FAIL_EMA20', EMA_GT_20: 'N', EMA_GT_50: 'Y', RSI_GT_50: 'Y', ADX_GT_25: 'Y', MACD_GT_0: 'Y' },
        { SYMBOL: 'FAIL_EMA50', EMA_GT_20: 'Y', EMA_GT_50: 'N', RSI_GT_50: 'Y', ADX_GT_25: 'Y', MACD_GT_0: 'Y' },
        { SYMBOL: 'FAIL_RSI', EMA_GT_20: 'Y', EMA_GT_50: 'Y', RSI_GT_50: 'N', ADX_GT_25: 'Y', MACD_GT_0: 'Y' },
        { SYMBOL: 'FAIL_ADX', EMA_GT_20: 'Y', EMA_GT_50: 'Y', RSI_GT_50: 'Y', ADX_GT_25: 'N', MACD_GT_0: 'Y' },
        { SYMBOL: 'FAIL_MACD', EMA_GT_20: 'Y', EMA_GT_50: 'Y', RSI_GT_50: 'Y', ADX_GT_25: 'Y', MACD_GT_0: 'N' },
      ],
    }).rows;

    expect(rows.filter(isPrudviTrendQualifiedRow).map((item) => item.SYMBOL)).toEqual(['PASS']);
  });

  test('calculates KPI counts from the full loaded dataset', () => {
    const rows = adaptPrudviStrategyPayload({
      data: [
        {
          SYMBOL: 'PASS',
          BULLISH_CANDLE: 'Y',
          EMA_GT_20: 'Y',
          EMA_GT_50: 'Y',
          RSI_GT_50: 'Y',
          ADX_GT_25: 'Y',
          MACD_GT_0: 'Y',
          VOLUME_GT_20: 'Y',
          DELIVERY_GT_60: 'Y',
        },
        {
          SYMBOL: 'FAIL',
          BULLISH_CANDLE: 'N',
          EMA_GT_20: 'Y',
          EMA_GT_50: 'Y',
          RSI_GT_50: 'Y',
          ADX_GT_25: 'N',
          MACD_GT_0: 'Y',
          VOLUME_GT_20: 'N',
          DELIVERY_GT_60: 'N',
        },
      ],
    }).rows;
    const counts = calculatePrudviKpiCounts(rows);

    expect(counts.totalStocksLoaded).toBe(2);
    expect(counts.trendQualifiedStocks).toBe(1);
    expect(counts.filteredOutStocks).toBe(1);
    expect(counts.flagCounts.EMA_GT_20).toBe(2);
    expect(counts.flagCounts.ADX_GT_25).toBe(1);
    expect(counts.flagCounts.BULLISH_CANDLE).toBe(1);
  });

  test('prioritizes strong uptrend rows for first-page display', () => {
    const rows = adaptPrudviStrategyPayload({
      data: [
        { SYMBOL: 'BETA', TREND: 'DOWNTREND', TREND_SCORE: 91 },
        { SYMBOL: 'ALPHA', TREND: 'UPTREND', TREND_SCORE: 82, SUPPORT_REVERSAL: 'Y' },
        { SYMBOL: 'GAMMA', TREND: 'UPTREND', TREND_SCORE: 72 },
      ],
    }).rows;

    expect(isStrongPrudviUptrendRow(rows[1])).toBe(true);
    expect(prioritizePrudviRowsForDisplay(rows).map((item) => item.SYMBOL)).toEqual(['ALPHA', 'GAMMA', 'BETA']);
  });

  test('maps score bands to required tones', () => {
    expect(prudviScoreTone(80)).toBe('green');
    expect(prudviScoreTone(65)).toBe('amber');
    expect(prudviScoreTone(50)).toBe('blue');
    expect(prudviScoreTone(49)).toBe('muted');
  });
});
