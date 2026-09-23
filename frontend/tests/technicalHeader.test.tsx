import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { CvingLegacyHeader } from '../src/components/navigation/CvingLegacyHeader';
import { technicalNavItems } from '../src/data/technicalNav';

const expectedLabels = [
  'EMA-20/50/100/200',
  'RSI > 50',
  'MACD > 0',
  'ATR 14',
  'ADX',
  'Price Action SR',
  'Price Action Analysis',
  'Trendline',
  'Breakout',
  'Chart Patterns',
  'Strong Technicals',
  'Price Action SR',
  'Volume MA > 20',
  'Delivery',
];

function escapeHtmlText(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function renderHeader(): string {
  return renderToStaticMarkup(<CvingLegacyHeader activeSection="technicals" activeTechnicalPage="ema.html" />);
}

describe('CvingLegacyHeader Technicals dropdown', () => {
  test('renders all Technicals items in the required order', () => {
    expect(technicalNavItems.map((item) => item.label)).toEqual(expectedLabels);

    const markup = renderHeader();
    let previousIndex = -1;
    for (const label of expectedLabels) {
      const index = markup.indexOf(escapeHtmlText(label), previousIndex + 1);
      expect(index).toBeGreaterThan(previousIndex);
      previousIndex = index;
    }
    expect(markup).not.toMatch(/suppor\s*&\s*resistance/i);
    expect(markup).not.toContain('SUPPORT &amp; RESISTANCE');
  });

  test('keeps Technicals items on canonical React routes', () => {
    const markup = renderHeader();

    expect(markup).toContain('href="/app/technical/ema"');
    expect(markup).toContain('href="/app/technical/rsi50"');
    expect(markup).toContain('href="/app/technical/macd"');
    expect(markup).toContain('href="/app/technical/delivery"');
    expect(markup).not.toMatch(/href="\/[^"]+\.html"/i);
  });

  test('marks only the Technicals top-level item and EMA submenu item active', () => {
    const markup = renderHeader();
    const activeMarkers = markup.match(/data-active="true"/g) ?? [];

    expect(markup).toContain('data-active-section="technicals"');
    expect(activeMarkers).toHaveLength(2);
    expect(markup).toMatch(/data-active="true"[^>]*data-section="technicals"/);
    expect(markup).toMatch(/data-active="true"[^>]*data-technical-page="ema\.html"/);
    expect(markup).not.toMatch(/data-active="true"[^>]*data-technical-page="rsi50\.html"/);
  });
});
