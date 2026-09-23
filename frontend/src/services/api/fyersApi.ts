import {
  legacyApiDelete,
  legacyApiGet,
  legacyApiPost,
  legacyApiPostForm,
  legacyApiPut,
  type QueryParams,
  type RequestOptions,
} from '../../api/client';

export type FyersApiPayload = Record<string, unknown>;

const FYERS_BASE = '/api/marketdata/fyers';
const FYERS_DEBUG_BASE = '/api/fyers';
const FYERS_RERUN_POLL_MS = 1500;
const FYERS_NO_CLIENT_TIMEOUT = null;
const FYERS_JOB_TERMINAL_STATUSES = new Set(['SUCCESS', 'FAILED', 'CANCELLED', 'COMPLETED', 'ERROR', 'SKIPPED', 'SUCCEEDED']);

function recordOf(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}

function readFyersPayload(payload: unknown): Record<string, unknown> {
  const source = recordOf(payload);
  return recordOf(source.data ?? payload);
}

export function fetchFyersAuthStatus(signal?: AbortSignal) {
  return legacyApiGet<FyersApiPayload>(`${FYERS_BASE}/auth-status`, undefined, {
    signal,
    timeoutMs: FYERS_NO_CLIENT_TIMEOUT,
  });
}

export function authorizeFyers(force = false) {
  return legacyApiPost<FyersApiPayload>(`${FYERS_BASE}/authorize`, { force }, { timeoutMs: FYERS_NO_CLIENT_TIMEOUT });
}

export function startFyersSingleJob(body: unknown) {
  return legacyApiPost<FyersApiPayload>(`${FYERS_BASE}/single/start`, body, { timeoutMs: FYERS_NO_CLIENT_TIMEOUT });
}

export function startFyersBatchJob(body: unknown) {
  return legacyApiPost<FyersApiPayload>(`${FYERS_BASE}/batch/start`, body, { timeoutMs: FYERS_NO_CLIENT_TIMEOUT });
}

export function startFyersAutomation(body: unknown) {
  return legacyApiPost<FyersApiPayload>(`${FYERS_BASE}/automation/start`, body, {
    timeoutMs: FYERS_NO_CLIENT_TIMEOUT,
  });
}

export function fetchFyersAutomationStatus(jobId: string, signal?: AbortSignal) {
  return legacyApiGet<FyersApiPayload>(
    `${FYERS_BASE}/automation/status/${encodeURIComponent(jobId)}`,
    undefined,
    {
      diagnostic: {
        action: 'poll-fyers-automation-job',
        component: 'FyersAutomationPage',
        suppress: true,
      },
      signal,
      timeoutMs: FYERS_NO_CLIENT_TIMEOUT,
    },
  );
}

export function fetchFyersJob(jobId: string, signal?: AbortSignal) {
  return legacyApiGet<FyersApiPayload>(`${FYERS_BASE}/jobs/${encodeURIComponent(jobId)}`, { tail: 260 }, {
    diagnostic: {
      action: 'poll-fyers-job',
      component: 'FyersAutomationPage',
      suppress: true,
    },
    signal,
    timeoutMs: FYERS_NO_CLIENT_TIMEOUT,
  });
}

export function stopFyersAutomation(jobId: string) {
  return legacyApiPost<FyersApiPayload>(
    `${FYERS_BASE}/automation/stop/${encodeURIComponent(jobId)}`,
    {},
    { timeoutMs: FYERS_NO_CLIENT_TIMEOUT },
  );
}

export function resumeFyersAutomation(body: unknown) {
  return legacyApiPost<FyersApiPayload>(`${FYERS_BASE}/automation/resume`, body, {
    timeoutMs: FYERS_NO_CLIENT_TIMEOUT,
  });
}

export function rerunFailedFyersAutomation(body: unknown) {
  return legacyApiPost<FyersApiPayload>(`${FYERS_BASE}/automation/rerun-failed`, body, {
    timeoutMs: FYERS_NO_CLIENT_TIMEOUT,
  });
}

export function rerunRemainingFyersAutomation(body: unknown) {
  return legacyApiPost<FyersApiPayload>(`${FYERS_BASE}/automation/rerun-remaining`, body, {
    timeoutMs: FYERS_NO_CLIENT_TIMEOUT,
  });
}

export function fetchLatestActiveFyersAutomationJob(signal?: AbortSignal) {
  return legacyApiGet<FyersApiPayload>(`${FYERS_BASE}/automation/latest-active-job`, undefined, {
    diagnostic: {
      action: 'discover-fyers-active-job',
      component: 'FyersAutomationPage',
      suppress: true,
    },
    signal,
    timeoutMs: FYERS_NO_CLIENT_TIMEOUT,
  });
}

export function fetchFyersSkippedSymbols(jobId: string, signal?: AbortSignal) {
  return legacyApiGet<FyersApiPayload>(
    `${FYERS_BASE}/automation/skipped-symbols/${encodeURIComponent(jobId)}`,
    undefined,
    { signal, timeoutMs: FYERS_NO_CLIENT_TIMEOUT },
  );
}

export function fetchFyersFailedSymbols(params?: QueryParams, signal?: AbortSignal) {
  return legacyApiGet<FyersApiPayload>(`${FYERS_BASE}/failed-symbols`, params, {
    signal,
    timeoutMs: FYERS_NO_CLIENT_TIMEOUT,
  });
}

