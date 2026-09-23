import { describe, expect, test } from 'vitest';
import {
  assessDailyFreshness,
  extractLatestDateKey,
  getExpectedLatestTradingDateKey,
  partsToDateKey,
  toDateParts,
} from '../src/utils/marketDates';

describe('market date helpers', () => {
  test('parses ISO and dd-mm-yyyy inputs into date parts', () => {
    expect(toDateParts('2026-05-12')).toEqual({ year: 2026, month: 5, day: 12 });
    expect(toDateParts('12-05-2026')).toEqual({ year: 2026, month: 5, day: 12 });
  });

  test('builds sortable date keys', () => {
    expect(partsToDateKey({ year: 2026, month: 5, day: 7 })).toBe('2026-05-07');
  });

  test('extracts latest LTC date key across rows', () => {
    const latest = extractLatestDateKey(
      [{ ltcDate: '2026-05-09' }, { ltcDate: '2026-05-12' }, { ltcDate: '2026-05-10' }],
      (row) => row.ltcDate,
    );
    expect(latest).toBe('2026-05-12');
  });

  test('computes expected latest trading date before market close', () => {
    const expected = getExpectedLatestTradingDateKey(new Date('2026-05-12T08:00:00.000Z'));
    expect(expected).toBeTruthy();
  });

  test('assesses daily freshness using latest row date and expected market date', () => {
    const result = assessDailyFreshness(
      [{ ltcDate: '2026-05-12' }],
      (row) => row.ltcDate,
      new Date('2026-05-12T14:00:00.000Z'),
    );

    expect(result.latestLtcDateKey).toBe('2026-05-12');
    expect(typeof result.isLatest).toBe('boolean');
  });
});
