import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { CvingLegacyHeader } from '../src/components/navigation/CvingLegacyHeader';

const expectedLabels = [
  'Automation',
  'Uniform_Data',
  'Holdings',
  'NIFTY500 Sync',
];

function renderHeader(): string {
  return renderToStaticMarkup(
    <CvingLegacyHeader activeSection="fyers" activeFyersPage="/app/fyers/automation" />,
  );
}

describe('CvingLegacyHeader FyersAPI dropdown', () => {
  test('renders all FyersAPI items in the required order', () => {
    const markup = renderHeader();
    let previousIndex = -1;

    for (const label of expectedLabels) {
      const index = markup.indexOf(label);
      expect(index).toBeGreaterThan(previousIndex);
      previousIndex = index;
    }
  });

  test('keeps FyersAPI items on canonical React routes', () => {
    const markup = renderHeader();

    expect(markup).toContain('href="/app/fyers/automation"');
    expect(markup).toContain('href="/app/fyers/failed-symbols"');
    expect(markup).toContain('href="/app/fyers/holdings"');
    expect(markup).toContain('href="/app/fyers/nifty500-sync"');
    expect(markup).not.toMatch(/href="\/[^"]+\.html"/i);
  });

  test('marks only the FyersAPI top-level item and active submenu item active', () => {
    const markup = renderHeader();
    const activeMarkers = markup.match(/data-active="true"/g) ?? [];

    expect(markup).toContain('data-active-section="fyers"');
    expect(activeMarkers).toHaveLength(2);
    expect(markup).toMatch(/data-active="true"[^>]*data-section="fyers"/);
    expect(markup).toMatch(/data-active="true"[^>]*data-fyers-page="\/app\/fyers\/automation"/);
    expect(markup).not.toMatch(/data-active="true"[^>]*data-fyers-page="\/app\/fyers\/holdings"/);
  });
});

