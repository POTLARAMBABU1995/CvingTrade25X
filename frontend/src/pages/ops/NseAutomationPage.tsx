import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { AppDataTable, type AppDataTableColumn } from '../../components/app/AppDataTable';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { Toast } from '../../components/ui/Toast';
import { legacyApiGet, legacyApiPost } from '../../api/client';
import {
  buildNseAutomationView,
  formatCellByKind,
  getNestedDataRecord,
  pickField,
  safeLegacyText,
  type NseAutomationView,
  type NseAutomationRowView,
  type UnknownRecord,
} from '../../adapters/databasePageAdapter';
import { OpsPageShell } from './OpsPageShell';
import { ActionButton, KpiGrid, PageHero, SelectField, TextField } from './opsPageHelpers';
import { TradingDayVerificationPanel } from './TradingDayVerificationPanel';
import { StrategyToolbar, type StrategyToolbarStatus } from '../../components/strategy/StrategyToolbar';
import type { NseAutomationPageConfig } from './nseAutomationConfigs';
import { marketClosedReason, previousMarketWorkingDateIso } from '../../utils/marketCalendar';

type LoadStatus = 'error' | 'loading' | 'online';
type ExtractionMode = '' | 'AUTOMATION' | 'MANUAL';
type FlowKey = 'download' | 'process' | 'success' | 'validate';

const flowKeys: FlowKey[] = ['download', 'validate', 'process', 'success'];

type FlowStepState = {
  detail?: string;
  elapsedMs: number;
  endedAt?: string;
  startedAt?: string;
  status: string;
};

type ProgressState = {
  current: number | null;
  percent: number | null;
  total: number | null;
};

type ToastTone = 'danger' | 'info' | 'success' | 'warn';

type ToastState = {
  description: string;
  title: string;
  tone: ToastTone;
};

const NSE_ACTIVE_JOB_STORAGE_PREFIX = 'ct_nse_automation_active_job';
const NSE_JOB_POLL_MS = 5000;

export function shouldAutoContinueAfterDownload(autoInsert: boolean, _symbols: string): boolean {
  return autoInsert;
}

function createInitialFlow(): Record<FlowKey, FlowStepState> {
  return {
    download: { elapsedMs: 0, status: 'NOT_STARTED' },
    process: { elapsedMs: 0, status: 'NOT_STARTED' },
    success: { elapsedMs: 0, status: 'NOT_STARTED' },
    validate: { elapsedMs: 0, status: 'NOT_STARTED' },
  };
}

function todayIso(): string {
  return previousMarketWorkingDateIso();
}

function yearFromDateText(value: string): number | null {
  const text = String(value || '').trim();
  if (!text) return null;
  const iso = text.match(/\b(\d{4})-\d{2}-\d{2}\b/);
  if (iso) return Number(iso[1]);
  const legacy = text.match(/\b\d{2}-\d{2}-(\d{4})\b/);
  if (legacy) return Number(legacy[1]);
  const anyYear = text.match(/\b(20\d{2}|19\d{2})\b/);
  if (anyYear) return Number(anyYear[1]);
  return null;
}

function resolveVerificationYear(...values: string[]): number {
  for (const value of values) {
    const year = yearFromDateText(value);
    if (year && Number.isFinite(year)) return year;
  }
  return new Date().getFullYear();
}

function resolveEndpoint(config: NseAutomationPageConfig, action: 'download' | 'init' | 'process' | 'validate') {
  return `${config.endpointBase}/${action}`;
}

function payloadStatus(payload: UnknownRecord): string {
  return safeLegacyText(pickField(payload, ['status', 'STATUS', 'state']), 'RUNNING').toUpperCase();
}

function terminalStatus(status: string): boolean {
  return [
    'ALREADY_EXISTS',
    'CANCELLED',
    'COMPLETED',
    'DONE',
    'ERROR',
    'FAILED',
    'FAILURE',
    'NO_ACTION',
    'PARTIAL',
    'SKIPPED',
    'SUCCESS',
    'SUCCEEDED',
    'TIMED_OUT',
  ].includes(status.toUpperCase());
}

export function resolveNseAutomationJobId(payload: UnknownRecord): string {
  return safeLegacyText(pickField(payload, ['jobId', 'job_id', 'id', 'runId', 'run_id']), '');
}

export function isNseAutomationJobActive(payload: UnknownRecord): boolean {
  const jobId = resolveNseAutomationJobId(payload);
  const statusText = safeLegacyText(pickField(payload, ['status', 'STATUS', 'state']), '').toUpperCase();
  return Boolean(jobId && statusText && !terminalStatus(statusText));
}

export function nseAutomationActiveJobStorageKey(endpointBase: string): string {
  return `${NSE_ACTIVE_JOB_STORAGE_PREFIX}:${String(endpointBase || '').trim()}`;
}

function isFailureStatus(status: string): boolean {
  return ['CANCELLED', 'ERROR', 'FAILED', 'FAILURE', 'TIMED_OUT'].includes(status.toUpperCase());
}

function isWarningStatus(status: string): boolean {
  return ['NO_ACTION', 'PARTIAL', 'SKIPPED'].includes(status.toUpperCase());
}

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {};
}

function normalizeFlowKey(value: unknown): FlowKey | null {
  const normalized = safeLegacyText(value, '').toLowerCase().replace(/[^a-z]/g, '');
  if (normalized === 'download') return 'download';
  if (normalized === 'validate' || normalized === 'validation' || normalized === 'extract') return 'validate';
  if (normalized === 'process' || normalized === 'insert' || normalized === 'load') return 'process';
  if (normalized === 'success' || normalized === 'complete' || normalized === 'completed') return 'success';
  return null;
}

function numberValue(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(String(value).replace(/,/g, '').trim());
  return Number.isFinite(parsed) ? parsed : null;
}

function numericField(record: UnknownRecord, aliases: readonly string[]): number | null {
  return numberValue(pickField(record, aliases));
}

