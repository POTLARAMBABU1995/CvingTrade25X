import { describe, expect, test } from 'vitest';
import {
  buildFyersAuthStatusMessage,
  describeWeekendRange,
  FYERS_AUTH_EXPIRED_TOAST,
  getFyersAuthExpiredToast,
} from '../src/pages/fyers/fyersPageUtils';

describe('fyersPageUtils', () => {
  test('formats authenticated auth status with expiry when available', () => {
    const message = buildFyersAuthStatusMessage({
      authenticated: true,
      expiresAt: '2026-05-23T12:00:00+05:30',
      expiryAvailable: true,
    });

    expect(message).toContain('Authorization status loaded. Authenticated. Expires:');
    expect(message).toContain('23-05-2026 12:00 PM');
  });

  test('detects weekend-only and mixed ranges', () => {
    expect(describeWeekendRange('2026-05-23', '2026-05-24')).toEqual({ block: true, warn: false });
    expect(describeWeekendRange('2026-05-22', '2026-05-24')).toEqual({ block: false, warn: true });
  });

  test('extracts the auth-expired toast from backend payloads', () => {
    expect(getFyersAuthExpiredToast({
      errorCode: 'FYERS_AUTH_FAILED',
      uiMessage: FYERS_AUTH_EXPIRED_TOAST,
    })).toBe(FYERS_AUTH_EXPIRED_TOAST);
  });
});