export async function rerunFyersFailedSymbols(body: unknown, signal?: AbortSignal) {
  const started = await startFyersFailedSymbolsRerunJob(body);
  const startedPayload = recordOf(started);
  const jobIdRaw = startedPayload.jobId ?? startedPayload.job_id;
  const jobId = typeof jobIdRaw === 'string' ? jobIdRaw.trim() : '';
  if (!jobId) return started;

  while (!signal?.aborted) {
    const snapshotPayload = await fetchFyersJob(jobId, signal);
    const snapshot = readFyersPayload(snapshotPayload);
    const status = String(snapshot.status ?? '').trim().toUpperCase();
    const done = snapshot.done === true || FYERS_JOB_TERMINAL_STATUSES.has(status);
    if (done) {
      const result = recordOf(snapshot.result);
      return Object.keys(result).length ? result : snapshot;
    }
    await new Promise((resolve) => window.setTimeout(resolve, FYERS_RERUN_POLL_MS));
  }
  throw new Error('Failed-symbol rerun request was cancelled.');
}

export function startFyersFailedSymbolsRerunJob(body: unknown) {
  return legacyApiPost<FyersApiPayload>(`${FYERS_BASE}/failed-symbols/rerun/start`, body, {
    timeoutMs: FYERS_NO_CLIENT_TIMEOUT,
  });
}

export function deleteFyersFailedSymbols(body: unknown) {
  return legacyApiDelete<FyersApiPayload>(`${FYERS_BASE}/failed-symbols`, body, { timeoutMs: 60000 });
}

export function fetchFyersHoldings(signal?: AbortSignal) {
  return legacyApiGet<FyersApiPayload>(`${FYERS_BASE}/holdings`, undefined, { signal, timeoutMs: 60000 });
}

export function fetchFyersHoldingsSummary(signal?: AbortSignal) {
  return legacyApiGet<FyersApiPayload>(`${FYERS_BASE}/holdings/summary`, undefined, { signal, timeoutMs: 60000 });
}

export function fetchFyersHoldingsImports(params?: QueryParams, signal?: AbortSignal) {
  return legacyApiGet<FyersApiPayload>(`${FYERS_BASE}/holdings/imports`, params, { signal, timeoutMs: 60000 });
}

export function fetchFyersHoldingsReconciliation(signal?: AbortSignal) {
  return legacyApiGet<FyersApiPayload>(`${FYERS_DEBUG_BASE}/holdings/reconcile`, undefined, { signal, timeoutMs: 60000 });
}

export function importFyersHoldings(formData: FormData) {
  return legacyApiPostForm<FyersApiPayload>(`${FYERS_BASE}/holdings/import`, formData, { timeoutMs: 120000 });
}

export function createFyersHolding(body: unknown) {
  return legacyApiPost<FyersApiPayload>(`${FYERS_BASE}/holdings`, body, { timeoutMs: 60000 });
}

export function updateFyersHolding(holdingId: string | number, body: unknown) {
  return legacyApiPut<FyersApiPayload>(`${FYERS_BASE}/holdings/${encodeURIComponent(String(holdingId))}`, body, {
    timeoutMs: 60000,
  });
}

export function deleteFyersHolding(holdingId: string | number) {
  return legacyApiDelete<FyersApiPayload>(`${FYERS_BASE}/holdings/${encodeURIComponent(String(holdingId))}`, undefined, {
    timeoutMs: 60000,
  });
}

export function fetchNifty500Sync(signal?: AbortSignal) {
  return legacyApiGet<FyersApiPayload>(`${FYERS_BASE}/nifty500-sync`, undefined, { signal, timeoutMs: 60000 });
}

export function compareNifty500Sync(body: unknown) {
  return legacyApiPost<FyersApiPayload>(`${FYERS_BASE}/nifty500-sync/compare`, body, { timeoutMs: 60000 });
}

export function compareNifty500SyncForm(formData: FormData) {
  return legacyApiPostForm<FyersApiPayload>(`${FYERS_BASE}/nifty500-sync/compare`, formData, { timeoutMs: 120000 });
}

export function mergeNifty500Sync(body: unknown) {
  return legacyApiPost<FyersApiPayload>(`${FYERS_BASE}/nifty500-sync/merge`, body, { timeoutMs: 120000 });
}

export function mergeNifty500SyncForm(formData: FormData) {
  return legacyApiPostForm<FyersApiPayload>(`${FYERS_BASE}/nifty500-sync/merge`, formData, { timeoutMs: 120000 });
}

export function addNifty500Rows(body: unknown) {
  return legacyApiPost<FyersApiPayload>(`${FYERS_BASE}/nifty500-sync/rows`, body, { timeoutMs: 60000 });
}

export function updateNifty500Row(body: unknown) {
  return legacyApiPut<FyersApiPayload>(`${FYERS_BASE}/nifty500-sync/rows`, body, { timeoutMs: 60000 });
}

export function deleteNifty500Row(body: unknown) {
  return legacyApiDelete<FyersApiPayload>(`${FYERS_BASE}/nifty500-sync/rows`, body, { timeoutMs: 60000 });
}

export function fetchFyersLatestJob(signal?: AbortSignal) {
  return legacyApiGet<FyersApiPayload>(`${FYERS_BASE}/jobs/latest`, undefined, { signal, timeoutMs: 60000 });
}
