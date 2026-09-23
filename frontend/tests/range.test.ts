import { describe, expect, test } from 'vitest';
import { getInitialRange, mergeBars } from '../src/utils/range';


describe('range utils', () => {
  test('getInitialRange returns ISO dates', () => {
    const range = getInitialRange('1D');
    expect(range.from).toMatch(/\d{4}-\d{2}-\d{2}/);
    expect(range.to).toMatch(/\d{4}-\d{2}-\d{2}/);
  });

  test('mergeBars de-duplicates by timestamp', () => {
    const bars = mergeBars([
      [{ t: 1, o: 1, h: 1, l: 1, c: 1, v: 1 }],
      [{ t: 1, o: 2, h: 2, l: 2, c: 2, v: 2 }],
      [{ t: 2, o: 1, h: 1, l: 1, c: 1, v: 1 }],
    ]);
    expect(bars.length).toBe(2);
  });
});
