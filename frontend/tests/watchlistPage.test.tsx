import { readFileSync } from 'node:fs';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { CvingLegacyHeader } from '../src/components/navigation/CvingLegacyHeader';
import { missingWatchlistValueLabel, WatchlistPage, normalizeWatchlistSymbols } from '../src/pages/watchlist/WatchlistPage';

const watchlistSource = readFileSync(new URL('../src/pages/watchlist/WatchlistPage.tsx', import.meta.url), 'utf8');

describe('Trade SetUp Watchlist', () => {
  test('places Watchlist between Dashboard and Sector with Trade SetUp in its dropdown', () => {
    const markup = renderToStaticMarkup(<CvingLegacyHeader activeSection="tradesetup" />);
    const dashboard = markup.indexOf('Dashboard');
    const watchlist = markup.indexOf('Watchlist');
    const sector = markup.indexOf('Sector');
    expect(dashboard).toBeGreaterThan(-1);
    expect(watchlist).toBeGreaterThan(dashboard);
    expect(sector).toBeGreaterThan(watchlist);
    expect(markup).toContain('aria-label="Watchlist"');
    expect(markup).toContain('href="/app/tradesetup"');
    expect(markup).toContain('Trade SetUp');
    expect(markup).toMatch(/data-active="true"[^>]*data-section="tradesetup"/);
    expect(markup).not.toContain('href="/app/watchlist"');
  });

  test('starts empty and exposes manual NSE symbol create controls without a duplicate API', () => {
    const markup = renderToStaticMarkup(<WatchlistPage />);
    expect(markup).toContain('Dynamic Swing-Trading Watchlist');
    expect(markup.indexOf('strategy-toolbar')).toBeLessThan(markup.indexOf('Dynamic Swing-Trading Watchlist'));
    expect(markup).toContain('Search My Watchlist');
    expect(markup).toContain('Total: 0');
    expect(markup).toContain('LTC_DATE: -');
    expect(markup).toContain('Last refreshed: -');
    expect(markup).toContain('>Refresh</button>');
    expect(markup).not.toContain('Download TXT');
    expect(markup).not.toContain('NSE only');
    expect(markup).toContain('Main NSE symbols');
    expect(markup).toContain('id="watchlist-symbol"');
    expect(markup).toContain('Loading NSE symbols...');
    expect(markup).not.toContain('<datalist');
    expect(markup).toContain('disabled=""');
    expect(markup).toContain('aria-haspopup="listbox"');
    expect(markup).toContain('watchlist-symbol-label');
    expect(markup).toContain('aria-label="Add symbol to watchlist"');
    expect(markup).toContain('data-testid="watchlist-symbol-controls"');
    expect(markup).toContain('data-testid="watchlist-add-symbol-form"');
    expect(markup).toContain('lg:grid-cols-[minmax(160px,0.5fr)_auto_minmax(160px,0.5fr)_minmax(150px,0.5fr)_auto]');
    expect(markup).not.toContain('Reset filter');
    expect(markup).toContain('for="watchlist-saved-symbols"');
    expect(markup).toContain('>My Watchlist symbols<');
    expect(markup).toContain('data-testid="watchlist-saved-symbols"');
    expect(markup).toContain('block w-full min-w-0 rounded-xl');
    expect(markup).not.toContain('style="width:20ch"');
    expect(markup).toContain('No symbols added');
    expect(markup).toContain('data-testid="watchlist-add-symbol-button"');
    expect(markup).not.toContain('Add NSE symbols manually.');
    expect(markup).toContain('bg-emerald-600');
    expect(markup).not.toMatch(/(?:bg|border|text|ring)-rose-/);
    expect(markup).not.toMatch(/(?:bg|border|text|ring)-red-/);

    const symbolInput = markup.indexOf('id="watchlist-symbol"');
    const addButton = markup.indexOf('data-testid="watchlist-add-symbol-button"');
    const savedSymbols = markup.indexOf('id="watchlist-saved-symbols"');
    const setupState = markup.indexOf('id="watchlist-setup-state"');
    expect(addButton).toBeGreaterThan(symbolInput);
    expect(savedSymbols).toBeGreaterThan(addButton);
    expect(setupState).toBeGreaterThan(savedSymbols);
    expect(markup).toContain('Your watchlist is empty');
    expect(markup).toContain('role="tablist"');
    expect(markup).toContain('class="overflow-x-hidden" data-testid="watchlist-table-scroll"');
    expect(markup).toContain('Identity · Market · Setup');
    expect(markup).toContain('Support · Resistance');
    expect(markup).toContain('Confirmation · Actions');
    expect(markup).not.toMatch(/<th[^>]*>Identity<\/th>/);
    expect(markup).not.toMatch(/<th[^>]*>Targets<\/th>/);
    expect(markup).not.toContain('>TCS</td>');
    expect(markup).not.toContain('/api/watchlist');
  });

  test('reads every manually supplied normalized symbol and exposes update and delete operations', () => {
    const markup = renderToStaticMarkup(<WatchlistPage initialSymbols={['NSE:TCS-EQ', 'HDFCBANK', 'BAJAJ-AUTO']} />);
    expect(markup).toContain('>TCS</td>');
    expect(markup).toContain('<option value="TCS" selected="">TCS</option>');
    expect(markup).toContain('<option value="HDFCBANK">HDFCBANK</option>');
    expect(markup).toContain('<option value="BAJAJ-AUTO">BAJAJ-AUTO</option>');
    expect(markup).toContain('>Edit</button>');
    expect(markup).toContain('>Remove</button>');
    expect(markup).toContain('Manual S&amp;R');
    expect(markup).toContain('/app/technical/price-action');
    expect(markup).toContain('data-testid="watchlist-source-status"');
    expect(markup).toContain('Bars: Loading…');
    expect(markup).toContain('Sector Rotation: Loading…');
  });

  test('normalizes and de-duplicates all symbol tokens while preserving embedded hyphens', () => {
    expect(normalizeWatchlistSymbols(['NSE:TCS-EQ', 'tcs', 'NSE:BAJAJ-AUTO-EQ', 'UNKNOWN'])).toEqual(['TCS', 'BAJAJ-AUTO', 'UNKNOWN']);
  });

  test('never renders Loaded as a missing row value after a source completes', () => {
    expect(missingWatchlistValueLabel('LOADING')).toBe('Loading…');
    expect(missingWatchlistValueLabel('LOADED')).toBe('Not available');
    expect(missingWatchlistValueLabel('LOAD_FAILED')).toBe('No Data');
  });

  test('hydrates only the selected saved symbol on route entry', () => {
    expect(watchlistSource).toContain("hydrateSymbol(symbol, '-', true, requestController.signal)");
    expect(watchlistSource).not.toContain("Promise.all(symbols.map((symbol) => hydrateSymbol(symbol, '-', true))).finally");
  });
});
