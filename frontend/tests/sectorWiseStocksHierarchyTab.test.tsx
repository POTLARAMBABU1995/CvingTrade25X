import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { sectorPageItems } from '../src/data/sectorNav';
import { SectorWiseStocksPage } from '../src/pages/sector/SectorWiseStocksPage';

describe('SectorWiseStocksPage hierarchy tab integration', () => {
  test('renders the title row with dropdown and hierarchy tabs while keeping stocks tab content as default', () => {
    const autoPage = sectorPageItems.find((item) => item.code === 'AUTO');
    expect(autoPage).toBeDefined();
    const markup = renderToStaticMarkup(<SectorWiseStocksPage sectorPage={autoPage!} />);
    const titleIndex = markup.indexOf('AUTO MOBILE');
    const dropdownIndex = markup.indexOf('aria-label="Select sector"');
    const stocksTabIndex = markup.lastIndexOf('Existing Sector Wise Stocks');
    const hierarchyTabIndex = markup.lastIndexOf('Sector Hierarchy');

    expect(markup).toContain('Existing Sector Wise Stocks');
    expect(markup).toContain('Sector Hierarchy');
    expect(markup).toContain('AUTO MOBILE');
    expect(markup).toContain('value="AUTO" selected="">7. Auto Mobile<');
    expect(titleIndex).toBeGreaterThanOrEqual(0);
    expect(dropdownIndex).toBeGreaterThan(titleIndex);
    expect(stocksTabIndex).toBeGreaterThan(dropdownIndex);
    expect(hierarchyTabIndex).toBeGreaterThan(stocksTabIndex);
    expect(markup).not.toContain('No hierarchy tree available for the selected parent sector.');
  });
});
