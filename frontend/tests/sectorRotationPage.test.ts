import { readFileSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { adaptSectorBreadthPayload, type SectorBreadthRow } from '../src/adapters/sectorPageAdapter';
import {
  evaluateBestSectorEligibility,
  filterSectorRotationRows,
  formatSectorRotationMetric,
  mergeDiscoveredWithBreadth,
  resolveSectorRotationVersion,
  resolveSectorLiveToolbarStatus,
  SectorRotationPage,
  SectorRotationV3Details,
  shouldForceSectorBreadthRead,
  sortSectorRotationRows,
} from '../src/pages/sector/SectorRotationPage';
import { StockEdgeSectorRotationPage } from '../src/pages/sector/StockEdgeSectorRotationPage';
import { isDatabaseSyncStatusStale, type DatabaseSyncStatus } from '../src/services/api/sectorApi';

const appStyles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

function makeRow(overrides: Partial<SectorBreadthRow>): SectorBreadthRow {
  return {
    asOfDate: '2026-06-29',
    countBreadth: 80,
    effectiveDate: '2026-06-29',
    ffmcBreadth: 78,
    mcapBreadth: 79,
    rsi50Pct: 80,
    rsi55Pct: 82,
    sectorCode: 'AUTO',
    sectorName: 'Auto Mobile',
    sma100Pct: 70,
    sma20Pct: 84,
    sma50Pct: 76,
    stockConfirmationScreening: '',
    totalStocks: 18,
    tableName: 'NSE_NIFTY_AUTO_STAGING',
    ...overrides,
  };
}

function makeSyncStatus(overrides: Partial<DatabaseSyncStatus> = {}): DatabaseSyncStatus {
  return {
    delivery_ltc_date: '2026-07-02',
    dev_ltc_date: '2026-07-02',
    ffmc_ltc_date: '2026-07-02',
    is_fully_synced: true,
    last_sync_time: '2026-07-02T20:15:00',
    mcap_ltc_date: '2026-07-02',
    message: 'All tables fully synchronized.',
    missing_delivery_count: 0,
    missing_ffmc_count: 0,
    missing_mcap_count: 0,
    missing_symbols: { delivery: [], ffmc: [], mcap: [] },
    stale_tables: [],
    ...overrides,
  };
}

describe('SectorRotationPage', () => {
  test('keeps V2 as the safe default unless the V3 feature flag is explicit', () => {
    expect(resolveSectorRotationVersion(undefined)).toBe('v2');
    expect(resolveSectorRotationVersion('v2')).toBe('v2');
    expect(resolveSectorRotationVersion('V3')).toBe('v3');
  });

  test('reads the persisted V3 snapshot after refresh while preserving V2 force refresh', () => {
    expect(shouldForceSectorBreadthRead('v2', 1)).toBe(true);
    expect(shouldForceSectorBreadthRead('v3', 1)).toBe(false);
    expect(shouldForceSectorBreadthRead('v3', 0)).toBe(false);
  });

  test('ranks V3 rows by canonical finalRotationScore instead of legacy breadth', () => {
    const rows = [
      makeRow({ finalRotationScore: 12, legacyDisplayScore: 99, sectorCode: 'LEGACY_HIGH', sectorName: 'Legacy High' }),
      makeRow({ finalRotationScore: 88, legacyDisplayScore: 10, sectorCode: 'V3_HIGH', sectorName: 'V3 High' }),
      makeRow({ finalRotationScore: null, legacyDisplayScore: 100, sectorCode: 'NO_V3_SCORE', sectorName: 'No V3 Score' }),
    ];

    expect(sortSectorRotationRows(rows, 'v3').map((row) => row.sectorCode)).toEqual([
      'V3_HIGH',
      'LEGACY_HIGH',
      'NO_V3_SCORE',
    ]);
  });

  test('adapts canonical V3 fields without replacing unavailable values with zero', () => {
    const [row] = adaptSectorBreadthPayload({
      rows: [{
        breadthDelta5D: -2.5,
        confidence: 'HIGH',
        configuredWeights: { momentum: 0.3 },
        coveragePercent: 91.25,
        dataQualityScore: 0,
        effectiveWeights: { momentum: 0.3158 },
        finalRotationScore: 84.75,
        latestDataDate: '2026-07-14',
        rankChange1W: 3,
        relativeReturn63: 4.2,
        riskWarnings: ['CONCENTRATION_HIGH'],
        rotationPhase: 'LEADING',
        sectorCode: 'IT',
        sectorName: 'Information Technology',
        sma200Percent: 72,
        weightRedistributionApplied: true,
      }],
    });

    expect(row?.finalRotationScore).toBe(84.75);
    expect(row?.coveragePercent).toBe(91.25);
    expect(row?.dataQualityScore).toBe(0);
    expect(row?.sma200Pct).toBe(72);
    expect(row?.riskWarnings).toEqual(['CONCENTRATION_HIGH']);
    expect(row?.effectiveWeights).toEqual({ momentum: 0.3158 });
    expect(row?.weightRedistributionApplied).toBe(true);
    expect(row?.moneyFlowScore).toBeNull();
  });

  test('formats V3 zero as data and missing metrics as N/A', () => {
    expect(formatSectorRotationMetric(0)).toBe('0.00');
    expect(formatSectorRotationMetric(null)).toBe('N/A');
    expect(formatSectorRotationMetric(undefined, { suffix: '%' })).toBe('N/A');
  });

  test('filters sector rotation rows by sector name and sector code', () => {
    const rows = [
      makeRow({ sectorCode: 'AUTO', sectorName: 'Auto Mobile' }),
      makeRow({ sectorCode: 'ALCOHOL_BREWERIES', sectorName: 'Alcohol Breweries' }),
      makeRow({ sectorCode: 'IT', sectorName: 'Information Technology' }),
    ];

    expect(filterSectorRotationRows(rows, 'alcohol')).toEqual([rows[1]]);
    expect(filterSectorRotationRows(rows, 'auto')).toEqual([rows[0]]);
    expect(filterSectorRotationRows(rows, 'it')).toEqual([rows[2]]);
  });

  test('returns all rows when the search token is blank', () => {
    const rows = [
      makeRow({ sectorCode: 'AUTO', sectorName: 'Auto Mobile' }),
      makeRow({ sectorCode: 'IT', sectorName: 'Information Technology' }),
    ];

    expect(filterSectorRotationRows(rows, '')).toEqual(rows);
    expect(filterSectorRotationRows(rows, '   ')).toEqual(rows);
  });

  test('adapts total stocks from breadth and discovery payload aliases', () => {
    const rows = adaptSectorBreadthPayload([
      { sectorCode: 'AUTO', sectorName: 'Auto Mobile', totalSymbols: 18 },
      { sectorCode: 'IT', sectorName: 'Information Technology', stockCount: 10 },
    ]);

    expect(rows).toHaveLength(2);
    expect(rows[0]?.totalStocks).toBe(18);
    expect(rows[1]?.totalStocks).toBe(10);
  });

  test('prefers backend totalStocks over staging totalSymbols when both are present', () => {
    const [row] = adaptSectorBreadthPayload([
      { sectorCode: 'AGRICULTURE', sectorName: 'Agriculture', totalStocks: 5, totalSymbols: 47 },
    ]);

    expect(row?.totalStocks).toBe(5);
  });

  test('uses staging discovery count when breadth total is lower', () => {
    const [row] = mergeDiscoveredWithBreadth(
      [
        {
          sectorCode: 'PSU_BANK',
          sectorKey: 'psu-bank',
          sectorName: 'PSU Bank',
          stockCount: 12,
          tableName: 'NSE_NIFTY_PSU_BANK_STAGING',
        },
      ],
      [
        makeRow({
          sectorCode: 'PSU_BANK',
          sectorName: 'PSU Bank',
          tableName: '',
          totalStocks: 1,
        }),
      ],
    );

    expect(row?.sectorCode).toBe('PSU_BANK');
    expect(row?.tableName).toBe('NSE_NIFTY_PSU_BANK_STAGING');
    expect(row?.totalStocks).toBe(12);
  });

  test('uses null V3 metrics for discovered sectors without analytics', () => {
    const [row] = mergeDiscoveredWithBreadth(
      [{
        sectorCode: 'NEW_SECTOR',
        sectorKey: 'new-sector',
        sectorName: 'New Sector',
        stockCount: 4,
        tableName: 'NSE_NIFTY_NEW_SECTOR_STAGING',
      }],
      [],
      'v3',
    );

    expect(row?.totalStocks).toBe(4);
    expect(row?.rsi55Pct).toBeNull();
    expect(row?.finalRotationScore).toBeNull();
  });

  test('preserves the complete 90-sector discovered master universe when V3 analytics cover fewer sectors', () => {
    const discovered = Array.from({ length: 90 }, (_, index) => ({
      sectorCode: `SECTOR_${index + 1}`,
      sectorKey: `sector-${index + 1}`,
      sectorName: `Sector ${index + 1}`,
      stockCount: index + 1,
      tableName: `NSE_NIFTY_SECTOR_${index + 1}_STAGING`,
    }));
    const breadthRows = discovered.slice(0, 78).map((sector, index) => makeRow({
      finalRotationScore: 90 - index,
      sectorCode: sector.sectorCode,
      sectorName: sector.sectorName,
      totalStocks: sector.stockCount,
    }));

    const rows = mergeDiscoveredWithBreadth(discovered, breadthRows, 'v3');

    expect(rows).toHaveLength(90);
    expect(new Set(rows.map((row) => row.sectorCode)).size).toBe(90);
    expect(rows.find((row) => row.sectorCode === 'SECTOR_90')).toMatchObject({
      finalRotationScore: null,
      totalStocks: 90,
    });
  });

  test('renders sync and refresh only in the shared sector toolbar', () => {
    const markup = renderToStaticMarkup(createElement(SectorRotationPage));

    expect(markup).toContain('Search Card');
    expect(markup).toContain('Syncing');
    expect(markup).not.toContain('>Synch<');
    expect(markup.match(/Refresh/g) ?? []).toHaveLength(1);
    expect(markup).not.toContain('aria-label="Sector rotation controls"');
    expect(markup).toContain('TotalStocks');
  });

  test('keeps the canonical Sector Rotation page on the established all-sector presentation', () => {
    const markup = renderToStaticMarkup(createElement(SectorRotationPage));

    expect(markup).toContain('SECTOR ROTATION');
    expect(markup).toContain('table-sticky-safe');
    expect(markup).toContain('data-sticky-role="sno"');
    expect(markup).toContain('data-sticky-role="symbol"');
    expect(markup).toContain('sticky-header-cell sticky-sno');
    expect(markup).toContain('sticky-header-cell sticky-symbol');
    expect(markup).toContain('RSI55 &gt; 0');
    expect(markup).toContain('MOMENTUM');
    expect(markup).toContain('BREADTH');
    expect(markup).not.toContain('Best Sectors');
    expect(markup).not.toContain('ELIGIBILITY');
  });

  test('keeps sticky sector names fully visible and blocks scrolled text in both themes', () => {
    expect(appStyles).toMatch(/\.sector-breadth-table\s*{[^}]*--app-symbol-width:\s*320px;/s);
    expect(appStyles).toMatch(/\.sector-breadth-table\s*{[^}]*--app-sticky-row-bg:\s*#ffffff;[^}]*--app-sticky-row-bg-alt:\s*#f8fafc;[^}]*--app-sticky-header-bg:\s*#f1f5f9;/s);
    expect(appStyles).toMatch(/\.ema-page--dark \.sector-breadth-table\s*{[^}]*--app-sticky-row-bg:\s*#020617;[^}]*--app-sticky-row-bg-alt:\s*#0f172a;[^}]*--app-sticky-header-bg:\s*#020617;/s);
  });

  test('renders the separate StockEdge page with all sectors as the data-visible default', () => {
    const markup = renderToStaticMarkup(createElement(StockEdgeSectorRotationPage));

    expect(markup).toContain('STOCKEDGE SECTOR ROTATION');
    expect(markup).toContain('sticky-header-cell sticky-sno');
    expect(markup).toContain('sticky-header-cell sticky-symbol');
    expect(markup).toContain('Best Sectors (0)');
    expect(markup).toContain('All Sectors (0)');
    expect(markup).toContain('FINAL SCORE');
    expect(markup).toContain('ROTATION BAND');
    expect(markup).toContain('MONEY FLOW');
    expect(markup).toContain('DATA DATE');
    expect(markup).toContain('ELIGIBILITY');
    expect(markup).not.toContain('RSI55 &gt; 0');
  });

  test('rejects stale and low-coverage high-score sectors from Best Sectors', () => {
    const common = {
      asOfDate: '2026-07-22',
      latestDataDate: '2026-07-22',
      finalRotationScore: 95,
      rotationBand: 'VERY_STRONG',
      rotationPhase: 'LEADING',
      confidence: 'HIGH',
      coveragePercent: 92,
      dataQualityScore: 90,
      riskScore: 75,
      moneyFlowScore: 70,
      riskWarnings: [],
    } satisfies Partial<SectorBreadthRow>;

    expect(evaluateBestSectorEligibility(makeRow(common), '2026-07-22').eligible).toBe(true);
    expect(evaluateBestSectorEligibility(makeRow({ ...common, latestDataDate: '2026-07-21' }), '2026-07-22').failedGates).toContain('currentDate');
    expect(evaluateBestSectorEligibility(makeRow({ ...common, coveragePercent: 84.99 }), '2026-07-22').failedGates).toContain('coverage');
  });

  test('renders expandable V3 factor details with badges-safe N/A values', () => {
    const markup = renderToStaticMarkup(createElement(SectorRotationV3Details, {
      row: makeRow({
        confidence: 'LOW',
        dataQualityScore: 0,
        effectiveWeights: { momentum: 0.3, breadth: 0.25 },
        moneyFlowScore: null,
        momentumScore: 76,
        reasonCodes: ['MOMENTUM_ACCELERATING'],
        riskWarnings: ['LOW_COVERAGE'],
      }),
    }));

    expect(markup).toContain('Momentum Score');
    expect(markup).toContain('76.00');
    expect(markup).toContain('Money-Flow Score');
    expect(markup).toContain('N/A');
    expect(markup).toContain('MOMENTUM_ACCELERATING');
    expect(markup).toContain('LOW_COVERAGE');
    expect(markup).toContain('momentum: 30.0%');
  });

  test('detects stale database sync states beyond the exact is_fully_synced flag', () => {
    expect(isDatabaseSyncStatusStale(makeSyncStatus())).toBe(false);
    expect(isDatabaseSyncStatusStale(makeSyncStatus({ is_fully_synced: false }))).toBe(true);
    expect(isDatabaseSyncStatusStale(makeSyncStatus({ stale_tables: ['MCAP'] }))).toBe(true);
    expect(isDatabaseSyncStatusStale(makeSyncStatus({ missing_mcap_count: 1 }))).toBe(true);
    expect(isDatabaseSyncStatusStale(makeSyncStatus({ status: 'stale' }))).toBe(true);
  });

  test('keeps the main sector toolbar status tied to live/error reachability instead of stale data freshness', () => {
    expect(resolveSectorLiveToolbarStatus(false)).toBe('live');
    expect(resolveSectorLiveToolbarStatus(true)).toBe('error');
  });
});
