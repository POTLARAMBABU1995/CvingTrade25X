import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { StrongUptrendReversalDashboard } from '../src/components/strategy/StrongUptrendReversalDashboard';

const rows = [
  {
    SYMBOL: 'RELIANCE',
    INDEX: 'LARGE',
    MCAP: 1900000.25,
    MCAP_RANK: 1,
    TRADING_DATE: '2026-05-14',
    CLOSE: 2948.65,
    EMA20: 2876.2,
    EMA50: 2764.8,
    EMA100: 2641.4,
    EMA200: 2508.75,
    RSI14: 61.8,
    MACD: 22.45,
    MACD_HIST: 4.6,
    ADX14: 29.4,
    PLUS_DI: 31.2,
    MINUS_DI: 16.9,
    VOLUME: 7854200,
    VOLUME_SMA20: 6123000,
    DELIVERY_PCT: null,
    HH_HL_STRUCTURE: true,
    SUPPORT_CONFIRMED: true,
    BULLISH_REVERSAL_CANDLE: true,
    BREAKOUT_OK: true,
    SCORE: 90,
    SIGNAL: 'STRONG_BUY_SETUP' as const,
    ENTRY_TRIGGER: true,
    ENTRY_PRICE: 2951.6,
    STOP_LOSS: 2844.2,
    TARGET_1: 3025,
    TARGET_2: 3166.4,
    REJECT_REASON: '',
  },
];

describe('StrongUptrendReversalDashboard', () => {
  test('renders KPI cards, sticky columns, and score/signal cells', () => {
    const markup = renderToStaticMarkup(
      <StrongUptrendReversalDashboard
        rows={rows}
        meta={{ tradingDate: '2026-05-14', rows: 1, cacheState: 'MISS' }}
      />,
    );

    expect(markup).toContain('Total Symbols');
    expect(markup.indexOf('strategy-toolbar')).toBeLessThan(markup.indexOf('Total Symbols'));
    expect(markup).toContain('LTC_DATE: 14-05-2026');
    expect(markup).toContain('Strong Buy');
    expect(markup).toContain('Entry Trigger');
    expect(markup).toContain('Export CSV');
    expect(markup).toContain('data-col="sno"');
    expect(markup).toContain('data-col="symbol"');
    expect(markup).toContain('data-col="index"');
    expect(markup).toContain('data-col="mcap"');
    expect(markup).toContain('data-col="mcapRank"');
    expect(markup).toContain('data-sticky-role="sno"');
    expect(markup).toContain('data-sticky-role="symbol"');
    expect(markup).toContain('trend-mcap-index-value--large');
    expect(markup).toContain('MCAP_RANK');
    expect(markup).toContain('Showing 1-1 of 1 symbols');
    expect(markup).toContain('STRONG_BUY_SETUP');
    expect(markup).toContain('delivery_pct');
  });

  test('uses EMA page size pagination for scanner rows', () => {
    const manyRows = Array.from({ length: 16 }, (_, index) => ({
      ...rows[0],
      SYMBOL: index === 15 ? 'PAGE_TWO_ONLY' : `RELIANCE${index + 1}`,
      MCAP_RANK: index + 1,
    }));

    const markup = renderToStaticMarkup(
      <StrongUptrendReversalDashboard
        rows={manyRows}
        meta={{ tradingDate: '2026-05-14', rows: manyRows.length, cacheState: 'MISS' }}
      />,
    );

    expect(markup).toContain('pagination-container');
    expect(markup).toContain('Showing 1-15 of 16 symbols');
    expect(markup).toContain('aria-current="page">1');
    expect(markup).toContain('>2</button>');
    expect(markup).toContain('RELIANCE15');
    expect(markup).not.toContain('PAGE_TWO_ONLY');
  });

  test('renders friendly error state when API is unavailable', () => {
    const markup = renderToStaticMarkup(
      <StrongUptrendReversalDashboard
        rows={[]}
        errorMessage="Strong uptrend scanner is unavailable right now. Please try again."
        meta={{ tradingDate: null, rows: 0 }}
      />,
    );

    expect(markup).toContain('Strong uptrend scanner unavailable');
    expect(markup).toContain('Please try again');
  });
});
