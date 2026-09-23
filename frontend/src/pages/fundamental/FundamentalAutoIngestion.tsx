import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import { DataBadge } from '../../components/ui/DataBadge';
import { FundamentalCopyIcon, FundamentalRefreshIcon, FundamentalShieldIcon } from '../../components/fundamental/fundamentalIcons';
import { FundamentalModulePage } from './FundamentalModulePage';
import {
  clearStuckFundamentalQueue,
  fetchLocalXlsxLogs,
  fetchLocalXlsxStatus,
  fetchFundamentalIngestionStatus,
  fetchUploadedScreenerSymbols,
  importNifty50Symbols,
  type LocalXlsxFlowStatusResponse,
  type LocalXlsxLogsResponse,
  manualRunUploadedScreenerSymbols,
  openScreenerLoginBrowser,
  pauseFundamentalScheduler,
  processLocalXlsxFiles,
  retryFailedFundamental,
  retryFailedFundamentalQueue,
  retryBlockedFundamentalQueue,
  resumeAfterScreenerLogin,
  type FundamentalDownloadRunResponse,
  type FundamentalIngestionSummary,
  runFundamentalFullAutoNow,
  runFundamentalIngestionNow,
  scanLocalXlsxFiles,
  runScreenerDownloadNow,
  resumeFundamentalScheduler,
  startFundamentalScheduler,
  stopFundamentalScheduler,
  validateScreenerFilesNow,
  type FundamentalIngestionStatusResponse,
  type FundamentalOperationalLog,
  type FundamentalPipelineState,
  type FundamentalScreenerAuthStatus,
  type FundamentalScreenerSchemaStatus,
  type FundamentalIngestionStatusRow,
  type FundamentalUploadedScreenerSymbol,
  type FundamentalSchedulerActionResponse,
  type FundamentalSchedulerStatus,
  type FundamentalWorkerMetrics,
  forceRunFundamentalQueue,
  uploadScreenerSymbolsCsv,
} from '../../services/fundamental/fundamentalIngestionApi';

const PAGE_SIZE = 15;

type SummaryCardConfig = {
  label: string;
  key: keyof FundamentalIngestionSummary & string;
  date?: boolean;
};

const summaryCards: ReadonlyArray<SummaryCardConfig> = [
  { label: 'Total Nifty50 Symbols', key: 'total_symbols' },
  { label: 'Download Completed', key: 'download_completed' },
  { label: 'Download Pending', key: 'download_pending' },
  { label: 'Download Failed', key: 'download_failed' },
  { label: 'Download Blocked', key: 'download_blocked' },
  { label: 'DB Ingestion Completed', key: 'db_ingestion_completed' },
  { label: 'DB Ingestion Pending', key: 'db_ingestion_pending' },
  { label: 'DB Ingestion Failed', key: 'db_ingestion_failed' },
  { label: 'Quarters per Stock', key: 'total_quarters_ingested' },
  { label: 'Years per Stock', key: 'total_years_ingested' },
  { label: 'Last Scheduler Run Time', key: 'last_scheduler_run_time', date: true },
  { label: 'Last Successful Ingestion Time', key: 'last_successful_ingestion_time', date: true },
] as const;

type FlowKey = 'download' | 'validate' | 'process' | 'success';
type FlowStatus = 'NOT_STARTED' | 'WORKING' | 'COMPLETED' | 'PARTIAL' | 'FAILED';
type ToastTone = 'success' | 'warn' | 'danger' | 'info';

type FlowStepState = {
  status: FlowStatus;
  startedAt: string | null;
  endedAt: string | null;
  elapsedMs: number;
  detail: string;
};

type PageToastState = {
  title: string;
  detail: string;
  tone: ToastTone;
};

type RunLogEntry = {
  at: string;
  level: 'INFO' | 'WARN' | 'ERROR';
  message: string;
};

type SchedulerControlAction =
  | 'start'
  | 'stop'
  | 'pause'
  | 'resume'
  | 'retry-failed-queue'
  | 'retry-blocked-queue'
  | 'clear-stuck'
  | 'force-run';

const flowSteps = [
  { key: 'download', label: 'Download' },
  { key: 'validate', label: 'Extract / Validate' },
  { key: 'process', label: 'Insert / Process' },
  { key: 'success', label: 'Success' },
] as const;

const initialFlowDetail = 'Not started yet';

function createInitialFlowSteps(): Record<FlowKey, FlowStepState> {
  return {
    download: { status: 'NOT_STARTED', startedAt: null, endedAt: null, elapsedMs: 0, detail: initialFlowDetail },
    validate: { status: 'NOT_STARTED', startedAt: null, endedAt: null, elapsedMs: 0, detail: initialFlowDetail },
    process: { status: 'NOT_STARTED', startedAt: null, endedAt: null, elapsedMs: 0, detail: initialFlowDetail },
    success: { status: 'NOT_STARTED', startedAt: null, endedAt: null, elapsedMs: 0, detail: initialFlowDetail },
  };
}

function formatDate(value?: string | null) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function statusTone(status?: string): 'default' | 'accent' | 'success' | 'warn' | 'danger' {
  const normalized = (status || '').toUpperCase();
  if (['SUCCESS', 'COMPLETED', 'DOWNLOADED', 'VALIDATED', 'EXTRACTED', 'DB_INSERTED'].includes(normalized)) return 'success';
  if (normalized === 'FAILED' || normalized === 'BLOCKED' || normalized.endsWith('_FAILED')) return 'danger';
  if (normalized === 'PARTIAL' || normalized === 'RUNNING' || normalized === 'IN_PROGRESS') return 'warn';
  if (normalized === 'SKIPPED' || normalized === 'SKIPPED_DUPLICATE') return 'accent';
  return 'default';
}

function batchFlowStatus(status?: string, failedCount = 0): Exclude<FlowStatus, 'NOT_STARTED'> {
  const normalized = (status || '').toUpperCase();
  if (normalized === 'SUCCESS') return failedCount ? 'PARTIAL' : 'COMPLETED';
  if (normalized === 'PARTIAL') return 'PARTIAL';
  if (normalized === 'IDLE' || normalized === 'SKIPPED') return 'PARTIAL';
  return 'FAILED';
}

function numberCell(value: number | null | undefined) {
  return typeof value === 'number' ? value.toLocaleString() : '0';
}

function fileSizeCell(value: number | null | undefined) {
  if (typeof value !== 'number' || value <= 0) return '-';
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(2)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(2)} KB`;
  return `${value} B`;
}

function currentStepCell(row: FundamentalIngestionStatusRow) {
  const upper = (value?: string | null) => (value || '').toUpperCase();
  if (upper(row.pipeline_stage) === 'COMPLETED') return 'PIPELINE_COMPLETED';
  if (upper(row.db_stage) === 'IN_PROGRESS') return 'DB_INSERT_IN_PROGRESS';
  if (upper(row.db_stage) === 'DB_INSERTED') return 'DB_INSERT_COMPLETED';
  if (upper(row.extraction_stage) === 'IN_PROGRESS') return 'EXTRACTION_IN_PROGRESS';
  if (upper(row.extraction_stage) === 'EXTRACTED') return 'EXTRACTION_COMPLETED';
  if (upper(row.validation_stage) === 'IN_PROGRESS') return 'VALIDATION_IN_PROGRESS';
  if (upper(row.validation_stage) === 'VALIDATED') return 'VALIDATED';
  if (upper(row.download_stage) === 'IN_PROGRESS') return 'DOWNLOAD_IN_PROGRESS';
  if (upper(row.download_stage) === 'DOWNLOADED') return 'DOWNLOAD_COMPLETED';
  if (upper(row.download_status) === 'FAILED') return 'DOWNLOAD_FAILED';
  if (upper(row.download_status) === 'BLOCKED') return 'DOWNLOAD_BLOCKED';
  return 'PENDING';
}

function elapsedForStep(step: FlowStepState) {
  if (step.status === 'WORKING' && step.startedAt) {
    const startedAt = Date.parse(step.startedAt);
    if (!Number.isNaN(startedAt)) {
      return Math.max(0, Date.now() - startedAt);
    }
  }
  return step.elapsedMs;
}

function formatFlowElapsed(ms: number) {
  return `${(Math.max(0, ms) / 1000).toFixed(2)}s`;
}

function flowStageClass(key: FlowKey) {
  if (key === 'download') return 'border-sky-200 bg-sky-50 shadow-sky-100';
  if (key === 'validate') return 'border-teal-200 bg-teal-50 shadow-teal-100';
  if (key === 'process') return 'border-amber-200 bg-amber-50 shadow-amber-100';
  return 'border-emerald-200 bg-emerald-50 shadow-emerald-100';
}

function flowStatusBadgeClass(status: FlowStatus) {
  if (status === 'COMPLETED') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'PARTIAL') return 'border-amber-200 bg-amber-50 text-amber-700';
  if (status === 'FAILED') return 'border-rose-200 bg-rose-50 text-rose-700';
  if (status === 'WORKING') return 'border-indigo-200 bg-indigo-50 text-indigo-700';
  return 'border-slate-200 bg-slate-50 text-slate-600';
}

function schedulerStatusBadgeClass(status?: string | null) {
  const normalized = (status || '').toUpperCase();
  if (normalized === 'AUTHENTICATED' || normalized === 'RUNNING') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (normalized === 'VERIFYING') return 'border-sky-200 bg-sky-50 text-sky-700';
  if (normalized === 'READY_EMPTY') return 'border-slate-200 bg-slate-50 text-slate-700';
  if (normalized === 'AUTH_REQUIRED' || normalized === 'SCHEMA_PENDING') return 'border-amber-200 bg-amber-50 text-amber-700';
  if (normalized === 'ERROR') return 'border-rose-200 bg-rose-50 text-rose-700';
  if (normalized === 'PAUSED') return 'border-amber-200 bg-amber-50 text-amber-700';
  if (normalized === 'BLOCKED' || normalized === 'SESSION_REQUIRED') return 'border-rose-200 bg-rose-50 text-rose-700';
  return 'border-slate-200 bg-slate-50 text-slate-600';
}

function toastClass(tone: ToastTone) {
  if (tone === 'success') return 'border-emerald-200 bg-emerald-50 text-emerald-900';
  if (tone === 'warn') return 'border-amber-200 bg-amber-50 text-amber-900';
  if (tone === 'danger') return 'border-rose-200 bg-rose-50 text-rose-900';
  return 'border-sky-200 bg-sky-50 text-sky-900';
}

function csvEscape(value: unknown) {
  return `"${String(value ?? '').replace(/"/g, '""')}"`;
}

