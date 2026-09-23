import { describe, expect, test } from 'vitest';
import {
  isMarketWorkingDate,
  isNseHolidayDate,
  isSpecialMarketWorkingDate,
  isWeekendDate,
  marketClosedReason,
  previousMarketWorkingDateIso,
} from '../src/utils/marketCalendar';

describe('market calendar utility', () => {
  test('blocks weekends and NSE 2026 holidays by default', () => {
    expect(isWeekendDate('2026-05-30')).toBe(true);
    expect(isMarketWorkingDate('2026-05-30')).toBe(false);
    expect(isNseHolidayDate('2026-05-28')).toBe(true);
    expect(isMarketWorkingDate('2026-05-28')).toBe(false);
    expect(marketClosedReason('2026-05-28')).toBe('NSE market holiday');
  });

  test('returns the latest working date when today is a weekend', () => {
    expect(previousMarketWorkingDateIso(new Date(2026, 4, 30))).toBe('2026-05-29');
  });

  test('matches the approved 2026 NSE holiday corrections', () => {
    expect(isNseHolidayDate('2026-01-15')).toBe(true);
    expect(isMarketWorkingDate('2026-01-15')).toBe(false);
    expect(marketClosedReason('2026-01-15')).toBe('NSE market holiday');
    expect(isNseHolidayDate('2026-11-10')).toBe(false);
    expect(isMarketWorkingDate('2026-11-10')).toBe(true);
    expect(marketClosedReason('2026-11-10')).toBe('');
    expect(isNseHolidayDate('2026-11-11')).toBe(true);
    expect(isMarketWorkingDate('2026-11-11')).toBe(false);
    expect(marketClosedReason('2026-11-11')).toBe('NSE market holiday');
  });

  test('treats budget day 2026 special Sunday session as a working date', () => {
    expect(isWeekendDate('2026-02-01')).toBe(true);
    expect(isSpecialMarketWorkingDate('2026-02-01')).toBe(true);
    expect(isMarketWorkingDate('2026-02-01')).toBe(true);
    expect(marketClosedReason('2026-02-01')).toBe('');
  });
});
