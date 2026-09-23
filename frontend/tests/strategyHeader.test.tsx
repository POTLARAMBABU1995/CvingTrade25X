import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { CvingLegacyHeader } from '../src/components/navigation/CvingLegacyHeader';

const expectedLabels = [
  'Stock Chart',
  'Asura',
  'Bhramhaputra',
  'Bhramhastra',
  'Ganga',
  'Kaveri',
  'Prudvi',
  'Thrinethra',
  'Thrisul',
  'Yamuna',
];

function escapeHtmlText(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function renderHeader(): string {
  return renderToStaticMarkup(
    <CvingLegacyHeader activeSection="strategy" {...{ activeStrategyPage: 'asura.html' }} />,
  );
}

describe('CvingLegacyHeader Strategy dropdown', () => {
  test('renders all Strategy items in the required order', () => {
    const markup = renderHeader();
    let previousIndex = -1;

    for (const label of expectedLabels) {
      const index = markup.indexOf(escapeHtmlText(label));
      expect(index).toBeGreaterThan(previousIndex);
      previousIndex = index;
    }
  });

  test('keeps Strategy items on canonical React routes', () => {
    const markup = renderHeader();

    expect(markup).toContain('href="/app/strategy/stock-chart"');
    expect(markup).toContain('href="/app/strategy/asura"');
    expect(markup).toContain('href="/app/strategy/bhramhaputra"');
    expect(markup).toContain('href="/app/strategy/bhramhastra"');
    expect(markup).toContain('href="/app/strategy/ganga"');
    expect(markup).toContain('href="/app/strategy/kaveri"');
    expect(markup).toContain('href="/app/strategy/prudvi"');
    expect(markup).toContain('href="/app/strategy/thrinethra"');
    expect(markup).toContain('href="/app/strategy/thrisul"');
    expect(markup).toContain('href="/app/strategy/yamuna"');
    expect(markup).not.toMatch(/href="\/[^"]+\.html"/i);
    expect(markup).not.toContain('Strategy.bak.html');
  });

  test('marks only the Strategy top-level item and active submenu item active', () => {
    const markup = renderHeader();
    const activeMarkers = markup.match(/data-active="true"/g) ?? [];

    expect(markup).toContain('data-active-section="strategy"');
    expect(activeMarkers).toHaveLength(2);
    expect(markup).toMatch(/data-active="true"[^>]*data-section="strategy"/);
    expect(markup).toMatch(/data-active="true"[^>]*data-strategy-page="asura\.html"/);
    expect(markup).not.toMatch(/data-active="true"[^>]*data-strategy-page="bhramhastra\.html"/);
  });
});
