import { beforeEach, describe, expect, test, vi } from 'vitest';
import * as apiClient from '../src/api/client';
import * as fyersApi from '../src/services/api/fyersApi';

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('fyersApi', () => {
  test('starts FYERS authorization without a synthetic client timeout', async () => {
    const spy = vi.spyOn(apiClient, 'legacyApiPost').mockResolvedValue({ job_id: 'auth-1' });

    await fyersApi.authorizeFyers(true);

    expect(spy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/authorize',
      { force: true },
      expect.objectContaining({ timeoutMs: null }),
    );
  });

  test('loads FYERS auth status without a synthetic client timeout', async () => {
    const spy = vi.spyOn(apiClient, 'legacyApiGet').mockResolvedValue({ ok: true });

    await fyersApi.fetchFyersAuthStatus();

    expect(spy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/auth-status',
      undefined,
      expect.objectContaining({ timeoutMs: null }),
    );
  });

  test('starts background automation without a synthetic client timeout', async () => {
    const spy = vi.spyOn(apiClient, 'legacyApiPost').mockResolvedValue({ job_id: 'job-1' });

    await fyersApi.startFyersAutomation({ startDate: '2026-06-17', endDate: '2026-06-17' });

    expect(spy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/automation/start',
      { startDate: '2026-06-17', endDate: '2026-06-17' },
      expect.objectContaining({ timeoutMs: null }),
    );
  });

  test('polls background automation status without a synthetic client timeout', async () => {
    const spy = vi.spyOn(apiClient, 'legacyApiGet').mockResolvedValue({ status: 'RUNNING' });

    await fyersApi.fetchFyersAutomationStatus('job/1');

    expect(spy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/automation/status/job%2F1',
      undefined,
      expect.objectContaining({ timeoutMs: null }),
    );
  });

  test('uses no-timeout policy for automation operations and failed-symbol reads/reruns', async () => {
    const getSpy = vi.spyOn(apiClient, 'legacyApiGet').mockResolvedValue({ ok: true });
    const postSpy = vi.spyOn(apiClient, 'legacyApiPost').mockResolvedValue({ ok: true });

    await fyersApi.stopFyersAutomation('job 1');
    await fyersApi.resumeFyersAutomation({ job_id: 'job 1' });
    await fyersApi.rerunFailedFyersAutomation({ job_id: 'job 1' });
    await fyersApi.rerunRemainingFyersAutomation({ job_id: 'job 1' });
    await fyersApi.fetchLatestActiveFyersAutomationJob();
    await fyersApi.fetchFyersSkippedSymbols('job 1');
    await fyersApi.fetchFyersFailedSymbols({ limit: 25 });
    await fyersApi.startFyersFailedSymbolsRerunJob({ symbols: ['ABC'] });

    expect(postSpy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/automation/stop/job%201',
      {},
      expect.objectContaining({ timeoutMs: null }),
    );
    expect(postSpy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/automation/resume',
      { job_id: 'job 1' },
      expect.objectContaining({ timeoutMs: null }),
    );
    expect(postSpy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/automation/rerun-failed',
      { job_id: 'job 1' },
      expect.objectContaining({ timeoutMs: null }),
    );
    expect(postSpy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/automation/rerun-remaining',
      { job_id: 'job 1' },
      expect.objectContaining({ timeoutMs: null }),
    );
    expect(getSpy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/automation/latest-active-job',
      undefined,
      expect.objectContaining({
        diagnostic: expect.objectContaining({ suppress: true }),
        timeoutMs: null,
      }),
    );
    expect(getSpy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/automation/skipped-symbols/job%201',
      undefined,
      expect.objectContaining({ timeoutMs: null }),
    );
    expect(getSpy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/failed-symbols',
      { limit: 25 },
      expect.objectContaining({ timeoutMs: null }),
    );
    expect(postSpy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/failed-symbols/rerun/start',
      { symbols: ['ABC'] },
      expect.objectContaining({ timeoutMs: null }),
    );
  });

  test('retains existing timeout budgets for holdings, NIFTY500 Sync, and failed-symbol deletion', async () => {
    const getSpy = vi.spyOn(apiClient, 'legacyApiGet').mockResolvedValue({ ok: true });
    const postSpy = vi.spyOn(apiClient, 'legacyApiPost').mockResolvedValue({ ok: true });
    const deleteSpy = vi.spyOn(apiClient, 'legacyApiDelete').mockResolvedValue({ ok: true });

    await fyersApi.fetchFyersHoldings();
    await fyersApi.fetchNifty500Sync();
    await fyersApi.compareNifty500Sync({ symbols: ['ABC'] });
    await fyersApi.deleteFyersFailedSymbols({ ids: [1] });

    expect(getSpy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/holdings',
      undefined,
      expect.objectContaining({ timeoutMs: 60000 }),
    );
    expect(getSpy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/nifty500-sync',
      undefined,
      expect.objectContaining({ timeoutMs: 60000 }),
    );
    expect(postSpy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/nifty500-sync/compare',
      { symbols: ['ABC'] },
      expect.objectContaining({ timeoutMs: 60000 }),
    );
    expect(deleteSpy).toHaveBeenCalledWith(
      '/api/marketdata/fyers/failed-symbols',
      { ids: [1] },
      expect.objectContaining({ timeoutMs: 60000 }),
    );
  });
});
