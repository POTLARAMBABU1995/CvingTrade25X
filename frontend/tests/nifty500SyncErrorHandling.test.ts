import { beforeEach, describe, expect, test, vi } from 'vitest';
import { legacyApiPost } from '../src/api/client';
import { buildNifty500SyncErrorContent, normalizeNifty500SyncSnapshot } from '../src/pages/fyers/Nifty500SyncPage';

describe('NIFTY500 sync error handling', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  test('uses backend message fields for API request errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          message: 'No symbols were found in the uploaded file. Ensure the file contains a symbol column.',
          request_id: 'CVT25X-TEST-400',
          status: 'error',
        }),
        {
          headers: { 'Content-Type': 'application/json' },
          status: 400,
        },
      ),
    ));

    await expect(legacyApiPost('/api/marketdata/fyers/nifty500-sync/compare', {})).rejects.toMatchObject({
      message: 'No symbols were found in the uploaded file. Ensure the file contains a symbol column.',
      status: 400,
    });
  });

  test('builds a targeted custom error page message for empty-symbol uploads', () => {
    const content = buildNifty500SyncErrorContent(
      {
        action: 'compare',
        message: 'No symbols were found in the uploaded file. Ensure the file contains a symbol column.',
      },
      'agriculture_sector_symbols47.csv',
    );

    expect(content.title).toBe('Uploaded file has no valid symbols');
    expect(content.retryLabel).toBe('Retry Compare');
    expect(content.description).toContain('agriculture_sector_symbols47.csv');
    expect(content.guidance).toContain('header named symbol');
  });

  test('unwraps a deployed snapshot envelope before rendering existing CSV rows', () => {
    const snapshot = normalizeNifty500SyncSnapshot({
      data: {
        existing: { rows: [{ symbol: 'RELIANCE' }], totalCount: 1 },
        summary: { matchedCount: 0 },
      },
    });

    expect(snapshot.existing).toEqual({ rows: [{ symbol: 'RELIANCE' }], totalCount: 1 });
    expect(snapshot.summary).toEqual({ matchedCount: 0 });
  });
});