function arrayLengthField(record: UnknownRecord, aliases: readonly string[]): number | null {
  const value = pickField(record, aliases);
  return Array.isArray(value) ? value.length : numericField(record, aliases);
}

function nestedPayloadRecords(data: UnknownRecord): UnknownRecord[] {
  const result = asRecord(pickField(data, ['result', 'payload']));
  return [
    data,
    asRecord(pickField(data, ['request'])),
    asRecord(pickField(data, ['counts'])),
    asRecord(pickField(data, ['inspection'])),
    asRecord(pickField(data, ['load'])),
    result,
    asRecord(pickField(result, ['request'])),
    asRecord(pickField(result, ['counts'])),
    asRecord(pickField(result, ['inspection'])),
    asRecord(pickField(result, ['load'])),
  ];
}

function firstNumericFromPayloads(data: UnknownRecord, aliases: readonly string[]): number | null {
  for (const record of nestedPayloadRecords(data)) {
    const value = numericField(record, aliases);
    if (value !== null) return value;
  }
  return null;
}

function firstArrayLengthFromPayloads(data: UnknownRecord, aliases: readonly string[]): number | null {
  for (const record of nestedPayloadRecords(data)) {
    const value = arrayLengthField(record, aliases);
    if (value !== null) return value;
  }
  return null;
}

function firstTextFromPayloads(data: UnknownRecord, aliases: readonly string[]): string {
  for (const record of nestedPayloadRecords(data)) {
    const value = safeLegacyText(pickField(record, aliases), '');
    if (value) return value;
  }
  return '';
}

function formatToastCount(label: string, value: number | null): string | null {
  return value === null ? null : `${label} ${formatCellByKind(value, 'count')}`;
}

function resolveTradeDateText(data: UnknownRecord, fallbackTradeDate: string): string {
  return firstTextFromPayloads(data, ['tradeDate', 'trade_date']) || fallbackTradeDate;
}

function resolveInsertedRows(data: UnknownRecord): number | null {
  return firstNumericFromPayloads(data, [
    'records_inserted',
    'recordsInserted',
    'insertedRows',
    'inserted_rows',
    'loadedCount',
    'loaded_count',
    'successRows',
    'success_rows',
    'successCount',
    'success_count',
  ]);
}

function resolveSkippedRows(data: UnknownRecord): number | null {
  const explicitSkipped = firstNumericFromPayloads(data, ['records_skipped_existing', 'recordsSkippedExisting']);
  if (explicitSkipped !== null) return explicitSkipped;
  const skippedRows = firstNumericFromPayloads(data, [
    'skippedRows',
    'skipped_rows',
    'skippedCount',
    'skipped_count',
    'universeSkippedCount',
    'universe_skipped_count',
  ]);
  const duplicateRows = firstNumericFromPayloads(data, [
    'duplicateRows',
    'duplicate_rows',
    'duplicateCount',
    'duplicate_count',
    'alreadyLoadedCount',
    'already_loaded_count',
  ]);
  if (skippedRows === null && duplicateRows === null) return null;
  return (skippedRows ?? 0) + (duplicateRows ?? 0);
}

function resolveValidRows(data: UnknownRecord): number | null {
  return firstNumericFromPayloads(data, [
    'validRows',
    'valid_rows',
    'matchedRows',
    'matched_rows',
    'rowsValidated',
    'rows_validated',
  ]);
}

function resolveInvalidRows(data: UnknownRecord): number | null {
  return firstNumericFromPayloads(data, [
    'invalidRows',
    'invalid_rows',
    'parseErrorRows',
    'parse_error_rows',
    'failureCount',
    'failure_count',
  ]) ?? firstArrayLengthFromPayloads(data, ['invalid_symbols', 'invalidSymbols']);
}

function resolveFailedRows(data: UnknownRecord): number | null {
  return firstNumericFromPayloads(data, ['failedRows', 'failed_rows', 'failureCount', 'failure_count']);
}

function buildToastDescription(summary: string, details: Array<string | null>): string {
  return [summary, ...details.filter((detail): detail is string => Boolean(detail))].join(' | ');
}

function toastIconLabel(tone: ToastTone): string {
  if (tone === 'success') return 'OK';
  if (tone === 'warn') return '!';
  if (tone === 'info') return 'i';
  return 'ERR';
}

export function buildNseValidateToast(heading: string, data: UnknownRecord, fallbackTradeDate = ''): ToastState {
  const tradeDate = resolveTradeDateText(data, fallbackTradeDate);
  const inserted = resolveInsertedRows(data) ?? resolveValidRows(data) ?? 0;
  return {
    description: buildToastDescription(
      `${heading} extracted successfully${tradeDate ? ` for ${tradeDate}` : ''}.`,
      [
        formatToastCount('Rows', inserted),
        formatToastCount('Valid', resolveValidRows(data)),
        formatToastCount('Invalid', resolveInvalidRows(data)),
        formatToastCount('Skipped', resolveSkippedRows(data)),
      ],
    ),
    title: `${heading} Extracted Successfully`,
    tone: 'success',
  };
}

export function buildNseProcessToast(heading: string, data: UnknownRecord, fallbackTradeDate = ''): ToastState {
  const tradeDate = resolveTradeDateText(data, fallbackTradeDate);
  const inserted = resolveInsertedRows(data);
  const insertedRows = inserted ?? 0;
  return {
    description: buildToastDescription(
      insertedRows > 0
        ? `${heading} extracted successfully${tradeDate ? ` for ${tradeDate}` : ''}.`
        : `${heading} is already up to date${tradeDate ? ` for ${tradeDate}` : ''}.`,
      [
        formatToastCount('Rows', inserted),
        formatToastCount('Inserted', inserted),
        formatToastCount('Skipped', resolveSkippedRows(data)),
        formatToastCount('Invalid', resolveInvalidRows(data)),
      ],
    ),
    title: insertedRows > 0 ? `${heading} Extracted Successfully` : `${heading} Already Up To Date`,
    tone: 'success',
  };
}

