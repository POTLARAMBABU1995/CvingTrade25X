import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { CvingLegacyHeader } from '../src/components/navigation/CvingLegacyHeader';

const expectedLabels = [
  'Sector Rotation',
  'StockEdge Sector Rotation',
  'Sector_Overview',
  'Sector Wise Stocks',
];

function renderHeader(): string {
  return renderToStaticMarkup(
    <CvingLegacyHeader activeSection="sector" {...{ activeSectorPage: '/app/sector/rotation' }} />,
  );
}

describe('CvingLegacyHeader Sector dropdown', () => {
  test('renders all Sector items in the required order', () => {
    const markup = renderHeader();
    let previousIndex = -1;

    for (const label of expectedLabels) {
      const index = markup.indexOf(label);
      expect(index).toBeGreaterThan(previousIndex);
      previousIndex = index;
    }
  });

  test('keeps Sector items on canonical React routes', () => {
    const markup = renderHeader();

    expect(markup).toContain('href="/app/sector/rotation"');
    expect(markup).toContain('href="/app/sector/stockedge-rotation"');
    expect(markup).toContain('href="/app/sector/overview"');
    expect(markup).toContain('href="/app/sector/stocks/auto"');
    expect(markup).not.toMatch(/href="\/[^"]+\.html"/i);
  });

  test('marks only the Sector top-level item and active submenu item active', () => {
    const markup = renderHeader();
    const activeMarkers = markup.match(/data-active="true"/g) ?? [];

    expect(markup).toContain('data-active-section="sector"');
    expect(activeMarkers).toHaveLength(2);
    expect(markup).toMatch(/data-active="true"[^>]*data-section="sector"/);
    expect(markup).toMatch(/data-active="true"[^>]*data-sector-page="\/app\/sector\/rotation"/);
    expect(markup).not.toMatch(/data-active="true"[^>]*data-sector-page="\/app\/sector\/stocks\/auto"/);
  });

  test('keeps Sector Wise Stocks active for migrated sector detail pages', () => {
    const markup = renderToStaticMarkup(
      <CvingLegacyHeader activeSection="sector" {...{ activeSectorPage: '/app/sector/stocks/bank' }} />,
    );

    expect(markup).toMatch(/data-active="true"[^>]*data-sector-page="\/app\/sector\/stocks\/auto"/);
  });
});
