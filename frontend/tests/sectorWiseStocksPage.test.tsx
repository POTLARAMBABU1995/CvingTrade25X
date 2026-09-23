import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { adaptSectorWisePayload, formatSectorDate, type SectorWiseRow } from '../src/adapters/sectorPageAdapter';
import {
  findSectorPageByCode,
  findSectorPageByPath,
  isSectorDropdownPageActive,
  sectorDropdownNavItems,
  sectorNavItems,
  sectorPageItems,
} from '../src/data/sectorNav';
import {
  calculateSectorTrendScore,
  buildSectorWiseUnknownCsv,
  buildSectorWiseUnknownTxt,
  filterSectorWiseRows,
  formatSectorAnalyticsValue,
  getSectorTrendBand,
  isSectorWiseUnknownOrInsufficient,
  renderSectorWiseCell,
  resolveSectorWiseVisibleColumns,
  SectorWiseStocksPage,
} from '../src/pages/sector/SectorWiseStocksPage';

function makeRow(overrides: Partial<SectorWiseRow>): SectorWiseRow {
  return {
    stock: 'TEST',
    trend: 'Downtrend',
    price: 100,
    ema20: 99,
    ema50: 98,
    ema100: 97,
    ema200: 96,
    ema20Flag: 'N',
    ema50Flag: 'N',
    ema100Flag: 'N',
    ema200Flag: 'N',
    ...overrides,
  } as SectorWiseRow;
}