export function buildNseAutomationToast(heading: string, data: UnknownRecord, fallbackTradeDate = ''): ToastState {
  const tradeDate = resolveTradeDateText(data, fallbackTradeDate);
  const inserted = resolveInsertedRows(data);
  const insertedRows = inserted ?? 0;
  return {
    description: buildToastDescription(
      insertedRows > 0
        ? `${heading} extracted successfully${tradeDate ? ` for ${tradeDate}` : ''}.`
        : `${heading} is already up to date${tradeDate ? ` for ${tradeDate}` : ''}.`,
      [
        formatToastCount('Rows', inserted),
        formatToastCount('Inserted', inserted),
        formatToastCount('Skipped', resolveSkippedRows(data)),
        formatToastCount('Failed', resolveFailedRows(data)),
      ],
    ),
    title: insertedRows > 0 ? `${heading} Extracted Successfully` : `${heading} Already Up To Date`,
    tone: 'success',
  };
}

export function resolveStageTradeDateLabel(data: UnknownRecord): string {
  const explicitLabel = firstTextFromPayloads(data, [
    'tradeDateLabel',
    'trade_date_display',
    'displayDate',
    'latestTradingDate',
  ]);
  if (explicitLabel) return explicitLabel;
  const tradeDate = firstTextFromPayloads(data, [
    'tradeDate',
    'trade_date',
    'latestTradeDate',
    'latest_trade_date',
    'endDate',
    'end_date',
  ]);
  return tradeDate ? formatCellByKind(tradeDate, 'date') : '';
}

function currentIso(): string {
  return new Date().toISOString();
}

function elapsedForStep(step: FlowStepState, nowMs = Date.now()): number {
  const startedAtMs = step.startedAt ? Date.parse(step.startedAt) : Number.NaN;
  const endedAtMs = step.endedAt ? Date.parse(step.endedAt) : Number.NaN;
  if (Number.isFinite(startedAtMs) && Number.isFinite(endedAtMs)) {
    return Math.max(0, endedAtMs - startedAtMs);
  }
  if (Number.isFinite(startedAtMs) && ['WORKING', 'RUNNING', 'STARTED'].includes(step.status.toUpperCase())) {
    return Math.max(0, nowMs - startedAtMs);
  }
  return Math.max(0, step.elapsedMs || 0);
}

