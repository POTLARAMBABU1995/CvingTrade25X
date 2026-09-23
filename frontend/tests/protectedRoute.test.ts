import { describe, expect, test } from 'vitest';
import { isPublicPhase4Path } from '../src/App';
import { shouldBlockProtectedRoute } from '../src/components/auth/ProtectedRoute';

describe('ProtectedRoute session verification', () => {
  test('keeps authenticated content visible while server verification runs in background', () => {
    expect(shouldBlockProtectedRoute({
      isAuthenticated: true,
      isLoading: true,
    })).toBe(false);
  });

  test('blocks protected content while an unauthenticated session is being verified', () => {
    expect(shouldBlockProtectedRoute({
      isAuthenticated: false,
      isLoading: true,
    })).toBe(true);
  });

  test('keeps the three NSE database pages public without widening to Market Cap Index', () => {
    expect(isPublicPhase4Path('/app/database/nse-market-cap')).toBe(true);
    expect(isPublicPhase4Path('/app/database/nse-ffmc')).toBe(true);
    expect(isPublicPhase4Path('/app/database/nse-delivery-data')).toBe(true);
    expect(isPublicPhase4Path('/app/database/nse-market-cap-index')).toBe(false);
  });
});
