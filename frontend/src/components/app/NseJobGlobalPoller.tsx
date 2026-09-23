import { useEffect, useState, useRef } from 'react';
import { Toast } from '../ui/Toast';

type JobStatusResponse = {
  ok?: boolean;
  status?: string;
  data?: {
    last_run_id?: string;
    current_status?: string;
    is_running?: boolean;
    message?: string;
    totals?: {
      rows_success: number;
      rows_failed: number;
      rows_skipped: number;
    };
    target_trade_date?: string;
  };
};

type MergeStatusResponse = {
  run_id?: string;
  status?: string;
  message?: string;
  latest_trading_date?: string;
  inserted_dev?: number;
  inserted_oracle?: number;
  updated_dev?: number;
  updated_oracle?: number;
  cleanup_deleted_source_rows?: number;
  cleanup_retention_days?: number;
};

type NseDatabaseJobSource = {
  endpoint: string;
  key: string;
  label: string;
};

type NseDatabaseJobPayload = Record<string, unknown>;

const NSE_DATABASE_JOB_SOURCES: NseDatabaseJobSource[] = [
  { endpoint: '/api/marketdata/nse-mcap/jobs/latest?tail=20', key: 'market-cap', label: 'NSE Market Cap' },
  { endpoint: '/api/marketdata/nse-ffmc/jobs/latest?tail=20', key: 'ffmc', label: 'NSE FFMC' },
  { endpoint: '/api/marketdata/nse-delivery/jobs/latest?tail=20', key: 'delivery', label: 'NSE Delivery Data' },
];

export const NSE_GLOBAL_POLL_ACTIVE_INTERVAL_MS = 5000;
export const NSE_GLOBAL_POLL_IDLE_INTERVAL_MS = 30000;
export const NSE_GLOBAL_POLL_HIDDEN_INTERVAL_MS = 60000;
const NSE_GLOBAL_POLL_REQUEST_TIMEOUT_MS = 10000;

export function isNseGlobalPollActiveStatus(value: unknown): boolean {
  return ['RUNNING', 'STARTED', 'QUEUED', 'PENDING', 'PROCESSING', 'IN_PROGRESS']
    .includes(String(value ?? '').trim().toUpperCase());
}

