import { describe, expect, test } from 'vitest';
import { shouldFetchTradingDayVerification } from '../src/pages/ops/TradingDayVerificationPanel';

describe('TradingDayVerificationPanel request guard', () => {
  test('does not auto-fetch verification on initial page load', () => {
    expect(shouldFetchTradingDayVerification(0)).toBe(false);
    expect(shouldFetchTradingDayVerification(1)).toBe(true);
  });
});
