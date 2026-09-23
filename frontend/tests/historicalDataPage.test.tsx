import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { HistoricalDataPage } from '../src/pages/ops/HistoricalDataPage';

describe('HistoricalDataPage', () => {
  test('renders the historical toolbar without insert-db or latest-date filter inputs', () => {
    const markup = renderToStaticMarkup(<HistoricalDataPage />);

    expect(markup).toContain('Historical Data');
    expect(markup).toContain('Syncing');
    expect(markup).toContain('Daily');
    expect(markup).toContain('Total: 0');
    expect(markup).toContain('Refresh');
    expect(markup).toContain('Source Table');
    expect(markup).toContain('Selected Table');
    expect(markup).toContain('S.NO');
    expect(markup).toContain('Download');
    expect(markup).toContain('Trade_Date');
    expect(markup).toContain('historical-data-strategy-toolbar');
    expect(markup).toContain('historical-data-table-shell');
    expect(markup).not.toContain('data-col="select"');
    expect(markup).not.toContain('Symbol Summary');
    expect(markup).not.toContain('Insert DB');
    expect(markup).not.toContain('Latest Trading Date From');
    expect(markup).not.toContain('Latest Trading Date To');
    expect(markup).not.toContain('Delete Selected');
  });
});