export function getNseGlobalPollDelay(hasActiveJob: boolean, isVisible: boolean): number {
  if (!isVisible) return NSE_GLOBAL_POLL_HIDDEN_INTERVAL_MS;
  return hasActiveJob ? NSE_GLOBAL_POLL_ACTIVE_INTERVAL_MS : NSE_GLOBAL_POLL_IDLE_INTERVAL_MS;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

function isDocumentVisible(): boolean {
  return document.visibilityState !== 'hidden';
}

function toMergeCount(value: unknown): number {
  const numeric = Number(value || 0);
  return Number.isFinite(numeric) ? numeric : 0;
}

function formatMergeCount(value: number): string {
  return value.toLocaleString('en-IN');
}

export function buildStockHistoryMergeToastDescription(payload: MergeStatusResponse): string {
  const devMerged = toMergeCount(payload.inserted_dev) + toMergeCount(payload.updated_dev);
  const oracleMerged = toMergeCount(payload.inserted_oracle) + toMergeCount(payload.updated_oracle);
  if (devMerged === oracleMerged) {
    return `${formatMergeCount(devMerged)} merged both the tables.`;
  }
  return `Dev:${formatMergeCount(devMerged)} and Oracle:${formatMergeCount(oracleMerged)} merged both the tables.`;
}

function asRecord(value: unknown): NseDatabaseJobPayload {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as NseDatabaseJobPayload : {};
}

function firstText(...values: unknown[]): string {
  for (const value of values) {
    const text = String(value ?? '').trim();
    if (text) return text;
  }
  return '';
}

function firstCount(...values: unknown[]): number {
  for (const value of values) {
    const numeric = toMergeCount(value);
    if (numeric > 0) return numeric;
  }
  return 0;
}

function nestedJobRecord(payload: NseDatabaseJobPayload): NseDatabaseJobPayload {
  return asRecord(payload.job || payload.data || payload);
}

function nseDatabaseInsertedRows(payload: NseDatabaseJobPayload): number {
  const job = nestedJobRecord(payload);
  const counts = asRecord(job.counts);
  const stats = asRecord(job.stats);
  const result = asRecord(job.result);
  const resultCounts = asRecord(result.counts);
  return firstCount(
    counts.insertedRows,
    counts.inserted_rows,
    stats.totalRecordsInserted,
    result.inserted_row_count,
    result.insertedRows,
    result.inserted_rows,
    resultCounts.insertedRows,
    resultCounts.inserted_rows,
  );
}

function nseDatabaseTradeDate(payload: NseDatabaseJobPayload): string {
  const job = nestedJobRecord(payload);
  const result = asRecord(job.result);
  const request = asRecord(job.request || result.request);
  return firstText(
    result.tradeDate,
    result.trade_date,
    job.tradeDate,
    job.trade_date,
    request.tradeDate,
    request.trade_date,
  );
}

function nseDatabaseRunId(payload: NseDatabaseJobPayload): string {
  const job = nestedJobRecord(payload);
  return firstText(job.jobId, job.job_id, job.id, job.runId, job.run_id);
}

function nseDatabaseStatus(payload: NseDatabaseJobPayload): string {
  const job = nestedJobRecord(payload);
  return firstText(job.status, job.current_status).toUpperCase();
}

export function buildNseDatabaseInsertToastDescription(label: string, payload: NseDatabaseJobPayload): string {
  const rows = nseDatabaseInsertedRows(payload);
  const date = nseDatabaseTradeDate(payload) || '-';
  return `${label} inserted into DB successfully. Rows: ${formatMergeCount(rows)}. Trading Date: ${date}.`;
}

export function NseJobGlobalPoller() {
  const [toastOpen, setToastOpen] = useState(false);
  const [toastData, setToastData] = useState({ title: '', description: '', tone: 'info' as 'success' | 'danger' | 'info' });
  const automationNotifiedRunIdRef = useRef<string | null>(null);
  const automationInitializedRef = useRef(false);
  const mergeNotifiedRunIdRef = useRef<string | null>(null);
  const mergeInitializedRef = useRef(false);
  const nseDatabaseInitializedRef = useRef<Record<string, boolean>>({});
  const nseDatabaseNotifiedRunIdRef = useRef<Record<string, string>>({});

  useEffect(() => {
    let stopped = false;
    let pollTimer: number | null = null;
    let pollController: AbortController | null = null;
    let pollInFlight = false;

    const fetchAutomationStatus = async (signal: AbortSignal): Promise<boolean> => {
      try {
        const response = await fetch('/api/automation/nse-marketdata/status', {
          signal,
          headers: {
            'Content-Type': 'application/json',
          },
        });
        if (!response.ok) return false;
        
        const json: JobStatusResponse = await response.json();
        const data = json.data || (json as any);
        
        const runId = data.last_run_id;
        const currentStatus = data.current_status;
        const isActive = Boolean(data.is_running) || isNseGlobalPollActiveStatus(currentStatus);
        if (!runId || !currentStatus) return isActive;

        if (!automationInitializedRef.current) {
          automationInitializedRef.current = true;
          if (currentStatus === 'SUCCESS' || currentStatus === 'FAILED') {
            automationNotifiedRunIdRef.current = runId;
          }
          return isActive;
        }

        if (automationNotifiedRunIdRef.current === runId) return isActive;

        if (currentStatus === 'SUCCESS') {
          const rows = data.totals?.rows_success || 0;
          const date = data.target_trade_date || '';
          setToastData({
            title: 'NSE Automation Completed',
            description: `NSE data inserted successfully. Rows: ${rows}. Trading Date: ${date}.`,
            tone: 'success',
          });
          setToastOpen(true);
          automationNotifiedRunIdRef.current = runId;
        } else if (currentStatus === 'FAILED') {
          setToastData({
            title: 'NSE Automation Failed',
            description: data.message || 'The background job encountered an error.',
            tone: 'danger',
          });
          setToastOpen(true);
          automationNotifiedRunIdRef.current = runId;
        }
        return isActive;
      } catch (err) {
        if (!isAbortError(err)) console.error('Failed to poll NSE background job status', err);
        return false;
      }
    };

    const fetchMergeStatus = async (signal: AbortSignal): Promise<boolean> => {
      try {
        const response = await fetch('/api/marketdata/merge/status/latest', {
          signal,
          headers: {
            'Content-Type': 'application/json',
          },
        });
        if (!response.ok) return false;

        const payload: MergeStatusResponse = await response.json();
        const runId = String(payload.run_id || '').trim();
        const status = String(payload.status || '').trim().toUpperCase();
        const isActive = isNseGlobalPollActiveStatus(status);
        if (!runId || !status) return isActive;

        if (!mergeInitializedRef.current) {
          mergeInitializedRef.current = true;
          if (status === 'SUCCESS' || status === 'FAILED' || status === 'SKIPPED' || status === 'SKIPPED_ALREADY_RUNNING') {
            mergeNotifiedRunIdRef.current = runId;
          }
          return isActive;
        }

        if (mergeNotifiedRunIdRef.current === runId) return isActive;

        if (status === 'SUCCESS') {
          setToastData({
            title: 'Stock history merge completed',
            description: buildStockHistoryMergeToastDescription(payload),
            tone: 'success',
          });
          setToastOpen(true);
          mergeNotifiedRunIdRef.current = runId;
        } else if (status === 'FAILED') {
          setToastData({
            title: 'Stock history merge failed',
            description: payload.message || 'The stock-history merge encountered an error.',
            tone: 'danger',
          });
          setToastOpen(true);
          mergeNotifiedRunIdRef.current = runId;
        } else if (status === 'SKIPPED') {
          setToastData({
            title: 'Stock history merge',
            description: String(payload.message || '').trim() || 'Already Up-to-Date',
            tone: 'info',
          });
          setToastOpen(true);
          mergeNotifiedRunIdRef.current = runId;
        } else if (status === 'SKIPPED_ALREADY_RUNNING') {
          mergeNotifiedRunIdRef.current = runId;
        }
        return isActive;
      } catch (err) {
        if (!isAbortError(err)) console.error('Failed to poll stock-history merge status', err);
        return false;
      }
    };

    const fetchNseDatabaseJobStatus = async (source: NseDatabaseJobSource, signal: AbortSignal): Promise<boolean> => {
      try {
        const response = await fetch(source.endpoint, {
          signal,
          headers: {
            'Content-Type': 'application/json',
          },
        });
        if (!response.ok) return false;

        const payload = await response.json() as NseDatabaseJobPayload;
        const runId = nseDatabaseRunId(payload);
        const status = nseDatabaseStatus(payload);
        const isActive = isNseGlobalPollActiveStatus(status);
        if (!runId || !status) return isActive;

        const isTerminal = status === 'SUCCESS' || status === 'FAILED' || status === 'ALREADY_EXISTS' || status === 'NO_ACTION';
        if (!nseDatabaseInitializedRef.current[source.key]) {
          nseDatabaseInitializedRef.current[source.key] = true;
          if (isTerminal) {
            nseDatabaseNotifiedRunIdRef.current[source.key] = runId;
          }
          return isActive;
        }

        if (nseDatabaseNotifiedRunIdRef.current[source.key] === runId) return isActive;

        const insertedRows = nseDatabaseInsertedRows(payload);
        if (status === 'SUCCESS' && insertedRows > 0) {
          setToastData({
            title: `${source.label} DB insert completed`,
            description: buildNseDatabaseInsertToastDescription(source.label, payload),
            tone: 'success',
          });
          setToastOpen(true);
          nseDatabaseNotifiedRunIdRef.current[source.key] = runId;
        } else if (isTerminal) {
          nseDatabaseNotifiedRunIdRef.current[source.key] = runId;
        }
        return isActive;
      } catch (err) {
        if (!isAbortError(err)) console.error(`Failed to poll ${source.label} job status`, err);
        return false;
      }
    };

    const clearPollTimer = () => {
      if (pollTimer !== null) {
        window.clearTimeout(pollTimer);
        pollTimer = null;
      }
    };

    const scheduleNextPoll = (delayMs: number) => {
      clearPollTimer();
      if (stopped) return;
      pollTimer = window.setTimeout(() => {
        void pollStatus();
      }, delayMs);
    };

    const pollStatus = async () => {
      if (stopped || pollInFlight) return;
      if (!isDocumentVisible()) {
        scheduleNextPoll(getNseGlobalPollDelay(false, false));
        return;
      }

      pollInFlight = true;
      const controller = new AbortController();
      pollController = controller;
      const requestTimeout = window.setTimeout(() => controller.abort(), NSE_GLOBAL_POLL_REQUEST_TIMEOUT_MS);
      let hasActiveJob = false;
      try {
        const activeStates = await Promise.all([
          fetchAutomationStatus(controller.signal),
          fetchMergeStatus(controller.signal),
          ...NSE_DATABASE_JOB_SOURCES.map((source) => fetchNseDatabaseJobStatus(source, controller.signal)),
        ]);
        hasActiveJob = activeStates.some(Boolean);
      } finally {
        window.clearTimeout(requestTimeout);
        if (pollController === controller) pollController = null;
        pollInFlight = false;
        if (!stopped) {
          scheduleNextPoll(getNseGlobalPollDelay(hasActiveJob, isDocumentVisible()));
        }
      }
    };

    const handleVisibilityChange = () => {
      clearPollTimer();
      if (!isDocumentVisible()) {
        pollController?.abort();
        scheduleNextPoll(getNseGlobalPollDelay(false, false));
        return;
      }
      if (!pollInFlight) void pollStatus();
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    void pollStatus();
    return () => {
      stopped = true;
      clearPollTimer();
      pollController?.abort();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  useEffect(() => {
    if (!toastOpen) return;
    const timeout = setTimeout(() => setToastOpen(false), 5000);
    return () => clearTimeout(timeout);
  }, [toastOpen]);

  return (
    <Toast
      open={toastOpen}
      title={toastData.title}
      description={toastData.description}
      tone={toastData.tone}
      placement="top-right"
      onClose={() => setToastOpen(false)}
    />
  );
}
