import { describe, expect, test } from 'vitest';
import { buildLocalStrategyRows, getLocalMarketDataset } from '../src/services/static/legacyMarketDataset';

describe('legacyMarketDataset', () => {
  test('enriches the local strategy rows with derived technical columns', () => {
    const dataset = getLocalMarketDataset();
    const rows = buildLocalStrategyRows(dataset.screener);

    expect(rows).toHaveLength(dataset.screener.length);
    expect(rows[0].symbol).toBe('SYM1');
    expect(rows[0].high1y).toBe(rows[0].high52);
    expect(rows[0].emaDays).toContain('20:');
    expect(rows[0].rsi).toMatch(/^\d+\.\d{2}$/);
    expect(rows[0].macd).toMatch(/^-?\d+\.\d{2}$/);
    expect(rows[0].atr).toMatch(/^\d+\.\d{2}$/);
    expect(rows[0].support).not.toBe('');
    expect(rows[0].resistance).not.toBe('');
  });
});
