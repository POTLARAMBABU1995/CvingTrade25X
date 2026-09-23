import { readFileSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { CvingLegacyHeader } from '../src/components/navigation/CvingLegacyHeader';
import { getInternalNavigationTarget } from '../src/utils/internalNavigation';

const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

const dropdownClasses = [
  'cving-technical-dropdown',
  'cving-sector-dropdown',
  'cving-database-dropdown',
  'cving-fyers-dropdown',
  'cving-strategy-dropdown',
] as const;

describe('CvingLegacyHeader dropdown dark-mode styles', () => {
  test('keeps every shared dropdown covered by root dark theme selectors', () => {
    for (const className of dropdownClasses) {
      expect(styles).toContain(`:root[data-theme="dark"] .${className}`);
      expect(styles).toContain(`html.dark .${className}`);
      expect(styles).toContain(`body.dark .${className}`);
      expect(styles).toContain(`:root[data-theme="dark"] .${className}__link`);
      expect(styles).toContain(`html.dark .${className}__link`);
      expect(styles).toContain(`body.dark .${className}__link`);
    }
  });

  test('keeps dark dropdown default and interactive text colors readable', () => {
    expect(styles).toMatch(/:root\[data-theme="dark"\][\s\S]*\.cving-strategy-dropdown__link[\s\S]*color:\s*#e2e8f0;/);
    expect(styles).toMatch(/body\.dark[\s\S]*\.cving-strategy-dropdown__link--active[\s\S]*color:\s*#f8fafc;/);
  });

  test('keeps click-open dropdown selectors for every shared dropdown', () => {
    for (const className of dropdownClasses) {
      expect(styles).toContain(`.cving-legacy-nav__item--open .${className}`);
    }
  });

  test('keeps long Sector labels on one horizontal row', () => {
    expect(styles).toMatch(/\.cving-sector-dropdown\s*\{[\s\S]*width:\s*min\(250px,\s*calc\(100vw - 24px\)\);/);
    expect(styles).toMatch(/\.cving-sector-dropdown__link\s*\{[\s\S]*white-space:\s*nowrap;/);
  });
});

describe('CvingLegacyHeader dropdown trigger navigation', () => {
  test('renders dropdown top-level items as buttons so first click opens instead of navigating', () => {
    const markup = renderToStaticMarkup(
      createElement(CvingLegacyHeader, {
        activeSection: 'technicals',
        activeTechnicalPage: '/app/technical/ema',
      }),
    );

    for (const section of ['sector', 'technicals', 'database', 'fyers', 'strategy']) {
      expect(markup).toContain(`<button type="button" class="cving-legacy-nav__link`);
      expect(markup).toContain(`data-section="${section}"`);
      expect(markup).toContain(`aria-controls="cving-dropdown-${section}"`);
      expect(markup).toContain('aria-haspopup="menu"');
    }

    expect(markup).toContain('href="/app/dashboard"');
    expect(markup).toContain('href="/app/portfolio"');
    expect(markup).toContain('href="/app/technical/ema"');
    expect(markup).toContain('href="/app/sector/rotation"');
    expect(markup).not.toMatch(/<a[^>]+data-section="technicals"[^>]+href="/);
    expect(markup).not.toMatch(/<a[^>]+data-section="sector"[^>]+href="/);
  });
});

describe('internal navigation target detection', () => {
  const baseHref = 'http://127.0.0.1:5055/app/technical/ema';

  test('keeps same-origin app routes inside the React shell', () => {
    expect(getInternalNavigationTarget('/app/strategy/asura-v3', baseHref)).toBe('/app/strategy/asura-v3');
    expect(getInternalNavigationTarget('/app/sector/stocks/healthcare?tab=hierarchy', baseHref)).toBe('/app/sector/stocks/healthcare?tab=hierarchy');
    expect(getInternalNavigationTarget('/fundamental/reports#admin', baseHref)).toBe('/fundamental/reports#admin');
  });

  test('rejects external and non-page URLs', () => {
    expect(getInternalNavigationTarget('https://example.com/app/dashboard', baseHref)).toBeNull();
    expect(getInternalNavigationTarget('/api/health', baseHref)).toBeNull();
    expect(getInternalNavigationTarget('mailto:support@example.com', baseHref)).toBeNull();
  });
});
