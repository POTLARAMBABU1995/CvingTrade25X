import { useEffect, useMemo, useRef, useState } from 'react';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { CopyTextButton } from '../../components/ui/CopyTextButton';
import { ThemeToggle } from '../../components/ThemeToggle';
import { Toast } from '../../components/ui/Toast';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { useAuth } from '../../context/AuthContext';
import {
  asRecord,
  formatLegacyDateOnly,
  pickField,
  safeLegacyText,
  type UnknownRecord,
} from '../../adapters/databasePageAdapter';
import { extractFyersStats, getFyersStatusMessage, readPayloadData } from '../../adapters/fyersPageAdapter';
import {
  authorizeFyers,
  fetchFyersAutomationStatus,
  fetchFyersAuthStatus,
  fetchFyersSkippedSymbols,
  fetchFyersJob,
  rerunFailedFyersAutomation,
  rerunRemainingFyersAutomation,
  startFyersAutomation,
  startFyersSingleJob,
  stopFyersAutomation,
} from '../../services/api/fyersApi';
import { KpiGrid, PageHero } from '../ops/opsPageHelpers';
import { FyersDatePickerField } from './FyersDatePickerField';
import { FyersMigrationLayout } from './FyersMigrationLayout';
import {
  buildFyersAuthStatusMessage,
  describeWeekendRange,
  FYERS_AUTH_EXPIRED_TOAST,
  getFyersAuthExpiredToast,
  withFyersToast,
  type FyersPageToast,
} from './fyersPageUtils';

type LoadStatus = 'error' | 'idle' | 'loading' | 'success' | 'warn';

const ACTIVE_JOB_STORAGE_KEY = 'ct_fyers_active_job';
const CLIENT_SESSION_STORAGE_KEY = 'ct_fyers_client_session';
const AUTH_STATUS_MAX_ATTEMPTS = 2;
const AUTH_STATUS_RETRY_DELAY_MS = 1500;
const BACKEND_UNREACHABLE_MESSAGE = 'Backend server is not reachable. Please check Flask/FastAPI service on port 5055.';
const POLL_MS = 1500;
const POLL_WARNING_THRESHOLD = 3;
const POLL_RETRY_MAX_DELAY_MS = 10000;
const TERMINAL_JOB_STATUSES = new Set(['SUCCESS', 'FAILED', 'CANCELLED', 'COMPLETED', 'ERROR', 'SKIPPED', 'STOPPED', 'SUCCEEDED']);
const STOPPED_JOB_STATUSES = new Set(['CANCELLED', 'STOPPED']);

type JobStatusSource = 'automation' | 'legacy';

export function shouldInitializeFyersAutomation(isSessionVerificationLoading: boolean): boolean {
  return !isSessionVerificationLoading;
}

export function canStartFyersExtraction(payload: unknown): boolean {
  const source = asRecord(payload);
  return source.canExtract === true && source.authenticated !== false;
}

export function isFyersAuthRequiredStartError(error: unknown): boolean {
  const source = asRecord(error);
  const status = Number(source.status ?? 0);
  const backendCode = safeLegacyText(pickField(source, ['backendCode', 'code', 'errorCode']), '').toUpperCase();
  const message = safeLegacyText(source.message, '').toLowerCase();
  return status === 428
    || backendCode === 'FYERS_AUTH_REQUIRED'
    || backendCode === 'FYERS_AUTH_VALIDATION_FAILED'
    || backendCode === 'FYERS_INVALID_REFRESH_TOKEN'
    || backendCode === 'FYERS_STALE_CALLBACK'
    || message.includes('authenticate fyers before extracting symbols')
    || message.includes('fresh login required')
    || message.includes('stale fyers callback');
}

export function shouldRetryFyersAuthStatusLoad(error: unknown): boolean {
  if (error instanceof Error && error.name === 'AbortError') return false;
  const source = asRecord(error);
  const status = Number(source.status ?? 0);
  if (status >= 500) return true;
  if (status > 0) return false;
  const message = safeLegacyText(source.message, error instanceof Error ? error.message : '').toLowerCase();
  return message.includes('failed to fetch')
    || message.includes('network')
    || message.includes('load failed')
    || message.includes('request timeout')
    || message.includes('temporarily unavailable');
}

export function isBackendUnreachableFyersError(error: unknown): boolean {
  const source = asRecord(error);
  const hasStatus = source.status !== undefined || source.httpStatus !== undefined;
  const status = Number(source.status ?? 0);
  if (hasStatus && status === 0) return true;
  const message = safeLegacyText(source.message, error instanceof Error ? error.message : '').toLowerCase();
  return message.includes('failed to fetch')
    || message.includes('networkerror')
    || message.includes('backend server is not reachable')
    || message.includes('load failed')
    || message.includes('network request failed');
}

export function formatFyersErrorMessage(error: unknown, fallback = 'Request failed.') {
  if (isBackendUnreachableFyersError(error)) return BACKEND_UNREACHABLE_MESSAGE;
  return error instanceof Error ? error.message : safeLegacyText(asRecord(error).message, fallback) || fallback;
}

function readOrCreateFyersClientSessionId() {
  try {
    const existing = window.localStorage.getItem(CLIENT_SESSION_STORAGE_KEY) || '';
    if (existing.trim()) return existing.trim();
    const next = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `fyers-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    window.localStorage.setItem(CLIENT_SESSION_STORAGE_KEY, next);
    return next;
  } catch {
    return `fyers-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
}

export interface FyersSkippedSymbolRow {
  symbol: string;
  status: string;
  reason: string;
  tradingDate: string;
  retryCount: number;
  lastError: string;
}

function csvCell(value: unknown) {
  const text = String(value ?? '');
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function buildSkippedSymbolsCsv(rows: FyersSkippedSymbolRow[]) {
  const header = ['Symbol', 'Status', 'Reason', 'Trading Date', 'Retry Count', 'Last Error'];
  return [
    header.map(csvCell).join(','),
    ...rows.map((row) => [
      row.symbol,
      row.status,
      row.reason,
      row.tradingDate,
      row.retryCount,
      row.lastError,
    ].map(csvCell).join(',')),
  ].join('\r\n');
}

export function buildSkippedSymbolsFilename(extension: 'csv' | 'txt', tradingDate?: string) {
  const safeDate = safeLegacyText(tradingDate, '--').replace(/[^0-9-]/g, '') || '--';
  return `FYERS_SKIPPED_SYMBOLS_${safeDate}.${extension}`;
}

export function fyersAutomationLatestSelectableDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    hour: '2-digit',
    hourCycle: 'h23',
    month: '2-digit',
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
  }).formatToParts(now).reduce<Record<string, string>>((result, part) => {
    result[part.type] = part.value;
    return result;
  }, {});
  const date = new Date(Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day)));
  if (Number(parts.hour) < 17) date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

