import { describe, expect, test } from 'vitest';
import {
  formatScreenerLoadError,
  isTransientScreenerLoadError,
} from '../src/pages/technical/TechnicalScreenerPage';

describe('technical screener page recovery helpers', () => {
  test('classifies browser transport failures as transient', () => {
    expect(isTransientScreenerLoadError(new TypeError('Failed to fetch'))).toBe(true);
    expect(isTransientScreenerLoadError({ status: 0, message: 'NetworkError when attempting to fetch resource.' })).toBe(true);
  });

  test('does not retry real backend HTTP errors', () => {
    expect(isTransientScreenerLoadError({ status: 401, message: 'Session expired. Please login again.' })).toBe(false);
    expect(isTransientScreenerLoadError({ status: 500, message: 'Failed to build trendline payload' })).toBe(false);
  });

  test('keeps the stale-row message scoped to transient backend interruptions', () => {
    expect(formatScreenerLoadError(new TypeError('Failed to fetch'), true)).toContain('Showing the last loaded rows');
    expect(formatScreenerLoadError({ status: 401, message: 'Unauthorized' }, true)).toBe('Unauthorized');
  });
});
