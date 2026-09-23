import { describe, expect, test } from 'vitest';
import { parseSessionExpiry } from '../src/services/auth/authSessionStore';

describe('auth session storage helpers', () => {
  test('parses epoch seconds and milliseconds consistently', () => {
    expect(parseSessionExpiry('1700000000')).toBe(1700000000000);
    expect(parseSessionExpiry('1700000000000')).toBe(1700000000000);
  });

  test('parses backend UTC ISO session expiry values', () => {
    expect(parseSessionExpiry('2026-05-24T10:15:30Z')).toBe(Date.parse('2026-05-24T10:15:30Z'));
  });

  test('rejects empty or invalid expiry values', () => {
    expect(parseSessionExpiry('')).toBe(0);
    expect(parseSessionExpiry('not-a-date')).toBe(0);
  });
});