function readActiveJob(): { jobId: string; source: JobStatusSource } {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(ACTIVE_JOB_STORAGE_KEY) || '{}') as {
      jobId?: unknown;
      source?: unknown;
    };
    return {
      jobId: safeLegacyText(parsed.jobId, ''),
      source: parsed.source === 'automation' ? 'automation' : 'legacy',
    };
  } catch {
    return { jobId: '', source: 'automation' };
  }
}

function readActiveJobId(): string {
  return readActiveJob().jobId;
}

function writeActiveJobId(jobId: string, source: JobStatusSource) {
  try {
    window.localStorage.setItem(ACTIVE_JOB_STORAGE_KEY, JSON.stringify({ jobId, source }));
  } catch {
    // Storage persistence is best-effort; the running backend job remains authoritative.
  }
}

function clearActiveJobId() {
  try {
    window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
  } catch {
    // Ignore storage failures.
  }
}

function jobLogLines(job: UnknownRecord): string[] {
  const logs = asRecord(job.logs);
  const tail = logs.tail;
  if (Array.isArray(tail)) return tail.map((line) => String(line));
  return [];
}

function jobIdOf(job: UnknownRecord) {
  return safeLegacyText(pickField(job, ['jobId', 'job_id', 'runId', 'run_id']), '');
}

function tradingDateOf(job: UnknownRecord, stats: UnknownRecord = {}) {
  const request = asRecord(job.request);
  return safeLegacyText(pickField(
    { ...request, ...stats, ...job },
    ['tradingDate', 'trading_date', 'ltcDate', 'ltc_date', 'LTC_DATE', 'endDate', 'end_date'],
  ), '');
}

export function formatFyersLtcDate(value: unknown): string {
  return formatLegacyDateOnly(value, '--');
}

function countOf(source: UnknownRecord, names: string[]) {
  const value = Number(pickField(source, names, 0));
  return Number.isFinite(value) ? value : 0;
}

function statsToCards(stats: UnknownRecord, job: UnknownRecord) {
  const source = { ...job, ...stats };
  return [
    { label: 'Total', value: countOf(source, ['total', 'totalSymbols', 'total_symbols']).toLocaleString('en-IN') },
    { label: 'LTC_DATE', value: formatFyersLtcDate(tradingDateOf(job, stats)) },
    { label: 'Existing Rows', value: countOf(source, ['existing_rows', 'existingRows', 'existingRowsCount']).toLocaleString('en-IN') },
    { label: 'Missing Ranges', value: countOf(source, ['missing_ranges_count', 'missingRangesCount', 'missingRanges']).toLocaleString('en-IN') },
    { label: 'Fetched Rows', value: countOf(source, ['fetched_rows', 'fetchedRows', 'fetchedCount']).toLocaleString('en-IN') },
    { label: 'Inserted', value: countOf(source, ['inserted', 'insertedCount', 'inserted_count', 'inserted_rows']).toLocaleString('en-IN') },
    { label: 'Updated Rows', value: countOf(source, ['updated_rows', 'updatedRows', 'updatedCount']).toLocaleString('en-IN') },
    { label: 'Remaining', value: countOf(source, ['remaining', 'remainingCount', 'remaining_count', 'pending_count']).toLocaleString('en-IN') },
    { label: 'Failed', value: countOf(source, ['failed', 'failedCount', 'failed_count']).toLocaleString('en-IN') },
    { label: 'Skipped', value: countOf(source, ['skipped', 'skippedCount', 'skipped_count', 'duplicate_rows_skipped']).toLocaleString('en-IN') },
    { label: 'Skipped Existing', value: countOf(source, ['skipped_existing_rows', 'skippedExistingRows', 'duplicate_rows_skipped']).toLocaleString('en-IN') },
    { label: 'Range Failed', value: countOf(source, ['failed_ranges_count', 'failedRangesCount', 'remaining_ranges', 'remainingRanges']).toLocaleString('en-IN') },
    { label: 'Inserted Skipped', value: countOf(source, ['insertedSkipped', 'inserted_skipped', 'insertedSkippedCount', 'inserted_skipped_count']).toLocaleString('en-IN') },
    { label: 'Invalid', value: countOf(source, ['invalid', 'invalidCount', 'invalid_count']).toLocaleString('en-IN') },
    { label: 'Errors', value: countOf(source, ['errors', 'errorCount', 'error_count']).toLocaleString('en-IN') },
  ];
}

function isRunningJob(job: UnknownRecord) {
  const normalizedStatus = safeLegacyText(job.status, '').toUpperCase();
  if (!jobIdOf(job)) return false;
  if (!normalizedStatus) return false;
  return !TERMINAL_JOB_STATUSES.has(normalizedStatus);
}