function formatDuration(ms: number | null | undefined): string {
  const seconds = Math.max(0, Math.round((ms || 0) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  if (minutes < 60) return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const minuteRemainder = minutes % 60;
  return minuteRemainder ? `${hours}h ${minuteRemainder}m` : `${hours}h`;
}

function formatTimestamp(value?: string): string {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function flowClassName(step: FlowStepState): string {
  const statusText = step.status.toUpperCase();
  if (isFailureStatus(statusText)) return 'is-failed';
  if (isWarningStatus(statusText)) return 'is-warning';
  if (['COMPLETED', 'DONE', 'SUCCESS'].includes(statusText)) return 'is-complete';
  if (['WORKING', 'RUNNING', 'STARTED'].includes(statusText)) return 'is-active';
  return '';
}

type NseAutomationPageProps = {
  config: NseAutomationPageConfig;
};

function NSEToolbar({ children }: { children: ReactNode }) {
  return <section className="nse-automation-toolbar">{children}</section>;
}

function NSEToolbarRow({
  children,
  variant,
}: {
  children: ReactNode;
  variant: 'actions' | 'dates' | 'enrichment';
}) {
  return <div className={`nse-toolbar-row nse-toolbar-row--${variant}`}>{children}</div>;
}

type StageRunOptions = {
  sourceMode?: ExtractionMode;
  successToast?: (data: UnknownRecord) => ToastState;
};

export function NseAutomationPage({ config }: NseAutomationPageProps) {
  const [allowMarketHoliday, setAllowMarketHoliday] = useState(false);
  const [autoInsert, setAutoInsert] = useState(true);
  const [endDate, setEndDate] = useState('');
  const [enrichLimit, setEnrichLimit] = useState('');
  const [eqOnly, setEqOnly] = useState(true);
  const [error, setError] = useState('');
  const [filterEnd, setFilterEnd] = useState('');
  const [filterRange, setFilterRange] = useState('MAX');
  const [filterStart, setFilterStart] = useState('');
  const [flow, setFlow] = useState<Record<FlowKey, FlowStepState>>(createInitialFlow);
  const [flowTick, setFlowTick] = useState(0);
  const [jobId, setJobId] = useState('');
  const [isPolling, setIsPolling] = useState(false);
  const [lastMessage, setLastMessage] = useState('');
  const [payload, setPayload] = useState<UnknownRecord>({});
  const [progress, setProgress] = useState<ProgressState | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [runtimeTradeDateLabel, setRuntimeTradeDateLabel] = useState('');
  const [startDate, setStartDate] = useState('');
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [symbols, setSymbols] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [toast, setToast] = useState<ToastState | null>(null);
  const [tradeDate, setTradeDate] = useState(todayIso);
  const pollTimerRef = useRef<number | null>(null);
  const toastTimerRef = useRef<number | null>(null);
  const activeJobStorageKey = useMemo(() => nseAutomationActiveJobStorageKey(config.endpointBase), [config.endpointBase]);

  useEffect(() => () => {
    if (pollTimerRef.current) {
      window.clearInterval(pollTimerRef.current);
    }
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
    }
  }, []);

  useEffect(() => {
    const hasActiveFlow = flowKeys.some((key) => ['WORKING', 'RUNNING', 'STARTED'].includes(flow[key].status.toUpperCase()));
    if (!hasActiveFlow) return undefined;
    const timer = window.setInterval(() => setFlowTick((current) => current + 1), 1000);
    return () => window.clearInterval(timer);
  }, [flow]);

  useEffect(() => {
    const controller = new AbortController();
    const params: Record<string, string | boolean> = { refresh: refreshVersion > 0 };
    if (filterStart || filterEnd) {
      params.startDate = filterStart || filterEnd;
      params.endDate = filterEnd || filterStart;
    } else if (filterRange) {
      params.range = filterRange;
    }
    setStatus('loading');
    setError('');
    legacyApiGet<UnknownRecord>(`${config.endpointBase}/summary`, params, {
      signal: controller.signal,
      timeoutMs: 600000,
    }).then((loadedPayload) => {
      setPayload(getNestedDataRecord(loadedPayload));
      setStatus('online');
    }).catch((loadError) => {
      if (controller.signal.aborted) return;
      setError(loadError instanceof Error ? loadError.message : String(loadError));
      setStatus('error');
    });
    return () => controller.abort();
  }, [config.endpointBase, filterEnd, filterRange, filterStart, refreshVersion]);

  useEffect(() => {
    setRuntimeTradeDateLabel('');
  }, [config.endpointBase, filterEnd, filterRange, filterStart]);

  useEffect(() => {
    if (!config.fullRunEndpoint) return undefined;
    let active = true;
    const controller = new AbortController();

    async function loadSnapshot(path: string): Promise<UnknownRecord | null> {
      try {
        const response = await legacyApiGet<UnknownRecord>(path, { tail: 180 }, {
          diagnostic: {
            action: 'poll-nse-job',
            component: 'NseAutomationPage',
            suppress: true,
          },
          signal: controller.signal,
          timeoutMs: 180000,
        });
        return getNestedDataRecord(response);
      } catch (loadError) {
        if (controller.signal.aborted) return null;
        console.info('[NSE][AUTOMATION_UI] job_rehydrate_skip', {
          endpointBase: config.endpointBase,
          error: loadError instanceof Error ? loadError.message : String(loadError),
        });
        return null;
      }
    }

    async function rehydrateActiveJob() {
      const rememberedJobId = readRememberedJobId();
      let snapshot: UnknownRecord | null = null;
      if (rememberedJobId) {
        snapshot = await loadSnapshot(`${config.endpointBase}/jobs/${encodeURIComponent(rememberedJobId)}`);
      }
      if (!snapshot || !isNseAutomationJobActive(snapshot)) {
        snapshot = await loadSnapshot(`${config.endpointBase}/jobs/latest`);
      }
      if (!active || !snapshot) return;
      hydrateJobSnapshot(snapshot);
      const nextJobId = resolveNseAutomationJobId(snapshot);
      if (isNseAutomationJobActive(snapshot) && nextJobId) {
        setStatus('online');
        startPolling(nextJobId);
      } else if (nextJobId) {
        clearRememberedJobId();
      }
    }

    rehydrateActiveJob();
    return () => {
      active = false;
      controller.abort();
    };
  }, [activeJobStorageKey, config.endpointBase, config.fullRunEndpoint]);

  const baseView = useMemo(() => buildNseAutomationView(config, payload), [config, payload]);
  const isRunBusy = status === 'loading' || isPolling;

  const view = useMemo<NseAutomationView>(() => {
    const nextView = isRunBusy && runtimeTradeDateLabel
      ? {
        ...baseView,
        kpis: baseView.kpis.map((kpi) => (
          kpi.label === 'Trade Date'
            ? { ...kpi, value: runtimeTradeDateLabel }
            : kpi
        )),
        selectedTradeDate: runtimeTradeDateLabel,
      }
      : baseView;
    return nextView;
  }, [baseView, isRunBusy, runtimeTradeDateLabel]);

  const overrideWarning = useMemo(() => {
    if (!allowMarketHoliday) return '';
    const candidates = [
      ['Trade Date', tradeDate],
      ['From / Start Date', startDate],
      ['To / End Date', endDate],
    ] as const;
    const closedDate = candidates.find(([, value]) => Boolean(value && marketClosedReason(value)));
    if (!closedDate) return '';
    return `${closedDate[0]} ${closedDate[1]} is ${marketClosedReason(closedDate[1])}. Manual override is enabled.`;
  }, [allowMarketHoliday, endDate, startDate, tradeDate]);

  const verificationYear = useMemo(
    () => resolveVerificationYear(filterEnd, filterStart, view.selectedTradeDate, tradeDate),
    [filterEnd, filterStart, tradeDate, view.selectedTradeDate],
  );

  const handleVerificationError = useCallback((message: string) => {
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
    setToast({
      description: message,
      title: `${config.heading} trading day verification failed`,
      tone: 'danger',
    });
    toastTimerRef.current = window.setTimeout(() => {
      setToast(null);
      toastTimerRef.current = null;
    }, 5000);
  }, [config.heading]);

  const columns = useMemo<Array<AppDataTableColumn<NseAutomationRowView>>>(() => config.rowColumns.map((column, cellIndex) => ({
    dataCol: column.key,
    getSortValue: (row) => row.cells[cellIndex] ?? null,
    key: column.key,
    label: column.label,
    renderCell: (row) => row.cells[cellIndex] ?? '-',
    sortType: column.format === 'date' || column.format === 'dateOnly' ? 'date' : column.format === 'number' || column.format === 'count' ? 'number' : 'string',
  })), [config.rowColumns]);

  const filteredRows = useMemo(() => {
    if (!searchQuery.trim()) return view.rows;
    const lowerQuery = searchQuery.toLowerCase().trim();
    return view.rows.filter((row) => 
      row.cells.some((cell) => String(cell).toLowerCase().includes(lowerQuery))
    );
  }, [view.rows, searchQuery]);

  let toolbarStatus: StrategyToolbarStatus = 'idle';
  if (status === 'loading' || isPolling) toolbarStatus = 'syncing';
  else if (status === 'error') toolbarStatus = 'error';
  else if (status === 'online') toolbarStatus = view.selectedTradeDate && view.selectedTradeDate !== '-' ? 'live' : 'stale';

  function requestPayload() {
    const body: Record<string, unknown> = {
      autoInsertAfterDownload: autoInsert,
      allowMarketHoliday,
      allow_override: allowMarketHoliday,
      eqOnly,
      tradeDate,
    };
    if (startDate) body.startDate = startDate;
    if (endDate) body.endDate = endDate;
    if (enrichLimit) body.enrichLimit = Number(enrichLimit);
    if (symbols.trim()) body.symbols = symbols.trim();
    return body;
  }

  function readRememberedJobId(): string {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(activeJobStorageKey) || '{}') as { jobId?: unknown };
      return safeLegacyText(parsed.jobId, '');
    } catch {
      return '';
    }
  }

  function rememberJobId(nextJobId: string) {
    if (!nextJobId) return;
    try {
      window.localStorage.setItem(activeJobStorageKey, JSON.stringify({ jobId: nextJobId }));
    } catch {
      // Job polling remains backend-authoritative; local storage only improves browser refresh recovery.
    }
  }

  function clearRememberedJobId() {
    try {
      window.localStorage.removeItem(activeJobStorageKey);
    } catch {
      // Ignore storage cleanup failures.
    }
  }

  function resetFlow(active?: FlowKey) {
    const timestamp = currentIso();
    setFlow(() => {
      const next = createInitialFlow();
      if (active) next[active] = { elapsedMs: 0, startedAt: timestamp, status: 'WORKING' };
      return next;
    });
    setProgress(null);
  }

  function startFlowStep(key: FlowKey) {
    const timestamp = currentIso();
    setFlow((current) => ({
      ...current,
      [key]: { elapsedMs: 0, startedAt: timestamp, status: 'WORKING' },
    }));
  }

  function finishFlowStep(key: FlowKey, result: string, detail?: string) {
    const timestamp = currentIso();
    setFlow((current) => {
      const step = current[key];
      const elapsedMs = elapsedForStep({ ...step, endedAt: timestamp, status: result });
      return {
        ...current,
        [key]: {
          ...step,
          detail: detail || step.detail,
          elapsedMs,
          endedAt: timestamp,
          status: result,
        },
      };
    });
  }

  function applyBackendFlow(flowPayload: unknown) {
    const flowRecord = asRecord(flowPayload);
    if (!Object.keys(flowRecord).length) return;
    const completed = asRecord(pickField(flowRecord, ['completed', 'completedStages', 'completed_stages']));
    const durations = asRecord(pickField(flowRecord, ['durationsMs', 'durations_ms', 'durations']));
    const history = asRecord(pickField(flowRecord, ['history', 'stages']));
    const activeKey = normalizeFlowKey(pickField(flowRecord, ['activeKey', 'active_key', 'currentStage', 'current_stage']));
    const failedKey = normalizeFlowKey(pickField(flowRecord, ['failedKey', 'failed_key']));
    const stageStartedAt = safeLegacyText(pickField(flowRecord, ['stageStartedAt', 'stage_started_at']), '');
    const timestamp = currentIso();

    setFlow((current) => {
      const next: Record<FlowKey, FlowStepState> = { ...current };
      flowKeys.forEach((key) => {
        const stepHistory = asRecord(pickField(history, [key]));
        const completedValue = pickField(completed, [key]);
        const durationMs = numericField(durations, [key, `${key}Ms`, `${key}_ms`]) ?? numericField(stepHistory, ['elapsedMs', 'elapsed_ms', 'durationMs', 'duration_ms']);
        const startedAt = safeLegacyText(pickField(stepHistory, ['startedAt', 'started_at']), current[key].startedAt || '');
        const endedAt = safeLegacyText(pickField(stepHistory, ['endedAt', 'ended_at', 'finishedAt', 'finished_at']), current[key].endedAt || '');
        const detail = safeLegacyText(pickField(stepHistory, ['message', 'detail']), current[key].detail || '');
        let nextStatus = current[key].status;
        const completedText = safeLegacyText(completedValue, '').toLowerCase();
        if (failedKey === key) {
          nextStatus = 'FAILED';
        } else if (completedValue === true || completedText === 'true' || completedText === '1') {
          nextStatus = 'COMPLETED';
        } else if (activeKey === key) {
          nextStatus = 'WORKING';
        }
        next[key] = {
          ...current[key],
          detail: detail || undefined,
          elapsedMs: durationMs ?? current[key].elapsedMs,
          endedAt: endedAt || (nextStatus === 'COMPLETED' ? current[key].endedAt || timestamp : undefined),
          startedAt: startedAt || (activeKey === key && stageStartedAt ? stageStartedAt : current[key].startedAt),
          status: nextStatus,
        };
      });
      return next;
    });
  }

  function extractProgress(data: UnknownRecord): ProgressState | null {
    const progressRecord = asRecord(pickField(data, ['progress', 'jobProgress', 'stats']));
    if (!Object.keys(progressRecord).length) return null;
    const total = numericField(progressRecord, ['total', 'totalSymbols', 'total_symbols', 'requested', 'totalRecords']);
    const current = numericField(progressRecord, ['current', 'processed', 'completed', 'successCount', 'totalSymbolsProcessed', 'total_symbols_processed']);
    const percent = numericField(progressRecord, ['percent', 'percentage', 'progressPercent', 'progress_percent']);
    if (total === null && current === null && percent === null) return null;
    return { current, percent, total };
  }

  function hydrateJobSnapshot(data: UnknownRecord) {
    const nextJobId = resolveNseAutomationJobId(data);
    const statusText = payloadStatus(data);
    if (nextJobId) setJobId(nextJobId);
    setLastMessage(safeLegacyText(pickField(data, ['message', 'detail']), statusText));
    setProgress(extractProgress(data));
    const nextTradeDateLabel = resolveStageTradeDateLabel(data);
    if (nextTradeDateLabel) setRuntimeTradeDateLabel(nextTradeDateLabel);
    applyBackendFlow(pickField(data, ['flow']));
    if (Array.isArray(data.latestRows) || Array.isArray(data.latest_rows)) {
      setPayload(data);
    }
  }

  function responseFailed(data: UnknownRecord): boolean {
    if (data.ok === false) return true;
    return isFailureStatus(payloadStatus(data));
  }

  function stageLabelText(stageLabel: string): string {
    if (stageLabel === 'download') return 'download';
    if (stageLabel === 'validate') return 'extract / validate';
    if (stageLabel === 'process') return 'insert / process';
    if (stageLabel === 'success') return 'success';
    return stageLabel;
  }

  function failureToast(stageLabel: string, message: string): ToastState {
    return {
      description: message,
      title: `${config.heading} ${stageLabelText(stageLabel)} failed`,
      tone: 'danger',
    };
  }

  function warningToast(stageLabel: string, message: string): ToastState {
    return {
      description: message,
      title: `${config.heading} ${stageLabelText(stageLabel)} warning`,
      tone: 'warn',
    };
  }

  function showToast(nextToast: ToastState) {
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
    setToast(nextToast);
    toastTimerRef.current = window.setTimeout(() => {
      setToast(null);
      toastTimerRef.current = null;
    }, 5000);
  }

  function dismissToast() {
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
      toastTimerRef.current = null;
    }
    setToast(null);
  }

  function setMarketDateValue(nextValue: string, setter: (value: string) => void, label: string) {
    const reason = marketClosedReason(nextValue);
    if (reason && !allowMarketHoliday) {
      showToast({
        description: `${label} ${nextValue} is ${reason}. Enable Allow market holiday or weekend date to select it manually.`,
        title: 'Market date blocked',
        tone: 'warn',
      });
      return;
    }
    setter(nextValue);
    if (reason && allowMarketHoliday) {
      showToast({
        description: `${label} ${nextValue} is ${reason}. Manual override is enabled.`,
        title: 'Market override enabled',
        tone: 'warn',
      });
    }
  }

  function validateMarketDateSelection(): boolean {
    const candidates = [
      ['Trade Date', tradeDate],
      ['From / Start Date', startDate],
      ['To / End Date', endDate],
    ] as const;
    const closedDate = candidates.find(([, value]) => Boolean(value && marketClosedReason(value)));
    if (!closedDate) return true;
    const message = `${closedDate[0]} ${closedDate[1]} is ${marketClosedReason(closedDate[1])}.`;
    if (allowMarketHoliday) {
      showToast({
        description: `${message} Manual override is enabled.`,
        title: 'Market override enabled',
        tone: 'warn',
      });
      return true;
    }
    setError(`${message} Enable Allow market holiday or weekend date to process it manually.`);
    showToast({
      description: `${message} Enable Allow market holiday or weekend date to process it manually.`,
      title: 'Market date blocked',
      tone: 'warn',
    });
    return false;
  }

  async function runStage(action: 'download' | 'init' | 'process' | 'validate', flowKey: FlowKey, options: StageRunOptions = {}): Promise<UnknownRecord | null> {
    if (action !== 'init' && !validateMarketDateSelection()) return null;
    startFlowStep(flowKey);
    setStatus('loading');
    setError('');
    try {
      const response = await legacyApiPost<UnknownRecord>(resolveEndpoint(config, action), action === 'init' ? {} : requestPayload(), {
        timeoutMs: 600000,
      });
      const data = getNestedDataRecord(response);
      setLastMessage(safeLegacyText(pickField(data, ['message', 'detail']), `${action} completed.`));
      const nextProgress = extractProgress(data);
      if (nextProgress) setProgress(nextProgress);
      const nextTradeDateLabel = resolveStageTradeDateLabel(data);
      if (nextTradeDateLabel) setRuntimeTradeDateLabel(nextTradeDateLabel);
      applyBackendFlow(pickField(data, ['flow']));
      if (responseFailed(data)) {
        const message = safeLegacyText(pickField(data, ['message', 'detail', 'error']), `${action} failed.`);
        finishFlowStep(flowKey, 'FAILED', message);
        if (flowKey === 'process') finishFlowStep('success', 'FAILED', message);
        setError(message);
        setStatus('error');
        showToast(failureToast(action === 'init' ? 'prepare' : flowKey, message));
        return null;
      }
      const statusText = payloadStatus(data);
      if (isWarningStatus(statusText)) {
        const message = safeLegacyText(pickField(data, ['message', 'detail']), statusText);
        finishFlowStep(flowKey, statusText, message);
        if (flowKey === 'process') finishFlowStep('success', statusText, message);
        showToast(warningToast(action === 'init' ? 'prepare' : flowKey, message));
        setStatus('online');
        setRefreshVersion((current) => current + 1);
        return data;
      }
      finishFlowStep(flowKey, 'COMPLETED');
      if (flowKey === 'process') finishFlowStep('success', 'COMPLETED');
      if (options.successToast) showToast(options.successToast(data));
      setStatus('online');
      setRefreshVersion((current) => current + 1);
      return data;
    } catch (stageError) {
      const message = stageError instanceof Error ? stageError.message : String(stageError);
      finishFlowStep(flowKey, 'FAILED', message);
      if (flowKey === 'process') finishFlowStep('success', 'FAILED', message);
      setError(message);
      setStatus('error');
      showToast(failureToast(action === 'init' ? 'prepare' : flowKey, message));
      return null;
    }
  }

  function stopPollingTimer() {
    if (pollTimerRef.current) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setIsPolling(false);
  }

  function finishPollingFromSnapshot(data: UnknownRecord, statusText: string) {
    stopPollingTimer();
    clearRememberedJobId();
    if (isFailureStatus(statusText)) {
      const message = safeLegacyText(pickField(data, ['message', 'detail']), statusText);
      finishFlowStep('success', 'FAILED', message);
      setError(message);
      setStatus('error');
      showToast(failureToast('automation', message));
    } else if (isWarningStatus(statusText)) {
      const message = safeLegacyText(pickField(data, ['message', 'detail']), statusText);
      finishFlowStep('download', 'COMPLETED');
      finishFlowStep('validate', 'COMPLETED');
      finishFlowStep('process', statusText, message);
      finishFlowStep('success', statusText, message);
      showToast(warningToast('automation', message));
      setStatus('online');
    } else {
      finishFlowStep('download', 'COMPLETED');
      finishFlowStep('validate', 'COMPLETED');
      finishFlowStep('process', 'COMPLETED');
      finishFlowStep('success', 'COMPLETED');
      showToast(buildNseAutomationToast(config.heading, data, tradeDate));
      setStatus('online');
    }
    setRefreshVersion((current) => current + 1);
  }

  async function pollJobOnce(nextJobId: string) {
    try {
      const response = await legacyApiGet<UnknownRecord>(`${config.endpointBase}/jobs/${encodeURIComponent(nextJobId)}`, { tail: 180 }, {
        diagnostic: {
          action: 'poll-nse-job',
          component: 'NseAutomationPage',
          suppress: true,
        },
        timeoutMs: 180000,
      });
      const data = getNestedDataRecord(response);
      const statusText = payloadStatus(data);
      hydrateJobSnapshot(data);
      if (terminalStatus(statusText) || data.done === true) {
        finishPollingFromSnapshot(data, statusText);
      }
    } catch (pollError) {
      const message = pollError instanceof Error ? pollError.message : String(pollError);
      setError(message);
      stopPollingTimer();
      finishFlowStep('success', 'FAILED', message);
      setStatus('error');
      showToast(failureToast('automation', message));
    }
  }

  function startPolling(nextJobId: string) {
    if (!nextJobId) return;
    if (pollTimerRef.current) window.clearInterval(pollTimerRef.current);
    rememberJobId(nextJobId);
    setIsPolling(true);
    void pollJobOnce(nextJobId);
    pollTimerRef.current = window.setInterval(() => {
      void pollJobOnce(nextJobId);
    }, NSE_JOB_POLL_MS);
  }

  async function runSequentialAutomation(sourceMode: ExtractionMode = 'AUTOMATION') {
    resetFlow('download');
    const downloadData = await runStage('download', 'download');
    if (!downloadData) return;
    const validateData = await runStage('validate', 'validate');
    if (!validateData) return;
    const processData = await runStage('process', 'process', { sourceMode });
    if (!processData) return;
    showToast(buildNseAutomationToast(config.heading, processData, tradeDate));
  }

  async function runFullAutomation(sourceMode: ExtractionMode = 'AUTOMATION') {
    if (!validateMarketDateSelection()) return;
    const endpoint = config.fullRunEndpoint;
    if (!endpoint) {
      await runSequentialAutomation(sourceMode);
      return;
    }
    setStatus('loading');
    resetFlow('download');
    try {
      const response = await legacyApiPost<UnknownRecord>(endpoint, { ...requestPayload(), jobMode: 'pipeline' }, {
        timeoutMs: 600000,
      });
      const data = getNestedDataRecord(response);
      const nextJobId = resolveNseAutomationJobId(data);
      hydrateJobSnapshot(data);
      if (nextJobId && isNseAutomationJobActive(data)) {
        startPolling(nextJobId);
      } else {
        const failed = responseFailed(data);
        const statusText = payloadStatus(data);
        const warning = isWarningStatus(statusText);
        if (nextJobId) clearRememberedJobId();
        finishFlowStep('success', failed ? 'FAILED' : warning ? statusText : 'COMPLETED');
        setStatus(failed ? 'error' : 'online');
        if (failed) {
          const message = safeLegacyText(pickField(data, ['message', 'detail', 'error']), 'Automation failed.');
          setError(message);
          showToast(failureToast('automation', message));
        } else if (warning) {
          const message = safeLegacyText(pickField(data, ['message', 'detail']), statusText);
          showToast(warningToast('automation', message));
        } else {
          showToast(buildNseAutomationToast(config.heading, data, tradeDate));
        }
        setRefreshVersion((current) => current + 1);
      }
    } catch (runError) {
      const message = runError instanceof Error ? runError.message : String(runError);
      finishFlowStep('download', 'FAILED', message);
      finishFlowStep('success', 'FAILED', message);
      setError(message);
      setStatus('error');
      showToast(failureToast('automation', message));
    }
  }

  async function handleDownloadAction() {
    if (shouldAutoContinueAfterDownload(autoInsert, symbols)) {
      await runFullAutomation('MANUAL');
      return;
    }
    await runStage('download', 'download');
  }

  const flowNowMs = useMemo(() => Date.now(), [flowTick]);

  function etaForStep(key: FlowKey, elapsedMs: number): number | null {
    const step = flow[key];
    if (key !== 'process' || !['WORKING', 'RUNNING', 'STARTED'].includes(step.status.toUpperCase())) return null;
    if (!progress?.current || !progress.total || progress.current <= 0 || progress.total <= progress.current) return null;
    return Math.max(0, Math.round((elapsedMs / progress.current) * (progress.total - progress.current)));
  }

  function flowMetaText(key: FlowKey, step: FlowStepState, elapsedMs: number): string {
    const started = formatTimestamp(step.startedAt);
    const ended = formatTimestamp(step.endedAt);
    const etaMs = etaForStep(key, elapsedMs);
    const active = ['WORKING', 'RUNNING', 'STARTED'].includes(step.status.toUpperCase());
    const parts: string[] = [];
    if (started) parts.push(`Started ${started}`);
    if (ended) parts.push(`Ended ${ended}`);
    if (etaMs !== null) {
      parts.push(`ETA ${formatDuration(etaMs)}`);
    } else if (active) {
      parts.push('ETA calculating');
    }
    if (key === 'process' && progress && progress.current !== null && progress.total !== null) {
      parts.push(`Progress ${formatCellByKind(progress.current, 'count')}/${formatCellByKind(progress.total, 'count')}`);
    } else if (key === 'process' && progress && progress.percent !== null) {
      parts.push(`Progress ${formatCellByKind(progress.percent, 'number')}%`);
    }
    if (!parts.length && elapsedMs > 0) return 'Flow time captured';
    return parts.join(' | ');
  }

  return (
    <OpsPageShell activeDatabasePage={config.activeDatabasePage} className="nse-automation-react-page">
      <Toast
        open={Boolean(toast)}
        title={toast?.title || ''}
        description={toast?.description || ''}
        tone={toast?.tone || 'info'}
        placement="top-right"
        icon={toast ? <span aria-hidden="true" className="text-[11px] font-semibold tracking-[0.14em]">{toastIconLabel(toast.tone)}</span> : undefined}
        onClose={dismissToast}
      />
      <PageHero title={config.heading} />
      
      <StrategyToolbar
        onRefresh={() => setRefreshVersion((v) => v + 1)}
        onSearchChange={setSearchQuery}
        refreshing={isRunBusy}
        searchValue={searchQuery}
        showTimeframe={true}
        timeframe="daily"
        status={toolbarStatus}
        lastRefreshed={view.selectedTradeDate || undefined}
        ltcDate={view.selectedTradeDate || undefined}
        showTotal={true}
        total={filteredRows.length}
      />

      <section className="card database-react-filter-card">
        <div className="database-react-filter-grid">
          <SelectField label="Range" value={filterRange} onChange={(value) => {
            setFilterRange(value);
            if (value) {
              setFilterStart('');
              setFilterEnd('');
            }
          }}>
            <option value="MAX">MAX</option>
            <option value="5Y">5Y</option>
            <option value="3Y">3Y</option>
            <option value="2Y">2Y</option>
            <option value="">Custom</option>
          </SelectField>
          <TextField label="From Date" value={filterStart} onChange={(value) => {
            setFilterStart(value);
            if (value) setFilterRange('');
          }} placeholder="YYYY-MM-DD" />
          <TextField label="To Date" value={filterEnd} onChange={(value) => {
            setFilterEnd(value);
            if (value) setFilterRange('');
          }} placeholder="YYYY-MM-DD" />
          <ActionButton disabled={isRunBusy} onClick={() => setRefreshVersion((current) => current + 1)}>Submit</ActionButton>
        </div>
      </section>

      <NSEToolbar>
        <NSEToolbarRow variant="dates">
          <TextField label="Trade Date" value={tradeDate} onChange={(value) => setMarketDateValue(value, setTradeDate, 'Trade Date')} type="date" />
          <TextField label="From / Start Date" value={startDate} onChange={(value) => setMarketDateValue(value, setStartDate, 'From / Start Date')} type="date" />
          <TextField label="To / End Date" value={endDate} onChange={(value) => setMarketDateValue(value, setEndDate, 'To / End Date')} type="date" />
          <label className="delivery-filter-check">
            <input type="checkbox" checked={allowMarketHoliday} onChange={(event) => setAllowMarketHoliday(event.currentTarget.checked)} />
            <span>Allow market holiday or weekend date</span>
          </label>
        </NSEToolbarRow>

        <NSEToolbarRow variant="enrichment">
          <TextField label="Enrich Limit" value={enrichLimit} onChange={setEnrichLimit} type="number" placeholder="All symbols" />
          <TextField label="Symbols Override" value={symbols} onChange={setSymbols} placeholder="Optional comma-separated symbols" />
          <label className="delivery-filter-check">
            <input type="checkbox" checked={eqOnly} onChange={(event) => setEqOnly(event.currentTarget.checked)} />
            <span>EQ series only</span>
          </label>
        </NSEToolbarRow>

        <NSEToolbarRow variant="actions">
          <ActionButton disabled={isRunBusy} onClick={() => runStage('init', 'download')}>Prepare</ActionButton>
          <ActionButton disabled={isRunBusy} onClick={handleDownloadAction}>Download</ActionButton>
          <ActionButton
            disabled={isRunBusy}
            onClick={() => runStage('validate', 'validate', {
              successToast: (data) => buildNseValidateToast(config.heading, data, tradeDate),
            })}
          >
            Extract / Validate
          </ActionButton>
          <ActionButton
            disabled={isRunBusy}
            onClick={() => runStage('process', 'process', {
              sourceMode: 'MANUAL',
              successToast: (data) => buildNseProcessToast(config.heading, data, tradeDate),
            })}
          >
            Insert / Process
          </ActionButton>
          <ActionButton disabled={isRunBusy} onClick={() => runFullAutomation('AUTOMATION')}>Run Full Automation</ActionButton>
          <label className="delivery-filter-check">
            <input type="checkbox" checked={autoInsert} onChange={(event) => setAutoInsert(event.currentTarget.checked)} />
            <span>Auto insert after download</span>
          </label>
        </NSEToolbarRow>
      </NSEToolbar>

      <section className="database-react-flow">
        {flowKeys.map((key) => {
          const step = flow[key];
          const elapsedMs = elapsedForStep(step, flowNowMs);
          const meta = flowMetaText(key, step, elapsedMs);
          return (
          <article className={`card database-react-flow__step database-react-flow__step--${key} ${flowClassName(step)}`} key={key}>
            <span>{key.toUpperCase()}</span>
            <strong>{step.status}</strong>
            <small className="database-react-flow__time">Elapsed {formatDuration(elapsedMs)}</small>
            {meta ? <small className="database-react-flow__meta">{meta}</small> : null}
          </article>
          );
        })}
      </section>

      {lastMessage || overrideWarning ? <section className="card"><span className="count-pill">{lastMessage || 'Ready'}</span>{jobId ? <span className="count-pill">JOB: {jobId}</span> : null}{overrideWarning ? <span className="count-pill count-pill--warn">{overrideWarning}</span> : null}</section> : null}
      {error ? <ErrorAlertCard message={error} /> : null}

      <TradingDayVerificationPanel
        onError={handleVerificationError}
        page={config.verificationPage}
        refreshKey={refreshVersion}
        year={verificationYear}
      />

      <KpiGrid items={view.kpis} />

      <section className="card">
        <div className="table-title">
          <h3>{config.tableTitle}</h3>
          <span className="count-pill">TOTAL: {formatCellByKind(filteredRows.length, 'count')}</span>
        </div>
        <AppDataTable
          columns={columns}
          emptyMessage="No latest rows returned."
          getRowKey={(row, index) => `${row.id}-${index}`}
          pageSize={15}
          rows={filteredRows}
          showTopPagination
          tableClassName="data-table--blue"
          tableId={`${config.heading.replace(/\W+/g, '')}LatestRowsTable`}
        />
      </section>
    </OpsPageShell>
  );
}


