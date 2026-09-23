import { describe, expect, test } from 'vitest';
import {
  adaptSrLevelsPayload,
  SR_LEVELS_COLUMNS,
} from '../src/adapters/srLevelsAdapter';

describe('support resistance adapter', () => {
  test('maps legacy SR fields, meta pagination, trend counts, and dash fallbacks', () => {
    const payload = adaptSrLevelsPayload({
      rows: [
        {
          SYMBOL: 'SRWIN',
          INDEX: null,
          MCAP: null,
          MCAP_RANK: null,
          price: 425.25,
          tradingDate: '01-01-1998',
          ltcDate: '11-05-2026',
          tradingDays: null,
          supportDisplay: 'S1: 410',
          resistanceDisplay: 'R1: 450',
          SCORE: 88,
          trend_direction: 'Uptrend',
          priceAction: { label: 'Breakout', state: 'breakout' },
        },
      ],
      meta: {
        page: 2,
        page_size: 15,
        total_rows: 31,
        total_pages: 3,
        trendCounts: { uptrend: 7, downtrend: 2, consolidation: 1, total: 10 },
      },
    }, 2, 15);

    expect(SR_LEVELS_COLUMNS.map((column) => column.key)).toEqual([
      'sNo',
      'symbol',
      'index',
      'mcap',
      'mcapRank',
      'price',
      'tradingDate',
      'ltcDate',
      'tradingDays',
      'support',
      'resistance',
      'score',
      'trendDirection',
      'priceAction',
    ]);
    expect(payload.page).toBe(2);
    expect(payload.totalRows).toBe(31);
    expect(payload.totalPages).toBe(3);
    expect(payload.trendCounts).toEqual({ uptrend: 7, downtrend: 2, consolidation: 1, total: 10 });
    expect(payload.rows[0].cells.sNo.text).toBe('16');
    expect(payload.rows[0].cells.index.text).toBe('-');
    expect(payload.rows[0].cells.mcap.text).toBe('-');
    expect(payload.rows[0].cells.mcapRank.text).toBe('-');
    expect(payload.rows[0].cells.tradingDate.text).toBe('N/A');
    expect(payload.rows[0].cells.tradingDays.text).toBe('N/A');
    expect(payload.rows[0].cells.support.text).toBe('S1: 410');
    expect(payload.rows[0].cells.resistance.text).toBe('R1: 450');
    expect(payload.rows[0].cells.score.sort).toBe(88);
    expect(payload.rows[0].cells.trendDirection.text).toBe('Uptrend');
    expect(payload.rows[0].cells.priceAction.text).toBe('Breakout');
  });
});
