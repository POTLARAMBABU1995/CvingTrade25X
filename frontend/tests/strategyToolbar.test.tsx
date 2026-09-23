import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { StrategyToolbar } from '../src/components/strategy/StrategyToolbar';

function textIndex(markup: string, text: string): number {
  const index = markup.indexOf(text);
  expect(index).toBeGreaterThanOrEqual(0);
  return index;
}

describe('StrategyToolbar', () => {
  test('renders the required two-row strategy toolbar order and meta format', () => {
    const markup = renderToStaticMarkup(
      <StrategyToolbar
        apiTimeMs={2770}
        dbTimeMs={0}
        lastRefreshed={new Date('2026-05-22T09:42:53')}
        loadTimeMs={3420}
        ltcDate="2026-05-22"
        onInsertDb={() => undefined}
        onDownload={() => undefined}
        onLiveRefresh={() => undefined}
        onRefresh={() => undefined}
        onSearchChange={() => undefined}
        onTimeframeChange={() => undefined}
        searchValue=""
        showInsertDb
        showTimeframe
        showTotal
        status="live"
        timeframe="daily"
        total={170}
      />,
    );

    const liveIndex = textIndex(markup, 'Live');
    const searchIndex = textIndex(markup, 'Search Symbol');
    const timeframeIndex = textIndex(markup, 'Daily');
    const totalIndex = textIndex(markup, 'Total: 170');
    const downloadIndex = textIndex(markup, 'Download TXT');
    const refreshIndex = textIndex(markup, 'Refresh');
    const insertIndex = textIndex(markup, 'Insert DB');

    expect(liveIndex).toBeLessThan(searchIndex);
    expect(searchIndex).toBeLessThan(timeframeIndex);
    expect(timeframeIndex).toBeLessThan(totalIndex);
    expect(totalIndex).toBeLessThan(downloadIndex);
    expect(downloadIndex).toBeLessThan(refreshIndex);
    expect(totalIndex).toBeLessThan(refreshIndex);
    expect(refreshIndex).toBeLessThan(insertIndex);
    expect(markup).toContain('LTC_DATE: 22-05-2026');
    expect(markup).toContain('Last refreshed: 09:42:53');
    expect(markup).toContain('Load: 3.42s');
    expect(markup).toContain('API: 2.77s');
    expect(markup).toContain('DB: 0ms');
    expect(markup).toContain('strategy-toolbar w-full strategy-toolbar-shell');
    expect(markup).toContain('strategy-toolbar-row-primary flex w-full items-center gap-3');
  });

  test('uses dynamic status labels and hides unsupported controls', () => {
    const markup = renderToStaticMarkup(
      <StrategyToolbar
        lastRefreshed={null}
        loadTimeMs={null}
        ltcDate={null}
        onLiveRefresh={() => undefined}
        onRefresh={() => undefined}
        onSearchChange={() => undefined}
        searchValue=""
        showTotal
        status="error"
        total={0}
      />,
    );

    expect(markup).toContain('Server Down');
    expect(markup).toContain('border-red-300');
    expect(markup).toContain('Total: 0');
    expect(markup).toContain('LTC_DATE: -');
    expect(markup).toContain('Last refreshed: -');
    expect(markup).toContain('Load: -');
    expect(markup).toContain('API: -');
    expect(markup).toContain('DB: -');
    expect(markup).not.toContain('Insert DB');
    expect(markup).not.toContain('aria-label="Timeframe"');
  });
});