function formatJobTimestamp(value: unknown, fallback = '--') {
  const text = safeLegacyText(value, '');
  if (!text) return fallback;
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return text;
  return parsed.toLocaleString('en-IN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  });
}

type FyersPollErrorDecision = {
  clearJob: boolean;
  consecutiveFailures: number;
  kind: 'not-found' | 'retry';
  message: string;
  preserveSnapshot: boolean;
  retryDelayMs: number;
  shouldToast: boolean;
  status: Extract<LoadStatus, 'loading' | 'warn'>;
};

export function resolveFyersPollError(error: unknown, consecutiveFailures: number): FyersPollErrorDecision {
  const source = error && typeof error === 'object'
    ? error as { backendCode?: unknown; code?: unknown; message?: unknown; status?: unknown }
    : {};
  const statusCode = Number(source.status ?? 0);
  const backendCode = safeLegacyText(source.backendCode ?? source.code, '').toUpperCase();
  const message = safeLegacyText(source.message, '');
  const explicitNotFound = statusCode === 404
    && (backendCode === 'FYERS_JOB_NOT_FOUND' || /FYERS job not found/i.test(message));
  if (explicitNotFound) {
    return {
      clearJob: true,
      consecutiveFailures: 0,
      kind: 'not-found',
      message: 'Previous FYERS job is no longer available. Start a new automation run.',
      preserveSnapshot: false,
      retryDelayMs: 0,
      shouldToast: false,
      status: 'warn',
    };
  }

  const nextFailureCount = Math.max(0, consecutiveFailures) + 1;
  const backendUnreachable = isBackendUnreachableFyersError(error);
  const retryDelayMs = backendUnreachable
    ? Math.min(POLL_RETRY_MAX_DELAY_MS, POLL_MS * (2 ** Math.min(nextFailureCount - 1, 3)))
    : POLL_MS;
  const warningThresholdReached = nextFailureCount >= POLL_WARNING_THRESHOLD;
  return {
    clearJob: false,
    consecutiveFailures: nextFailureCount,
    kind: 'retry',
    message: backendUnreachable
      ? BACKEND_UNREACHABLE_MESSAGE
      : warningThresholdReached
        ? 'Unable to refresh status. Last known job may still be running.'
        : 'Connection delayed. Job may still be running. Retrying...',
    preserveSnapshot: true,
    retryDelayMs,
    shouldToast: backendUnreachable ? nextFailureCount === 1 : nextFailureCount === POLL_WARNING_THRESHOLD,
    status: backendUnreachable || warningThresholdReached ? 'warn' : 'loading',
  };
}

export function isTerminalFyersJobFailure(status: unknown): boolean {
  const normalizedStatus = safeLegacyText(status, '').toUpperCase();
  return normalizedStatus === 'FAILED' || normalizedStatus === 'ERROR';
}

function buildJobTelemetry(job: UnknownRecord, running: boolean) {
  const timing = asRecord(job.timing);
  return {
    authorizationUrl: safeLegacyText(
      pickField(job, ['loginUrl', 'login_url', 'auth_url']),
      '',
    ),
    currentSymbol: safeLegacyText(
      pickField(job, ['currentSymbol', 'current_symbol']),
      running ? 'Waiting for next symbol...' : '--',
    ),
    etaTimestamp: formatJobTimestamp(
      pickField(timing, ['etaTimestamp', 'eta_timestamp']),
      running ? 'Calculating after first completed symbol' : '--',
    ),
    lastHeartbeat: formatJobTimestamp(
      pickField(timing, ['lastHeartbeatAt', 'last_heartbeat_at', 'updatedAt', 'updated_at']),
      '--',
    ),
  };
}

function normalizeSkippedSymbolRows(payload: unknown): FyersSkippedSymbolRow[] {
  const source = asRecord(payload);
  const data = source.data ?? payload;
  const candidates = Array.isArray(data)
    ? data
    : pickField(asRecord(data), ['rows', 'items', 'symbols', 'skippedSymbols', 'skipped_symbols'], []);
  if (!Array.isArray(candidates)) return [];
  return candidates.map((candidate) => {
    const row = asRecord(candidate);
    return {
      symbol: safeLegacyText(pickField(row, ['symbol', 'stockSymbol', 'stock_symbol']), '--'),
      status: safeLegacyText(row.status, '--'),
      reason: safeLegacyText(pickField(row, ['reason', 'statusReason', 'status_reason']), '--'),
      tradingDate: safeLegacyText(pickField(row, ['tradingDate', 'trading_date', 'ltcDate', 'ltc_date']), '--'),
      retryCount: countOf(row, ['retryCount', 'retry_count', 'retries']),
      lastError: safeLegacyText(pickField(row, ['lastError', 'last_error', 'errorMessage', 'error_message']), '--'),
    };
  });
}

export function FyersAutomationPage() {
  const { isLoading: isSessionVerificationLoading } = useAuth();
  const latestSelectableDate = fyersAutomationLatestSelectableDate();
  const [authMessage, setAuthMessage] = useState('Checking authorization...');
  const [batchEnd, setBatchEnd] = useState(fyersAutomationLatestSelectableDate);
  const [batchStart, setBatchStart] = useState(fyersAutomationLatestSelectableDate);
  const [canExtract, setCanExtract] = useState(false);
  const [error, setError] = useState('');
  const [isAuthorizing, setIsAuthorizing] = useState(false);
  const [isRefreshingAuth, setIsRefreshingAuth] = useState(false);
  const [job, setJob] = useState<UnknownRecord>({});
  const [isStarting, setIsStarting] = useState(false);
  const [logText, setLogText] = useState('No FyersAPI run yet.');
  const [singleEnd, setSingleEnd] = useState(fyersAutomationLatestSelectableDate);
  const [singleStart, setSingleStart] = useState('1998-01-01');
  const [singleSymbol, setSingleSymbol] = useState('');
  const [skippedRows, setSkippedRows] = useState<FyersSkippedSymbolRow[]>([]);
  const [stats, setStats] = useState<UnknownRecord>({});
  const [status, setStatus] = useState<LoadStatus>('idle');
  const [statusMessage, setStatusMessage] = useState('Idle');
  const [stopLoading, setStopLoading] = useState(false);
  const [toast, setToast] = useState<FyersPageToast | null>(null);
  const pollControllerRef = useRef<AbortController | null>(null);
  const consecutivePollFailuresRef = useRef(0);
  const pollFailureToastShownRef = useRef(false);
  const runningToastJobRef = useRef('');
  const lastBatchProgressRef = useRef(0);
  const skippedSnapshotKeyRef = useRef('');

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), 5000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  function pushToast(nextToast: FyersPageToast) {
    setToast(nextToast);
  }

  function stopPolling(reason: string) {
    if (pollControllerRef.current) {
      console.info('[FYERS][AUTOMATION_UI] poll_stop', { reason });
      pollControllerRef.current.abort();
      pollControllerRef.current = null;
    }
  }

  function clearStaleJob(reason: string, message: string) {
    clearActiveJobId();
    setJob({});
    setStopLoading(false);
    setStatus('warn');
    setStatusMessage(message);
    console.warn('[FYERS][AUTOMATION_UI] stale_job_cleared', { reason });
  }

  function beginStart(message: string) {
    setError('');
    setStopLoading(false);
    setIsStarting(true);
    setStatus('loading');
    setStatusMessage(message);
  }

  function finishStart() {
    setIsStarting(false);
  }

  function resetPollFailureWarning() {
    consecutivePollFailuresRef.current = 0;
    pollFailureToastShownRef.current = false;
  }

  async function waitForAuthRetry(signal?: AbortSignal) {
    if (signal?.aborted) return;
    await new Promise<void>((resolve) => {
      const timer = window.setTimeout(() => {
        signal?.removeEventListener('abort', handleAbort);
        resolve();
      }, AUTH_STATUS_RETRY_DELAY_MS);
      const handleAbort = () => {
        window.clearTimeout(timer);
        resolve();
      };
      signal?.addEventListener('abort', handleAbort, { once: true });
    });
  }

  async function startOrAttachJob(
    started: UnknownRecord,
    runningMessage: string,
    duplicateRunMessage: string,
    source: JobStatusSource,
  ) {
    const authToast = getFyersAuthExpiredToast(started);
    if (authToast) {
      pushToast(withFyersToast('Authorization Required', authToast, 'danger'));
    }
    const runningStatus = safeLegacyText(started.status, '').toUpperCase() === 'RUNNING' && started.ok === false;
    const nextJobId = safeLegacyText(pickField(started, ['jobId', 'job_id', 'runId', 'run_id']), '');
    if (!nextJobId) {
      throw new Error(getFyersStatusMessage(started, 'Failed to start FYERS automation job.'));
    }
    if (runningStatus) {
      pushToast(withFyersToast('Already Running', duplicateRunMessage, 'warn'));
    }
    resetPollFailureWarning();
    const controller = new AbortController();
    pollControllerRef.current = controller;
    await pollJob(nextJobId, runningStatus ? duplicateRunMessage : runningMessage, source, controller.signal);
  }

  async function refreshAuth(signal?: AbortSignal, attempt = 1) {
    if (!signal?.aborted) setIsRefreshingAuth(true);
    try {
      const payload = await fetchFyersAuthStatus(signal);
      setCanExtract(canStartFyersExtraction(payload));
      setAuthMessage(buildFyersAuthStatusMessage(payload, 'Authorization status loaded.'));
    } catch (authError) {
      if (signal?.aborted) return;
      if (attempt < AUTH_STATUS_MAX_ATTEMPTS && shouldRetryFyersAuthStatusLoad(authError)) {
        setCanExtract(false);
        setAuthMessage('Unable to reach authorization status. Retrying...');
        await waitForAuthRetry(signal);
        if (signal?.aborted) return;
        return refreshAuth(signal, attempt + 1);
      }
      setCanExtract(false);
      setAuthMessage(formatFyersErrorMessage(authError, 'Unable to load authorization status.'));
    } finally {
      if (!signal?.aborted) setIsRefreshingAuth(false);
    }
  }

  function blockUnauthenticatedExtraction() {
    if (canExtract) return false;
    setStatus('warn');
    setStatusMessage('Authentication required');
    setAuthMessage('Authentication Expired. Please do the authentication.');
    pushToast(withFyersToast(
      'Authorization Required',
      'Authentication Expired. Please authenticate FYERS before extracting symbols.',
      'danger',
    ));
    return true;
  }

  function handleAuthRequiredStartFailure(message: string) {
    setCanExtract(false);
    setError('');
    setStatus('warn');
    setStatusMessage('Authentication required');
    setAuthMessage(message);
    pushToast(withFyersToast('Authorization Required', message, 'danger'));
  }

  function validateDateRange(startDate: string, endDate: string) {
    if (!startDate || !endDate) {
      setStatus('warn');
      setStatusMessage('Select both dates.');
      setError('Select both From Date and To Date.');
      return false;
    }
    if (endDate < startDate) {
      setStatus('warn');
      setStatusMessage('Invalid date range');
      setError('To Date cannot be earlier than From Date.');
      return false;
    }
    return true;
  }

  function handleWeekendWarning(startDate: string, endDate: string) {
    const weekend = describeWeekendRange(startDate, endDate);
    if (weekend.block) {
      pushToast(withFyersToast('Weekend Selected', 'Weekend selected. Saturday and Sunday are market holidays.', 'warn'));
      setStatus('warn');
      setStatusMessage('Weekend-only range blocked');
      return false;
    }
    if (weekend.warn) {
      pushToast(withFyersToast('Weekend Selected', 'Weekend selected. Saturday and Sunday are market holidays.', 'warn'));
    }
    return true;
  }

  function copyToClipboard(text: string, label: string) {
    if (!navigator.clipboard) {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand('copy');
        pushToast(withFyersToast('Copied', `${label} copied to clipboard`, 'success'));
      } catch (err) {
        pushToast(withFyersToast('Error', `Failed to copy ${label}`, 'danger'));
      }
      document.body.removeChild(textarea);
      return;
    }
    navigator.clipboard.writeText(text).then(
      () => {
        pushToast(withFyersToast('Copied', `${label} copied to clipboard`, 'success'));
      },
      () => {
        pushToast(withFyersToast('Error', `Failed to copy ${label}`, 'danger'));
      }
    );
  }

  function downloadFile(text: string, filename: string, label: string, type: string) {
    const element = document.createElement('a');
    const file = new Blob([text], { type });
    element.href = URL.createObjectURL(file);
    element.download = filename;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
    URL.revokeObjectURL(element.href);
    pushToast(withFyersToast('Downloaded', `${label} file downloaded`, 'success'));
  }

  async function refreshSkippedSymbols(jobId: string, signal?: AbortSignal) {
    if (!jobId) {
      setSkippedRows([]);
      return;
    }
    try {
      const payload = await fetchFyersSkippedSymbols(jobId, signal);
      setSkippedRows(normalizeSkippedSymbolRows(payload));
    } catch (skippedError) {
      if (signal?.aborted) return;
      console.warn('[FYERS][AUTOMATION_UI] skipped_symbols_refresh_failed', { jobId, skippedError });
    }
  }

  async function pollJob(
    jobId: string,
    runningMessage: string,
    source: JobStatusSource,
    signal?: AbortSignal,
  ) {
    writeActiveJobId(jobId, source);
    setStatus('loading');
    setStatusMessage(runningMessage);
    resetPollFailureWarning();
    console.info('[FYERS][AUTOMATION_UI] poll_start', { jobId, runningMessage, source });
    while (!signal?.aborted) {
      let payload: UnknownRecord;
      try {
        payload = await (source === 'automation'
          ? fetchFyersAutomationStatus(jobId, signal)
          : fetchFyersJob(jobId, signal));
      } catch (jobError) {
        if (signal?.aborted) return;
        const decision = resolveFyersPollError(jobError, consecutivePollFailuresRef.current);
        if (decision.kind === 'not-found') {
          clearStaleJob('fyers_job_not_found', decision.message);
          return;
        }
        consecutivePollFailuresRef.current = decision.consecutiveFailures;
        setError('');
        setStatus(decision.status);
        setStatusMessage(decision.message);
        if (decision.shouldToast && !pollFailureToastShownRef.current) {
          pollFailureToastShownRef.current = true;
          pushToast(withFyersToast(
            'Status Refresh Delayed',
            decision.message,
            'warn',
          ));
        }
        console.warn('[FYERS][AUTOMATION_UI] poll_refresh_failed', {
          consecutiveFailures: decision.consecutiveFailures,
          jobError,
          jobId,
        });
        await new Promise((resolve) => window.setTimeout(resolve, decision.retryDelayMs));
        continue;
      }
      const receivedJob = readPayloadData(payload);
      const currentJob: UnknownRecord = { ...receivedJob, jobId: jobIdOf(receivedJob) || jobId };
      const currentStats = { ...currentJob, ...asRecord(currentJob.stats) };
      resetPollFailureWarning();
      setError('');
      setJob(currentJob);
      setStats(currentStats);
      const skippedSnapshotKey = [
        countOf(currentStats, ['failed', 'failed_count']),
        countOf(currentStats, ['skipped', 'skipped_count']),
        countOf(currentStats, ['insertedSkipped', 'inserted_skipped', 'inserted_skipped_count']),
        countOf(currentStats, ['invalid', 'invalid_count']),
        countOf(currentStats, ['errors', 'error_count']),
      ].join(':');
      if (skippedSnapshotKey !== skippedSnapshotKeyRef.current) {
        skippedSnapshotKeyRef.current = skippedSnapshotKey;
        await refreshSkippedSymbols(jobId, signal);
      }
      const logs = jobLogLines(currentJob);
      setLogText(logs.length ? logs.join('\n') : safeLegacyText(currentJob.message, runningMessage));
      const normalizedStatus = safeLegacyText(currentJob.status, '').toUpperCase();
      const done = currentJob.done === true || TERMINAL_JOB_STATUSES.has(normalizedStatus);
      if (done) {
        clearActiveJobId();
        setStopLoading(false);
        await refreshSkippedSymbols(jobId, signal);
        const result = asRecord(currentJob.result);
        const resultStats = extractFyersStats(result);
        if (Object.keys(resultStats).length) setStats({ ...currentStats, ...resultStats });
        const failed = countOf({ ...currentStats, ...resultStats }, ['failed', 'failed_count']);
        const errors = countOf({ ...currentStats, ...resultStats }, ['errors', 'error_count']);
        const cancelled = result.cancelled === true || STOPPED_JOB_STATUSES.has(normalizedStatus);
        const authToast = getFyersAuthExpiredToast(result);
        const resultFailed = isTerminalFyersJobFailure(normalizedStatus);
        const finalMessage = authToast || getFyersStatusMessage(result, safeLegacyText(currentJob.message, 'FyersAPI run completed.'));
        setStatus(cancelled ? 'warn' : resultFailed ? 'error' : failed > 0 || errors > 0 ? 'warn' : 'success');
        setStatusMessage(cancelled ? 'Stopped by user' : finalMessage);
        console.info('[FYERS][AUTOMATION_UI] terminal_status_received', { jobId, status: normalizedStatus || safeLegacyText(currentJob.status, '') });
        if (authToast) {
          pushToast(withFyersToast('Authorization Required', authToast, 'danger'));
        } else if (cancelled) {
          pushToast(withFyersToast('Extraction Stopped', 'Stopped by user', 'warn'));
        } else if (resultFailed) {
          pushToast(withFyersToast('Extraction Failed', 'Fyers automation job failed.', 'danger'));
        } else if (failed > 0 || errors > 0) {
          pushToast(withFyersToast('Extraction Completed with Failures', `Fyers job completed. ${failed} symbols failed.`, 'warn'));
        } else {
          pushToast(withFyersToast('Extraction Completed Successfully', 'Fyers automation job completed successfully.', 'success'));
        }
        await refreshAuth(signal);
        return;
      }
      if (runningToastJobRef.current !== jobId) {
        runningToastJobRef.current = jobId;
        pushToast(withFyersToast('Extraction Running', 'FYERS extraction is running in the background.', 'info'));
      }
      setStatus('loading');
      const completedBatches = countOf(currentStats, ['completedBatches', 'completed_batches', 'batchesCompleted', 'batches_completed']);
      if (completedBatches > lastBatchProgressRef.current) {
        lastBatchProgressRef.current = completedBatches;
        pushToast(withFyersToast(
          'Batch Completed',
          `FYERS extraction completed batch ${completedBatches.toLocaleString('en-IN')}.`,
          'success',
        ));
      }
      setStatusMessage(stopLoading ? 'Stopping...' : safeLegacyText(currentJob.message, runningMessage));
      await new Promise((resolve) => window.setTimeout(resolve, POLL_MS));
    }
  }

  useEffect(() => {
    if (!shouldInitializeFyersAutomation(isSessionVerificationLoading)) return undefined;

    const pageController = new AbortController();
    void refreshAuth(pageController.signal);

    const initializeJob = async () => {
      const storedJob = readActiveJob();
      const activeJobId = storedJob.jobId;
      const activeJobSource = storedJob.source;

      if (activeJobId && !pageController.signal.aborted) {
        resetPollFailureWarning();
        stopPolling('resume_before_new_poller');
        const controller = new AbortController();
        pollControllerRef.current = controller;
        pollJob(activeJobId, 'Resuming FyersAPI insertion...', activeJobSource, controller.signal)
          .catch((resumeError: unknown) => {
            if (controller.signal.aborted || pageController.signal.aborted) return;
            console.warn('[FYERS][AUTOMATION_UI] poll_resume_failed', { activeJobId, resumeError });
            setError('');
            setStatus('warn');
            setStatusMessage('Unable to refresh status. Last known job may still be running.');
          })
          .finally(() => {
            if (pollControllerRef.current === controller) pollControllerRef.current = null;
          });
      }
    };

    void initializeJob();

    return () => {
      stopPolling('route_unmount_cleanup');
      pageController.abort();
    };
  }, [isSessionVerificationLoading]);

  async function runAuthorize() {
    if (isAuthorizing) return;
    setIsAuthorizing(true);
    setStatus('loading');
    setStatusMessage('Authorizing FYERS...');
    setError('');
    try {
      const payload = await authorizeFyers();
      const started = asRecord(payload);
      const startedJobId = safeLegacyText(pickField(started, ['jobId', 'job_id', 'runId', 'run_id']), '');
      if (startedJobId) {
        pushToast(withFyersToast(
          'Authorization Started',
          'FYERS authorization started in background. Open the login URL from the Active Job panel when it appears.',
          'info',
        ));
        await startOrAttachJob(
          started,
          'Waiting for FYERS authorization...',
          'FYERS authorization is already running. Reconnected to the active authorization job.',
          'legacy',
        );
        return;
      }
      const message = getFyersStatusMessage(payload, 'FYERS authorization completed.');
      setStats(extractFyersStats(payload));
      setLogText(message);
      setStatus(started.ok === false ? 'error' : 'success');
      setStatusMessage(message);
      await refreshAuth();
    } catch (authorizeError) {
      const message = formatFyersErrorMessage(authorizeError, 'Authorization failed.');
      setError(message);
      setStatus('error');
      setStatusMessage('Authorization failed');
      setCanExtract(false);
    } finally {
      setIsAuthorizing(false);
    }
  }

  async function runSingle() {
    if (blockUnauthenticatedExtraction()) return;
    const symbol = singleSymbol.trim().toUpperCase();
    if (!symbol) {
      setError('Stock Name is required for Single Stock fetch.');
      setStatus('warn');
      pushToast(withFyersToast('Validation', 'Stock Name is required for Single Stock fetch.', 'warn'));
      return;
    }
    if (!validateDateRange(singleStart, singleEnd)) return;
    if (!handleWeekendWarning(singleStart, singleEnd)) return;
    beginStart(`Starting ${symbol}...`);
    try {
      stopPolling('new_single_run');
      const started = await startFyersSingleJob({
        authorize: false,
        clientSessionId: readOrCreateFyersClientSessionId(),
        endDate: singleEnd,
        resolution: '1D',
        startDate: singleStart,
        symbol,
      });
      pushToast(withFyersToast('Extraction Started', `Single stock fetch started for ${symbol}.`, 'success'));
      await startOrAttachJob(
        started,
        `Running ${symbol}...`,
        'A FYERS insertion job is already running. Resuming the active run instead of starting another one.',
        'legacy',
      );
    } catch (runError) {
      const message = formatFyersErrorMessage(runError, 'Unable to start single stock extraction.');
      if (isFyersAuthRequiredStartError(runError)) {
        handleAuthRequiredStartFailure(message);
        return;
      }
      setError('');
      setStatus('warn');
      setStatusMessage(isBackendUnreachableFyersError(runError) ? message : 'Unable to confirm single stock start. The backend job may still be running.');
      pushToast(withFyersToast(
        isBackendUnreachableFyersError(runError) ? 'Backend Unreachable' : 'Start Status Unknown',
        isBackendUnreachableFyersError(runError) ? message : 'Unable to confirm single stock start. Check Active Job status before retrying.',
        'warn',
      ));
      if (message.includes(FYERS_AUTH_EXPIRED_TOAST)) {
        pushToast(withFyersToast('Authorization Required', FYERS_AUTH_EXPIRED_TOAST, 'danger'));
      }
    } finally {
      finishStart();
      pollControllerRef.current = null;
    }
  }

  async function runBatch() {
    if (blockUnauthenticatedExtraction()) return;
    if (!validateDateRange(batchStart, batchEnd)) return;
    if (!handleWeekendWarning(batchStart, batchEnd)) return;
    beginStart('Starting FYERS batch insertion...');
    try {
      stopPolling('new_batch_run');
      runningToastJobRef.current = '';
      lastBatchProgressRef.current = 0;
      skippedSnapshotKeyRef.current = '';
      setSkippedRows([]);
      const started = await startFyersAutomation({
        authorize: false,
        clientSessionId: readOrCreateFyersClientSessionId(),
        endDate: batchEnd,
        resolution: '1D',
        startDate: batchStart,
      });
      pushToast(withFyersToast('Extraction Started', 'Batch extraction and insertion job started.', 'success'));
      await startOrAttachJob(
        started,
        'Running direct API batch...',
        'A FYERS insertion job is already running. Resuming the active run instead of starting another one.',
        'automation',
      );
    } catch (runError) {
      const message = formatFyersErrorMessage(runError, 'Unable to start batch extraction.');
      if (isFyersAuthRequiredStartError(runError)) {
        handleAuthRequiredStartFailure(message);
        return;
      }
      setError('');
      setStatus('warn');
      setStatusMessage(isBackendUnreachableFyersError(runError) ? message : 'Unable to confirm batch start. The backend job may still be running.');
      pushToast(withFyersToast(
        isBackendUnreachableFyersError(runError) ? 'Backend Unreachable' : 'Start Status Unknown',
        isBackendUnreachableFyersError(runError) ? message : 'Unable to confirm batch start. Check Active Job status before retrying.',
        'warn',
      ));
      if (message.includes(FYERS_AUTH_EXPIRED_TOAST)) {
        pushToast(withFyersToast('Authorization Required', FYERS_AUTH_EXPIRED_TOAST, 'danger'));
      }
    } finally {
      finishStart();
      pollControllerRef.current = null;
    }
  }

  async function requestStop() {
    const activeJob = readActiveJob();
    const jobId = jobIdOf(job) || activeJob.jobId;
    if (!jobId || stopLoading) return;
    const confirmed = window.confirm('Stop the active FYERS API job immediately?');
    if (!confirmed) return;
    setStopLoading(true);
    setError('');
    setStatus('loading');
    setStatusMessage('Stopping...');
    stopPolling('stop_requested_by_user');
    try {
      const payload = await stopFyersAutomation(jobId);
      setJob((current) => ({ ...current, ...asRecord(payload) }));
      setStatusMessage('Stopping...');
      pushToast(withFyersToast(
        'Stop Requested',
        'Fyers automation stop requested. Stopping immediately.',
        'warn',
      ));
      const controller = new AbortController();
      pollControllerRef.current = controller;
      void pollJob(jobId, 'Stopping...', activeJob.source, controller.signal)
        .catch((stopPollError: unknown) => {
          if (controller.signal.aborted) return;
          const message = formatFyersErrorMessage(stopPollError, 'Unable to confirm stop status.');
          setStatus('warn');
          setStatusMessage(message);
        })
        .finally(() => {
          if (pollControllerRef.current === controller) pollControllerRef.current = null;
        });
    } catch (stopError) {
      const message = formatFyersErrorMessage(stopError, 'Unable to stop FYERS automation job.');
      setStopLoading(false);
      setError(message);
      setStatus('error');
      setStatusMessage('Stop failed');
      pushToast(withFyersToast('Stop Failed', message, 'danger'));
    }
  }

  async function rerunAutomation(mode: 'failed' | 'remaining') {
    const currentJobId = jobIdOf(job);
    beginStart(mode === 'failed' ? 'Starting failed-symbol rerun...' : 'Starting remaining-symbol rerun...');
    try {
      stopPolling(`rerun_${mode}`);
      runningToastJobRef.current = '';
      lastBatchProgressRef.current = 0;
      skippedSnapshotKeyRef.current = '';
      const request = {
        clientSessionId: readOrCreateFyersClientSessionId(),
        job_id: currentJobId || undefined,
        trading_date: tradingDateOf(job, stats) || undefined,
      };
      const started = await (mode === 'failed'
        ? rerunFailedFyersAutomation(request)
        : rerunRemainingFyersAutomation(request));
      pushToast(withFyersToast(
        'Extraction Started',
        mode === 'failed' ? 'Failed-symbol rerun started.' : 'Remaining-symbol rerun started.',
        'success',
      ));
      await startOrAttachJob(
        started,
        mode === 'failed' ? 'Rerunning failed symbols...' : 'Rerunning remaining symbols...',
        'A FYERS automation job is already running. Reconnected to the active job.',
        'automation',
      );
    } catch (rerunError) {
      const message = formatFyersErrorMessage(rerunError, 'Unable to start rerun.');
      setError(message);
      setStatus('error');
      setStatusMessage(mode === 'failed' ? 'Failed-symbol rerun failed' : 'Remaining-symbol rerun failed');
      pushToast(withFyersToast('Extraction Failed', message, 'danger'));
    } finally {
      finishStart();
      pollControllerRef.current = null;
    }
  }

  const kpis = useMemo(() => statsToCards(stats, job), [job, stats]);
  const jobRunning = useMemo(() => isRunningJob(job), [job]);
  const jobTelemetry = useMemo(() => buildJobTelemetry(job, jobRunning), [job, jobRunning]);
  const skippedSymbolsText = useMemo(
    () => skippedRows.map((row) => row.symbol).filter((symbol) => symbol && symbol !== '--').join(','),
    [skippedRows],
  );
  const jobTradingDate = useMemo(() => tradingDateOf(job, stats), [job, stats]);

  return (
    <FyersMigrationLayout activeFyersPage="/app/fyers/automation" className="fyers-automation-react-page">
      <PageHero title="FYERS API AUTOMATION" />

      <section className="card database-fyers-card">
        <div className="database-fyers-card__header">
          <h2>FyersAPI</h2>
          <span className={`database-badge database-badge--${status === 'error' ? 'error' : status === 'loading' ? 'loading' : status === 'success' ? 'ok' : 'neutral'}`}>{statusMessage}</span>
        </div>

        <section className="fyers-authorization-strip" aria-label="Fyers authorization controls">
          <span className="database-badge database-badge--warn">{authMessage}</span>
          <div className="fyers-react-actions fyers-react-actions--inline">
            {jobRunning ? (
              <Button type="button" variant="danger" disabled={stopLoading} onClick={() => { void requestStop(); }}>
                {stopLoading ? 'Stopping...' : 'Stop'}
              </Button>
            ) : null}
            <Button
              type="button"
              variant="secondary"
              disabled={isRefreshingAuth}
              onClick={() => { void refreshAuth(); }}
            >
              {isRefreshingAuth ? 'Refreshing...' : 'Refresh Status'}
            </Button>
            <Button type="button" variant="secondary" disabled={isAuthorizing || jobRunning || isStarting} onClick={() => { void runAuthorize(); }}>
              {isAuthorizing ? 'Authorizing...' : 'Authorize'}
            </Button>
          </div>
        </section>

        <div className="database-fyers-grid">
          <section className="database-fyers-block">
            <h3>Single Stock</h3>
            <label className="database-react-field">
              <span>Stock Name</span>
              <Input
                variant="light"
                value={singleSymbol}
                placeholder="TIMKEN, ALIVUS, NSE:RENUKA-EQ"
                onChange={(event) => setSingleSymbol(event.currentTarget.value)}
              />
            </label>
            <div className="fyers-react-form-grid fyers-react-form-grid--dates">
              <FyersDatePickerField label="From Date" maxDate={latestSelectableDate} value={singleStart} onChange={setSingleStart} />
              <FyersDatePickerField label="To Date" maxDate={latestSelectableDate} value={singleEnd} onChange={setSingleEnd} />
              <label className="database-react-field">
                <span>Resolution</span>
                <Input variant="light" value="1D" readOnly />
              </label>
            </div>
            <div className="fyers-automation-action-row">
              <Button fullWidth type="button" variant="primary" disabled={!canExtract || status === 'loading' || isStarting} onClick={() => { void runSingle(); }}>
                {isStarting ? 'Starting...' : 'Fetch & Insert'}
              </Button>
            </div>
          </section>

          <section className="database-fyers-block">
            <h3>Direct API Batch</h3>
            <div className="fyers-automation-stock-spacer" aria-hidden="true" />
            <div className="fyers-react-form-grid fyers-react-form-grid--dates">
              <FyersDatePickerField label="From Date" maxDate={latestSelectableDate} value={batchStart} onChange={setBatchStart} />
              <FyersDatePickerField label="To Date" maxDate={latestSelectableDate} value={batchEnd} onChange={setBatchEnd} />
              <label className="database-react-field">
                <span>Resolution</span>
                <Input variant="light" value="1D" readOnly />
              </label>
            </div>
            <div className="fyers-automation-action-row">
              <Button fullWidth type="button" variant="primary" disabled={!canExtract || status === 'loading' || isStarting} onClick={() => { void runBatch(); }}>
                {isStarting ? 'Starting...' : 'Run Batch Insert'}
              </Button>
            </div>
          </section>
        </div>

        <KpiGrid items={kpis} />

        {error ? <ErrorAlertCard message={error} /> : null}

        <section className="database-fyers-summary">
          <div className="table-title">
            <h3>Active Job</h3>
            <div className="flex items-center gap-2">
              <span className="count-pill">{jobIdOf(job) || 'No active job'}</span>
              <CopyTextButton text={logText} label="Copy logs" />
              <ThemeToggle className="rounded-full border border-slate-200 bg-white/90 text-slate-700 hover:border-sky-300 hover:text-slate-950 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200 dark:hover:border-sky-500 dark:hover:text-white" />
            </div>
          </div>
          <div className="fyers-react-definition-grid fyers-react-definition-grid--compact">
            <div>
              <dt>Authorization URL</dt>
              <dd>
                {jobTelemetry.authorizationUrl ? (
                  <a
                    href={jobTelemetry.authorizationUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sky-700 underline underline-offset-2 hover:text-sky-900 dark:text-sky-300 dark:hover:text-sky-200"
                  >
                    Open login
                  </a>
                ) : '--'}
              </dd>
            </div>
            <div>
              <dt>Current Symbol</dt>
              <dd>{jobTelemetry.currentSymbol}</dd>
            </div>
            <div>
              <dt>Last Heartbeat</dt>
              <dd>{jobTelemetry.lastHeartbeat}</dd>
            </div>
            <div>
              <dt>ETA Timestamp</dt>
              <dd>{jobTelemetry.etaTimestamp}</dd>
            </div>
          </div>

          <pre className="database-fyers-log" aria-live="polite">{logText}</pre>
        </section>

        <section className="database-fyers-summary">
          <div className="table-title">
            <div>
              <h3>Currently Skipped Symbols</h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                Failed, skipped, already inserted, duplicate-safe skipped, invalid, and error symbols.
              </p>
            </div>
            <span className="count-pill">{skippedRows.length.toLocaleString('en-IN')}</span>
          </div>
          <div className="mb-3 flex flex-wrap gap-2">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={!skippedSymbolsText}
              onClick={() => copyToClipboard(skippedSymbolsText, 'Currently skipped symbols')}
            >
              Copy comma-separated symbols
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={!skippedSymbolsText}
              onClick={() => downloadFile(
                skippedSymbolsText,
                buildSkippedSymbolsFilename('txt', jobTradingDate),
                'Currently skipped symbols',
                'text/plain;charset=utf-8',
              )}
            >
              Download TXT
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={!skippedRows.length}
              onClick={() => downloadFile(
                buildSkippedSymbolsCsv(skippedRows),
                buildSkippedSymbolsFilename('csv', jobTradingDate),
                'Currently skipped symbols CSV',
                'text/csv;charset=utf-8',
              )}
            >
              Download detailed CSV
            </Button>
          </div>
          <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-100/80 text-xs uppercase tracking-wide text-slate-600 dark:bg-slate-900 dark:text-slate-300">
                <tr>
                  <th className="px-4 py-3">Symbol</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Reason</th>
                  <th className="px-4 py-3">Trading Date</th>
                  <th className="px-4 py-3">Retry Count</th>
                  <th className="px-4 py-3">Last Error</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 bg-white/70 dark:divide-slate-800 dark:bg-slate-950/40">
                {skippedRows.length ? skippedRows.map((row, index) => (
                  <tr key={`${row.symbol}-${row.status}-${index}`}>
                    <td className="whitespace-nowrap px-4 py-3 font-semibold text-slate-900 dark:text-slate-100">{row.symbol}</td>
                    <td className="whitespace-nowrap px-4 py-3">{row.status}</td>
                    <td className="min-w-48 px-4 py-3">{row.reason}</td>
                    <td className="whitespace-nowrap px-4 py-3">{row.tradingDate}</td>
                    <td className="whitespace-nowrap px-4 py-3">{row.retryCount}</td>
                    <td className="min-w-56 px-4 py-3 text-red-700 dark:text-red-300">{row.lastError}</td>
                  </tr>
                )) : (
                  <tr>
                    <td className="px-4 py-8 text-center text-slate-500 dark:text-slate-400" colSpan={6}>
                      No skipped or failed symbols are available for this job.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </section>

      <Toast
        open={Boolean(toast)}
        title={toast?.title || ''}
        description={toast?.description || ''}
        tone={toast?.tone || 'info'}
        onClose={() => setToast(null)}
      />
    </FyersMigrationLayout>
  );
}
