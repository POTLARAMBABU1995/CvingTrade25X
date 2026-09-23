import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { CvingLegacyHeader } from '../src/components/navigation/CvingLegacyHeader';
import {
  findPhaseOneNavItem,
  isPhaseOnePath,
  phaseOneCategoryOrder,
  phaseOneItemsForCategory,
  phaseOneNavItems,
} from '../src/data/phaseOneNav';
import { PhaseOneWorkspacePage } from '../src/pages/phase-one/PhaseOneWorkspacePage';
import { buildPhaseOneRequests } from '../src/services/api/phaseOneApi';

describe('Phase 1 route and navigation contract', () => {
  test('keeps every additive Phase 1 page on a unique protected app route', () => {
    expect(phaseOneNavItems).toHaveLength(17);
    expect(new Set(phaseOneNavItems.map((item) => item.id)).size).toBe(phaseOneNavItems.length);
    expect(new Set(phaseOneNavItems.map((item) => item.href)).size).toBe(phaseOneNavItems.length);
    expect(phaseOneNavItems.every((item) => item.href.startsWith('/app/phase-1/'))).toBe(true);
    expect(phaseOneCategoryOrder.every((category) => phaseOneItemsForCategory(category).length > 0)).toBe(true);
  });

  test('maps the Phase 1 root to its dashboard without capturing existing routes', () => {
    expect(isPhaseOnePath('/app/phase-1')).toBe(true);
    expect(isPhaseOnePath('/app/phase-1/stock-360/')).toBe(true);
    expect(findPhaseOneNavItem('/app/phase-1')?.id).toBe('main-dashboard');
    expect(findPhaseOneNavItem('/app/phase-1/data-quality')?.id).toBe('data-quality');
    expect(isPhaseOnePath('/app/dashboard')).toBe(false);
    expect(isPhaseOnePath('/app/technical/ema')).toBe(false);
  });

  test('adds one non-dropdown Phase 1 entry to the existing header', () => {
    const markup = renderToStaticMarkup(<CvingLegacyHeader activeSection="phase1" />);

    expect(markup).toContain('href="/app/phase-1"');
    expect(markup).toMatch(/data-active="true"[^>]*data-section="phase1"/);
    expect(markup).not.toContain('aria-controls="cving-dropdown-phase1"');
  });
});

describe('Phase 1 existing-service reuse', () => {
  test('builds Stock 360 reads from approved chart and SR endpoints', () => {
    const requests = buildPhaseOneRequests('stock-360', 'NSE:RELIANCE-EQ');

    expect(requests.map((request) => request.path)).toEqual([
      '/api/bars',
      '/api/indicators',
      '/api/overlays',
      '/api/sr-levels',
    ]);
    expect(requests.every((request) => request.params?.symbol === 'RELIANCE' || request.params?.search === 'RELIANCE')).toBe(true);
    expect(requests.filter((request) => request.kind === 'chart').every((request) => request.params?.tf === '1D')).toBe(true);
  });

  test('uses the current delivery and manual-level query contracts', () => {
    const delivery = buildPhaseOneRequests('volume-delivery', 'RELIANCE');
    const supportResistance = buildPhaseOneRequests('support-resistance', 'RELIANCE');

    expect(delivery.find((request) => request.key === 'delivery')?.params?.sort_by).toBe('DELIVERY_SCORE');
    expect(supportResistance.find((request) => request.key === 'manual')?.params).toEqual({ search: 'RELIANCE' });
  });

  test('renders isolated category and page navigation with live source evidence', () => {
    const markup = renderToStaticMarkup(
      <PhaseOneWorkspacePage
        currentPath="/app/phase-1/dashboard"
        disableFetch
        initialSources={[
          {
            endpoint: '/api/health',
            key: 'health',
            label: 'Application health',
            payload: { status: 'ok', total: 193 },
            status: 'online',
          },
        ]}
      />,
    );

    expect(markup.match(/aria-label="Phase 1 category navigation"/g)).toHaveLength(1);
    expect(markup.match(/aria-label="Phase 1 page navigation"/g)).toHaveLength(1);
    expect(markup).toContain('id="phase-one-page-title"');
    expect(markup).toContain('Main Dashboard');
    expect(markup).toContain('Application health');
    expect(markup).toContain('GET /api/health');
    expect(markup).toContain('This Phase 1 surface is read-only');
  });
});
