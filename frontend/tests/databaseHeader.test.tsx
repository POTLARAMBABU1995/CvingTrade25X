import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { CvingLegacyHeader } from '../src/components/navigation/CvingLegacyHeader';
import { databaseNavItems } from '../src/data/databaseNav';

const expectedLabels = [
  'Stock History',
  'Historical Data',
  'Corporate Actions',
  'NSE Market Cap',
  'NSE Market Cap Index',
  'NSE FFMC',
  'NSE Delivery Data',
  'Server',
];

function escapeHtmlText(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function renderHeader(): string {
  return renderToStaticMarkup(<CvingLegacyHeader activeSection="database" activeDatabasePage="database.html" />);
}

describe('CvingLegacyHeader Database dropdown', () => {
  test('renders all Database items in the required order', () => {
    expect(databaseNavItems.map((item) => item.label)).toEqual(expectedLabels);

    const markup = renderHeader();
    let previousIndex = -1;
    for (const label of expectedLabels) {
      const index = markup.indexOf(escapeHtmlText(label));
      expect(index).toBeGreaterThan(previousIndex);
      previousIndex = index;
    }
  });

  test('keeps Database items on canonical React routes', () => {
    const markup = renderHeader();

    expect(markup).toContain('href="/app/database/stock-history"');
    expect(markup).toContain('href="/app/database/historical-data"');
    expect(markup).toContain('href="/app/database/corporate-actions"');
    expect(markup).toContain('href="/app/database/nse-market-cap"');
    expect(markup).toContain('href="/app/database/nse-market-cap-index"');
    expect(markup).toContain('href="/app/database/nse-ffmc"');
    expect(markup).toContain('href="/app/database/nse-delivery-data"');
    expect(markup).toContain('href="/app/database/server"');
    expect(markup).not.toMatch(/href="\/[^"]+\.html"/i);
  });

  test('marks only the Database top-level item and active submenu item active', () => {
    const markup = renderHeader();
    const activeMarkers = markup.match(/data-active="true"/g) ?? [];

    expect(markup).toContain('data-active-section="database"');
    expect(activeMarkers).toHaveLength(2);
    expect(markup).toMatch(/data-active="true"[^>]*data-section="database"/);
    expect(markup).toMatch(/data-active="true"[^>]*data-database-page="database\.html"/);
    expect(markup).not.toMatch(/data-active="true"[^>]*data-database-page="historical_data\.html"/);
  });
});
