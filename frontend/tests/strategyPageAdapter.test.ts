import { describe, expect, test } from 'vitest';
import {
  getStrategySortValue,
  isStrategyPayloadRefreshing,
  isStrategyPayloadStale,
  pickStrategyField,
} from '../src/adapters/strategyPageAdapter';
import { resolveStrategyRuntimeDates } from '../src/pages/strategy/StrategyApiScreenerPage';
import { asuraConfig, bhramhaputraConfig, bhramhastraConfig } from '../src/pages/strategy/strategyScreenerConfigs';

describe('strategy page adapter', () => {
  test('uses explicit field aliases and preserves valid zero values', () => {
    const row = { entryPrice: 0, rsi: 51.2 };

    expect(pickStrategyField(row, ['buyPrice', 'entryPrice'])).toBe(0);
    expect(getStrategySortValue(row, { key: 'rsi14', label: 'RSI14', fields: ['rsi'] })).toBe(51.2);
  });

  test('detects backend refreshing payloads without treating every empty payload as final', () => {
    expect(isStrategyPayloadRefreshing({ rows: [], refreshing: true, staleReasons: ['cold_start'] })).toBe(true);
    expect(isStrategyPayloadRefreshing({ rows: [], meta: { refreshing: true } })).toBe(true);
    expect(isStrategyPayloadRefreshing({ rows: [] })).toBe(false);
  });

  test('detects stale strategy payloads from root or meta flags', () => {
    expect(isStrategyPayloadStale({ rows: [], stale: true })).toBe(true);
    expect(isStrategyPayloadStale({ rows: [], meta: { is_stale: true } })).toBe(true);
    expect(isStrategyPayloadStale({ rows: [], staleReasons: ['cold_start'] })).toBe(true);
    expect(isStrategyPayloadStale({ rows: [], meta: { status: 'live' } })).toBe(false);
  });

  test('keeps Bhramhastra cold-start polling scoped to that strategy config', () => {
    expect(bhramhastraConfig.endpoint).toBe('/api/bhramhastra');
    expect(bhramhastraConfig.pageSize).toBe(25);
    expect(bhramhastraConfig.pollWhileRefreshing).toBe(true);
    expect(bhramhastraConfig.refreshPollMaxAttempts).toBe(60);
    expect(bhramhastraConfig.showToolbarTotal).toBe(true);
    expect(bhramhastraConfig.tableVariant).toBe('ema');
    expect(bhramhastraConfig.columns.slice(0, 5).map((column) => column.label)).toEqual([
      'S.NO',
      'SYMBOL',
      'INDEX',
      'MCAP',
      'MCAP_RANK',
    ]);
    expect(bhramhastraConfig.columns.find((column) => column.key === 'index')?.renderAs).toBe('marketCapIndex');
    expect(bhramhastraConfig.columns.find((column) => column.key === 'mcap')?.renderAs).toBe('marketCapValue');
    expect(bhramhastraConfig.columns.find((column) => column.key === 'mcap_rank')?.renderAs).toBe('marketCapRank');
    expect(bhramhastraConfig.columns.find((column) => column.key === 'mcap_rank')?.fields).toContain('mcapRank');
    expect(bhramhastraConfig.columns.find((column) => column.key === 'buyPrice')?.fields).toContain('entryPrice');
    expect(bhramhastraConfig.columns.find((column) => column.key === 'rsi14')?.fields).toContain('rsi');
    expect(bhramhastraConfig.columns.find((column) => column.key === 'ema20')?.fields).toContain('EMA20');
    expect(bhramhastraConfig.columns.find((column) => column.key === 'ema100')?.fields).toContain('EMA100');
    expect(bhramhastraConfig.columns.find((column) => column.key === 'ema200')?.fields).toContain('EMA200');
    expect(bhramhastraConfig.columns.find((column) => column.key === 'adx14')?.fields).toContain('ADX14');
    expect(bhramhastraConfig.columns.find((column) => column.key === 'trendDirection')?.fields).toContain('trend');
    expect(bhramhastraConfig.columns.find((column) => column.key === 'setupType')?.fields).toContain('setup_type');
    const gapIndex = bhramhastraConfig.columns.findIndex((column) => column.key === 'gap');
    const athIndex = bhramhastraConfig.columns.findIndex((column) => column.key === 'ath');
    expect(gapIndex).toBeGreaterThan(-1);
    expect(athIndex).toBe(gapIndex + 1);
    expect(bhramhastraConfig.columns[gapIndex].renderAs).toBe('gap');
    expect(bhramhastraConfig.columns[athIndex].renderAs).toBe('ath');
  });

  test('keeps Asura table aligned to EMA market-cap behavior with 25-row pagination', () => {
    expect(asuraConfig.pageSize).toBe(25);
    expect(asuraConfig.tableVariant).toBe('ema');
    expect(asuraConfig.showToolbarTotal).toBe(true);
    expect(asuraConfig.columns.slice(0, 5).map((column) => column.label)).toEqual([
      'S.NO',
      'SYMBOL',
      'INDEX',
      'MCAP',
      'MCAP_RANK',
    ]);

    const gapIndex = asuraConfig.columns.findIndex((column) => column.key === 'gap');
    const athIndex = asuraConfig.columns.findIndex((column) => column.key === 'ath');
    expect(gapIndex).toBeGreaterThan(-1);
    expect(athIndex).toBe(gapIndex + 1);
    expect(asuraConfig.columns.find((column) => column.key === 'mcap_rank')?.fields).toContain('mcapRank');
  });

  test('uses loaded payload date for strategy toolbar state while tracking expected latest date', () => {
    expect(resolveStrategyRuntimeDates({
      hasLoadedRows: true,
      payloadLatestDateKey: '2026-05-25',
      toolbarLtcDateKey: '2026-05-26',
    })).toEqual({
      dataDateKey: '2026-05-25',
      dataIsCurrent: false,
      expectedDateKey: '2026-05-26',
    });

    expect(resolveStrategyRuntimeDates({
      hasLoadedRows: true,
      payloadLatestDateKey: '2026-05-26',
      toolbarLtcDateKey: '2026-05-25',
    })).toEqual({
      dataDateKey: '2026-05-26',
      dataIsCurrent: true,
      expectedDateKey: '2026-05-25',
    });
  });

  test('uses payload ltc date as expected date when toolbar date lookup is unavailable', () => {
    expect(resolveStrategyRuntimeDates({
      hasLoadedRows: true,
      now: new Date(2026, 4, 31),
      payloadLatestDateKey: '2026-05-29',
      toolbarLtcDateKey: null,
    })).toEqual({
      dataDateKey: '2026-05-29',
      dataIsCurrent: true,
      expectedDateKey: '2026-05-29',
    });
  });

  test('keeps Bhramhaputra aligned to EMA market-cap, total, and 25-row pagination behavior', () => {
    expect(bhramhaputraConfig.pageSize).toBe(25);
    expect(bhramhaputraConfig.tableVariant).toBe('ema');
    expect(bhramhaputraConfig.showToolbarTotal).toBe(true);
    expect(bhramhaputraConfig.columns.slice(0, 5).map((column) => column.label)).toEqual([
      'S.NO',
      'SYMBOL',
      'INDEX',
      'MCAP',
      'MCAP_RANK',
    ]);

    const priceIndex = bhramhaputraConfig.columns.findIndex((column) => column.key === 'price');
    const athIndex = bhramhaputraConfig.columns.findIndex((column) => column.key === 'ath');
    const gapIndex = bhramhaputraConfig.columns.findIndex((column) => column.key === 'gap');
    const ytdIndex = bhramhaputraConfig.columns.findIndex((column) => column.key === 'ytdPct');
    expect(priceIndex).toBeGreaterThan(-1);
    expect(athIndex).toBe(priceIndex + 1);
    expect(gapIndex).toBe(athIndex + 1);
    expect(ytdIndex).toBe(gapIndex + 1);
    expect(bhramhaputraConfig.columns.find((column) => column.key === 'ytdPct')?.renderAs).toBe('signedPercent');
    expect(bhramhaputraConfig.columns.some((column) => column.key === 'cutoffDate')).toBe(false);
    expect(bhramhaputraConfig.columns.some((column) => column.key === 'sellDate')).toBe(false);
    expect(bhramhaputraConfig.columns.some((column) => column.key === 'sellPrice')).toBe(false);
    expect(bhramhaputraConfig.columns.find((column) => column.key === 'index')?.renderAs).toBe('marketCapIndex');
    expect(bhramhaputraConfig.columns.find((column) => column.key === 'mcap_rank')?.fields).toContain('mcapRank');
    expect(bhramhaputraConfig.columns.find((column) => column.key === 'supportDisplay')?.renderAs).toBe('srLevels');
    expect(bhramhaputraConfig.columns.find((column) => column.key === 'supportDisplay')?.fields).toContain('support');
    expect(bhramhaputraConfig.columns.find((column) => column.key === 'resistanceDisplay')?.renderAs).toBe('srLevels');
    expect(bhramhaputraConfig.columns.find((column) => column.key === 'resistanceDisplay')?.fields).toContain('resistance');
  });
});