function parseSymbolsOverride(value: string) {
  const seen = new Set<string>();
  return value
    .split(',')
    .map((item) => item.trim().toUpperCase())
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

function matchesUploadedSymbol(symbol: FundamentalUploadedScreenerSymbol, query: string) {
  if (!query) return true;
  const normalized = query.trim().toUpperCase();
  if (!normalized) return true;
  return symbol.symbol.toUpperCase().includes(normalized) || (symbol.source || '').toUpperCase().includes(normalized);
}

function workerLevelFromStatus(status?: string | null): RunLogEntry['level'] {
  const normalized = (status || '').toUpperCase();
  if (normalized.includes('FAIL') || normalized.includes('BLOCK')) return 'ERROR';
  if (normalized.includes('WARN') || normalized === 'PARTIAL' || normalized === 'PAUSED' || normalized === 'SESSION_REQUIRED' || normalized === 'AUTH_REQUIRED' || normalized === 'SCHEMA_PENDING' || normalized === 'READY_EMPTY') return 'WARN';
  return 'INFO';
}

function effectiveAuthStatus(
  scheduler?: FundamentalSchedulerStatus,
  auth?: FundamentalScreenerAuthStatus | null,
) {
  const explicit = (auth?.auth_status || scheduler?.auth_status || '').toUpperCase();
  if (explicit) return explicit;
  const legacy = (scheduler?.login_status || '').toUpperCase();
  if (legacy === 'LOGIN_REQUIRED' || legacy === 'BLOCKED') return 'AUTH_REQUIRED';
  if (legacy === 'SCHEMA_PENDING') return 'SCHEMA_PENDING';
  return 'READY';
}

function effectiveAuthMessage(
  scheduler?: FundamentalSchedulerStatus,
  auth?: FundamentalScreenerAuthStatus | null,
  schema?: FundamentalScreenerSchemaStatus | null,
) {
  if (auth?.message) return auth.message;
  if ((schema?.status || '').toUpperCase() === 'SCHEMA_PENDING') {
    return `Screener queue schema pending. Apply ${schema?.apply_script || 'database/fundamental/006_screener_queue.sql'}.`;
  }
  return scheduler?.pause_reason || scheduler?.last_error || null;
}

function mergeBackendLogs(current: RunLogEntry[], backendLogs?: FundamentalOperationalLog[]) {
  const next = [...current];
  const seen = new Set(next.map((entry) => `${entry.at}|${entry.level}|${entry.message}`));
  (backendLogs || []).forEach((entry) => {
    const at = entry.timestamp || new Date().toISOString();
    const level = workerLevelFromStatus(entry.status);
    const message = [
      entry.category ? `[${entry.category}]` : '',
      entry.symbol ? `${entry.symbol}` : '',
      entry.message,
    ].filter(Boolean).join(' ');
    const key = `${at}|${level}|${message}`;
    if (seen.has(key)) return;
    seen.add(key);
    next.push({ at, level, message });
  });
  return next.slice(-150);
}

function formatCountdown(seconds?: number | null) {
  if (typeof seconds !== 'number' || seconds <= 0) return '-';
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return minutes > 0 ? `${minutes}m ${remaining}s` : `${remaining}s`;
}

function describeDownloadCounts(result: Pick<FundamentalDownloadRunResponse, 'completed_count' | 'blocked_count' | 'failed_count' | 'skipped_count'>) {
  return `Downloaded ${result.completed_count}, blocked ${result.blocked_count}, failed ${result.failed_count}, skipped ${result.skipped_count}.`;
}

function isZeroProcessedDownload(result: Pick<FundamentalDownloadRunResponse, 'total_symbols' | 'completed_count' | 'blocked_count' | 'failed_count' | 'skipped_count'>) {
  return result.total_symbols === 0
    && result.completed_count === 0
    && result.blocked_count === 0
    && result.failed_count === 0
    && result.skipped_count === 0;
}

function exportRows(rows: FundamentalIngestionStatusRow[]) {
  const header = [
    'S.No',
    'Symbol',
    'Company',
    'Screener URL',
    'Current Step',
    'Download Status',
    'Download Stage',
    'Validation Stage',
    'Extraction Stage',
    'DB Stage',
    'Pipeline Stage',
    'Ingestion Status',
    'Local File Name',
    'File Size Bytes',
    'Retry Count',
    'Run ID',
    'Last Download Start',
    'Last Download End',
    'Local Folder',
    'Last Download Time',
    'Last Ingestion Time',
    'Rows Extracted',
    'Quarters',
    'Years',
    'First Year',
    'Latest Year',
    'First Quarter',
    'Latest Quarter',
    'Inserted',
    'Updated',
    'Skipped',
    'Failed',
    'Error',
  ];
  const lines = [
    header.join(','),
    ...rows.map((row, index) => [
      index + 1,
      row.symbol,
      row.company_name,
      row.screener_url,
      currentStepCell(row),
      row.download_status || 'PENDING',
      row.download_stage || '-',
      row.validation_stage || '-',
      row.extraction_stage || '-',
      row.db_stage || '-',
      row.pipeline_stage || '-',
      row.ingestion_status || row.status || 'PENDING',
      row.local_file_name || row.source_file_name,
      row.file_size_bytes,
      row.retry_count,
      row.run_id,
      row.last_download_start_time,
      row.last_download_end_time,
      row.local_folder_path,
      row.last_download_time,
      row.last_ingestion_time,
      (row.inserted_count || 0) + (row.updated_count || 0) + (row.skipped_count || 0) + (row.failed_count || 0),
      row.quarters_count,
      row.years_count,
      row.first_year,
      row.latest_year,
      row.first_quarter,
      row.latest_quarter,
      row.inserted_count,
      row.updated_count,
      row.skipped_count,
      row.failed_count,
      row.error_message,
    ].map(csvEscape).join(',')),
  ];
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'fundamental_auto_ingestion_status.csv';
  anchor.click();
  URL.revokeObjectURL(url);
}

function headingClassName(heading: string) {
  if (heading === 'Error') return 'min-w-[560px] px-4 py-4';
  if (heading === 'Action') return 'min-w-[320px] px-4 py-4';
  if (heading.endsWith('Stage')) return 'min-w-[150px] px-4 py-4';
  if (heading === 'Local File Name') return 'min-w-[220px] px-4 py-4';
  return 'px-4 py-4';
}

async function copyTextToClipboard(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', 'true');
  textarea.style.position = 'fixed';
  textarea.style.left = '-9999px';
  textarea.style.top = '0';
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  const copied = document.execCommand('copy');
  document.body.removeChild(textarea);
  if (!copied) {
    throw new Error('Clipboard copy is not available in this browser.');
  }
}

function SchedulerStrip({
  scheduler,
  auth,
  schema,
}: {
  scheduler?: FundamentalSchedulerStatus;
  auth?: FundamentalScreenerAuthStatus | null;
  schema?: FundamentalScreenerSchemaStatus | null;
}) {
  const running = scheduler?.running;
  const schedulerStatus = scheduler?.scheduler_status || (running ? 'RUNNING' : 'STOPPED');
  const downloadMode = scheduler?.download_mode === 'manual_pickup' ? 'Manual pickup' : 'Browser';
  const authStatus = effectiveAuthStatus(scheduler, auth);
  const authMessage = effectiveAuthMessage(scheduler, auth, schema);
  return (
    <section className="grid gap-3 rounded-[28px] border border-slate-200 bg-white p-4 shadow-sm lg:grid-cols-7">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Scheduler</p>
        <div className="mt-2 flex items-center gap-2">
          <span className={`inline-flex rounded-full border px-3 py-1 text-[11px] font-black uppercase tracking-[0.08em] ${schedulerStatusBadgeClass(schedulerStatus)}`}>
            {schedulerStatus}
          </span>
        </div>
      </div>
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Interval</p>
        <p className="mt-2 text-sm font-semibold text-slate-700">{scheduler?.interval_label || `${scheduler?.interval_seconds ?? 20}s`}</p>
      </div>
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Next Run</p>
        <p className="mt-2 text-sm font-semibold text-slate-700">{formatDate(scheduler?.next_run_time)}</p>
      </div>
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Download Mode</p>
        <p className="mt-2 text-sm font-semibold text-slate-700">{downloadMode}</p>
      </div>
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Last File</p>
        <p className="mt-2 truncate text-sm font-semibold text-slate-700" title={scheduler?.last_processed_file || ''}>
          {scheduler?.last_processed_file || '-'}
        </p>
      </div>
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Screener Auth</p>
        <div className="mt-2 flex items-center gap-2">
          <span className={`inline-flex rounded-full border px-3 py-1 text-[11px] font-black uppercase tracking-[0.08em] ${schedulerStatusBadgeClass(authStatus)}`}>
            {authStatus}
          </span>
        </div>
      </div>
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Uploaded Symbols</p>
        <p className="mt-2 text-sm font-semibold text-slate-700">{scheduler?.uploaded_symbols_count ?? 0}</p>
      </div>
      {authMessage ? (
        <div className="lg:col-span-7">
          <div className={`rounded-2xl border px-4 py-3 text-sm font-semibold ${
            authStatus === 'AUTHENTICATED'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
              : authStatus === 'SCHEMA_PENDING'
                ? 'border-amber-200 bg-amber-50 text-amber-900'
                : authStatus === 'AUTH_REQUIRED' || authStatus === 'VERIFYING'
                  ? 'border-sky-200 bg-sky-50 text-sky-900'
                  : 'border-slate-200 bg-slate-50 text-slate-800'
          }`}>
            {authMessage}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function FlowAndTimePanel({
  steps,
  tick,
  scheduler,
  actionLoading,
  onControlAction,
}: {
  steps: Record<FlowKey, FlowStepState>;
  tick: number;
  scheduler?: FundamentalSchedulerStatus;
  actionLoading: boolean;
  onControlAction: (action: SchedulerControlAction) => void;
}) {
  void tick;
  const schedulerStatus = scheduler?.scheduler_status || (scheduler?.running ? 'RUNNING' : 'STOPPED');
  const isPaused = schedulerStatus === 'PAUSED' || Boolean(scheduler?.queue_paused);
  const isBlocked = schedulerStatus === 'BLOCKED' || schedulerStatus === 'SESSION_REQUIRED';

  return (
    <section className="rounded-[28px] border border-sky-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="text-2xl font-black tracking-[-0.03em] text-slate-950">Flow &amp; Time</h2>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className={`inline-flex rounded-full border px-3 py-1 text-[11px] font-black uppercase tracking-[0.08em] ${schedulerStatusBadgeClass(schedulerStatus)}`}>
              {schedulerStatus}
            </span>
            <span className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-black uppercase tracking-[0.08em] text-slate-700">
              Mode {scheduler?.active_mode || 'AUTO'}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => onControlAction('start')} disabled={actionLoading}>
            Start Scheduler
          </button>
          <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => onControlAction('stop')} disabled={actionLoading}>
            Stop Scheduler
          </button>
          <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => onControlAction('pause')} disabled={actionLoading || isPaused}>
            Pause Queue
          </button>
          <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => onControlAction('resume')} disabled={actionLoading || (!isPaused && !isBlocked)}>
            Resume Queue
          </button>
          <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => onControlAction('retry-failed-queue')} disabled={actionLoading}>
            Retry Failed
          </button>
          <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => onControlAction('retry-blocked-queue')} disabled={actionLoading}>
            Retry Blocked
          </button>
          <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => onControlAction('clear-stuck')} disabled={actionLoading}>
            Clear Stuck
          </button>
          <button className="rounded-full bg-gradient-to-r from-[rgb(var(--page-accent-rgb))] to-[rgb(var(--page-accent-rgb-2))] px-4 py-2 text-sm font-bold text-white shadow-sm shadow-[rgba(59,130,246,0.16)] transition hover:brightness-110 disabled:opacity-60" type="button" onClick={() => onControlAction('force-run')} disabled={actionLoading}>
            Force Manual Run
          </button>
        </div>
      </div>
      {scheduler?.pause_reason ? (
        <div className={`mt-4 rounded-2xl border px-4 py-3 text-sm font-semibold ${isBlocked ? 'border-rose-200 bg-rose-50 text-rose-900' : 'border-amber-200 bg-amber-50 text-amber-900'}`}>
          {scheduler.pause_reason}
        </div>
      ) : null}
      <div className="mt-5 grid gap-3 lg:grid-cols-4">
        {flowSteps.map((flowStep) => {
          const state = steps[flowStep.key];
          const elapsed = elapsedForStep(state);
          return (
            <article
              key={flowStep.key}
              className={`min-h-[164px] rounded-2xl border p-4 shadow-sm transition ${flowStageClass(flowStep.key)} ${
                state.status === 'WORKING' ? 'ring-2 ring-slate-950/10' : ''
              }`}
            >
              <div className="flex h-full flex-col justify-between gap-4">
                <div>
                  <h3 className="text-sm font-black text-slate-950">{flowStep.label}</h3>
                  <span className={`mt-3 inline-flex rounded-full border px-3 py-1 text-[11px] font-black uppercase tracking-[0.08em] ${flowStatusBadgeClass(state.status)}`}>
                    {state.status}
                  </span>
                  <p className="mt-2 text-sm font-medium leading-5 text-slate-700">{state.detail || initialFlowDetail}</p>
                </div>
                <p className="text-2xl font-black tracking-[-0.04em] text-slate-950">{formatFlowElapsed(elapsed)}</p>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function createStatusFlowSteps(payload: FundamentalIngestionStatusResponse): Record<FlowKey, FlowStepState> {
  const nowIso = new Date().toISOString();
  const nowMs = Date.now();
  const pipeline = payload.pipeline || payload.scheduler.pipeline;
  const rows = payload.items || payload.rows || [];
  const upper = (value?: string | null) => (value || '').toUpperCase();
  const countRows = (predicate: (row: FundamentalIngestionStatusRow) => boolean) => rows.filter(predicate).length;
  const total = payload.summary.total_symbols || rows.length;
  const schedulerError = payload.scheduler.last_error;
  const schedulerRunning = Boolean(payload.scheduler.running);
  const RUNNING_STALE_MS = 10 * 60 * 1000;

  if (pipeline) {
    const stageStateFromWorker = (
      worker: FundamentalWorkerMetrics | undefined,
      detail: string,
      fallback: FlowStatus = 'NOT_STARTED',
    ): FlowStepState => {
      const status = (worker?.status || '').toUpperCase();
      const startedAt = worker?.last_started_at || payload.scheduler.last_run_time || nowIso;
      const endedAt = worker?.last_finished_at || payload.scheduler.last_success_time || payload.scheduler.last_run_time || nowIso;
      const elapsedMs = worker?.last_duration_ms || worker?.average_duration_ms || 0;
      let flowStatus: FlowStatus = fallback;
      if (status === 'RUNNING') flowStatus = 'WORKING';
      else if (status === 'BLOCKED') flowStatus = 'FAILED';
      else if (status === 'PAUSED') flowStatus = 'PARTIAL';
      else if (status === 'PARTIAL') flowStatus = 'PARTIAL';
      else if (status === 'COMPLETED' || status === 'SUCCESS') flowStatus = 'COMPLETED';
      else if (status === 'FAILED') flowStatus = 'FAILED';
      else if ((worker?.completed_count || 0) > 0) flowStatus = 'COMPLETED';
      else if ((worker?.failed_count || 0) > 0 || (worker?.blocked_count || 0) > 0) flowStatus = 'PARTIAL';
      return {
        status: flowStatus,
        startedAt,
        endedAt,
        elapsedMs,
        detail,
      };
    };

    const downloadDetail = [
      `Completed ${pipeline.download.completed_count || 0}`,
      `pending ${pipeline.download.pending_count || 0}`,
      `failed ${pipeline.download.failed_count || 0}`,
      `blocked ${pipeline.download.blocked_count || 0}`,
      `retry ${pipeline.download.retry_count || 0}.`,
      `Current ${pipeline.download.current_symbol || pipeline.download.last_symbol || '-'}.`,
      `Cooldown ${formatCountdown(pipeline.download.cooldown_remaining_seconds)}.`,
      pipeline.download.last_error ? `Last error: ${pipeline.download.last_error}` : '',
    ].filter(Boolean).join(' ');
    const validateDetail = [
      `Validated ${pipeline.validate.completed_count || 0}`,
      `failed ${pipeline.validate.failed_count || 0}`,
      `pending ${pipeline.validate.pending_count || 0}.`,
      `Current ${pipeline.validate.current_file || pipeline.validate.last_file || '-'}.`,
    ].filter(Boolean).join(' ');
    const insertDetail = [
      `Inserted ${pipeline.insert.completed_count || 0}`,
      `failed ${pipeline.insert.failed_count || 0}`,
      `pending ${pipeline.insert.pending_count || 0}.`,
      `Current ${pipeline.insert.current_symbol || pipeline.insert.last_symbol || '-'}.`,
    ].filter(Boolean).join(' ');
    const successDetail = [
      `Pipeline completed ${pipeline.success.completed_count || 0}`,
      `failed ${pipeline.success.failed_count || 0}`,
      `pending ${pipeline.success.pending_count || 0}.`,
      `Last ${payload.scheduler.last_processed_symbol || '-'} / ${payload.scheduler.last_processed_file || '-'}.`,
    ].filter(Boolean).join(' ');

    return {
      download: stageStateFromWorker(
        pipeline.download,
        downloadDetail,
        pipeline.download.pending_count ? 'PARTIAL' : 'NOT_STARTED',
      ),
      validate: stageStateFromWorker(
        pipeline.validate,
        validateDetail,
        pipeline.validate.pending_count ? 'PARTIAL' : 'NOT_STARTED',
      ),
      process: stageStateFromWorker(
        pipeline.insert,
        insertDetail,
        pipeline.insert.pending_count ? 'PARTIAL' : 'NOT_STARTED',
      ),
      success: stageStateFromWorker(
        pipeline.success,
        successDetail,
        pipeline.success.pending_count ? 'PARTIAL' : 'NOT_STARTED',
      ),
    };
  }

  const isFreshIso = (value?: string | null, maxAgeMs = RUNNING_STALE_MS) => {
    if (!value) return false;
    const ts = Date.parse(value);
    if (Number.isNaN(ts)) return false;
    return nowMs - ts <= maxAgeMs;
  };

  const downloadCompleted = payload.summary.download_completed ?? countRows((row) => ['SUCCESS', 'SKIPPED', 'SKIPPED_DUPLICATE'].includes(upper(row.download_status)));
  const downloadPending = payload.summary.download_pending ?? countRows((row) => ['PENDING', 'RUNNING', 'IN_PROGRESS', ''].includes(upper(row.download_status)));
  const downloadFailed = payload.summary.download_failed ?? countRows((row) => ['FAILED', 'BLOCKED'].includes(upper(row.download_status)));
  const downloadBlocked = payload.summary.download_blocked ?? countRows((row) => upper(row.download_status) === 'BLOCKED');
  const dbCompleted = payload.summary.db_ingestion_completed ?? countRows((row) => ['SUCCESS', 'SKIPPED', 'SKIPPED_DUPLICATE'].includes(upper(row.ingestion_status || row.status)));
  const dbPending = payload.summary.db_ingestion_pending ?? countRows((row) => ['PENDING', 'RUNNING', 'IN_PROGRESS', ''].includes(upper(row.ingestion_status || row.status)));
  const dbFailed = payload.summary.db_ingestion_failed ?? countRows((row) => ['FAILED', 'PARTIAL'].includes(upper(row.ingestion_status || row.status)));

  const downloadReadyRows = rows.filter((row) => ['SUCCESS', 'SKIPPED', 'SKIPPED_DUPLICATE'].includes(upper(row.download_status)));
  const validationCompleted = downloadReadyRows.filter((row) => upper(row.validation_stage) === 'VALIDATED').length;
  const validationFailed = downloadReadyRows.filter((row) => upper(row.validation_stage) === 'VALIDATION_FAILED').length;
  const validationPending = Math.max(0, downloadReadyRows.length - validationCompleted - validationFailed);
  const extractionCompleted = downloadReadyRows.filter((row) => upper(row.extraction_stage) === 'EXTRACTED').length;
  const extractionFailed = downloadReadyRows.filter((row) => upper(row.extraction_stage) === 'EXTRACTION_FAILED').length;
  const extractionPending = Math.max(0, downloadReadyRows.length - extractionCompleted - extractionFailed);
  const pipelineCompleted = countRows((row) => upper(row.pipeline_stage) === 'COMPLETED');
  const pipelineFailed = countRows((row) => upper(row.pipeline_stage) === 'FAILED');
  const pipelinePending = Math.max(0, total - pipelineCompleted - pipelineFailed);

  const runningDownload = schedulerRunning && rows.some((row) => {
    const isRunning = ['RUNNING', 'IN_PROGRESS'].includes(upper(row.download_status));
    return isRunning && isFreshIso(row.last_download_start_time || row.last_download_time);
  });
  const runningValidation = schedulerRunning && rows.some((row) => upper(row.validation_stage) === 'IN_PROGRESS');
  const runningExtraction = schedulerRunning && rows.some((row) => upper(row.extraction_stage) === 'IN_PROGRESS');
  const runningDb = schedulerRunning && rows.some((row) => {
    const isRunning = ['RUNNING', 'IN_PROGRESS'].includes(upper(row.ingestion_status || row.status));
    return isRunning && isFreshIso(row.last_ingestion_time || payload.scheduler.last_run_time);
  });
  const runningPipeline = runningDownload || runningValidation || runningExtraction || runningDb;

  const resolveStageStatus = ({
    completed,
    pending,
    failed,
    working,
    partialOnPending,
  }: {
    completed: number;
    pending: number;
    failed: number;
    working: boolean;
    partialOnPending?: boolean;
  }): FlowStatus => {
    if (working) return 'WORKING';
    if (failed > 0 && completed > 0) return 'PARTIAL';
    if (failed > 0 && pending > 0) return 'PARTIAL';
    if (failed > 0) return 'FAILED';
    if (completed > 0 && pending > 0) return partialOnPending ? 'PARTIAL' : 'COMPLETED';
    if (completed > 0) return 'COMPLETED';
    if (pending > 0) return 'NOT_STARTED';
    return 'NOT_STARTED';
  };

  const latestRow = rows.find((row) => row.symbol === payload.scheduler.last_processed_symbol) || rows[0];
  const latestSymbol = payload.scheduler.last_processed_symbol || latestRow?.symbol || '-';
  const latestFile = payload.scheduler.last_processed_file || latestRow?.local_file_name || latestRow?.source_file_name || '-';

  const downloadStatus = resolveStageStatus({
    completed: downloadCompleted,
    pending: downloadPending,
    failed: downloadFailed,
    working: runningDownload,
    partialOnPending: true,
  });
  const validateStatus = downloadReadyRows.length === 0
    ? 'NOT_STARTED'
    : resolveStageStatus({
      completed: validationCompleted,
      pending: validationPending,
      failed: validationFailed,
      working: runningValidation,
    });
  const processInputReady = validationCompleted > 0 || extractionCompleted > 0 || dbCompleted > 0;
  const processStatus = !processInputReady && !(runningDb || runningExtraction)
    ? 'NOT_STARTED'
    : resolveStageStatus({
      completed: dbCompleted,
      pending: dbPending,
      failed: dbFailed,
      working: runningDb || runningExtraction,
    });
  const successStatus: FlowStatus = runningPipeline
    ? 'WORKING'
    : pipelineFailed > 0 && pipelineCompleted > 0
      ? 'PARTIAL'
      : pipelineFailed > 0
        ? 'FAILED'
        : pipelineCompleted > 0 && pipelineCompleted < total
          ? 'PARTIAL'
          : pipelineCompleted > 0 && pipelineCompleted === total
            ? 'COMPLETED'
            : pipelinePending > 0
              ? 'NOT_STARTED'
              : 'NOT_STARTED';

  if (schedulerError && total > 0 && pipelineCompleted === 0 && !runningPipeline) {
    return {
      download: {
        status: downloadStatus === 'NOT_STARTED' ? 'FAILED' : downloadStatus,
        startedAt: payload.scheduler.last_failure_time || nowIso,
        endedAt: payload.scheduler.last_failure_time || nowIso,
        elapsedMs: 0,
        detail: schedulerError,
      },
      validate: {
        status: validateStatus,
        startedAt: payload.scheduler.last_run_time || nowIso,
        endedAt: payload.scheduler.last_failure_time || payload.scheduler.last_run_time || nowIso,
        elapsedMs: 0,
        detail: `Validated ${validationCompleted}, failed ${validationFailed}, pending ${validationPending}.`,
      },
      process: {
        status: processStatus,
        startedAt: payload.scheduler.last_run_time || nowIso,
        endedAt: payload.scheduler.last_failure_time || payload.scheduler.last_run_time || nowIso,
        elapsedMs: 0,
        detail: `DB completed ${dbCompleted}, failed ${dbFailed}, pending ${dbPending}.`,
      },
      success: {
        status: 'FAILED',
        startedAt: payload.scheduler.last_failure_time || nowIso,
        endedAt: payload.scheduler.last_failure_time || nowIso,
        elapsedMs: 0,
        detail: schedulerError,
      },
    };
  }

  return {
    download: {
      status: downloadStatus,
      startedAt: payload.scheduler.last_run_time || nowIso,
      endedAt: payload.scheduler.last_download_time || payload.scheduler.last_run_time || nowIso,
      elapsedMs: 0,
      detail: `Completed ${downloadCompleted}, pending ${downloadPending}, failed ${downloadFailed}, blocked ${downloadBlocked}. Latest ${latestFile}.`,
    },
    validate: {
      status: validateStatus,
      startedAt: payload.scheduler.last_run_time || nowIso,
      endedAt: payload.scheduler.last_run_time || nowIso,
      elapsedMs: 0,
      detail: downloadReadyRows.length === 0
        ? 'Waiting for valid downloaded workbook(s) before validation.'
        : `Validated ${validationCompleted}, failed ${validationFailed}, pending ${validationPending}.`,
    },
    process: {
      status: processStatus,
      startedAt: payload.scheduler.last_run_time || nowIso,
      endedAt: payload.scheduler.last_success_time || payload.scheduler.last_run_time || nowIso,
      elapsedMs: 0,
      detail: processInputReady
        ? `DB completed ${dbCompleted}, failed ${dbFailed}, pending ${dbPending}.`
        : 'Waiting for validation/extraction before DB insert.',
    },
    success: {
      status: successStatus,
      startedAt: payload.scheduler.last_success_time || payload.scheduler.last_run_time || nowIso,
      endedAt: payload.scheduler.last_success_time || payload.scheduler.last_run_time || nowIso,
      elapsedMs: 0,
      detail: `Pipeline completed ${pipelineCompleted}, failed ${pipelineFailed}, pending ${pipelinePending}. Latest ${latestSymbol} / ${latestFile}.`,
    },
  };
}

export function FundamentalAutoIngestion() {
  const [payload, setPayload] = useState<FundamentalIngestionStatusResponse | null>(null);
  const [localXlsxPayload, setLocalXlsxPayload] = useState<LocalXlsxFlowStatusResponse | null>(null);
  const [localXlsxLogsPayload, setLocalXlsxLogsPayload] = useState<LocalXlsxLogsResponse | null>(null);
  const [localXlsxLoading, setLocalXlsxLoading] = useState(true);
  const [localXlsxError, setLocalXlsxError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('Loading auto ingestion data extraction status...');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [manualSymbols, setManualSymbols] = useState('');
  const [uploadedSymbols, setUploadedSymbols] = useState<FundamentalUploadedScreenerSymbol[]>([]);
  const [uploadedSymbolSearch, setUploadedSymbolSearch] = useState('');
  const [selectedUploadedSymbol, setSelectedUploadedSymbol] = useState('');
  const [uploadingCsv, setUploadingCsv] = useState(false);
  const [autoProcessAfterDownload, setAutoProcessAfterDownload] = useState(true);
  const [page, setPage] = useState(1);
  const [flowState, setFlowState] = useState<Record<FlowKey, FlowStepState>>(createInitialFlowSteps);
  const [flowTick, setFlowTick] = useState(0);
  const [toast, setToast] = useState<PageToastState | null>(null);
  const [runLogs, setRunLogs] = useState<RunLogEntry[]>([]);
  const flowTimersRef = useRef<number[]>([]);
  const toastTimerRef = useRef<number | null>(null);
  const csvInputRef = useRef<HTMLInputElement | null>(null);

  const activeFlowKey = useMemo(() => {
    return flowSteps.find((step) => flowState[step.key].status === 'WORKING')?.key;
  }, [flowState]);

  const clearFlowTimers = () => {
    flowTimersRef.current.forEach((timerId) => window.clearTimeout(timerId));
    flowTimersRef.current = [];
  };

  const showToast = (nextToast: PageToastState) => {
    if (toastTimerRef.current !== null) {
      window.clearTimeout(toastTimerRef.current);
    }
    setToast(nextToast);
    toastTimerRef.current = window.setTimeout(() => {
      setToast(null);
      toastTimerRef.current = null;
    }, 4200);
  };

  const appendLog = (level: RunLogEntry['level'], messageText: string) => {
    const nextEntry: RunLogEntry = {
      at: new Date().toISOString(),
      level,
      message: messageText,
    };
    setRunLogs((current) => [...current.slice(-119), nextEntry]);
  };

  const markFlowStage = (key: FlowKey, status: FlowStatus, detail: string) => {
    const nowIso = new Date().toISOString();
    const nowMs = Date.now();
    setFlowState((current) => {
      const next = { ...current };

      flowSteps.forEach((step) => {
        const existing = current[step.key];
        next[step.key] = { ...existing };
        if (step.key !== key && existing.status === 'WORKING' && existing.startedAt) {
          const startedAt = Date.parse(existing.startedAt);
          next[step.key] = {
            ...next[step.key],
            status: 'COMPLETED',
            endedAt: nowIso,
            elapsedMs: Number.isNaN(startedAt) ? existing.elapsedMs : Math.max(0, nowMs - startedAt),
          };
        }
      });

      const currentStep = next[key];
      if (status === 'NOT_STARTED') {
        next[key] = {
          ...currentStep,
          status: 'NOT_STARTED',
          startedAt: null,
          endedAt: null,
          elapsedMs: 0,
          detail,
        };
      } else if (status === 'WORKING') {
        next[key] = {
          ...currentStep,
          status,
          startedAt: currentStep.startedAt || nowIso,
          endedAt: null,
          elapsedMs: currentStep.elapsedMs || 0,
          detail,
        };
      } else {
        const startedAt = currentStep.startedAt ? Date.parse(currentStep.startedAt) : nowMs;
        next[key] = {
          ...currentStep,
          status,
          startedAt: currentStep.startedAt || nowIso,
          endedAt: nowIso,
          elapsedMs: Number.isNaN(startedAt) ? currentStep.elapsedMs : Math.max(currentStep.elapsedMs, nowMs - startedAt),
          detail,
        };
      }

      return next;
    });
  };

  const startFlowRun = () => {
    clearFlowTimers();
    const nowIso = new Date().toISOString();
    setFlowState((current) => ({
      ...current,
      validate: {
        status: 'WORKING',
        startedAt: nowIso,
        endedAt: null,
        elapsedMs: 0,
        detail: 'Validating downloaded workbook(s) before DB insert.',
      },
      process: {
        status: 'NOT_STARTED',
        startedAt: null,
        endedAt: null,
        elapsedMs: 0,
        detail: 'Waiting for validation before DB insert.',
      },
      success: {
        status: 'NOT_STARTED',
        startedAt: null,
        endedAt: null,
        elapsedMs: 0,
        detail: initialFlowDetail,
      },
    }));
  };

  const completeFlowRun = (result: Awaited<ReturnType<typeof runFundamentalIngestionNow>>) => {
    clearFlowTimers();
    const nowIso = new Date().toISOString();
    const nowMs = Date.now();
    if (result.status === 'IDLE' || result.total_files === 0) {
      const detail = result.message || 'No Screener Excel/CSV files found in symbol folders or screener_exports.';
      setFlowState((current) => ({
        ...current,
        validate: {
          status: 'NOT_STARTED',
          startedAt: current.validate.startedAt,
          endedAt: nowIso,
          elapsedMs: current.validate.elapsedMs,
          detail: 'Download required before validation.',
        },
        process: {
          status: 'NOT_STARTED',
          startedAt: null,
          endedAt: null,
          elapsedMs: 0,
          detail: 'Validation required before DB insert.',
        },
        success: { status: 'PARTIAL', startedAt: nowIso, endedAt: nowIso, elapsedMs: 0, detail },
      }));
      return;
  }
  const successStatus: FlowStatus = result.failed_count > 0 ? 'PARTIAL' : 'COMPLETED';
  const completedFiles = result.success_count + (result.failed_count === 0 ? result.skipped_count : 0);
  const resultDetail = `Files completed ${completedFiles}, failed ${result.failed_count}, already ingested ${result.skipped_count}.`;

    setFlowState((current) => {
      const next = { ...current };
      (['download', 'validate', 'process'] as FlowKey[]).forEach((key) => {
        const step = current[key];
        const startedAt = step.startedAt ? Date.parse(step.startedAt) : nowMs;
        next[key] = {
          ...step,
          status: step.status === 'FAILED' ? 'FAILED' : 'COMPLETED',
          startedAt: step.startedAt || nowIso,
          endedAt: step.endedAt || nowIso,
          elapsedMs: Number.isNaN(startedAt) ? step.elapsedMs : Math.max(step.elapsedMs, nowMs - startedAt),
          detail: step.detail === initialFlowDetail ? 'Completed.' : step.detail,
        };
      });
      next.success = {
        status: successStatus,
        startedAt: nowIso,
        endedAt: nowIso,
        elapsedMs: 0,
        detail: result.latest_processed_symbol || result.latest_processed_file ? `${resultDetail} Latest ${result.latest_processed_symbol || result.latest_processed_file}.` : resultDetail,
      };
      return next;
    });
  };

  const failFlowRun = (detail: string) => {
    clearFlowTimers();
    const failingKey = activeFlowKey || 'process';
    markFlowStage(failingKey, 'FAILED', detail || 'Ingestion failed.');
  };

  const loadStatus = async (signal?: AbortSignal, options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setError(null);
      setLoading(true);
    }
    try {
      const response = await fetchFundamentalIngestionStatus(signal);
      const items = response.items || response.rows || [];
      const normalizedResponse: FundamentalIngestionStatusResponse = {
        ...response,
        items,
      };
      setError(null);
      setPayload(normalizedResponse);
      setFlowState(createStatusFlowSteps(normalizedResponse));
      setRunLogs((current) => mergeBackendLogs(current, response.logs || response.scheduler.logs));
      setMessage(items.length ? 'Auto ingestion data extraction status loaded from Oracle.' : 'No symbols loaded yet. Import Nifty50 symbols first.');
    } catch (err) {
      if (signal?.aborted) return;
      const loadError = err instanceof Error ? err.message : 'Unable to load ingestion status.';
      setError(loadError);
      if (!options?.silent) {
        setPayload(null);
        setMessage('Unable to load status. Verify Oracle scripts and backend health.');
        appendLog('ERROR', `Status refresh failed: ${loadError}`);
        showToast({
          title: 'Status load failed',
          detail: loadError,
          tone: 'danger',
        });
      }
    } finally {
      if (!signal?.aborted && !options?.silent) {
        setLoading(false);
      }
    }
  };

  const loadUploadedSymbols = async (signal?: AbortSignal, options?: { silent?: boolean }) => {
    try {
      const symbols = await fetchUploadedScreenerSymbols(signal);
      setUploadedSymbols(symbols);
      setSelectedUploadedSymbol((current) => {
        if (current && symbols.some((item) => item.symbol === current)) return current;
        return current ? current : '';
      });
    } catch (err) {
      if (signal?.aborted) return;
      const loadError = err instanceof Error ? err.message : 'Unable to load uploaded Screener symbols.';
      if (!options?.silent) {
        appendLog('ERROR', `Uploaded symbol load failed: ${loadError}`);
      }
    }
  };

  const loadLocalXlsxStatus = async (signal?: AbortSignal, options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setLocalXlsxLoading(true);
      setLocalXlsxError(null);
    }
    try {
      const [statusPayload, logsPayload] = await Promise.all([
        fetchLocalXlsxStatus(signal),
        fetchLocalXlsxLogs(200, signal),
      ]);
      setLocalXlsxPayload(statusPayload);
      setLocalXlsxLogsPayload(logsPayload);
      setLocalXlsxError(null);
    } catch (err) {
      if (signal?.aborted) return;
      const loadError = err instanceof Error ? err.message : 'Unable to load local XLSX status.';
      setLocalXlsxError(loadError);
      if (!options?.silent) {
        appendLog('ERROR', `[local_xlsx] status load failed: ${loadError}`);
      }
    } finally {
      if (!signal?.aborted && !options?.silent) {
        setLocalXlsxLoading(false);
      }
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    loadStatus(controller.signal);
    void loadLocalXlsxStatus(controller.signal);
    void loadUploadedSymbols(controller.signal, { silent: true });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (actionLoading) return undefined;
    let disposed = false;
    let inFlight = false;
    const timerId = window.setInterval(() => {
      if (disposed || inFlight || document.hidden) return;
      inFlight = true;
      void Promise.all([
        loadStatus(undefined, { silent: true }),
        loadLocalXlsxStatus(undefined, { silent: true }),
        loadUploadedSymbols(undefined, { silent: true }),
      ]).finally(() => {
        inFlight = false;
      });
    }, 8000);
    return () => {
      disposed = true;
      window.clearInterval(timerId);
    };
  }, [actionLoading]);

  useEffect(() => {
    if (!activeFlowKey) return undefined;
    const timerId = window.setInterval(() => {
      setFlowTick((current) => current + 1);
    }, 250);
    return () => window.clearInterval(timerId);
  }, [activeFlowKey]);

  useEffect(() => {
    return () => {
      clearFlowTimers();
      if (toastTimerRef.current !== null) {
        window.clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

  const filteredRows = useMemo(() => {
    const query = search.trim().toUpperCase();
    return (payload?.items || []).filter((row) => {
      const symbolMatch = !query || row.symbol.toUpperCase().includes(query) || (row.company_name || '').toUpperCase().includes(query);
      const statusMatch = !status
        || (row.status || '').toUpperCase() === status
        || (row.download_status || '').toUpperCase() === status
        || (row.ingestion_status || '').toUpperCase() === status;
      return symbolMatch && statusMatch;
    });
  }, [payload?.items, search, status]);

  const filteredUploadedSymbols = useMemo(() => {
    return uploadedSymbols.filter((item) => matchesUploadedSymbol(item, uploadedSymbolSearch));
  }, [uploadedSymbols, uploadedSymbolSearch]);

  const maxPage = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
  const pageRows = filteredRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const localIngestionPayload = localXlsxPayload;
  const localXlsxSummary = localXlsxPayload?.summary;
  const localXlsxCounts = localXlsxPayload?.counts;
  const localStatus = (localIngestionPayload?.status || 'IDLE').toUpperCase();
  const localProcessingActive = ['RUNNING', 'VALIDATING', 'EXTRACTING', 'INSERTING', 'PROCESSING'].includes(localStatus)
    || (localXlsxSummary?.processing_count || 0) > 0;
  const manualSuccessCount = localXlsxCounts?.success || 0;
  const manualFailedCount = localXlsxCounts?.failed || 0;
  const manualProcessedCount = localXlsxCounts?.processed || 0;
  const manualPendingCount = localXlsxCounts?.pending || 0;
  const manualTotalCount = localXlsxCounts?.total || 0;
  const localSummaryCards = [
    { label: 'Schema Status', value: localIngestionPayload?.schema_status || '-' },
    { label: 'Flow Status', value: localIngestionPayload?.status || '-' },
    { label: 'Total Files', value: numberCell(localXlsxCounts?.total) },
    { label: 'Pending', value: numberCell(localXlsxCounts?.pending) },
    { label: 'Processed', value: numberCell(localXlsxCounts?.processed) },
    { label: 'Success Files', value: numberCell(localXlsxCounts?.success) },
    { label: 'Failed Files', value: numberCell(localXlsxCounts?.failed) },
  ];
  const manualPipelineSteps = ['Run', 'Validate / Extract', 'Process / Insert', 'Success'];
  const manualPipelineCountCards = [
    { label: 'Success Files', value: numberCell(manualSuccessCount) },
    { label: 'Failed Count', value: numberCell(manualFailedCount) },
    { label: 'Processed Count', value: numberCell(manualProcessedCount) },
    { label: 'Pending Count', value: numberCell(manualPendingCount) },
    { label: 'Total Count', value: numberCell(manualTotalCount) },
  ];

  const manualSymbolList = () => {
    const symbols = parseSymbolsOverride(manualSymbols);
    return symbols.length ? symbols : undefined;
  };

  const applySelectedUploadedSymbol = (symbol: string) => {
    setSelectedUploadedSymbol(symbol);
    setManualSymbols(symbol);
    appendLog('INFO', `Selected uploaded symbol ${symbol} for manual run.`);
  };

  const triggerCsvUpload = () => {
    csvInputRef.current?.click();
  };

  const handleCsvUploadChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setUploadingCsv(true);
    setActionLoading(true);
    setError(null);
    appendLog('INFO', `CSV upload started: ${file.name}.`);
    try {
      const result = await uploadScreenerSymbolsCsv(file);
      await loadUploadedSymbols(undefined, { silent: true });
      await loadStatus(undefined, { silent: true });
      const detail = `CSV uploaded: ${result.inserted_rows} inserted, ${result.duplicate_skipped_rows} duplicates skipped, ${result.invalid_rows} invalid.`;
      setMessage(detail);
      showToast({
        title: 'CSV uploaded',
        detail,
        tone: result.invalid_rows || result.duplicate_skipped_rows ? 'warn' : 'success',
      });
      appendLog(
        result.invalid_rows || result.duplicate_skipped_rows ? 'WARN' : 'INFO',
        `CSV upload finished. total_rows=${result.total_rows}, inserted_rows=${result.inserted_rows}, duplicate_rows=${result.duplicate_skipped_rows}, invalid_rows=${result.invalid_rows}.`,
      );
      if (result.inserted_rows > 0 && !selectedUploadedSymbol && result.errors?.length !== result.total_rows) {
        const firstInserted = (await fetchUploadedScreenerSymbols()).find((item) => item.active_flag === 'Y');
        if (firstInserted) {
          setSelectedUploadedSymbol(firstInserted.symbol);
        }
      }
    } catch (err) {
      const uploadError = err instanceof Error ? err.message : 'CSV upload failed.';
      setError(uploadError);
      appendLog('ERROR', `CSV upload failed: ${uploadError}`);
      showToast({ title: 'CSV upload failed', detail: uploadError, tone: 'danger' });
    } finally {
      setUploadingCsv(false);
      setActionLoading(false);
    }
  };

  const runSelectedUploadedSymbol = async () => {
    const symbol = selectedUploadedSymbol || manualSymbolList()?.[0];
    if (!symbol) {
      showToast({ title: 'No symbol selected', detail: 'Select a symbol from Uploaded Symbols before running manual ingestion.', tone: 'warn' });
      return;
    }
    setActionLoading(true);
    setError(null);
    appendLog('INFO', `Manual selected-symbol run started: ${symbol}.`);
    try {
      const result = await manualRunUploadedScreenerSymbols([symbol], 1);
      await loadStatus(undefined, { silent: true });
      const detail = `Queued ${result.enqueued_count ?? 0} manual job(s) for ${symbol}.`;
      setMessage(detail);
      showToast({ title: 'Run selected symbol', detail, tone: 'success' });
      appendLog('INFO', `Manual selected-symbol run queued for ${symbol}. enqueued=${result.enqueued_count ?? 0}.`);
    } catch (err) {
      const runError = err instanceof Error ? err.message : 'Manual selected-symbol run failed.';
      setError(runError);
      appendLog('ERROR', `Manual selected-symbol run failed: ${runError}`);
      showToast({ title: 'Manual run failed', detail: runError, tone: 'danger' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleResumeAfterLogin = async () => {
    const symbol = selectedUploadedSymbol || manualSymbolList()?.[0];
    setActionLoading(true);
    setError(null);
    appendLog('INFO', `Verify-login/resume started. symbol=${symbol || 'AUTO'}.`);
    try {
      const result = await resumeAfterScreenerLogin(symbol);
      await loadStatus(undefined, { silent: true });
      const detail = result.message
        || (result.session_ready
          ? `Screener authentication verified. Requeued ${result.reenqueued_count ?? 0} blocked job(s).`
          : (result.last_error || 'Screener login is still not verified. Please complete login in the opened browser and retry.'));
      setMessage(detail);
      showToast({
        title: result.session_ready
          ? (result.status === 'SCHEMA_PENDING' ? 'DB script required' : 'Screener authentication verified')
          : 'Screener login not verified',
        detail,
        tone: result.status === 'SCHEMA_PENDING' ? 'warn' : result.session_ready ? 'success' : 'warn',
      });
      appendLog(result.session_ready ? 'INFO' : 'WARN', `Verify-login/resume finished. ${detail}`);
    } catch (err) {
      const resumeError = err instanceof Error ? err.message : 'Verify Login / Resume failed.';
      setError(resumeError);
      appendLog('ERROR', `Verify-login/resume failed: ${resumeError}`);
      showToast({ title: 'Verify Login / Resume failed', detail: resumeError, tone: 'danger' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleOpenScreenerLogin = async () => {
    const symbol = selectedUploadedSymbol || manualSymbolList()?.[0];
    setActionLoading(true);
    setError(null);
    appendLog('INFO', `Screener login browser open requested. symbol=${symbol || 'AUTO'}.`);
    try {
      const result = await openScreenerLoginBrowser(symbol);
      const detail = result.message || 'Login browser opened. Complete Screener login, then click Verify Login / Resume.';
      setMessage(detail);
      showToast({
        title: 'Screener login opened',
        detail,
        tone: 'info',
      });
      appendLog('INFO', `Screener login browser opened. symbol=${result.symbol || symbol || 'AUTO'}.`);
    } catch (err) {
      const loginError = err instanceof Error ? err.message : 'Unable to open Screener login browser.';
      setError(loginError);
      appendLog('ERROR', `Screener login browser open failed: ${loginError}`);
      showToast({ title: 'Screener login failed', detail: loginError, tone: 'danger' });
    } finally {
      setActionLoading(false);
    }
  };

  const runManualScreenerStage = async (stage: 'prepare' | 'download' | 'validate' | 'process' | 'refresh') => {
    setActionLoading(true);
    setError(null);
    const symbols = manualSymbolList();
    const failMissing = Boolean(symbols?.length);
    appendLog('INFO', `Manual stage started: ${stage}. symbols=${symbols?.join(',') || 'AUTO'}.`);
    try {
      if (stage === 'prepare') {
        const result = await importNifty50Symbols();
        const detail = `Prepared ${result.inserted_count} symbol(s), skipped ${result.skipped_count}, failed ${result.failed_count}.`;
        setMessage(`Manual Screener prepare completed: ${detail}`);
        showToast({ title: 'Prepare completed', detail, tone: result.failed_count ? 'warn' : 'success' });
        appendLog('INFO', `Prepare completed. ${detail}`);
      } else if (stage === 'download') {
        clearFlowTimers();
        setFlowState({
          ...createInitialFlowSteps(),
          download: {
            status: 'WORKING',
            startedAt: new Date().toISOString(),
            endedAt: null,
            elapsedMs: 0,
            detail: symbols?.length
              ? `Downloading Screener workbook for ${symbols.join(', ')}.`
              : 'Downloading pending Screener workbooks.',
          },
        });
        const download = await runScreenerDownloadNow(symbols?.length ? 'selected' : 'pending', symbols);
        const downloadStatus = batchFlowStatus(download.status, download.failed_count + download.blocked_count);
        markFlowStage('download', downloadStatus, download.message);
        const validatedSymbols = (download.items || [])
          .filter((item) => ['SUCCESS', 'SKIPPED', 'SKIPPED_DUPLICATE'].includes((item.status || item.download_status || '').toUpperCase()))
          .map((item) => item.symbol);
        const zeroProcessed = isZeroProcessedDownload(download);
        const countDetail = describeDownloadCounts(download);

        if (autoProcessAfterDownload && validatedSymbols.length) {
          markFlowStage('validate', 'WORKING', 'Validating downloaded Screener workbook(s).');
          const validation = await validateScreenerFilesNow(validatedSymbols, false);
          markFlowStage('validate', batchFlowStatus(validation.status, validation.failed_count), validation.message);
          markFlowStage('process', 'WORKING', 'Inserting parsed Screener rows into Oracle.');
          const ingestion = await runFundamentalIngestionNow(validatedSymbols, false);
          markFlowStage('process', batchFlowStatus(ingestion.status, ingestion.failed_count), ingestion.message);
          markFlowStage('success', batchFlowStatus(ingestion.status, ingestion.failed_count), `Download ${download.completed_count}, validation ${validation.success_count}, ingestion ${ingestion.success_count}.`);
          setMessage(`Manual download + insert completed. ${ingestion.message}`);
          showToast({
            title: 'Download + insert completed',
            detail: `Downloaded ${download.completed_count}, validated ${validation.success_count}, inserted/updated ${ingestion.success_count}, failed ${ingestion.failed_count}.`,
            tone: download.failed_count || download.blocked_count || validation.failed_count || ingestion.failed_count ? 'warn' : 'success',
          });
          appendLog(
            download.failed_count || download.blocked_count || validation.failed_count || ingestion.failed_count ? 'WARN' : 'INFO',
            `Download+insert completed. download_completed=${download.completed_count}, blocked=${download.blocked_count}, failed=${download.failed_count}, validation_failed=${validation.failed_count}, db_failed=${ingestion.failed_count}.`,
          );
        } else if (zeroProcessed) {
          const detail = download.message || 'No symbols were processed. Please import symbols or select symbols first.';
          markFlowStage('success', 'PARTIAL', detail);
          setMessage(detail);
          showToast({
            title: 'No symbols processed',
            detail,
            tone: 'warn',
          });
          appendLog('WARN', `Download stage idle: ${detail}`);
        } else {
          const detail = autoProcessAfterDownload
            ? `${download.message || countDetail} No validated downloaded symbol available for insert. Place XLSX file manually or run successful download first.`
            : download.message || countDetail;
          markFlowStage('success', download.failed_count || download.blocked_count ? 'PARTIAL' : 'COMPLETED', detail);
          setMessage(autoProcessAfterDownload ? detail : `Manual download completed: ${detail}`);
          showToast({
            title: autoProcessAfterDownload ? 'Download finished without insert' : 'Download completed',
            detail,
            tone: download.failed_count || download.blocked_count || !validatedSymbols.length ? 'warn' : 'success',
          });
          appendLog(
            download.failed_count || download.blocked_count || !validatedSymbols.length ? 'WARN' : 'INFO',
            `Download stage finished. completed=${download.completed_count}, blocked=${download.blocked_count}, failed=${download.failed_count}, latest=${download.latest_processed_symbol || '-'}.`,
          );
        }
      } else if (stage === 'validate') {
        clearFlowTimers();
        const hasCompletedDownloads = (payload?.summary.download_completed || 0) > 0;
        setFlowState({
          ...createInitialFlowSteps(),
          download: {
            status: hasCompletedDownloads ? 'COMPLETED' : 'NOT_STARTED',
            startedAt: new Date().toISOString(),
            endedAt: new Date().toISOString(),
            elapsedMs: 0,
            detail: hasCompletedDownloads
              ? 'Using completed download(s) for validation.'
              : 'Download required before validation.',
          },
          validate: {
            status: 'WORKING',
            startedAt: new Date().toISOString(),
            endedAt: null,
            elapsedMs: 0,
            detail: 'Extracting and validating local Screener workbook(s).',
          },
        });
        const validation = await validateScreenerFilesNow(symbols, failMissing);
        markFlowStage('validate', batchFlowStatus(validation.status, validation.failed_count), validation.message);
        markFlowStage('success', batchFlowStatus(validation.status, validation.failed_count), `Validated ${validation.success_count}, skipped ${validation.skipped_count}, failed ${validation.failed_count}.`);
        setMessage(`Manual extract/validate completed: ${validation.message}`);
        showToast({
          title: 'Extract / Validate completed',
          detail: validation.message,
          tone: validation.failed_count ? 'warn' : validation.status === 'IDLE' ? 'info' : 'success',
        });
        appendLog(
          validation.failed_count ? 'WARN' : 'INFO',
          `Validate stage completed. success=${validation.success_count}, failed=${validation.failed_count}, skipped=${validation.skipped_count}.`,
        );
      } else if (stage === 'process') {
        startFlowRun();
        const ingestion = await runFundamentalIngestionNow(symbols, failMissing);
        completeFlowRun(ingestion);
        setMessage(`Manual insert/process completed: ${ingestion.message}`);
        showToast({
          title: 'Insert / Process completed',
          detail: ingestion.message,
          tone: ingestion.failed_count ? 'warn' : ingestion.status === 'IDLE' ? 'info' : 'success',
        });
        appendLog(
          ingestion.failed_count ? 'WARN' : 'INFO',
          `Insert/process completed. success=${ingestion.success_count}, failed=${ingestion.failed_count}, skipped=${ingestion.skipped_count}.`,
        );
      } else {
        await Promise.all([
          loadStatus(),
          loadLocalXlsxStatus(),
        ]);
        showToast({ title: 'Status refreshed', detail: 'Manual Screener status reloaded.', tone: 'info' });
        appendLog('INFO', 'Manual refresh completed.');
        return;
      }
      await Promise.all([
        loadStatus(),
        loadLocalXlsxStatus(undefined, { silent: true }),
      ]);
    } catch (err) {
      const actionError = err instanceof Error ? err.message : 'Manual Screener action failed.';
      if (stage !== 'prepare' && stage !== 'refresh') {
        failFlowRun(actionError);
      }
      setError(actionError);
      appendLog('ERROR', `Manual stage failed: ${stage}. ${actionError}`);
      showToast({ title: 'Manual Screener action failed', detail: actionError, tone: 'danger' });
    } finally {
      setActionLoading(false);
    }
  };

  const runSchedulerControlAction = async (action: SchedulerControlAction) => {
    if (action === 'clear-stuck' && !window.confirm('Clear stale RUNNING jobs and move them back to retry/failed state?')) {
      return;
    }
    setActionLoading(true);
    setError(null);
    appendLog('INFO', `Scheduler control started: ${action}.`);
    try {
      let response: FundamentalSchedulerActionResponse;
      if (action === 'start') {
        response = await startFundamentalScheduler() as FundamentalSchedulerActionResponse;
      } else if (action === 'stop') {
        response = await stopFundamentalScheduler() as FundamentalSchedulerActionResponse;
      } else if (action === 'pause') {
        response = await pauseFundamentalScheduler();
      } else if (action === 'resume') {
        response = await resumeFundamentalScheduler();
      } else if (action === 'retry-failed-queue') {
        response = await retryFailedFundamentalQueue();
      } else if (action === 'retry-blocked-queue') {
        response = await retryBlockedFundamentalQueue();
      } else if (action === 'clear-stuck') {
        response = await clearStuckFundamentalQueue();
      } else {
        const symbols = manualSymbolList();
        response = await forceRunFundamentalQueue(symbols, symbols?.length);
      }

      const detailByAction: Record<SchedulerControlAction, string> = {
        start: response.status === 'SCHEMA_PENDING'
          ? (response.last_error || 'Screener queue schema pending.')
          : response.status === 'AUTH_REQUIRED'
            ? (response.message || response.last_error || 'Screener authentication verification is required before queue controls can run.')
            : response.status === 'READY_EMPTY'
              ? (response.message || 'No pending Screener jobs found. Queue prepared for 0 job(s).')
              : `Scheduler ${response.scheduler_status || (response.running ? 'RUNNING' : 'STOPPED')}. Interval ${response.interval_label || `${response.interval_seconds ?? 20}s`}.`,
        stop: 'Background scheduler stopped safely.',
        pause: response.pause_reason || 'Queue paused safely.',
        resume: response.pause_reason || 'Queue resumed.',
        'retry-failed-queue': `Queued ${response.enqueued_count ?? 0} failed job(s) for retry.`,
        'retry-blocked-queue': `Queued ${response.enqueued_count ?? 0} blocked job(s) for retry.`,
        'clear-stuck': `Recovered ${response.recovered_count ?? 0} stuck job(s).`,
        'force-run': response.status === 'SCHEMA_PENDING'
          ? (response.last_error || 'Screener queue schema pending.')
          : response.status === 'AUTH_REQUIRED'
            ? (response.message || response.last_error || 'Screener authentication verification is required before queue controls can run.')
            : response.status === 'READY_EMPTY'
              ? (response.message || 'No pending Screener jobs found. Queue prepared for 0 job(s).')
              : `Manual queue run prepared for ${response.enqueued_count ?? response.symbols?.length ?? 0} job(s).`,
      };
      const titleByAction: Record<SchedulerControlAction, string> = {
        start: 'Scheduler started',
        stop: 'Scheduler stopped',
        pause: 'Queue paused',
        resume: 'Queue resumed',
        'retry-failed-queue': 'Failed jobs queued',
        'retry-blocked-queue': 'Blocked jobs queued',
        'clear-stuck': 'Stuck jobs cleared',
        'force-run': 'Manual run queued',
      };
      const tone: ToastTone = response.status === 'SCHEMA_PENDING' || response.status === 'AUTH_REQUIRED'
        ? 'warn'
        : action === 'stop'
        ? 'info'
        : action === 'pause' || response.scheduler_status === 'BLOCKED' || response.scheduler_status === 'SESSION_REQUIRED'
          ? 'warn'
          : 'success';

      setPayload((current) => current ? { ...current, scheduler: { ...current.scheduler, ...response } } : current);
      setMessage(detailByAction[action]);
      showToast({
        title: titleByAction[action],
        detail: detailByAction[action],
        tone,
      });
      appendLog(workerLevelFromStatus(response.scheduler_status || response.status), `${titleByAction[action]}. ${detailByAction[action]}`);
      await Promise.all([
        loadStatus(undefined, { silent: true }),
        loadLocalXlsxStatus(undefined, { silent: true }),
      ]);
    } catch (err) {
      const actionError = err instanceof Error ? err.message : 'Scheduler control failed.';
      setError(actionError);
      appendLog('ERROR', `Scheduler control failed: ${action}. ${actionError}`);
      showToast({ title: 'Scheduler control failed', detail: actionError, tone: 'danger' });
    } finally {
      setActionLoading(false);
    }
  };

  const runAction = async (action: 'import' | 'download' | 'run' | 'full' | 'retry') => {
    setActionLoading(true);
    setError(null);
    appendLog('INFO', `Action started: ${action}.`);
    try {
      if (action === 'import') {
        const result = await importNifty50Symbols();
        const detail = `Inserted ${result.inserted_count}, skipped ${result.skipped_count}, failed ${result.failed_count}.`;
        setMessage(`Nifty50 import completed: ${detail}`);
        showToast({ title: 'Nifty50 import completed', detail, tone: result.failed_count ? 'warn' : 'success' });
        appendLog('INFO', `Import completed. ${detail}`);
      } else if (action === 'download') {
        clearFlowTimers();
        setFlowState({
          ...createInitialFlowSteps(),
          download: {
            status: 'WORKING',
            startedAt: new Date().toISOString(),
            endedAt: null,
            elapsedMs: 0,
            detail: 'Opening Screener and downloading Excel exports one symbol at a time.',
          },
        });
        const result = await runScreenerDownloadNow('pending');
        clearFlowTimers();
        const downloadStageStatus: Exclude<FlowStatus, 'NOT_STARTED'> = result.status === 'SUCCESS'
          ? 'COMPLETED'
          : result.status === 'PARTIAL'
            ? 'PARTIAL'
            : result.status === 'IDLE'
              ? 'PARTIAL'
              : 'FAILED';
        const countDetail = `${describeDownloadCounts(result)} Latest ${result.latest_processed_symbol || '-'}.`;
        const zeroProcessed = isZeroProcessedDownload(result);
        markFlowStage('download', downloadStageStatus, result.message || countDetail);
        if (zeroProcessed) {
          const detail = result.message || 'No symbols were processed. Please import symbols or select symbols first.';
          setMessage(detail);
          showToast({ title: 'No symbols processed', detail, tone: 'warn' });
          appendLog('WARN', `Download action idle. ${detail}`);
        } else {
          const downloadCompleted = result.status === 'SUCCESS';
          const downloadPartial = result.status === 'PARTIAL';
          const statusPrefix = downloadCompleted ? 'Download completed' : downloadPartial ? 'Download partial' : 'Download not completed';
          setMessage(`${statusPrefix}: ${countDetail}`);
          showToast({
            title: result.status === 'SCHEMA_PENDING' ? 'DB script required' : downloadCompleted ? 'Download completed' : downloadPartial ? 'Download partial' : 'Download blocked',
            detail: result.message || countDetail,
            tone: downloadCompleted && !result.failed_count && !result.blocked_count ? 'success' : 'warn',
          });
          appendLog(
            downloadCompleted && !result.failed_count && !result.blocked_count ? 'INFO' : 'WARN',
            `Download action finished. completed=${result.completed_count}, blocked=${result.blocked_count}, failed=${result.failed_count}.`,
          );
        }
      } else if (action === 'run') {
        startFlowRun();
        const result = await runFundamentalIngestionNow();
        completeFlowRun(result);
        const noFiles = result.status === 'IDLE' || result.total_files === 0;
      const detail = noFiles
        ? result.message || 'No Screener Excel/CSV files found in symbol folders or screener_exports.'
        : `Files completed ${result.success_count + (result.failed_count === 0 ? result.skipped_count : 0)}, failed ${result.failed_count}, already ingested ${result.skipped_count}. Latest ${result.latest_processed_symbol || result.latest_processed_file || '-'}.`;
        setMessage(noFiles ? `Ingestion skipped: ${detail}` : `Ingestion completed: ${detail}`);
        showToast({ title: noFiles ? 'No Screener files found' : 'DB ingestion completed', detail, tone: noFiles || result.failed_count ? 'warn' : 'success' });
        appendLog(noFiles || result.failed_count ? 'WARN' : 'INFO', `DB ingestion action finished. ${detail}`);
      } else if (action === 'full') {
        clearFlowTimers();
        setFlowState({
          ...createInitialFlowSteps(),
          download: {
            status: 'WORKING',
            startedAt: new Date().toISOString(),
            endedAt: null,
            elapsedMs: 0,
            detail: 'Downloading, validating, extracting, and upserting Screener workbooks.',
          },
        });
        const result = await runFundamentalFullAutoNow('pending');
        const download = result.download;
        const validation = result.validation;
        const ingestion = result.ingestion;
        const zeroProcessed = isZeroProcessedDownload(download);
        const downloadFlowStatus: Exclude<FlowStatus, 'NOT_STARTED'> = zeroProcessed
          ? 'PARTIAL'
          : download.status === 'SUCCESS'
            ? 'COMPLETED'
            : download.status === 'PARTIAL'
              ? 'PARTIAL'
              : 'FAILED';
        markFlowStage('download', downloadFlowStatus, download.message);
        if (validation && validation.total_files > 0) {
          markFlowStage('validate', batchFlowStatus(validation.status, validation.failed_count), validation.message);
        } else {
          markFlowStage('validate', 'NOT_STARTED', 'Download required before validation.');
        }
        if (ingestion.total_files > 0) {
          markFlowStage('process', ingestion.failed_count ? 'PARTIAL' : 'COMPLETED', ingestion.message);
          markFlowStage('success', ingestion.failed_count ? 'PARTIAL' : 'COMPLETED', `Inserted/updated files ${ingestion.success_count}, skipped ${ingestion.skipped_count}, failed ${ingestion.failed_count}.`);
        } else {
          markFlowStage('process', 'NOT_STARTED', 'Validation required before DB insert.');
          markFlowStage('success', 'PARTIAL', zeroProcessed ? (download.message || ingestion.message) : (ingestion.message || download.message));
        }
        const detail = `${describeDownloadCounts(download)} ingestion success ${ingestion.success_count}, failed ${ingestion.failed_count}, skipped ${ingestion.skipped_count}. Last ${download.latest_processed_symbol || ingestion.latest_processed_symbol || '-'}.`;
        const fullAutoMessage = zeroProcessed ? (ingestion.message || download.message) : `Full auto ingestion finished: ${detail}`;
        setMessage(fullAutoMessage);
        showToast({
          title: zeroProcessed ? 'Full auto skipped' : 'Full auto ingestion finished',
          detail: zeroProcessed ? (ingestion.message || download.message || 'No files downloaded. Ingestion skipped.') : detail,
          tone: zeroProcessed || download.failed_count || download.blocked_count || ingestion.failed_count ? 'warn' : 'success',
        });
        appendLog(
          zeroProcessed || download.failed_count || download.blocked_count || ingestion.failed_count ? 'WARN' : 'INFO',
          `Full auto finished. download_completed=${download.completed_count}, blocked=${download.blocked_count}, failed=${download.failed_count}, db_failed=${ingestion.failed_count}.`,
        );
      } else if (action === 'retry') {
        const result = await retryFailedFundamental();
        const download = result.download;
        const ingestion = result.ingestion;
        const detail = `${result.message} ${download ? describeDownloadCounts(download) : 'Downloaded 0, blocked 0, failed 0, skipped 0.'} ingestion success ${ingestion?.success_count ?? 0}, failed ${ingestion?.failed_count ?? 0}, skipped ${ingestion?.skipped_count ?? 0}.`;
        const idleRetry = result.status === 'IDLE' && !download && !ingestion;
        setMessage(idleRetry ? 'Retry skipped: no failed or pending symbols required processing.' : `Retry failed completed: ${detail}`);
        showToast({
          title: idleRetry ? 'Retry skipped' : 'Retry failed completed',
          detail: idleRetry ? 'No failed or pending symbols required processing.' : detail,
          tone: idleRetry || (download?.failed_count || download?.blocked_count || ingestion?.failed_count) ? 'warn' : 'success',
        });
        appendLog(
          idleRetry || (download?.failed_count || download?.blocked_count || ingestion?.failed_count) ? 'WARN' : 'INFO',
          `Retry completed. ${detail}`,
        );
      }
      await Promise.all([
        loadStatus(),
        loadLocalXlsxStatus(undefined, { silent: true }),
      ]);
    } catch (err) {
      const actionError = err instanceof Error ? err.message : 'Action failed.';
      if (action === 'run' || action === 'download' || action === 'full') {
        failFlowRun(actionError);
      }
      setError(actionError);
      appendLog('ERROR', `Action failed: ${action}. ${actionError}`);
      showToast({ title: 'Action failed', detail: actionError, tone: 'danger' });
    } finally {
      setActionLoading(false);
    }
  };

  const runRowAction = async (row: FundamentalIngestionStatusRow, action: 'download' | 'ingest' | 'retry') => {
    setActionLoading(true);
    setError(null);
    appendLog('INFO', `Row action started: ${row.symbol} -> ${action}.`);
    try {
      if (action === 'download') {
        const result = await runScreenerDownloadNow('selected', [row.symbol]);
        const zeroProcessed = isZeroProcessedDownload(result);
        const detail = `${describeDownloadCounts(result)} Last symbol: ${result.latest_processed_symbol || row.symbol}.`;
        setMessage(
          zeroProcessed
            ? `${row.symbol} download skipped. ${result.message || 'No symbols were processed.'}`
            : `${row.symbol} download action finished. ${detail}`,
        );
        showToast({
          title: zeroProcessed ? `${row.symbol} not processed` : result.blocked_count ? `${row.symbol} blocked` : `${row.symbol} download finished`,
          detail: result.message || detail,
          tone: zeroProcessed || result.failed_count || result.blocked_count ? 'warn' : 'success',
        });
        appendLog(
          zeroProcessed || result.failed_count || result.blocked_count ? 'WARN' : 'INFO',
          `${row.symbol} download action finished. ${result.message || detail}`,
        );
      } else if (action === 'ingest') {
        const result = await runFundamentalIngestionNow([row.symbol], true);
        const detail = `Ingestion completed: inserted/updated files ${result.success_count}, skipped ${result.skipped_count}, failed ${result.failed_count}.`;
        setMessage(`${row.symbol} ingestion action finished. ${detail}`);
        showToast({
          title: `${row.symbol} ingestion finished`,
          detail: result.message || detail,
          tone: result.failed_count ? 'warn' : 'success',
        });
        appendLog(result.failed_count ? 'WARN' : 'INFO', `${row.symbol} ingestion action finished. ${result.message || detail}`);
      } else {
        const result = await runFundamentalFullAutoNow('selected', [row.symbol]);
        const zeroProcessed = isZeroProcessedDownload(result.download);
        const detail = `${describeDownloadCounts(result.download)} ingestion success ${result.ingestion.success_count}, failed ${result.ingestion.failed_count}, skipped ${result.ingestion.skipped_count}.`;
        setMessage(
          zeroProcessed
            ? `${row.symbol} retry skipped. ${result.ingestion.message || result.download.message || 'No files downloaded. Ingestion skipped.'}`
            : `${row.symbol} retry finished. ${detail}`,
        );
        showToast({
          title: zeroProcessed ? `${row.symbol} retry skipped` : `${row.symbol} retry finished`,
          detail: zeroProcessed ? (result.ingestion.message || result.download.message || 'No files downloaded. Ingestion skipped.') : detail,
          tone: zeroProcessed || result.download.failed_count || result.download.blocked_count || result.ingestion.failed_count ? 'warn' : 'success',
        });
        appendLog(
          zeroProcessed || result.download.failed_count || result.download.blocked_count || result.ingestion.failed_count ? 'WARN' : 'INFO',
          `${row.symbol} retry action finished. ${zeroProcessed ? (result.ingestion.message || result.download.message || 'No files downloaded. Ingestion skipped.') : detail}`,
        );
      }
      await Promise.all([
        loadStatus(),
        loadLocalXlsxStatus(undefined, { silent: true }),
      ]);
    } catch (err) {
      const actionError = err instanceof Error ? err.message : 'Row action failed.';
      setError(actionError);
      appendLog('ERROR', `${row.symbol} row action failed: ${action}. ${actionError}`);
      showToast({ title: `${row.symbol} action failed`, detail: actionError, tone: 'danger' });
    } finally {
      setActionLoading(false);
    }
  };

  const copyErrorMessage = async (row: FundamentalIngestionStatusRow) => {
    const errorMessage = row.error_message?.trim();
    if (!errorMessage) return;

    try {
      await copyTextToClipboard(errorMessage);
      showToast({
        title: `${row.symbol} error copied`,
        detail: 'Full error message copied to clipboard.',
        tone: 'success',
      });
    } catch (err) {
      const copyError = err instanceof Error ? err.message : 'Unable to copy error message.';
      setError(copyError);
      showToast({
        title: 'Copy failed',
        detail: copyError,
        tone: 'danger',
      });
    }
  };

  const copyRunLogs = async () => {
    const latestRow = (payload?.items || payload?.rows || [])[0];
    const latestStep = latestRow ? currentStepCell(latestRow) : '-';
    const headerLines = [
      `run_id=${latestRow?.run_id || '-'}`,
      `symbol=${latestRow?.symbol || '-'}`,
      `step=${latestStep || '-'}`,
      `download_status=${latestRow?.download_status || '-'}`,
      `validation_stage=${latestRow?.validation_stage || '-'}`,
      `extraction_stage=${latestRow?.extraction_stage || '-'}`,
      `db_stage=${latestRow?.db_stage || '-'}`,
      `error=${latestRow?.error_message || latestRow?.download_error_message || latestRow?.ingestion_error_message || '-'}`,
    ];
    const lines = runLogs.length
      ? runLogs.map((entry) => `[${formatDate(entry.at)}] ${entry.level}: ${entry.message}`)
      : ['No operational logs recorded yet.'];
    const payloadText = [...headerLines, ...lines].join('\n');
    try {
      await copyTextToClipboard(payloadText);
      showToast({ title: 'Logs copied', detail: 'Latest logs copied to clipboard.', tone: 'success' });
      appendLog('INFO', 'Logs copied to clipboard.');
    } catch (err) {
      const copyError = err instanceof Error ? err.message : 'Unable to copy logs.';
      setError(copyError);
      appendLog('ERROR', `Log copy failed: ${copyError}`);
      showToast({ title: 'Copy failed', detail: copyError, tone: 'danger' });
    }
  };

  const runLocalXlsxFlow = async (action: 'scan' | 'run') => {
    setActionLoading(true);
    setError(null);
    appendLog('INFO', `[local_xlsx] action started: ${action}.`);
    try {
      const result = action === 'scan' ? await scanLocalXlsxFiles() : await processLocalXlsxFiles();
      const detail = `Total ${result.counts?.total ?? 0}, pending ${result.counts?.pending ?? 0}, processed ${result.counts?.processed ?? 0}, success ${result.counts?.success ?? 0}, failed ${result.counts?.failed ?? 0}.`;
      const title = action === 'scan' ? 'Local XLSX scan completed' : 'Local XLSX ingestion completed';
      setMessage(`${title}: ${result.message || detail}`);
      showToast({ title, detail: result.message || detail, tone: (result.counts?.failed || 0) > 0 ? 'warn' : 'success' });
      appendLog((result.counts?.failed || 0) > 0 ? 'WARN' : 'INFO', `[local_xlsx] ${title}. ${detail}`);
      await Promise.all([
        loadStatus(undefined, { silent: true }),
        loadLocalXlsxStatus(undefined, { silent: true }),
      ]);
    } catch (err) {
      const actionError = err instanceof Error ? err.message : 'Local XLSX action failed.';
      setError(actionError);
      appendLog('ERROR', `[local_xlsx] action failed: ${action}. ${actionError}`);
      showToast({ title: 'Local XLSX action failed', detail: actionError, tone: 'danger' });
    } finally {
      setActionLoading(false);
    }
  };

  const copyLocalXlsxLogs = async () => {
    const counts = localXlsxPayload?.counts;
    const headerLines = [
      `flow=${localXlsxPayload?.flow || 'LOCAL_XLSX_AUTO_INGESTION'}`,
      `schema_status=${localXlsxPayload?.schema_status || '-'}`,
      `status=${localXlsxPayload?.status || '-'}`,
      `source_dir=${localXlsxPayload?.source_dir || '-'}`,
      `output_dir=${localXlsxPayload?.output_dir || '-'}`,
      `total=${counts?.total ?? 0}`,
      `pending=${counts?.pending ?? 0}`,
      `processed=${counts?.processed ?? 0}`,
      `success=${counts?.success ?? 0}`,
      `failed=${counts?.failed ?? 0}`,
      `message=${localXlsxPayload?.message || '-'}`,
    ];
    const logLines = (localXlsxLogsPayload?.items || []).length
      ? (localXlsxLogsPayload?.items || []).map(
        (entry) => `[${formatDate(entry.timestamp)}] ${entry.status}/${entry.stage} ${entry.file_name || '-'} ${entry.symbol || '-'} ${entry.message}`,
      )
      : ['No local XLSX logs recorded yet.'];
    const text = [...headerLines, ...logLines].join('\n');
    try {
      await copyTextToClipboard(text);
      showToast({ title: 'Local XLSX logs copied', detail: 'Local ingestion logs copied to clipboard.', tone: 'success' });
      appendLog('INFO', '[local_xlsx] logs copied to clipboard.');
    } catch (err) {
      const copyError = err instanceof Error ? err.message : 'Unable to copy local XLSX logs.';
      setError(copyError);
      appendLog('ERROR', `[local_xlsx] log copy failed: ${copyError}`);
      showToast({ title: 'Copy failed', detail: copyError, tone: 'danger' });
    }
  };

  return (
    <FundamentalModulePage
      title="Auto Ingestion"
      description="Track uploaded Screener symbols, Excel downloads, scheduler health, queue status, source files, and per-symbol ingestion completion from one operational surface."
      actions={
        <div className="flex flex-wrap gap-2">
          <input
            ref={csvInputRef}
            accept=".csv,text/csv"
            className="hidden"
            type="file"
            onChange={handleCsvUploadChange}
          />
          <button
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
            type="button"
            onClick={() => {
              void Promise.all([loadStatus(), loadLocalXlsxStatus()]);
            }}
            disabled={loading || actionLoading}
          >
            <FundamentalRefreshIcon className="h-4 w-4" />
            Refresh
          </button>
          <button
            className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
            type="button"
            onClick={triggerCsvUpload}
            disabled={loading || actionLoading || uploadingCsv}
          >
            Upload CSV
          </button>
          <button
            className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
            type="button"
            onClick={runSelectedUploadedSymbol}
            disabled={loading || actionLoading || !(selectedUploadedSymbol || manualSymbols.trim())}
          >
            Run Selected Symbol
          </button>
          <button
            className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
            type="button"
            onClick={handleOpenScreenerLogin}
            disabled={loading || actionLoading}
          >
            Open Screener Login
          </button>
          <button
            className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
            type="button"
            onClick={handleResumeAfterLogin}
            disabled={loading || actionLoading}
          >
            Verify Login / Resume
          </button>
          <button
            aria-label="Copy logs"
            className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
            type="button"
            title="Copy logs"
            onClick={copyRunLogs}
            disabled={loading || actionLoading}
          >
            <FundamentalCopyIcon className="h-4 w-4" />
          </button>
          <button
            className="rounded-full bg-gradient-to-r from-[rgb(var(--page-accent-rgb))] to-[rgb(var(--page-accent-rgb-2))] px-4 py-2 text-sm font-bold text-white shadow-sm shadow-[rgba(59,130,246,0.16)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
            type="button"
            onClick={() => runAction('run')}
            disabled={loading || actionLoading}
          >
            Run DB Ingestion
          </button>
        </div>
      }
    >
      {toast ? (
        <div className="fixed right-5 top-5 z-50 w-[min(380px,calc(100vw-2.5rem))]" role="status" aria-live="polite">
          <div className={`rounded-2xl border px-5 py-4 shadow-xl ${toastClass(toast.tone)}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-black">{toast.title}</p>
                <p className="mt-1 text-sm font-semibold leading-5 opacity-85">{toast.detail}</p>
              </div>
              <button
                aria-label="Close notification"
                className="shrink-0 rounded-full border border-current/15 px-2 py-0.5 text-xs font-black opacity-70 transition hover:opacity-100"
                type="button"
                onClick={() => setToast(null)}
              >
                X
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <SchedulerStrip scheduler={payload?.scheduler} auth={payload?.auth || payload?.scheduler?.auth} schema={payload?.schema || payload?.scheduler?.schema} />
      <FlowAndTimePanel
        steps={flowState}
        tick={flowTick}
        scheduler={payload?.scheduler}
        actionLoading={actionLoading}
        onControlAction={runSchedulerControlAction}
      />

      <section className="rounded-[28px] border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <FundamentalShieldIcon className="h-4 w-4 text-slate-500" />
            <span className="text-sm font-bold text-slate-950">Admin Logs</span>
          </div>
          <button
            aria-label="Copy logs"
            className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
            title="Copy logs"
            type="button"
            onClick={copyRunLogs}
            disabled={actionLoading}
          >
            <FundamentalCopyIcon className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-3 grid gap-2 text-xs text-slate-700 md:grid-cols-2">
          <p><span className="font-bold text-slate-900">Run ID:</span> {(payload?.items?.[0] || payload?.rows?.[0])?.run_id || '-'}</p>
          <p><span className="font-bold text-slate-900">Symbol:</span> {(payload?.items?.[0] || payload?.rows?.[0])?.symbol || '-'}</p>
          <p><span className="font-bold text-slate-900">Step:</span> {(payload?.items?.[0] || payload?.rows?.[0]) ? currentStepCell((payload?.items?.[0] || payload?.rows?.[0]) as FundamentalIngestionStatusRow) : '-'}</p>
          <p><span className="font-bold text-slate-900">Auth Mode:</span> {payload?.scheduler?.download_mode || '-'}</p>
          <p className="md:col-span-2"><span className="font-bold text-slate-900">Last Error:</span> {(payload?.items?.[0] || payload?.rows?.[0])?.error_message || payload?.scheduler?.last_error || '-'}</p>
        </div>
        <div className="mt-3 max-h-52 overflow-auto rounded-xl border border-slate-100 bg-slate-50 p-3">
          {runLogs.length ? (
            <ul className="space-y-1 text-xs text-slate-700">
              {runLogs.slice().reverse().slice(0, 40).map((entry, index) => (
                <li key={`${entry.at}-${index}`} className="whitespace-pre-wrap break-words">
                  <span className="font-semibold text-slate-900">{formatDate(entry.at)}</span>
                  <span className="ml-2 font-black">{entry.level}</span>
                  <span className="ml-2">{entry.message}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-slate-500">No logs yet.</p>
          )}
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map((card) => {
          const value = payload?.summary?.[card.key];
          return (
            <div key={card.key} className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">{card.label}</p>
              <p className="mt-3 text-2xl font-black tracking-[-0.04em] text-slate-950">
                {card.date ? formatDate(value as string | null | undefined) : numberCell(value as number | undefined)}
              </p>
            </div>
          );
        })}
      </section>

      <section className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Manual XLSX Auto-Ingestion</p>
            <p className="mt-1 text-sm text-slate-700">
              Source: {localIngestionPayload?.source_dir || localXlsxSummary?.inbox_dir || '-'} | Output: {localIngestionPayload?.output_dir || localXlsxSummary?.output_root_dir || '-'}
            </p>
            {localXlsxLoading ? <p className="mt-1 text-sm font-semibold text-slate-600">Loading local XLSX ingestion status...</p> : null}
            {!localXlsxLoading && localXlsxError ? <p className="mt-1 text-sm font-semibold text-rose-700">{localXlsxError}</p> : null}
            {!localXlsxLoading && !localXlsxError && localIngestionPayload?.schema_status === 'SCHEMA_PENDING' ? (
              <p className="mt-1 text-sm font-semibold text-amber-700">Local XLSX ingestion schema missing. Apply database/fundamental/007_screener_local_xlsx_ingestion.sql first.</p>
            ) : null}
            {!localXlsxLoading && !localXlsxError && localIngestionPayload?.schema_status !== 'SCHEMA_PENDING' && (localXlsxCounts?.total || 0) === 0 ? (
              <p className="mt-1 text-sm font-semibold text-slate-600">No local XLSX files found in {localIngestionPayload?.source_dir || 'configured inbox folder'}.</p>
            ) : null}
            {!localXlsxLoading && !localXlsxError && localIngestionPayload?.message ? (
              <p className="mt-1 text-sm font-semibold text-slate-700">{localIngestionPayload.message}</p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60"
              type="button"
              onClick={() => {
                void runLocalXlsxFlow('run');
              }}
              disabled={actionLoading || localProcessingActive}
            >
              {localProcessingActive ? 'Processing running...' : 'Run Local XLSX Ingestion'}
            </button>
            <button
              className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60"
              type="button"
              onClick={() => {
                void loadLocalXlsxStatus();
              }}
              disabled={actionLoading || localXlsxLoading}
            >
              Refresh Local XLSX Status
            </button>
            <button
              className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60"
              type="button"
              onClick={() => {
                void runLocalXlsxFlow('scan');
              }}
              disabled={actionLoading}
            >
              Scan Local XLSX Files
            </button>
            <button
              className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60"
              type="button"
              onClick={copyLocalXlsxLogs}
              disabled={actionLoading}
            >
              Copy Local XLSX Logs
            </button>
          </div>
        </div>
        <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Manual XLSX Pipeline</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {manualPipelineSteps.map((step, index) => (
              <div key={step} className="flex items-center gap-2">
                <span className="inline-flex rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-black uppercase tracking-[0.08em] text-slate-700">
                  {step}
                </span>
                {index < manualPipelineSteps.length - 1 ? <span className="text-xs font-black text-slate-400">{'>'}</span> : null}
              </div>
            ))}
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            {manualPipelineCountCards.map((card) => (
              <div key={card.label} className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-[11px] font-bold uppercase tracking-[0.08em] text-slate-500">{card.label}</p>
                <p className="mt-1 text-lg font-black text-slate-950">{card.value}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {localSummaryCards.map((card) => (
          <div key={card.label} className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">{card.label}</p>
            <p className="mt-3 text-sm font-black text-slate-950 break-words">{card.value}</p>
          </div>
        ))}
      </section>

      <section className="rounded-[28px] border border-slate-200 bg-white p-4 shadow-sm">
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-black text-slate-800">Uploaded Symbols</p>
                  <p className="mt-1 text-sm text-slate-600">
                    Unique symbols are loaded from Oracle and used for polite one-by-one Screener exports.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <DataBadge tone={uploadedSymbols.length ? 'success' : 'warn'}>
                    {uploadedSymbols.length} symbol{uploadedSymbols.length === 1 ? '' : 's'}
                  </DataBadge>
                  <button
                    className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60"
                    type="button"
                    onClick={triggerCsvUpload}
                    disabled={actionLoading || uploadingCsv}
                  >
                    Upload CSV
                  </button>
                </div>
              </div>
              <div className="mt-3 grid gap-3 lg:grid-cols-[1fr_220px_auto_auto]">
                <input
                  className="h-10 rounded-full border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-slate-500"
                  value={uploadedSymbolSearch}
                  onChange={(event) => setUploadedSymbolSearch(event.target.value)}
                  placeholder="Search uploaded symbol"
                  type="search"
                />
                <select
                  className="h-10 rounded-full border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 outline-none transition focus:border-slate-500"
                  value={selectedUploadedSymbol}
                  onChange={(event) => applySelectedUploadedSymbol(event.target.value)}
                >
                  <option value="">Select symbol</option>
                  {filteredUploadedSymbols.map((item) => (
                    <option key={item.symbol} value={item.symbol}>{item.symbol}</option>
                  ))}
                </select>
                <button
                  className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60"
                  type="button"
                  onClick={runSelectedUploadedSymbol}
                  disabled={actionLoading || !(selectedUploadedSymbol || manualSymbols.trim())}
                >
                  Run Selected Symbol
                </button>
                <button
                  className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60"
                  type="button"
                  onClick={handleOpenScreenerLogin}
                  disabled={actionLoading}
                >
                  Open Screener Login
                </button>
                <button
                  className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60"
                  type="button"
                  onClick={handleResumeAfterLogin}
                  disabled={actionLoading}
                >
                  Verify Login / Resume
                </button>
              </div>
              <div className="mt-3 max-h-40 overflow-auto rounded-2xl border border-slate-200 bg-white p-3">
                {filteredUploadedSymbols.length ? (
                  <div className="flex flex-wrap gap-2">
                    {filteredUploadedSymbols.map((item) => (
                      <button
                        key={item.symbol}
                        className={`rounded-full border px-3 py-1.5 text-xs font-black transition ${
                          selectedUploadedSymbol === item.symbol
                            ? 'border-[rgb(var(--page-accent-rgb)/0.18)] bg-[rgb(var(--page-accent-rgb)/0.12)] text-text'
                            : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:text-slate-950'
                        }`}
                        type="button"
                        onClick={() => applySelectedUploadedSymbol(item.symbol)}
                      >
                        {item.symbol}
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm font-semibold text-slate-500">No symbols uploaded yet. Upload CSV to start.</p>
                )}
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
              <p className="text-sm font-black text-slate-800">Auto Ingestion Snapshot</p>
              <div className="mt-3 grid gap-3 text-sm text-slate-700 sm:grid-cols-2">
                <div>
                  <p className="text-[11px] font-black uppercase tracking-[0.08em] text-slate-400">Current Symbol</p>
                  <p className="mt-1 font-semibold text-slate-900">{payload?.scheduler?.workers?.download?.current_symbol || payload?.scheduler?.last_processed_symbol || '-'}</p>
                </div>
                <div>
                  <p className="text-[11px] font-black uppercase tracking-[0.08em] text-slate-400">Cooldown</p>
                  <p className="mt-1 font-semibold text-slate-900">{formatCountdown(payload?.pipeline?.download?.cooldown_remaining_seconds)}</p>
                </div>
                <div>
                  <p className="text-[11px] font-black uppercase tracking-[0.08em] text-slate-400">Screener Auth</p>
                  <p className="mt-1 font-semibold text-slate-900">{effectiveAuthStatus(payload?.scheduler, payload?.auth || payload?.scheduler?.auth)}</p>
                </div>
                <div>
                  <p className="text-[11px] font-black uppercase tracking-[0.08em] text-slate-400">Last File</p>
                  <p className="mt-1 truncate font-semibold text-slate-900" title={payload?.scheduler?.last_processed_file || ''}>{payload?.scheduler?.last_processed_file || '-'}</p>
                </div>
              </div>
            </div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
            <label className="text-sm font-black text-slate-800" htmlFor="screenerManualSymbols">Symbols Override</label>
            <div className="mt-2 flex flex-col gap-3 lg:flex-row lg:items-center">
              <input
                id="screenerManualSymbols"
                className="h-10 min-w-[260px] flex-1 rounded-full border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-slate-500"
                value={manualSymbols}
                onChange={(event) => setManualSymbols(event.target.value)}
                placeholder="Optional comma-separated symbols, e.g. RELIANCE,TCS"
                type="text"
              />
              <label className="inline-flex items-center gap-2 text-sm font-bold text-slate-700">
                <input
                  className="h-4 w-4 rounded border-slate-300 text-indigo-600"
                  checked={autoProcessAfterDownload}
                  onChange={(event) => setAutoProcessAfterDownload(event.target.checked)}
                  type="checkbox"
                />
                Auto validate &amp; insert after download
              </label>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => runManualScreenerStage('prepare')} disabled={actionLoading}>
                Prepare
              </button>
              <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => runManualScreenerStage('download')} disabled={actionLoading}>
                Download
              </button>
              <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => runManualScreenerStage('validate')} disabled={actionLoading}>
                Extract / Validate
              </button>
              <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => runManualScreenerStage('process')} disabled={actionLoading}>
                Insert / Process
              </button>
              <button className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => runManualScreenerStage('refresh')} disabled={actionLoading || loading}>
                <FundamentalRefreshIcon className="h-4 w-4" />
                Refresh
              </button>
            </div>
          </div>
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Extraction Controls</p>
            <p className="mt-1 text-sm text-slate-600">{message}</p>
            {error ? <p className="mt-2 text-sm font-semibold text-rose-700">{error}</p> : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <input
              className="h-10 min-w-[180px] rounded-full border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 outline-none transition placeholder:text-slate-400 focus:border-slate-400"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              placeholder="Search symbol"
              type="search"
            />
            <select
              className="h-10 rounded-full border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 outline-none transition focus:border-slate-400"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setPage(1);
              }}
            >
              <option value="">All status</option>
              <option value="SUCCESS">Success</option>
              <option value="PENDING">Pending</option>
              <option value="RUNNING">Running</option>
              <option value="IN_PROGRESS">In Progress</option>
              <option value="FAILED">Failed</option>
              <option value="BLOCKED">Blocked</option>
              <option value="PARTIAL">Partial</option>
              <option value="SKIPPED">Skipped</option>
              <option value="SKIPPED_DUPLICATE">Skipped Duplicate</option>
            </select>
            <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => runAction('import')} disabled={actionLoading}>
              Import Nifty50 CSV
            </button>
            <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => runAction('download')} disabled={actionLoading}>
              Download XLSX
            </button>
            <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => runAction('run')} disabled={actionLoading}>
              Run DB Ingestion
            </button>
            <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => runAction('full')} disabled={actionLoading}>
              Full Auto Ingestion
            </button>
            <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => runAction('retry')} disabled={actionLoading}>
              Retry Failed
            </button>
            <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => runSchedulerControlAction('start')} disabled={actionLoading}>
              Start Scheduler
            </button>
            <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => runSchedulerControlAction('stop')} disabled={actionLoading}>
              Stop Scheduler
            </button>
            <button className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:opacity-60" type="button" onClick={() => exportRows(filteredRows)} disabled={!filteredRows.length}>
              Export CSV
            </button>
          </div>
        </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-4">
          <div className="flex items-center gap-2">
            <FundamentalShieldIcon className="h-4 w-4 text-slate-500" />
            <span className="text-sm font-bold text-slate-950">Symbol-wise ingestion status</span>
          </div>
          <DataBadge tone={error ? 'danger' : loading ? 'warn' : 'success'}>
            {loading ? 'Loading' : error ? 'Error' : `${filteredRows.length} rows`}
          </DataBadge>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-[3200px] w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-[0.14em] text-slate-500">
              <tr>
                {[
                  'S.No',
                  'Symbol',
                  'Company',
                  'Screener URL',
                  'Current Step',
                  'Download Status',
                  'Download Stage',
                  'Validation Stage',
                  'Extraction Stage',
                  'DB Stage',
                  'Pipeline Stage',
                  'Ingestion Status',
                  'Local File Name',
                  'File Size',
                  'Retry Count',
                  'Run ID',
                  'Last Download Start',
                  'Last Download End',
                  'Last Download',
                  'Last Ingestion',
                  'Rows Extracted',
                  'Quarters',
                  'Years',
                  'First FY',
                  'Latest FY',
                  'First Quarter',
                  'Latest Quarter',
                  'Inserted',
                  'Updated',
                  'Skipped',
                  'Failed',
                  'Error',
                  'Action',
                ].map((heading) => (
                  <th key={heading} className={headingClassName(heading)}>{heading}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td className="px-4 py-8 text-center text-slate-500" colSpan={36}>Loading ingestion status...</td></tr>
              ) : null}
              {!loading && !pageRows.length ? (
                <tr><td className="px-4 py-8 text-center text-slate-500" colSpan={36}>No ingestion status rows found.</td></tr>
              ) : null}
              {!loading && pageRows.map((row, rowIndex) => (
                <tr key={`${row.symbol}-${row.index_name}`} className="border-t border-slate-100">
                  <td className="px-4 py-4 text-slate-500">{(page - 1) * PAGE_SIZE + rowIndex + 1}</td>
                  <td className="px-4 py-4 font-black text-slate-950">{row.symbol}</td>
                  <td className="max-w-[220px] truncate px-4 py-4 text-slate-700" title={row.company_name || ''}>{row.company_name || '-'}</td>
                  <td className="max-w-[280px] truncate px-4 py-4 text-slate-700" title={row.screener_url || ''}>
                    {row.screener_url ? <a className="font-semibold text-indigo-700 hover:text-indigo-900" href={row.screener_url} target="_blank" rel="noreferrer">Open</a> : '-'}
                  </td>
                  <td className="px-4 py-4"><DataBadge tone={statusTone(currentStepCell(row))}>{currentStepCell(row)}</DataBadge></td>
                  <td className="px-4 py-4"><DataBadge tone={statusTone(row.download_status || undefined)}>{row.download_status || 'PENDING'}</DataBadge></td>
                  <td className="px-4 py-4"><DataBadge tone={statusTone(row.download_stage || undefined)}>{row.download_stage || '-'}</DataBadge></td>
                  <td className="px-4 py-4"><DataBadge tone={statusTone(row.validation_stage || undefined)}>{row.validation_stage || '-'}</DataBadge></td>
                  <td className="px-4 py-4"><DataBadge tone={statusTone(row.extraction_stage || undefined)}>{row.extraction_stage || '-'}</DataBadge></td>
                  <td className="px-4 py-4"><DataBadge tone={statusTone(row.db_stage || undefined)}>{row.db_stage || '-'}</DataBadge></td>
                  <td className="px-4 py-4"><DataBadge tone={statusTone(row.pipeline_stage || undefined)}>{row.pipeline_stage || '-'}</DataBadge></td>
                  <td className="px-4 py-4"><DataBadge tone={statusTone(row.ingestion_status || row.status)}>{row.ingestion_status || row.status || 'PENDING'}</DataBadge></td>
                  <td className="max-w-[240px] truncate px-4 py-4 text-slate-700" title={row.local_file_name || row.source_file_name || ''}>{row.local_file_name || row.source_file_name || '-'}</td>
                  <td className="px-4 py-4 text-slate-700">{fileSizeCell(row.file_size_bytes)}</td>
                  <td className="px-4 py-4 text-slate-700">{numberCell(row.retry_count)}</td>
                  <td className="px-4 py-4 text-slate-700">{row.run_id || '-'}</td>
                  <td className="px-4 py-4 text-slate-700">{formatDate(row.last_download_start_time)}</td>
                  <td className="px-4 py-4 text-slate-700">{formatDate(row.last_download_end_time)}</td>
                  <td className="px-4 py-4 text-slate-700">{formatDate(row.last_download_time)}</td>
                  <td className="px-4 py-4 text-slate-700">{formatDate(row.last_ingestion_time)}</td>
                  <td className="px-4 py-4 text-slate-700">{numberCell((row.inserted_count || 0) + (row.updated_count || 0) + (row.skipped_count || 0) + (row.failed_count || 0))}</td>
                  <td className="px-4 py-4 text-slate-700">{numberCell(row.quarters_count)}</td>
                  <td className="px-4 py-4 text-slate-700">{numberCell(row.years_count)}</td>
                  <td className="px-4 py-4 text-slate-700">{row.first_year || '-'}</td>
                  <td className="px-4 py-4 text-slate-700">{row.latest_year || '-'}</td>
                  <td className="px-4 py-4 text-slate-700">{row.first_quarter || '-'}</td>
                  <td className="px-4 py-4 text-slate-700">{row.latest_quarter || '-'}</td>
                  <td className="px-4 py-4 text-slate-700">{numberCell(row.inserted_count)}</td>
                  <td className="px-4 py-4 text-slate-700">{numberCell(row.updated_count)}</td>
                  <td className="px-4 py-4 text-slate-700">{numberCell(row.skipped_count)}</td>
                  <td className="px-4 py-4 text-slate-700">{numberCell(row.failed_count)}</td>
                <td className="min-w-[560px] max-w-[680px] px-4 py-4 align-top text-slate-700">
                  {row.error_message ? (
                    <div className="flex items-start gap-2">
                      <p
                        className="min-w-0 flex-1 whitespace-pre-wrap break-words pr-1 text-sm font-medium leading-5 text-slate-700 selection:bg-indigo-100"
                      >
                        {row.error_message}
                        </p>
                        <button
                          aria-label={`Copy ${row.symbol} error message`}
                          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 transition hover:border-slate-300 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
                          title="Copy full error message"
                          type="button"
                          onClick={() => copyErrorMessage(row)}
                          disabled={actionLoading}
                        >
                          <FundamentalCopyIcon className="h-4 w-4" />
                        </button>
                      </div>
                    ) : (
                      <span className="text-slate-500">-</span>
                    )}
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex min-w-[300px] flex-wrap gap-1.5">
                      <button className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-black text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-50" type="button" disabled={actionLoading} onClick={() => runRowAction(row, 'download')}>
                        Download XLSX
                      </button>
                      <button className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-black text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-50" type="button" disabled={actionLoading} onClick={() => runRowAction(row, 'ingest')}>
                        Run DB Ingestion
                      </button>
                      <button className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-black text-slate-700 transition hover:border-slate-300 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-50" type="button" disabled={actionLoading} onClick={() => runRowAction(row, 'retry')}>
                        Retry
                      </button>
                      <a className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-black text-slate-700 transition hover:border-slate-300 hover:text-slate-950" href={`/api/fundamental/data/${encodeURIComponent(row.symbol)}`} target="_blank" rel="noreferrer">
                        View Data
                      </a>
                      <button className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-black text-slate-400" type="button" disabled title="Opening a Windows folder directly is not supported from this browser UI.">
                        Open Folder
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-4 py-4 text-sm text-slate-600">
          <span>Page {page} of {maxPage}</span>
          <div className="flex gap-2">
            <button className="rounded-full border border-slate-200 px-4 py-2 font-bold disabled:cursor-not-allowed disabled:opacity-50" type="button" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page <= 1}>
              Prev
            </button>
            <button className="rounded-full border border-slate-200 px-4 py-2 font-bold disabled:cursor-not-allowed disabled:opacity-50" type="button" onClick={() => setPage((current) => Math.min(maxPage, current + 1))} disabled={page >= maxPage}>
              Next
            </button>
          </div>
        </div>
      </section>
    </FundamentalModulePage>
  );
}
