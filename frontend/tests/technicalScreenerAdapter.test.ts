import { describe, expect, test } from 'vitest';
import {
  adaptTechnicalScreenerPayload,
  TECHNICAL_SCREENER_CONFIGS,
} from '../src/adapters/technicalScreenerAdapter';

describe('technical screener adapter', () => {
  test('defines Price Action Analysis with legacy endpoint, columns, and sort contract', () => {
    const config = TECHNICAL_SCREENER_CONFIGS.priceActionAnalysis;

    expect(config.endpoint).toBe('/api/technicals/price-action');
    expect(config.defaultSort).toBe('priceActionScore');
    expect(config.defaultSortDir).toBe('desc');
    expect(config.activeTechnicalPage).toBe('priceactionanalysis.html');
    expect(config.columns.map((column) => column.key)).toEqual([
      'sNo',
      'symbol',
      'index',
      'mcap',
      'mcapRank',
      'price',
      'ath',
      'gap',
      'ltcDate',
      'trendStructure',
      'lastSwingHigh',
      'lastSwingLow',
      'hhHlStatus',
      'support',
      'resistance',
      'srLevels',
      'priceActionScore',
      'riskLevel',
    ]);
  });

  test('defines Trendline with legacy endpoint, columns, and sort contract', () => {
    const config = TECHNICAL_SCREENER_CONFIGS.trendline;

    expect(config.endpoint).toBe('/api/technicals/trendline');
    expect(config.defaultSort).toBe('trendlineScore');
    expect(config.defaultSortDir).toBe('desc');
    expect(config.activeTechnicalPage).toBe('trendline.html');
    expect(config.initialForceRefresh).toBe(false);
    expect(config.pageSize).toBe(25);
    expect(config.columns.map((column) => column.key)).toEqual([
      'sNo',
      'symbol',
      'index',
      'mcap',
      'mcapRank',
      'price',
      'ath',
      'gap',
      'ltcDate',
      'trendlineStatus',
      'trendlineType',
      'slope',
      'touchCount',
      'distanceFromTrendlinePct',
      'support',
      'invalidationLevel',
      'trendlineScore',
    ]);
  });

  test('defines Breakout with legacy endpoint, columns, filters, and sort contract', () => {
    const config = TECHNICAL_SCREENER_CONFIGS.breakout;

    expect(config.endpoint).toBe('/api/technicals/breakout');
    expect(config.defaultSort).toBe('breakoutScore');
    expect(config.defaultSortDir).toBe('desc');
    expect(config.activeTechnicalPage).toBe('breakout.html');
    expect(config.initialForceRefresh).toBe(false);
    expect(config.breakoutStatusOptions).toContain('Volume Confirmed Breakout');
    expect(config.columns.map((column) => column.key)).toEqual([
      'sNo',
      'symbol',
      'index',
      'mcap',
      'mcapRank',
      'price',
      'ltcDate',
      'breakoutStatus',
      'breakoutType',
      'breakoutLevel',
      'resistance',
      'volumeRatio',
      'closePositionPct',
      'breakoutScore',
      'riskLevel',
    ]);
  });

  test('defines Chart Patterns with legacy endpoint, columns, filters, and sort contract', () => {
    const config = TECHNICAL_SCREENER_CONFIGS.chartPatterns;

    expect(config.endpoint).toBe('/api/technicals/chart-patterns');
    expect(config.defaultSort).toBe('chartPatternScore');
    expect(config.defaultSortDir).toBe('desc');
    expect(config.activeTechnicalPage).toBe('chartpatterns.html');
    expect(config.patternOptions).toContain('Ascending Triangle');
    expect(config.columns.map((column) => column.key)).toEqual([
      'sNo',
      'symbol',
      'index',
      'mcap',
      'mcapRank',
      'price',
      'ltcDate',
      'patternName',
      'patternStatus',
      'confidenceScore',
      'breakoutLevel',
      'support',
      'resistance',
      'volumeConfirmation',
      'riskLevel',
    ]);
  });

  test('defines Strong Technicals with legacy endpoint and default shared columns', () => {
    const config = TECHNICAL_SCREENER_CONFIGS.strongTechnicals;

    expect(config.endpoint).toBe('/api/technicals/strong');
    expect(config.defaultSort).toBe('techScoreSort');
    expect(config.defaultSortDir).toBe('desc');
    expect(config.activeTechnicalPage).toBe('strongtechnicals.html');
    expect(config.columns.map((column) => column.key)).toEqual([
      'sNo',
      'symbol',
      'index',
      'mcap',
      'mcapRank',
      'ath',
      'support',
      'resistance',
      'trendDirection',
      'ema20',
      'ema50',
      'ema100',
      'ema200',
      'macdGt0',
      'rsiGt50',
      'adxGt25',
      'atrGt14',
      'score',
      'price',
      'ltcDate',
      'techScore',
      'techStatus',
      'trendStructure',
      'emaAlignment',
      'trendlineStatus',
      'patternName',
      'breakoutStatus',
      'volumeRatio',
      'deliveryScore',
      'riskLevel',
      'nearestSupport',
      'nearestResistance',
      'invalidationLevel',
    ]);
  });

  test('maps Strong Technicals backend aliases into required visible columns', () => {
    const payload = adaptTechnicalScreenerPayload({
      rows: [
        {
          SYMBOL: 'RELIANCE',
          INDEX: 'LARGE',
          MCAP: 1500000,
          MCAP_RANK: 1,
          ATH: 3200.55,
          SUPPORT: 2850.1,
          RESISTANCE: 3050.25,
          TREND_DIRECTION: 'UPTREND',
          EMA20: 2980.12,
          EMA50: 2910.43,
          EMA100: 2805.87,
          EMA200: 2600.19,
          MACD_GT_0: 'Y',
          RSI_GT_50: 'Y',
          ADX_GT_25: 'N',
          ATR_GT_14: 'Y',
          SCORE: 84.5,
        },
      ],
      total: 1,
      page: 1,
      total_pages: 1,
    }, TECHNICAL_SCREENER_CONFIGS.strongTechnicals, 1, 15);

    const cells = payload.rows[0].cells;
    expect(cells.ath.text).toBe('3,200.55');
    expect(cells.support.text).toBe('2,850.1');
    expect(cells.resistance.text).toBe('3,050.25');
    expect(cells.trendDirection.text).toBe('UPTREND');
    expect(cells.ema20.text).toBe('2,980.12');
    expect(cells.ema50.text).toBe('2,910.43');
    expect(cells.ema100.text).toBe('2,805.87');
    expect(cells.ema200.text).toBe('2,600.19');
    expect(cells.macdGt0.text).toBe('Y');
    expect(cells.rsiGt50.text).toBe('Y');
    expect(cells.adxGt25.text).toBe('N');
    expect(cells.atrGt14.text).toBe('Y');
    expect(cells.score.text).toBe('84.5');
  });

  test('maps Price Action Analysis manual sr_levels into Support & Resistance column', () => {
    const payload = adaptTechnicalScreenerPayload({
      rows: [
        {
          symbol: 'ABC',
          price: 100,
          support: 95,
          resistance: 110,
          sr_levels: '95, 110',
          priceActionScore: 80,
        },
        {
          symbol: 'EMPTY',
          price: 50,
          support: 45,
          resistance: 55,
          sr_levels: '',
          priceActionScore: 70,
        },
      ],
      total: 2,
      page: 1,
      total_pages: 1,
    }, TECHNICAL_SCREENER_CONFIGS.priceActionAnalysis, 1, 25);

    expect(payload.rows[0].cells.srLevels.text).toBe('95, 110');
    expect(payload.rows[0].cells.srLevels.sort).toBe('95, 110');
    expect(payload.rows[1].cells.srLevels.text).toBe('-');
  });

  test('normalizes backend rows without changing payload field names', () => {
    const payload = adaptTechnicalScreenerPayload({
      rows: [
        {
          SYMBOL: 'TRENDWIN',
          INDEX: null,
          MCAP: null,
          MCAP_RANK: null,
          PRICE: 210.55,
          LTC_DATE: '11-05-2026',
          TRENDLINE_STATUS: 'Near Trendline Support',
          TRENDLINE_SCORE: 82.5,
        },
      ],
      total: 1,
      page: 2,
      total_pages: 4,
    }, TECHNICAL_SCREENER_CONFIGS.trendline, 2, 15);

    expect(payload.rows[0].cells.sNo.text).toBe('16');
    expect(payload.rows[0].cells.symbol.text).toBe('TRENDWIN');
    expect(payload.rows[0].cells.index.text).toBe('-');
    expect(payload.rows[0].cells.mcap.text).toBe('-');
    expect(payload.rows[0].cells.mcapRank.text).toBe('-');
    expect(payload.rows[0].cells.price.text).toBe('210.55');
    expect(payload.rows[0].cells.ltcDate.text).toBe('11-05-2026');
    expect(payload.rows[0].cells.trendlineStatus.text).toBe('Near Trendline Support');
    expect(payload.rows[0].cells.trendlineScore.sort).toBe(82.5);
    expect(payload.total).toBe(1);
    expect(payload.page).toBe(2);
    expect(payload.totalPages).toBe(4);
  });
});
