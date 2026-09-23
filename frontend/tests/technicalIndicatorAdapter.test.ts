import { describe, expect, test } from 'vitest';
import {
  adaptTechnicalIndicatorPayload,
  adaptTechnicalIndicatorRow,
  filterTechnicalIndicatorRowsBySymbol,
  TECHNICAL_INDICATOR_CONFIGS,
} from '../src/adapters/technicalIndicatorAdapter';
import type { TechnicalIndicatorPayloadWire, TechnicalIndicatorScreenWireRow } from '../src/types/api/technical';

describe('technical indicator adapter', () => {
  test('maps RSI50 rows with market-cap dash fallbacks and disabled-since handling', () => {
    const row: TechnicalIndicatorScreenWireRow = {
      symbol: 'RSIWIN',
      INDEX: null,
      MCAP: null,
      MCAP_RANK: null,
      price: 101.5,
      tradingDate: '01-01-1998',
      ltcDate: '11-05-2026',
      tradingDays: 732,
      rsi: 58.4,
      rsiScore: 82.25,
    };

    const adapted = adaptTechnicalIndicatorRow(row, 0, 'rsi50');

    expect(adapted.cells.sNo.text).toBe('1');
    expect(adapted.cells.symbol.text).toBe('RSIWIN');
    expect(adapted.cells.index.text).toBe('-');
    expect(adapted.cells.mcap.text).toBe('-');
    expect(adapted.cells.mcapRank.text).toBe('-');
    expect(adapted.cells.tradingDate.text).toBe('N/A');
    expect(adapted.cells.tradingDays.text).toBe('N/A');
    expect(adapted.cells.rsi.text).toBe('58.4');
    expect(adapted.cells.rsiScore.sort).toBe(82.25);
  });

  test('maps MACD visible columns and return-window tones', () => {
    const adapted = adaptTechnicalIndicatorRow({
      symbol: 'MACDWIN',
      INDEX: 'Nifty Largecap 100',
      MCAP: '123456.78',
      MCAP_RANK: '12',
      price: 250,
      tradingDate: '2020-01-03',
      ltcDate: '11-05-2026',
      tradingDays: 1500,
      macdScore: 7,
      d5: '3.10%',
      d5Sort: 3.1,
      d10: '-1.25%',
      d10Sort: -1.25,
    }, 2, 'macd');

    expect(adapted.cells.sNo.text).toBe('3');
    expect(adapted.cells.index.text).toBe('LARGE');
    expect(adapted.cells.mcap.text).toBe('1,23,456.78');
    expect(adapted.cells.macdScore.text).toBe('7');
    expect(adapted.cells.d5.tone).toBe('positive');
    expect(adapted.cells.d10.tone).toBe('negative');
    expect(TECHNICAL_INDICATOR_CONFIGS.macd.columns.map((column) => column.key)).toEqual([
      'sNo',
      'symbol',
      'index',
      'mcap',
      'mcapRank',
      'price',
      'tradingDate',
      'ltcDate',
      'tradingDays',
      'macdScore',
      'd5',
      'd10',
      'd15',
      'd22',
      'd44',
      'd66',
      'd88',
    ]);
  });

  test('maps ATR14 rows and filters by symbol only', () => {
    const payload: TechnicalIndicatorPayloadWire = {
      cached: true,
      count: 2,
      rows: [
        { symbol: 'ATRONE', price: 90, ltcDate: '10-05-2026', atr: 8.25, atrScore: 91 },
        { symbol: 'OTHER', price: 80, ltcDate: '11-05-2026', atr: 4.1, atrScore: 50 },
      ],
      timeframe: 'daily',
    };

    const adapted = adaptTechnicalIndicatorPayload(payload, 'atr14');

    expect(adapted.cached).toBe(true);
    expect(adapted.latestLtcDateKey).toBe('2026-05-11');
    expect(adapted.rows[0].cells.atr.text).toBe('8.25');
    expect(adapted.rows[0].cells.atrScore.sort).toBe(91);
    expect(filterTechnicalIndicatorRowsBySymbol(adapted.rows, 'atr').map((row) => row.symbol)).toEqual(['ATRONE']);
    expect(filterTechnicalIndicatorRowsBySymbol(adapted.rows, '90')).toHaveLength(0);
  });

  test('maps ADX rows with exact legacy columns and fixed decimal metrics', () => {
    const adapted = adaptTechnicalIndicatorRow({
      symbol: 'ADXWIN',
      INDEX: null,
      MCAP: null,
      MCAP_RANK: null,
      price: 325.75,
      tradingDate: '02-01-2026',
      ltcDate: '11-05-2026',
      td: 89,
      adxGt20: 31.236,
      adxGt25: 31.236,
      plusDm: 18.2,
      minusDm: 9,
      adxScore: 40.236,
    }, 4, 'adx');

    expect(TECHNICAL_INDICATOR_CONFIGS.adx.columns.map((column) => column.key)).toEqual([
      'sNo',
      'symbol',
      'index',
      'mcap',
      'mcapRank',
      'price',
      'tradingDate',
      'ltcDate',
      'tradingDays',
      'adxGt20',
      'adxGt25',
      'plusDm',
      'minusDm',
      'adxScore',
    ]);
    expect(adapted.cells.sNo.text).toBe('5');
    expect(adapted.cells.index.text).toBe('-');
    expect(adapted.cells.mcap.text).toBe('-');
    expect(adapted.cells.mcapRank.text).toBe('-');
    expect(adapted.cells.adxGt20.text).toBe('31.24');
    expect(adapted.cells.adxGt25.text).toBe('31.24');
    expect(adapted.cells.plusDm.text).toBe('18.20');
    expect(adapted.cells.minusDm.text).toBe('9.00');
    expect(adapted.cells.adxScore.text).toBe('40.24');
  });

  test('maps Volume MA rows with legacy columns, number formatting, and symbol-only search', () => {
    const payload: TechnicalIndicatorPayloadWire = {
      cached: true,
      count: 2,
      rows: [
        {
          symbol: 'VOLWIN',
          INDEX: null,
          MCAP: null,
          MCAP_RANK: null,
          price: 125.5,
          tradingDate: '01-01-1998',
          ltcDate: '11-05-2026',
          volume: 1234567,
          volumeAvg20: 987654.2,
          volumeRatio: 1.249,
          volumeScore: 72.125,
        },
        { symbol: 'OTHER', price: 80, volume: 1000, volumeAvg20: 2000, volumeRatio: 0.5, volumeScore: 15 },
      ],
      timeframe: 'daily',
    };

    const adapted = adaptTechnicalIndicatorPayload(payload, 'volume');

    expect(TECHNICAL_INDICATOR_CONFIGS.volume.columns.map((column) => column.key)).toEqual([
      'sNo',
      'symbol',
      'index',
      'mcap',
      'mcapRank',
      'price',
      'tradingDate',
      'ltcDate',
      'tradingDays',
      'volume',
      'volumeAvg20',
      'volumeRatio',
      'volumeScore',
    ]);
    expect(adapted.rows[0].cells.index.text).toBe('-');
    expect(adapted.rows[0].cells.mcap.text).toBe('-');
    expect(adapted.rows[0].cells.mcapRank.text).toBe('-');
    expect(adapted.rows[0].cells.tradingDate.text).toBe('N/A');
    expect(adapted.rows[0].cells.tradingDays.text).toBe('N/A');
    expect(adapted.rows[0].cells.volume.text).toBe('1,234,567');
    expect(adapted.rows[0].cells.volumeAvg20.text).toBe('987,654');
    expect(adapted.rows[0].cells.volumeRatio.text).toBe('1.25');
    expect(adapted.rows[0].cells.volumeScore.text).toBe('72.13');
    expect(filterTechnicalIndicatorRowsBySymbol(adapted.rows, 'vol').map((row) => row.symbol)).toEqual(['VOLWIN']);
    expect(filterTechnicalIndicatorRowsBySymbol(adapted.rows, '125')).toHaveLength(0);
  });
});
