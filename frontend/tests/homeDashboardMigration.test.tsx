import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import {
  DashboardPage,
  buildTickerSegments,
  normalizeDashboardPayload,
  shouldAnimateDashboardTicker,
} from '../src/pages/dashboard/DashboardPage';
import { HomePage } from '../src/pages/static/HomePage';

const dashboardPayload = {
  breadth: { advances: 321, declines: 151, skip: 3, totalSymbols: 500, unchanged: 25 },
  breadthRows: [
    { advances: 34, declines: 12, expectedSymbols: 50, segment: 'nifty50', unchanged: 4 },
    { advances: 28, declines: 18, expectedSymbols: 50, segment: 'next50', unchanged: 2 },
  ],
  gainers: [{ percentage: 1.234, points: 12.5, price: 100.456, stockName: 'AAA' }],
  losers: [{ percentChange: -2.5, change: -9.75, close: 88.1, symbol: 'BBB' }],
  tradingDate: '2026-05-12',
};

describe('Home and Dashboard React migrations', () => {
  test('renders the migrated home landing content and active navigation targets', () => {
    const markup = renderToStaticMarkup(<HomePage />);

    expect(markup).toContain('Trade Smarter. Faster. Confidently.');
    expect(markup).toContain('href="/app/dashboard"');
    expect(markup).toContain('Login');
    expect(markup).toContain('Register');
    expect(markup).toContain('CvingTrade25X AI');
  });

  test('normalizes dashboard movers and breadth like the legacy table renderer', () => {
    const normalized = normalizeDashboardPayload(dashboardPayload);

    expect(normalized.gainers[0]).toMatchObject({
      percentage: '1.23%',
      points: '12.50',
      price: '100.46',
      stock: 'AAA',
    });
    expect(normalized.losers[0]).toMatchObject({
      percentage: '2.50%',
      points: '9.75',
      price: '88.10',
      stock: 'BBB',
    });
    expect(normalized.breadthRows.map((row) => row.index)).toEqual(['nifty50', 'next50', 'Nifty500']);
    expect(normalized.breadthRows[0].skip).toBe('0');
  });

  test('falls back to ticker movers when the primary dashboard payload has empty gainers and losers', () => {
    const normalized = normalizeDashboardPayload(
      {
        breadth: dashboardPayload.breadth,
        breadthRows: dashboardPayload.breadthRows,
        gainers: [],
        losers: [],
        tradingDate: dashboardPayload.tradingDate,
      },
      {
        gainers: dashboardPayload.gainers,
        losers: dashboardPayload.losers,
      },
    );

    expect(normalized.gainers[0]).toMatchObject({
      percentage: '1.23%',
      points: '12.50',
      price: '100.46',
      stock: 'AAA',
    });
    expect(normalized.losers[0]).toMatchObject({
      percentage: '2.50%',
      points: '9.75',
      price: '88.10',
      stock: 'BBB',
    });
  });

  test('renders dashboard tables without requiring the volume ticker feed', () => {
    const ticker = buildTickerSegments(dashboardPayload, { rows: [{ symbol: 'VOL', volumeRatio: 2.345 }] });
    const markup = renderToStaticMarkup(<DashboardPage disableFetch initialPayload={dashboardPayload} />);

    expect(ticker).toContain('Gainers (1):');
    expect(ticker).toContain('Losers (1):');
    expect(ticker).not.toContain('Volume (1):');
    expect(markup).toContain('Nifty50 Top 5 Gainers');
    expect(markup).toContain('Market Breadth');
    expect(markup).toContain('AAA');
    expect(markup).toContain('BBB');
    expect(markup).toContain('dashboard-react-page');
    expect(markup).toContain('dashboard-table--compact');
    expect(markup).toContain('dashboard-react-ticker');
    expect(markup).toContain('dashboard-react-ticker__track');
    expect(markup).not.toContain('<marquee');
    expect(markup).not.toContain('Investments in securities market are subject to market risk');
    expect(markup).toContain('data-active-section="dashboard"');
  });

  test('keeps the dashboard ticker animation active for live and fallback states', () => {
    expect(shouldAnimateDashboardTicker([{ label: 'Gainers', items: [{ display: '1.00%', symbol: 'AAA', tone: 'up' }] }])).toBe(true);
    expect(shouldAnimateDashboardTicker([{ label: 'Gainers', items: [] }])).toBe(true);
  });
});
