import { beforeEach, describe, expect, test, vi } from 'vitest';
import * as apiClient from '../src/api/client';
import { fetchAsuraV3YearlySummary } from '../src/services/asuraV3Service';

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('asuraV3Service', () => {
  test('normalizes Oracle date-shaped SIGNAL_YEAR values to numeric years', async () => {
    vi.spyOn(apiClient, 'legacyApiGet').mockResolvedValue({
      items: [
        { SIGNAL_YEAR: '2026-01-01T00:00:00', TOTAL_TRADES: 14 },
        { signalYear: 2025, totalTrades: 61 },
      ],
    });

    const rows = await fetchAsuraV3YearlySummary();

    expect(rows.map((row) => row.signalYear)).toEqual([2026, 2025]);
    expect(rows[0].totalTrades).toBe(14);
  });
});
