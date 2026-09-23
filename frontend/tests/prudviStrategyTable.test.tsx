import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { PrudviStrategyTable } from '../src/components/strategy/PrudviStrategyTable';
import { calculatePrudviKpiCounts, PRUDVI_COLUMNS } from '../src/adapters/prudviStrategyAdapter';
import type { PrudviStrategyFilters, PrudviStrategyRow } from '../src/types/strategy/prudvi';

const row: PrudviStrategyRow = {
  S_NO: 1,
  SYMBOL: 'RELIANCE',
  INDEX: 'LARGE',
  MCAP: 1987654.23,
  MCAP_RANK: 1,
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
  EMA_GT_50: 'Y',
  RSI_GT_50: 'Y',
  ADX_GT_25: 'Y',
  MACD_GT_0: 'Y',
  VOLUME_GT_20: 'Y',
  DELIVERY_GT_60: 'Y',
  TREND: 'UPTREND',
  TREND_SCORE: 92,
};

const filters: PrudviStrategyFilters = {
  minimumScore: '',
  search: '',
  trend: 'ALL',
};

function renderTable(rows: PrudviStrategyRow[] = [row], loadedRows: PrudviStrategyRow[] = rows) {
  return renderToStaticMarkup(
    <PrudviStrategyTable
      filters={filters}
      kpiCounts={calculatePrudviKpiCounts(loadedRows)}
      onFiltersChange={() => undefined}
      onRefresh={() => undefined}
      onStrongUptrendOnlyChange={() => undefined}
      rows={rows}
      strongUptrendOnly={false}
      totalRows={loadedRows.length}
    />,
  );
}

function buildRows(count: number): PrudviStrategyRow[] {
  return Array.from({ length: count }, (_, index) => ({
    ...row,
    S_NO: index + 1,
    SYMBOL: `ROW${index + 1}`,
    TREND_SCORE: index === 0 ? 92 : 55,
    TREND: index === 0 ? 'UPTREND' : 'CONSOLIDATION',
  }));
}

function escapeHtmlText(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

describe('PrudviStrategyTable', () => {
  test('renders only the new Prudvi strategy table content', () => {
    const markup = renderTable();

    expect(markup).toContain('Search symbol');
    expect(markup).toContain('Show only strong uptrend rows');
    expect(markup).toContain('RELIANCE');
    expect(markup).toContain('UPTREND');
    expect(markup).not.toContain('Strategy Screener');
    expect(markup).not.toContain('Toggle columns');
    expect(markup).not.toContain('Momentum');
  });

  test('renders required headers in sequence', () => {
    const markup = renderTable();
    const headerLabels = Array.from(markup.matchAll(/<th\b[^>]*>(.*?)<\/th>/g), (match) => match[1]);

    expect(headerLabels).toEqual(PRUDVI_COLUMNS.map((column) => escapeHtmlText(column.label)));
  });

  test('applies index tone to symbol and market-cap columns', () => {
    const markup = renderTable();

    expect(markup).toContain('trend-mcap-index-value--large">RELIANCE</span>');
    expect(markup).toContain('trend-mcap-index-value--large">LARGE</span>');
    expect(markup).toContain('trend-mcap-index-value--large">19,87,654.23</span>');
    expect(markup).toContain('trend-mcap-index-value--large">1</span>');
  });

  test('renders empty state without blank cells', () => {
    const markup = renderTable([]);

    expect(markup).toContain('No Prudvi strategy rows matched the current filters.');
  });

  test('renders sector-style pagination with 25 rows per page', () => {
    const markup = renderTable(buildRows(27));

    expect(markup).toContain('Strong uptrend: 1');
    expect(markup).toContain('Showing 1-25 of 27 symbols');
    expect(markup).toContain('Next');
    expect(markup).toContain('ROW25');
    expect(markup).not.toContain('ROW26');
  });

  test('renders KPI cards from full loaded rows', () => {
    const loadedRows = [
      row,
      {
        ...row,
        S_NO: 2,
        SYMBOL: 'FILTERED',
        EMA_GT_20: 'N' as const,
        ADX_GT_25: 'N' as const,
        VOLUME_GT_20: 'N' as const,
      },
    ];
    const markup = renderTable([row], loadedRows);

    expect(markup).toContain('TOTAL STOCKS LOADED');
    expect(markup).toContain('TREND QUALIFIED STOCKS');
    expect(markup).toContain('FILTERED OUT STOCKS');
    expect(markup).toContain('CURRENT PAGE ROWS');
    expect(markup).toContain('BULLISH_CANDLE');
    expect(markup).toContain('EMA&gt;20');
    expect(markup).toContain('EMA&gt;50');
    expect(markup).toContain('RSI&gt;50');
    expect(markup).toContain('ADX&gt;25');
    expect(markup).toContain('MACD&gt;0');
    expect(markup).toContain('VOLUME&gt;20');
    expect(markup).toContain('DELIVERY%&gt;60');
    expect(markup).toContain('1 / 2');
    expect(markup).toContain('50.0%');
    expect(markup).not.toContain('FILTERED</span>');
  });

  test('uses an expanded non-clipping table viewport for the 25-row page', () => {
    const markup = renderTable(buildRows(25));

    expect(markup).toContain('overflow-x-auto overflow-y-visible lg:min-h-[780px]');
    expect(markup).not.toContain('max-h-[calc(100vh-260px)]');
  });
});
