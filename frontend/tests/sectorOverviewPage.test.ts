import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import {
  buildOverviewCards,
  buildOverviewCsv,
  buildOverviewTxt,
  isSectorOverviewOlderThanDev,
  sectorOverviewRequestStatus,
  SectorOverviewPage,
  STATIC_TREND_ORDER,
} from '../src/pages/sector/SectorOverviewPage';
import { isDatabaseSyncStatusStale } from '../src/services/api/sectorApi';

describe('SectorOverviewPage overview cards', () => {
  test('keeps only the explicit unknown-or-insufficient bucket in the static card order', () => {
    expect(STATIC_TREND_ORDER).toContain('Unknown / Insufficient Data');
    expect(STATIC_TREND_ORDER).toContain('Sideways');
    expect(STATIC_TREND_ORDER).not.toContain('Sideway');
    expect(STATIC_TREND_ORDER).not.toContain('Insufficient');
    expect(STATIC_TREND_ORDER).not.toContain('Consolidation');
  });

  test('renders the merged unknown-or-insufficient card, normalizes sideways, and hides removed overview buckets', () => {
    const cards = buildOverviewCards({
      total_sectors: 2,
      total_stocks: 6,
      ltc_date: '28-06-2026',
      trend_counts: {
        Sideway: 3,
        'Unknown / Insufficient Data': 2,
      },
      dynamic_trend_counts: {
        Consolidation: 4,
      },
    });

    expect(cards).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: 'LTC_DATE', value: '28-06-2026' }),
      expect.objectContaining({ label: 'Sideways', value: '3' }),
      expect.objectContaining({ label: 'Unknown / Insufficient Data', value: '2' }),
    ]));
    expect(cards).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ label: 'Insufficient' }),
      expect.objectContaining({ label: 'Consolidation' }),
    ]));
  });

  test('keeps CSV tabular and exports TXT as a plain comma-separated stock list', () => {
    const rows = [
      {
        serialNo: 1,
        stock: 'ABC',
        ltcDate: '28-06-2026',
        price: 123.45,
        trend: 'Strong Uptrend' as const,
      },
      {
        serialNo: 2,
        stock: 'XYZ',
        ltcDate: '',
        price: null,
        trend: 'Unknown / Insufficient Data' as const,
      },
    ];

    expect(buildOverviewCsv(rows)).toContain('S.NO,STOCK,LTC_DATE,PRICE,TREND');
    expect(buildOverviewCsv(rows)).toContain('"1","ABC","28-06-2026","123.45","Strong Uptrend"');
    expect(buildOverviewTxt(rows)).toBe('ABC,XYZ');
  });

  test('renders the same single-surface sector toolbar variant without the old hardcoded Synch label', () => {
    const markup = renderToStaticMarkup(createElement(SectorOverviewPage));

    expect(markup).toContain('Search Card');
    expect(markup).toContain('Syncing');
    expect(markup).not.toContain('>Synch<');
    expect(markup).toContain('strategy-toolbar-scroll');
    expect(markup).not.toContain('strategy-toolbar-shell');
  });

  test('shares the database sync stale resolver used by the sector toolbar', () => {
    expect(isDatabaseSyncStatusStale({
      delivery_ltc_date: '2026-07-02',
      dev_ltc_date: '2026-07-02',
      ffmc_ltc_date: '2026-07-02',
      is_fully_synced: true,
      last_sync_time: '2026-07-02T20:15:00',
      mcap_ltc_date: '2026-07-02',
      message: 'Sync pending / stale tables detected.',
      missing_delivery_count: 1,
      missing_ffmc_count: 0,
      missing_mcap_count: 0,
      missing_symbols: { delivery: ['ABC'], ffmc: [], mcap: [] },
      stale_tables: [],
    })).toBe(true);
  });

  test('refreshes the overview only when DEV has advanced beyond its snapshot', () => {
    expect(isSectorOverviewOlderThanDev({ source_dev_ltc_date: '2026-07-23' }, '2026-07-24')).toBe(true);
    expect(isSectorOverviewOlderThanDev({ source_dev_ltc_date: '2026-07-24' }, '2026-07-24')).toBe(false);
    expect(isSectorOverviewOlderThanDev({ source_dev_ltc_date: undefined }, '2026-07-24')).toBe(false);
  });

  test('keeps snapshot cards visible while a newer overview refreshes in the background', () => {
    expect(sectorOverviewRequestStatus(0)).toBe('loading');
    expect(sectorOverviewRequestStatus(1)).toBe('refreshing');
    expect(sectorOverviewRequestStatus(2)).toBe('refreshing');
  });
});