describe('SectorWiseStocksPage', () => {
  test('formats LTC_DATE as DD-MM-YYYY only', () => {
    expect(formatSectorDate('2026-08-06')).toBe('06-08-2026');
    expect(formatSectorDate('2026-08-06T14:25:30Z')).toBe('06-08-2026');
    expect(formatSectorDate('06-08-2026')).toBe('06-08-2026');
  });

  test('exports only unknown, insufficient, or blank Trend rows with the displayed columns', () => {
    const rows = [
      makeRow({ stock: 'UNKNOWN1', trend: 'Unknown / Insufficient Data', price: 123.45 }),
      makeRow({ stock: 'BLANK1', trend: '', price: 101 }),
      makeRow({ stock: 'UP1', trend: 'Uptrend', price: 99 }),
    ];
    const exportRows = rows.filter(isSectorWiseUnknownOrInsufficient).map((row, index) => ({ ...row, sNo: index + 1 }));
    const columns = resolveSectorWiseVisibleColumns(rows);

    expect(exportRows.map((row) => row.stock)).toEqual(['UNKNOWN1', 'BLANK1']);
    expect(buildSectorWiseUnknownTxt(exportRows)).toBe('UNKNOWN1,BLANK1');
    expect(buildSectorWiseUnknownCsv(exportRows, columns)).toContain('"SYMBOL"');
    expect(buildSectorWiseUnknownCsv(exportRows, columns)).toContain('"Unknown / Insufficient Data"');
    expect(buildSectorWiseUnknownCsv(exportRows, columns)).toContain('"123.45"');
    expect(buildSectorWiseUnknownCsv(exportRows, columns)).not.toContain('"UP1"');
  });

  test('maps and renders the V3 stock-strength contract', () => {
    const payload = adaptSectorWisePayload({
      version: 'v3',
      runId: 'run-v3',
      asOfDate: '2026-07-22',
      technicalSourceDate: '2026-07-22',
      rows: [{
        stock: 'TEST',
        trendState: 'STRONG_UPTREND',
        stockEdgeScore: 88.5,
        stockEdgeBand: 'VERY_STRONG',
        coverage: 100,
        return21: 4.5,
        return63: 12.2,
        return126: 25.4,
        rsi: 61,
        macd: 2.4,
        macdHist: 0.6,
        adx14: 31,
        volumeRatio: 1.4,
        deliveryScore: 70,
        riskLevel: 'LOW',
        CONFIDENCE: 'HIGH',
        week52HighLevel: 215.42,
        week52LowLevel: 132.1,
      }],
    });
    const row = payload.rows[0];

    expect(row).toMatchObject({
      trendState: 'STRONG_UPTREND',
      stockEdgeScore: 88.5,
      stockEdgeBand: 'VERY_STRONG',
      confidence: 'HIGH',
      high52w: 215.42,
      low52w: 132.1,
    });
    expect(payload).toMatchObject({
      version: 'v3',
      runId: 'run-v3',
      asOfDate: '2026-07-22',
      technicalSourceDate: '2026-07-22',
    });
    expect(resolveSectorWiseVisibleColumns(payload.rows).map((column) => column.key)).toEqual([
      'S_NO',
      'STOCK',
      'INDEX',
      'MCAP',
      'MCAP_RANK',
      'LTC_DATE',
      'PRICE',
      'ATH',
      'GAP',
      '52WH',
      '52WL',
      'EMA20_FLAG',
      'EMA50_FLAG',
      'EMA100_FLAG',
      'EMA200_FLAG',
      'TREND',
      'SCORE',
      'CONFIDENCE',
    ]);
    expect(renderToStaticMarkup(<>{renderSectorWiseCell(row, 'TREND_STATE')}</>)).toBe('STRONG_UPTREND');
    expect(renderToStaticMarkup(<>{renderSectorWiseCell(row, 'RETURN21')}</>)).toBe('4.5%');
    expect(renderToStaticMarkup(<>{renderSectorWiseCell(row, 'TECHNICALS')}</>)).toContain('?symbol=TEST');
    expect(formatSectorAnalyticsValue(null)).toBe('-');
  });

  test('resolves Alcohol Breweries from rotation code and stock page paths', () => {
    expect(findSectorPageByCode('ALCOHOL_BREWERIES')).toMatchObject({
      code: 'ALCOHOL_BREWERIES',
      href: '/app/sector/stocks/alcohol-breweries',
      label: 'Alcohol Breweries',
    });
    expect(findSectorPageByPath('/app/sector/stocks/alcohol-breweries')).toMatchObject({
      code: 'ALCOHOL_BREWERIES',
    });
    expect(findSectorPageByPath('/app/sector/stocks/alcohol_breweries')).toMatchObject({
      code: 'ALCOHOL_BREWERIES',
    });
  });

  test('resolves Auto Mobile and Auto Ancillaries from rotation codes and stock page paths', () => {
    expect(findSectorPageByCode('AUTO')).toMatchObject({
      code: 'AUTO',
      href: '/app/sector/stocks/auto',
      label: 'Auto Mobile',
    });
    expect(findSectorPageByPath('/app/sector/stocks/auto-mobile')).toMatchObject({
      code: 'AUTO',
    });
    expect(findSectorPageByCode('AUTO_ANCILLARIES')).toMatchObject({
      code: 'AUTO_ANCILLARIES',
      href: '/app/sector/stocks/auto-ancillaries',
      label: 'Auto Ancillaries',
    });
    expect(findSectorPageByPath('/app/sector/stocks/auto-ancillaries')).toMatchObject({
      code: 'AUTO_ANCILLARIES',
    });
    expect(findSectorPageByPath('/app/sector/stocks/auto_ancillaries')).toMatchObject({
      code: 'AUTO_ANCILLARIES',
    });
  });

  test('resolves restaurants, hospitality, and tourism stock pages from rotation codes and underscore routes', () => {
    expect(findSectorPageByCode('RESTAURANTS')).toMatchObject({
      code: 'RESTAURANTS',
      href: '/app/sector/stocks/restaurants',
      label: 'Restaurants',
    });
    expect(findSectorPageByCode('HOSPITALITY_HOTELS_RESORTS')).toMatchObject({
      code: 'HOSPITALITY_HOTELS_RESORTS',
      href: '/app/sector/stocks/hospitality-hotels-resorts',
      label: 'Hospitality Hotels & Resorts',
    });
    expect(findSectorPageByCode('TOURISM_TRAVEL')).toMatchObject({
      code: 'TOURISM_TRAVEL',
      href: '/app/sector/stocks/tourism-travel',
      label: 'Tourism & Travel',
    });
    expect(findSectorPageByPath('/app/sector/stocks/hospitality_hotels_resorts')).toMatchObject({
      code: 'HOSPITALITY_HOTELS_RESORTS',
      href: '/app/sector/stocks/hospitality-hotels-resorts',
    });
    expect(findSectorPageByPath('/app/sector/stocks/tourism_travel')).toMatchObject({
      code: 'TOURISM_TRAVEL',
      href: '/app/sector/stocks/tourism-travel',
    });
  });

  test('collapses sector aliases into one unique stock page per sector', () => {
    expect(findSectorPageByCode('CONS_DUR')).toMatchObject({
      code: 'CONSUMER_DURABLES',
      href: '/app/sector/stocks/consumer-durables',
    });
    expect(findSectorPageByCode('OIL_GAS')).toMatchObject({
      code: 'OIL_AND_GAS',
      href: '/app/sector/stocks/oil-and-gas',
    });
    expect(findSectorPageByPath('/app/sector/stocks/oil-gas')).toMatchObject({
      code: 'OIL_AND_GAS',
      href: '/app/sector/stocks/oil-and-gas',
    });
    expect(findSectorPageByCode('TELECOM')).toMatchObject({
      code: 'TELECOMMUNICATION',
      href: '/app/sector/stocks/telecommunication',
    });
    expect(findSectorPageByPath('/app/sector/stocks/telecom')).toMatchObject({
      code: 'TELECOMMUNICATION',
      href: '/app/sector/stocks/telecommunication',
    });
  });

  test('registers new unique source-pack sector pages', () => {
    expect(findSectorPageByCode('HOUSEHOLD_PERSONAL_PRODUCTS')).toMatchObject({
      code: 'HOUSEHOLD_PERSONAL_PRODUCTS',
      href: '/app/sector/stocks/household-personal-products',
      label: 'Household & Personal Products',
    });
    expect(findSectorPageByCode('METALS_MINING')).toMatchObject({
      code: 'METALS_MINING',
      href: '/app/sector/stocks/metals-mining',
      label: 'Metals & Mining',
    });
    expect(findSectorPageByCode('TEXTILES_APPARELS')).toMatchObject({
      code: 'TEXTILES_APPARELS',
      href: '/app/sector/stocks/textiles-apparels',
      label: 'Textiles & Apparels',
    });
  });

  test('keeps the static sector registry unique by code and label', () => {
    expect(new Set(sectorPageItems.map((item) => item.code)).size).toBe(sectorPageItems.length);
    expect(new Set(sectorPageItems.map((item) => item.label)).size).toBe(sectorPageItems.length);
  });

  test('registers Sector_Overview in the canonical sector navigation', () => {
    expect(sectorNavItems).toEqual(expect.arrayContaining([
      expect.objectContaining({
        href: '/app/sector/overview',
        label: 'Sector_Overview',
        page: '/app/sector/overview',
      }),
    ]));
  });

  test('keeps canonical unversioned sector dropdown entries including the separate StockEdge page', () => {
    expect(sectorDropdownNavItems).toEqual(sectorNavItems);
    expect(sectorDropdownNavItems.some((item) => /V[123]/i.test(item.label))).toBe(false);
    expect(isSectorDropdownPageActive('/app/sector/rotation', '/app/sector/rotation')).toBe(true);
    expect(isSectorDropdownPageActive('/app/sector/stockedge-rotation', '/app/sector/stockedge-rotation')).toBe(true);
    expect(isSectorDropdownPageActive('/app/sector/stocks/auto', '/app/sector/stocks/auto')).toBe(true);
  });

  test('renders SYMBOL header without the default sort caret', () => {
    const markup = renderToStaticMarkup(<SectorWiseStocksPage sectorPage={sectorPageItems[0]} />);

    expect(markup).toMatch(/<th[^>]*data-sort="STOCK"[^>]*>SYMBOL<\/th>/);
    expect(markup).not.toContain('SYMBOL ^');
    expect(markup).not.toContain('SYMBOL v');
    expect(markup).toContain('LTC_DATE');
    expect(markup).toContain('ATH');
    expect(markup).toContain('52WH');
    expect(markup).toContain('TREND');
    expect(markup).toContain('SCORE');
    expect(markup).not.toContain('STOCK STRENGTH');
    expect(markup).not.toContain('1M RETURN');
    expect(markup).not.toContain('TECHNICALS');
    expect(markup).not.toContain('Strong Uptrend + Uptrend');
    expect(markup).not.toContain('Filter stock trend state');
    expect(markup).toContain('Existing Sector Wise Stocks');
  });

  test('does not hide legacy rows that have no V3 trend state', () => {
    const rows = [
      makeRow({ stock: 'MARUTI', trendState: undefined }),
      makeRow({ stock: 'M&M', trendState: undefined }),
    ];

    expect(filterSectorWiseRows(rows, '')).toEqual(rows);
    expect(filterSectorWiseRows(rows, 'mar')).toEqual([rows[0]]);
  });

  test('marks S.NO and SYMBOL as explicit sticky columns', () => {
    const markup = renderToStaticMarkup(<SectorWiseStocksPage sectorPage={sectorPageItems[0]} />);

    expect(markup).toContain('data-col="sno" data-sticky-role="sno"');
    expect(markup).toContain('data-col="symbol" data-sticky-role="symbol"');
    expect(markup).toContain('class="sortable sticky-header-cell sticky-sno"');
    expect(markup).toContain('class="sortable sticky-header-cell sticky-symbol"');
    expect(markup).toContain('data-sticky-col="left" data-sticky-role="sno"');
    expect(markup).toContain('data-sticky-col="left" data-sticky-role="symbol"');
  });

  test('renders sector selector options with serial numbers from the sorted list', () => {
    const markup = renderToStaticMarkup(<SectorWiseStocksPage sectorPage={sectorPageItems[0]} />);
    const orderedItems = [...sectorPageItems].sort((left, right) => left.label.localeCompare(right.label));
    const autoMobileIndex = orderedItems.findIndex((item) => item.code === 'AUTO');

    expect(markup.match(/<option\b/g) ?? []).toHaveLength(orderedItems.length);
    expect(markup).toContain(`value="${orderedItems[0].code}">1. ${orderedItems[0].label}<`);
    expect(markup).toContain(`value="${orderedItems[orderedItems.length - 1].code}">${orderedItems.length}. `);
    expect(autoMobileIndex).toBeGreaterThanOrEqual(0);
    expect(markup).toContain(`value="AUTO">${autoMobileIndex + 1}. Auto Mobile<`);
    expect(markup).toContain('>AGRICULTURE<');
  });

  test('renders the shared sector toolbar above the sector-wise stocks controls', () => {
    const markup = renderToStaticMarkup(<SectorWiseStocksPage sectorPage={sectorPageItems[0]} />);

    expect(markup).toContain('Search Card');
    expect(markup).toContain('Syncing');
    expect(markup).not.toContain('>Synch<');
    expect(markup).toContain('Total: 0');
    expect(markup).toContain('LTC_DATE: -');
    expect(markup).toContain('Last refreshed: -');
  });

  test('preserves stale snapshot metadata from the sector-wise backend payload', () => {
    const view = adaptSectorWisePayload({
      source: 'stale_snapshot',
      isStale: true,
      staleReason: 'snapshot_behind_latest_raw_date',
      totalCount: 1,
      pageSize: 25,
      rows: [{ stock: 'ABC', ltcDate: '2026-06-30' }],
    });

    expect(view.isStale).toBe(true);
    expect(view.source).toBe('stale_snapshot');
    expect(view.staleReason).toBe('snapshot_behind_latest_raw_date');
  });

  test('maps rows into the required non-overlapping 0-100 score bands', () => {
    const strongDowntrend = calculateSectorTrendScore(makeRow({
      trend: 'Downtrend',
      gapPct: -45,
    }));
    const downtrend = calculateSectorTrendScore(makeRow({
      trend: 'Downtrend',
      gapPct: -18,
      ema20Flag: 'Y',
      price: 100,
      ema20: 98,
      ema50: 101,
      ema100: 104,
      ema200: 107,
    }));
    const sideways = calculateSectorTrendScore(makeRow({
      trend: 'Sideways',
      gapPct: -20,
      ema20Flag: 'Y',
      ema50Flag: 'Y',
      ema100Flag: 'N',
      ema200Flag: 'N',
    }));
    const pullback = calculateSectorTrendScore(makeRow({
      trend: 'Pullback in Uptrend',
      gapPct: -8,
      price: 100,
      ema20: 102,
      ema50: 95,
      ema100: 90,
      ema200: 85,
      ema20Flag: 'N',
      ema50Flag: 'Y',
      ema100Flag: 'Y',
      ema200Flag: 'Y',
    }));
    const uptrend = calculateSectorTrendScore(makeRow({
      trend: 'Uptrend',
      gapPct: -12,
      price: 120,
      ema20: 110,
      ema50: 100,
      ema100: 90,
      ema200: 80,
      ema20Flag: 'Y',
      ema50Flag: 'Y',
      ema100Flag: 'Y',
      ema200Flag: 'Y',
      score: 99,
      scoreSort: 99,
    }));
    const strongUptrend = calculateSectorTrendScore(makeRow({
      trend: 'Strong Uptrend',
      gapPct: -4,
      price: 120,
      ema20: 110,
      ema50: 100,
      ema100: 90,
      ema200: 80,
      ema20Flag: 'Y',
      ema50Flag: 'Y',
      ema100Flag: 'Y',
      ema200Flag: 'Y',
      score: 12,
      scoreSort: 12,
    }));

    expect(strongDowntrend.label).toBe('Strong Downtrend');
    expect(strongDowntrend.score).toBeGreaterThanOrEqual(0);
    expect(strongDowntrend.score).toBeLessThanOrEqual(20);

    expect(downtrend.label).toBe('Downtrend');
    expect(downtrend.score).toBeGreaterThanOrEqual(21);
    expect(downtrend.score).toBeLessThanOrEqual(40);

    expect(sideways.label).toBe('Sideways');
    expect(sideways.score).toBeGreaterThanOrEqual(41);
    expect(sideways.score).toBeLessThanOrEqual(60);

    expect(pullback.label).toBe('Pullback in Uptrend');
    expect(pullback.score).toBeGreaterThanOrEqual(61);
    expect(pullback.score).toBeLessThanOrEqual(70);

    expect(uptrend.label).toBe('Uptrend');
    expect(uptrend.score).toBeGreaterThanOrEqual(71);
    expect(uptrend.score).toBeLessThanOrEqual(85);

    expect(strongUptrend.label).toBe('Strong Uptrend');
    expect(strongUptrend.score).toBeGreaterThanOrEqual(86);
    expect(strongUptrend.score).toBeLessThanOrEqual(100);
  });

  test('keeps score bands non-overlapping and sorts rows numerically in the required order', () => {
    const rows = [
      makeRow({ trend: 'Downtrend', gapPct: -45 }),
      makeRow({ trend: 'Downtrend', gapPct: -18, ema20Flag: 'Y', price: 100, ema20: 98, ema50: 101, ema100: 104, ema200: 107 }),
      makeRow({ trend: 'Sideways', gapPct: -20, ema20Flag: 'Y', ema50Flag: 'Y', ema100Flag: 'N', ema200Flag: 'N' }),
      makeRow({ trend: 'Pullback in Uptrend', gapPct: -8, price: 100, ema20: 102, ema50: 95, ema100: 90, ema200: 85, ema20Flag: 'N', ema50Flag: 'Y', ema100Flag: 'Y', ema200Flag: 'Y' }),
      makeRow({ trend: 'Uptrend', gapPct: -12, price: 120, ema20: 110, ema50: 100, ema100: 90, ema200: 80, ema20Flag: 'Y', ema50Flag: 'Y', ema100Flag: 'Y', ema200Flag: 'Y' }),
      makeRow({ trend: 'Strong Uptrend', gapPct: -4, price: 120, ema20: 110, ema50: 100, ema100: 90, ema200: 80, ema20Flag: 'Y', ema50Flag: 'Y', ema100Flag: 'Y', ema200Flag: 'Y' }),
    ];
    const results = rows.map((row) => calculateSectorTrendScore(row));
    const sortedLabels = [...results]
      .sort((left, right) => right.score - left.score)
      .map((item) => item.label);

    results.forEach((result) => {
      expect(getSectorTrendBand(result.score).label).toBe(result.label);
      expect(result.score).toBeGreaterThanOrEqual(result.band.min);
      expect(result.score).toBeLessThanOrEqual(result.band.max);
    });

    expect(sortedLabels).toEqual([
      'Strong Uptrend',
      'Uptrend',
      'Pullback in Uptrend',
      'Sideways',
      'Downtrend',
      'Strong Downtrend',
    ]);
  });

  test('treats invalid or empty trend values as deterministic sideways scores', () => {
    const invalid = calculateSectorTrendScore(makeRow({
      trend: '',
      ema20Flag: '',
      ema50Flag: '',
      ema100Flag: '',
      ema200Flag: '',
      gapPct: null,
    }));

    expect(invalid.label).toBe('Sideways');
    expect(invalid.score).toBeGreaterThanOrEqual(41);
    expect(invalid.score).toBeLessThanOrEqual(60);
  });

  test('maps exact boundary values to one band only', () => {
    expect(getSectorTrendBand(0).label).toBe('Strong Downtrend');
    expect(getSectorTrendBand(20).label).toBe('Strong Downtrend');
    expect(getSectorTrendBand(21).label).toBe('Downtrend');
    expect(getSectorTrendBand(40).label).toBe('Downtrend');
    expect(getSectorTrendBand(41).label).toBe('Sideways');
    expect(getSectorTrendBand(60).label).toBe('Sideways');
    expect(getSectorTrendBand(61).label).toBe('Pullback in Uptrend');
    expect(getSectorTrendBand(70).label).toBe('Pullback in Uptrend');
    expect(getSectorTrendBand(71).label).toBe('Uptrend');
    expect(getSectorTrendBand(85).label).toBe('Uptrend');
    expect(getSectorTrendBand(86).label).toBe('Strong Uptrend');
    expect(getSectorTrendBand(100).label).toBe('Strong Uptrend');
  });
});
