import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { StrategyToolbar } from '../src/components/strategy/StrategyToolbar';

describe('StrategyToolbar singleSurface', () => {
  test('flattens the toolbar into one visible surface without the outer shell card', () => {
    const markup = renderToStaticMarkup(
      <StrategyToolbar
        lastRefreshed={new Date('2026-06-30T06:06:39')}
        ltcDate="2026-06-29"
        onLiveRefresh={() => undefined}
        onRefresh={() => undefined}
        onSearchChange={() => undefined}
        searchPlaceholder="Search Card"
        searchValue=""
        showTotal
        singleSurface
        status="live"
        total={10}
      />,
    );

    expect(markup).not.toContain('strategy-toolbar-shell');
    expect(markup).toContain('strategy-toolbar-scroll');
    expect(markup).toContain('rounded-[32px]');
    expect(markup).toContain('bg-sky-50/95');
    expect(markup).toContain('dark:bg-sky-50/95');
    expect(markup).not.toContain('dark:bg-slate-900/55');
    expect(markup).toContain('dark:bg-white/95');
    expect(markup).not.toContain('shadow-inner');
    expect(markup).toContain('Search Card');
    expect(markup).toContain('Total: 10');
    expect(markup).toContain('LTC_DATE: 29-06-2026');
    expect(markup).toContain('Last refreshed: 06:06:39');
  });
});
