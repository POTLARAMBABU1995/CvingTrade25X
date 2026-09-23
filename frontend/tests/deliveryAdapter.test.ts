import { describe, expect, test } from 'vitest';
import {
  adaptDeliveryPayload,
  DELIVERY_COLUMNS,
} from '../src/adapters/deliveryAdapter';

describe('delivery adapter', () => {
  test('maps delivery API payload with summary cards, pagination, and market-cap dash fallbacks', () => {
    const payload = adaptDeliveryPayload({
      status: 'success',
      data: [
        {
          s_no: 26,
          symbol: 'DELWIN',
          INDEX: null,
          MCAP: null,
          MCAP_RANK: null,
          price: 315.25,
          trading_date: '2026-05-01',
          ltc_date: '2026-05-11',
          t_d: 6,
          delivery_qty: 123456,
          delivery_qty_rising: true,
          delivery_pct: 45.67,
          delivery_score: 78,
        },
      ],
      total_records: 77,
      ltc_date: '2026-05-11',
      summary: {
        total_stocks: 77,
        delivery_pct_eq_100_count: 1,
        delivery_pct_gt_90_count: 2,
        delivery_pct_gt_80_count: 4,
        delivery_pct_gt_70_count: 6,
        delivery_pct_gt_60_count: 12,
        delivery_pct_gt_50_count: 18,
        delivery_pct_gt_40_count: 25,
        delivery_score_gt_100_count: 1,
        delivery_score_gt_90_count: 2,
        delivery_score_gt_80_count: 3,
        delivery_score_gt_70_count: 8,
        delivery_score_gt_60_count: 14,
        delivery_score_gt_50_count: 21,
        strong_accumulation_count: 4,
      },
    }, 2, 25);

    expect(DELIVERY_COLUMNS.map((column) => column.key)).toEqual([
      'sNo',
      'symbol',
      'index',
      'mcap',
      'mcapRank',
      'ltcDate',
      'price',
      'deliveryQty',
      'deliveryPct',
      'deliveryScore',
    ]);
    expect(payload.page).toBe(2);
    expect(payload.totalRecords).toBe(77);
    expect(payload.totalPages).toBe(4);
    expect(payload.latestLtcDate).toBe('2026-05-11');
    expect(payload.summary.totalStocks).toBe(77);
    expect(payload.summary.deliveryPctEq100Count).toBe(1);
    expect(payload.summary.deliveryPctGt90Count).toBe(2);
    expect(payload.summary.deliveryPctGt80Count).toBe(4);
    expect(payload.summary.deliveryPctGt70Count).toBe(6);
    expect(payload.summary.deliveryPctGt60Count).toBe(12);
    expect(payload.summary.deliveryPctGt50Count).toBe(18);
    expect(payload.summary.deliveryPctGt40Count).toBe(25);
    expect(payload.summary.deliveryScoreGt100Count).toBe(1);
    expect(payload.summary.deliveryScoreGt90Count).toBe(2);
    expect(payload.summary.deliveryScoreGt80Count).toBe(3);
    expect(payload.summary.deliveryScoreGt70Count).toBe(8);
    expect(payload.summary.deliveryScoreGt60Count).toBe(14);
    expect(payload.summary.deliveryScoreGt50Count).toBe(21);
    expect(payload.summary.strongAccumulationCount).toBe(4);
    expect(payload.rows[0].cells.sNo.text).toBe('26');
    expect(payload.rows[0].cells.index.text).toBe('-');
    expect(payload.rows[0].cells.mcap.text).toBe('-');
    expect(payload.rows[0].cells.mcapRank.text).toBe('-');
    expect(payload.rows[0].cells.tradingDate.text).toBe('01-05-2026');
    expect(payload.rows[0].cells.ltcDate.text).toBe('11-05-2026');
    expect(payload.rows[0].cells.tradingDays.text).toBe('6');
    expect(payload.rows[0].cells.deliveryQty.text).toBe('123,456 UP');
    expect(payload.rows[0].cells.deliveryPct.text).toBe('45.67%');
    expect(payload.rows[0].cells.deliveryScore.text).toBe('78');
  });

  test('uses payload latest LTC date and INDEX tone for market-cap cells', () => {
    const payload = adaptDeliveryPayload({
      status: 'success',
      data: [
        {
          s_no: 1,
          symbol: 'MIDWIN',
          INDEX: 'MID',
          MCAP: 12345.67,
          MCAP_RANK: 101,
          trading_date: '2026-01-15',
          ltc_date: '2026-01-15',
          t_d: 85,
          price: 412.5,
        },
      ],
      total_records: 1,
      ltc_date: '2026-05-15',
    }, 1, 25);

    const row = payload.rows[0];
    expect(row.cells.ltcDate.text).toBe('15-05-2026');
    expect(row.cells.tradingDays.text).toBe('85');
    expect(row.cells.symbol.marketCapTone).toBe('mid');
    expect(row.cells.index.marketCapTone).toBe('mid');
    expect(row.cells.mcap.marketCapTone).toBe('mid');
    expect(row.cells.mcapRank.marketCapTone).toBe('mid');
  });
});
