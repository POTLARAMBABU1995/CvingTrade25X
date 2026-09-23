import { useEffect, useMemo, useRef, useState } from 'react';
import { AppDataTable, type AppDataTableColumn } from '../../components/app/AppDataTable';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { CopyTextButton } from '../../components/ui/CopyTextButton';
import { TrashIcon } from '../../components/ui/Icons';
import { Toast } from '../../components/ui/Toast';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { asRecord, pickField, safeLegacyText, type UnknownRecord } from '../../adapters/databasePageAdapter';
import { getFyersStatusMessage, readPayloadData } from '../../adapters/fyersPageAdapter';
import { deleteFyersFailedSymbols, fetchFyersFailedSymbols, fetchFyersJob, startFyersFailedSymbolsRerunJob } from '../../services/api/fyersApi';
import { KpiGrid, PageHero } from '../ops/opsPageHelpers';
import { FyersDatePickerField } from './FyersDatePickerField';
import { FyersMigrationLayout } from './FyersMigrationLayout';
import {
  FYERS_AUTH_EXPIRED_TOAST,
  formatFyersDateTime,
  getFyersAuthExpiredToast,
  withFyersToast,
  type FyersPageToast,
} from './fyersPageUtils';

type FailedSymbolRow = {
  month_max_td_count: number;
  reason_error_message: string;
  row_id: number;
  symbol: string;
  symbol_month_failed_td_count: number;
  td_count: number;
  td_flag: string;
  trading_date: string;
};

type RepeatingSymbolRow = {
  failed_dates: string;
  from_date: string;
  occurrences: number;
  symbol: string;
  to_date: string;
};

type FailedSymbolsSummary = {
  pendingRerun: number;
  rerunFailed: number;
  rerunSuccess: number;
  totalFailed: number;
  totalRejected: number;
  totalSkipped: number;
};

type FilterState = {
  fromDate: string;
  sourceMode: string;
  status: string;
  symbol: string;
  toDate: string;
};

const PAGE_SIZE = 25;
const POLL_MS = 1500;
const TERMINAL_JOB_STATUSES = new Set(['SUCCESS', 'FAILED', 'CANCELLED', 'COMPLETED', 'ERROR', 'SKIPPED', 'SUCCEEDED']);
const DEFAULT_SUMMARY: FailedSymbolsSummary = {
  pendingRerun: 0,
  rerunFailed: 0,
  rerunSuccess: 0,
  totalFailed: 0,
  totalRejected: 0,
  totalSkipped: 0,
};
const EMPTY_FILTERS: FilterState = {
  fromDate: '',
  sourceMode: '',
  status: '',
  symbol: '',
  toDate: '',
};

function normalizeRow(row: UnknownRecord): FailedSymbolRow {
  const reasonErrorMessage = safeLegacyText(pickField(row, ['reason_error_message', 'reasonErrorMessage']), '');
  const reason = safeLegacyText(pickField(row, ['reason', 'REASON']), '');
  const errorMessage = safeLegacyText(pickField(row, ['error_message', 'errorMessage']), '');
  return {
    row_id: Number(pickField(row, ['row_id', 'rowId'], 0)) || 0,
    symbol: safeLegacyText(pickField(row, ['symbol', 'SYMBOL']), '-'),
    trading_date: safeLegacyText(pickField(row, ['trading_date', 'tradingDate']), ''),
    reason_error_message: reasonErrorMessage || [reason, errorMessage].filter((item) => item && item !== '-').join(' - ') || '-',
    td_count: Number(pickField(row, ['td_count', 'tdCount'], 0)) || 0,
    symbol_month_failed_td_count: Number(pickField(row, ['symbol_month_failed_td_count', 'symbolMonthFailedTdCount'], 0)) || 0,
    month_max_td_count: Number(pickField(row, ['month_max_td_count', 'monthMaxTdCount'], 0)) || 0,
    td_flag: safeLegacyText(pickField(row, ['td_flag', 'tdFlag']), 'NORMAL').toUpperCase(),
  };
}

function failedSymbolRowKey(row: Pick<FailedSymbolRow, 'symbol' | 'trading_date'>): string {
  return `${row.symbol}-${row.trading_date}`;
}

function dedupeFailedSymbolRows(nextRows: FailedSymbolRow[]): FailedSymbolRow[] {
  const seen = new Set<string>();
  return nextRows.filter((row) => {
    const key = failedSymbolRowKey(row);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function normalizeRepeatingSymbol(row: UnknownRecord): RepeatingSymbolRow {
  return {
    symbol: safeLegacyText(pickField(row, ['symbol', 'SYMBOL']), ''),
    occurrences: Number(pickField(row, ['occurrences', 'repeat_count', 'repeatCount'], 0)) || 0,
    from_date: safeLegacyText(pickField(row, ['from_date', 'fromDate']), ''),
    to_date: safeLegacyText(pickField(row, ['to_date', 'toDate']), ''),
    failed_dates: safeLegacyText(pickField(row, ['failed_dates', 'failedDates']), ''),
  };
}

function tdFlagBadgeClass(token: string) {
  const value = token.toUpperCase();
  if (value === 'FULL_MONTH_FAILED') return 'database-badge database-badge--error';
  if (value === 'HIGH_FAILED_DATES') return 'database-badge database-badge--warn';
  return 'database-badge database-badge--ok';
}

function collectRerunFailureReasons(payload: UnknownRecord): string[] {
  const details = asRecord(payload.details);
  const batches = Array.isArray(details.results) ? details.results : [];
  const reasons: string[] = [];

  for (const batchItem of batches) {
    const batch = asRecord(batchItem);
    const batchRows = Array.isArray(batch.results) ? batch.results : [];
    if (!batchRows.length && batch.ok === false) {
      const fallbackMessage = safeLegacyText(batch.message, '');
      if (fallbackMessage) reasons.push(fallbackMessage);
      continue;
    }
    for (const resultItem of batchRows) {
      const resultRow = asRecord(resultItem);
      const statusToken = safeLegacyText(resultRow.status, '').toUpperCase();
      if (!statusToken || statusToken === 'SUCCESS') continue;
      const symbol = safeLegacyText(pickField(resultRow, ['normalized_symbol', 'input_symbol']), 'UNKNOWN');
      const reason = safeLegacyText(resultRow.error_message, statusToken);
      reasons.push(`${symbol}: ${reason}`);
    }
  }

  return Array.from(new Set(reasons));
}

function buildRerunLog(label: string, payload: UnknownRecord, startedAtIso: string): string {
  const stats = asRecord(payload.stats);
  const details = asRecord(payload.details);
  const inserted = Number(stats.inserted ?? 0) || 0;
  const skipped = Number(stats.skipped ?? 0) || 0;
  const failed = Number(stats.failed ?? 0) || 0;
  const deletedSuccessRows = Number(stats.deletedSuccessRows ?? details.deletedSuccessRows ?? 0) || 0;
  const lines = [
    `[${formatFyersDateTime(startedAtIso)}] ${label}`,
    `Status: ${safeLegacyText(payload.message, payload.ok === false ? 'Re-run failed.' : 'Re-run completed.')}`,
    `Inserted: ${inserted.toLocaleString('en-IN')}`,
    `Skipped: ${skipped.toLocaleString('en-IN')}`,
    `Failed: ${failed.toLocaleString('en-IN')}`,
    `Removed From Failed Table: ${deletedSuccessRows.toLocaleString('en-IN')}`,
  ];
  const reasons = collectRerunFailureReasons(payload);
  if (reasons.length) {
    lines.push('Failure Reasons:');
    reasons.slice(0, 25).forEach((reason) => lines.push(`- ${reason}`));
  }
  return lines.join('\n');
}

function jobLogLines(job: UnknownRecord): string[] {
  const logs = asRecord(job.logs);
  const tail = logs.tail;
  if (Array.isArray(tail)) return tail.map((line) => String(line));
  return [];
}

function SelectAllCheckbox({
  checked,
  indeterminate,
  onChange,
}: {
  checked: boolean;
  indeterminate: boolean;
  onChange: (checked: boolean) => void;
}) {
  const ref = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <input
      ref={ref}
      className="fyers-checkbox"
      type="checkbox"
      checked={checked}
      onChange={(event) => onChange(event.currentTarget.checked)}
      aria-label="Select all visible failed symbols"
    />
  );
}

export function FyersFailedSymbolsPage() {
  const [activeRerunJobId, setActiveRerunJobId] = useState('');
  const [error, setError] = useState('');
  const [deleteBusyKey, setDeleteBusyKey] = useState<string>('');
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [repeatingSymbols, setRepeatingSymbols] = useState<RepeatingSymbolRow[]>([]);
  const [rerunBusyKey, setRerunBusyKey] = useState<string>('');
  const [rerunLogText, setRerunLogText] = useState('No Uniform_Data re-run yet.');
  const [rows, setRows] = useState<FailedSymbolRow[]>([]);
  const [selectedRepeatSymbol, setSelectedRepeatSymbol] = useState('');
  const [selectedRowKeys, setSelectedRowKeys] = useState<Set<string>>(new Set());
  const [summary, setSummary] = useState<FailedSymbolsSummary>(DEFAULT_SUMMARY);
  const [toast, setToast] = useState<FyersPageToast | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const pollControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), 5000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => () => {
    if (pollControllerRef.current) {
      pollControllerRef.current.abort();
      pollControllerRef.current = null;
    }
  }, []);

  async function loadRows(nextPage = page, nextFilters = filters, signal?: AbortSignal) {
    setLoading(true);
    setError('');
    try {
      const payload = asRecord(await fetchFyersFailedSymbols({
        limit: PAGE_SIZE,
        offset: (nextPage - 1) * PAGE_SIZE,
        status: nextFilters.status || undefined,
        symbol: nextFilters.symbol || undefined,
        from_date: nextFilters.fromDate || undefined,
        to_date: nextFilters.toDate || undefined,
        source_mode: nextFilters.sourceMode || undefined,
      }, signal));
      const nextRows = Array.isArray(payload.rows)
        ? dedupeFailedSymbolRows(payload.rows.map((row) => normalizeRow(asRecord(row))))
        : [];
      const nextSummary = asRecord(payload.summary);
      const nextRepeating = Array.isArray(payload.repeatingSymbols)
        ? payload.repeatingSymbols.map((row) => normalizeRepeatingSymbol(asRecord(row))).filter((row) => row.symbol)
        : [];
      setRows(nextRows);
      setRepeatingSymbols(nextRepeating);
      setSelectedRepeatSymbol((current) => (nextRepeating.some((row) => row.symbol === current) ? current : ''));
      setSelectedRowKeys((current) => {
        const retained = new Set<string>();
        nextRows.forEach((row) => {
          const rowKey = failedSymbolRowKey(row);
          if (current.has(rowKey)) retained.add(rowKey);
        });
        return retained;
      });
      setTotalCount(Number(payload.totalCount ?? 0) || 0);
      setSummary({
        totalFailed: Number(nextSummary.totalFailed ?? 0) || 0,
        totalSkipped: Number(nextSummary.totalSkipped ?? 0) || 0,
        totalRejected: Number(nextSummary.totalRejected ?? 0) || 0,
        pendingRerun: Number(nextSummary.pendingRerun ?? 0) || 0,
        rerunSuccess: Number(nextSummary.rerunSuccess ?? 0) || 0,
        rerunFailed: Number(nextSummary.rerunFailed ?? 0) || 0,
      });
    } catch (loadError) {
      if (signal?.aborted) return;
      setRows([]);
      setRepeatingSymbols([]);
      setSelectedRepeatSymbol('');
      setTotalCount(0);
      setSummary(DEFAULT_SUMMARY);
      setError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void loadRows(page, filters, controller.signal);
    return () => controller.abort();
  }, [page]);

  const visibleRowKeys = useMemo(
    () => rows.map((row) => failedSymbolRowKey(row)),
    [rows],
  );
  const allVisibleSelected = Boolean(visibleRowKeys.length) && visibleRowKeys.every((rowKey) => selectedRowKeys.has(rowKey));
  const partiallySelected = visibleRowKeys.some((rowKey) => selectedRowKeys.has(rowKey)) && !allVisibleSelected;
  const selectedRows = useMemo(
    () => rows.filter((row) => selectedRowKeys.has(failedSymbolRowKey(row))),
    [rows, selectedRowKeys],
  );
  const selectedRepeatEntry = useMemo(
    () => repeatingSymbols.find((row) => row.symbol === selectedRepeatSymbol) || null,
    [repeatingSymbols, selectedRepeatSymbol],
  );

  const kpis = useMemo(() => ([
    { className: 'fyers-failed-kpi fyers-failed-kpi--failed', label: 'Total Failed', value: summary.totalFailed.toLocaleString('en-IN') },
    { className: 'fyers-failed-kpi fyers-failed-kpi--skipped', label: 'Total Skipped', value: summary.totalSkipped.toLocaleString('en-IN') },
    { className: 'fyers-failed-kpi fyers-failed-kpi--rejected', label: 'Total Rejected', value: summary.totalRejected.toLocaleString('en-IN') },
    { className: 'fyers-failed-kpi fyers-failed-kpi--pending', label: 'Pending Re-Run', value: summary.pendingRerun.toLocaleString('en-IN') },
    { className: 'fyers-failed-kpi fyers-failed-kpi--success', label: 'Re-Run Success', value: summary.rerunSuccess.toLocaleString('en-IN') },
    { className: 'fyers-failed-kpi fyers-failed-kpi--rerun-failed', label: 'Re-Run Failed', value: summary.rerunFailed.toLocaleString('en-IN') },
  ]), [summary]);

  function toggleVisibleSelection(checked: boolean) {
    setSelectedRowKeys(() => (checked ? new Set(visibleRowKeys) : new Set()));
  }

  function copyToClipboard(text: string, label: string) {
    if (!navigator.clipboard) {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand('copy');
        setToast(withFyersToast('Copied', `${label} copied to clipboard`, 'success'));
      } catch (err) {
        setToast(withFyersToast('Error', `Failed to copy ${label}`, 'danger'));
      }
      document.body.removeChild(textarea);
      return;
    }
    navigator.clipboard.writeText(text).then(
      () => {
        setToast(withFyersToast('Copied', `${label} copied to clipboard`, 'success'));
      },
      () => {
        setToast(withFyersToast('Error', `Failed to copy ${label}`, 'danger'));
      }
    );
  }

  function downloadTxtFile(text: string, filename: string, label: string) {
    const element = document.createElement('a');
    const file = new Blob([text], { type: 'text/plain' });
    element.href = URL.createObjectURL(file);
    element.download = filename;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
    setToast(withFyersToast('Downloaded', `${label} file downloaded`, 'success'));
  }

  async function handleCopyAllFailedSymbols() {
    setLoading(true);
    try {
      const payload = asRecord(await fetchFyersFailedSymbols({
        limit: 100000,
        offset: 0,
        status: filters.status || undefined,
        symbol: filters.symbol || undefined,
        from_date: filters.fromDate || undefined,
        to_date: filters.toDate || undefined,
        source_mode: filters.sourceMode || undefined,
      }));
      const allRows = Array.isArray(payload.rows) ? payload.rows.map((r) => normalizeRow(asRecord(r))) : [];
      const symbols = Array.from(new Set(allRows.map(r => r.symbol))).join(',');
      if (!symbols) {
        setToast(withFyersToast('Copy Failed', 'No failed symbols found to copy.', 'warn'));
        return;
      }
      copyToClipboard(symbols, 'All filtered failed symbols');
    } catch (err) {
      setToast(withFyersToast('Copy Failed', err instanceof Error ? err.message : String(err), 'danger'));
    } finally {
      setLoading(false);
    }
  }

  async function handleDownloadAllFailedSymbols() {
    setLoading(true);
    try {
      const payload = asRecord(await fetchFyersFailedSymbols({
        limit: 100000,
        offset: 0,
        status: filters.status || undefined,
        symbol: filters.symbol || undefined,
        from_date: filters.fromDate || undefined,
        to_date: filters.toDate || undefined,
        source_mode: filters.sourceMode || undefined,
      }));
      const allRows = Array.isArray(payload.rows) ? payload.rows.map((r) => normalizeRow(asRecord(r))) : [];
      const symbols = Array.from(new Set(allRows.map(r => r.symbol))).join(',');
      if (!symbols) {
        setToast(withFyersToast('Download Failed', 'No failed symbols found to download.', 'warn'));
        return;
      }
      downloadTxtFile(symbols, 'failed_symbols.txt', 'All filtered failed symbols');
    } catch (err) {
      setToast(withFyersToast('Download Failed', err instanceof Error ? err.message : String(err), 'danger'));
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(targetRows: FailedSymbolRow[]) {
    const rowIds = Array.from(new Set(targetRows.map((row) => row.row_id).filter((rowId) => rowId > 0)));
    const rowLocators = Array.from(
      new Map(
        targetRows
          .map((row) => {
            const symbol = row.symbol?.trim() || '';
            const tradingDate = row.trading_date?.trim() || '';
            if (!symbol || !tradingDate) return null;
            return [`${symbol}-${tradingDate}`, { symbol, tradingDate }];
          })
          .filter((entry): entry is [string, { symbol: string; tradingDate: string }] => Boolean(entry)),
      ).values(),
    );
    if (!rowIds.length && !rowLocators.length) {
      setToast(withFyersToast('Delete Skipped', 'No valid failed-symbol rows were selected for delete.', 'warn'));
      return;
    }
    const isSingle = targetRows.length === 1;
    const confirmMessage = isSingle
      ? `Delete ${targetRows[0]?.symbol || 'selected symbol'} from failed symbols?`
      : `Delete ${rowIds.length} selected failed symbol row(s)?`;
    if (!window.confirm(confirmMessage)) return;

    const busyKey = isSingle ? `row-${rowIds[0]}` : 'bulk';
    setDeleteBusyKey(busyKey);
    setError('');
    try {
      const payload = asRecord(await deleteFyersFailedSymbols({ rowIds, rowLocators }));
      const deletedCount = Number(payload.deletedCount ?? targetRows.length) || targetRows.length;
      setSelectedRowKeys((current) => {
        const next = new Set(current);
        targetRows.forEach((row) => next.delete(failedSymbolRowKey(row)));
        return next;
      });
      await loadRows(page, filters);
      setToast(withFyersToast('Delete Complete', safeLegacyText(payload.message, `${deletedCount} failed symbol row(s) deleted.`), 'success'));
      setRerunLogText((current) => {
        const stamp = formatFyersDateTime(new Date().toISOString());
        const nextLine = `[${stamp}] Deleted failed-symbol rows: ${deletedCount.toLocaleString('en-IN')}`;
        return current ? `${nextLine}\n${current}` : nextLine;
      });
    } catch (deleteError) {
      const message = deleteError instanceof Error ? deleteError.message : String(deleteError);
      setToast(withFyersToast('Delete Failed', message, 'danger'));
    } finally {
      setDeleteBusyKey('');
    }
  }

  async function runRerun(payload: Record<string, unknown>, busyKey: string, runningLabel: string) {
    if (pollControllerRef.current) {
      pollControllerRef.current.abort();
      pollControllerRef.current = null;
    }
    setRerunBusyKey(busyKey);
    setActiveRerunJobId('');
    const startedAtIso = new Date().toISOString();
    setRerunLogText(`[${formatFyersDateTime(startedAtIso)}] ${runningLabel}\nStatus: RUNNING`);
    const controller = new AbortController();
    pollControllerRef.current = controller;
    try {
      const started = asRecord(await startFyersFailedSymbolsRerunJob(payload));
      const startedAuthToast = getFyersAuthExpiredToast(started);
      if (startedAuthToast) {
        setToast(withFyersToast('Authorization Required', startedAuthToast, 'danger'));
      }
      const jobId = safeLegacyText(pickField(started, ['jobId', 'job_id']), '');
      if (!jobId) throw new Error(getFyersStatusMessage(started, 'Failed to start failed-symbols re-run job.'));
      setActiveRerunJobId(jobId);

      while (!controller.signal.aborted) {
        const payloadJob = await fetchFyersJob(jobId, controller.signal);
        const currentJob = readPayloadData(payloadJob);
        const logLines = jobLogLines(currentJob);
        setRerunLogText(logLines.length ? logLines.join('\n') : safeLegacyText(currentJob.message, runningLabel));
        const normalizedStatus = safeLegacyText(currentJob.status, '').toUpperCase();
        const done = currentJob.done === true || TERMINAL_JOB_STATUSES.has(normalizedStatus);
        if (!done) {
          await new Promise((resolve) => window.setTimeout(resolve, POLL_MS));
          continue;
        }

        const resultPayload = asRecord(currentJob.result);
        const finalPayload = Object.keys(resultPayload).length ? resultPayload : currentJob;
        const authToast = getFyersAuthExpiredToast(finalPayload);
        const stats = asRecord(finalPayload.stats);
        const details = asRecord(finalPayload.details);
        const inserted = Number(stats.inserted ?? 0) || 0;
        const skipped = Number(stats.skipped ?? 0) || 0;
        const failed = Number(stats.failed ?? 0) || 0;
        const deletedSuccessRows = Number(stats.deletedSuccessRows ?? details.deletedSuccessRows ?? 0) || 0;
        if (authToast) {
          setToast(withFyersToast('Authorization Required', authToast, 'danger'));
        } else {
          const tone = finalPayload.ok === false || failed > 0 ? (inserted > 0 || skipped > 0 ? 'warn' : 'danger') : 'success';
          const failureReasons = collectRerunFailureReasons(finalPayload);
          const previewReason = failureReasons.length ? ` Reason: ${failureReasons[0]}` : '';
          setToast(withFyersToast(
            'Re-Run Summary',
            `Inserted ${inserted}, skipped ${skipped}, failed ${failed}, removed ${deletedSuccessRows} successful rows.${previewReason}`,
            tone,
          ));
        }
        const finalSummaryLog = buildRerunLog(runningLabel, finalPayload, startedAtIso);
        setRerunLogText(logLines.length ? `${logLines.join('\n')}\n\n${finalSummaryLog}` : finalSummaryLog);
        setSelectedRowKeys(new Set<string>());
        await loadRows(page, filters);
        return;
      }
    } catch (rerunError) {
      if (controller.signal.aborted) return;
      const message = rerunError instanceof Error ? rerunError.message : String(rerunError);
      const description = message.includes(FYERS_AUTH_EXPIRED_TOAST) ? FYERS_AUTH_EXPIRED_TOAST : message;
      setToast(withFyersToast('Re-Run Failed', description, description === FYERS_AUTH_EXPIRED_TOAST ? 'danger' : 'warn'));
      setRerunLogText(
        `[${formatFyersDateTime(startedAtIso)}] ${runningLabel}\nStatus: FAILED\nReason: ${description}`,
      );
    } finally {
      if (pollControllerRef.current === controller) {
        pollControllerRef.current = null;
      }
      setRerunBusyKey('');
      setActiveRerunJobId('');
    }
  }

  async function handleRerun(targetRows: FailedSymbolRow[]) {
    if (!targetRows.length) return;
    const rowIds = targetRows.map((row) => row.row_id).filter((rowId) => rowId > 0);
    const symbols = targetRows.map((row) => row.symbol).filter(Boolean);
    const singleRow = targetRows.length === 1 ? targetRows[0] : null;
    const selectedDates = Array.from(new Set(targetRows.map((row) => row.trading_date).filter(Boolean)));
    const sharedTradingDate = selectedDates.length === 1 ? selectedDates[0] : '';
    await runRerun(
      {
        rowIds,
        symbols,
        from_date: singleRow?.trading_date || sharedTradingDate || undefined,
        to_date: singleRow?.trading_date || sharedTradingDate || undefined,
        mode: 'SINGLE_STOCK_RERUN',
      },
      singleRow ? `row-${singleRow.row_id}` : 'bulk',
      singleRow ? `Re-running ${singleRow.symbol}` : 'Re-running selected symbols',
    );
  }

  async function handleRerunAllFiltered() {
    await runRerun(
      {
        rerunAll: true,
        mode: 'SINGLE_STOCK_RERUN_ALL',
        filters: {
          status: filters.status || undefined,
          symbol: filters.symbol || undefined,
          from_date: filters.fromDate || undefined,
          to_date: filters.toDate || undefined,
          source_mode: filters.sourceMode || undefined,
        },
      },
      'all',
      'Re-running all filtered symbols',
    );
  }

  async function handleRerunRepeatingSymbol() {
    if (!selectedRepeatSymbol) return;
    await runRerun(
      {
        symbols: [selectedRepeatSymbol],
        mode: 'SINGLE_STOCK_RERUN_MULTI_DATE',
      },
      'repeat-symbol',
      `Re-running ${selectedRepeatSymbol} for all failed dates`,
    );
  }

  const columns = useMemo<Array<AppDataTableColumn<FailedSymbolRow>>>(() => [
    {
      dataCol: 'select',
      getSortValue: () => null,
      key: 'select',
      label: (
        <SelectAllCheckbox
          checked={allVisibleSelected}
          indeterminate={partiallySelected}
          onChange={toggleVisibleSelection}
        />
      ),
      renderCell: (row) => (
        <input
          className="fyers-checkbox"
          type="checkbox"
          checked={selectedRowKeys.has(failedSymbolRowKey(row))}
          onChange={(event) => {
            const checked = event.currentTarget.checked;
            setSelectedRowKeys((current) => {
              const next = new Set(current);
              const rowKey = failedSymbolRowKey(row);
              if (checked) next.add(rowKey);
              else next.delete(rowKey);
              return next;
            });
          }}
          aria-label={`Select ${row.symbol}`}
        />
      ),
      sortType: 'string',
    },
    {
      dataCol: 'sno',
      getSortValue: () => null,
      key: 'sno',
      label: 'S.NO',
      renderCell: (row) => ((page - 1) * PAGE_SIZE + rows.findIndex((item) => failedSymbolRowKey(item) === failedSymbolRowKey(row)) + 1).toLocaleString('en-IN'),
      sortType: 'number',
      sticky: true,
      stickyWidthPx: 88,
    },
    {
      dataCol: 'symbol',
      getSortValue: (row) => row.symbol,
      key: 'symbol',
      label: 'SYMBOL',
      renderCell: (row) => <strong>{row.symbol}</strong>,
      sortType: 'string',
      sticky: true,
      stickyWidthPx: 180,
    },
    {
      dataCol: 'trading_date',
      getSortValue: (row) => row.trading_date,
      key: 'trading_date',
      label: 'TRADING_DATE',
      renderCell: (row) => row.trading_date || '-',
      sortType: 'date',
    },
    {
      dataCol: 'td_count',
      getSortValue: (row) => row.td_count,
      key: 'td_count',
      label: 'TD_COUNT',
      renderCell: (row) => row.td_count.toLocaleString('en-IN'),
      sortType: 'number',
    },
    {
      dataCol: 'symbol_month_failed_td_count',
      getSortValue: (row) => row.symbol_month_failed_td_count,
      key: 'symbol_month_failed_td_count',
      label: 'MONTH FAILED TD COUNT',
      renderCell: (row) => row.symbol_month_failed_td_count.toLocaleString('en-IN'),
      sortType: 'number',
    },
    {
      dataCol: 'month_max_td_count',
      getSortValue: (row) => row.month_max_td_count,
      key: 'month_max_td_count',
      label: 'MONTH MAX TD COUNT',
      renderCell: (row) => row.month_max_td_count.toLocaleString('en-IN'),
      sortType: 'number',
    },
    {
      dataCol: 'td_flag',
      getSortValue: (row) => row.td_flag,
      key: 'td_flag',
      label: 'FLAG',
      renderCell: (row) => <span className={tdFlagBadgeClass(row.td_flag)}>{row.td_flag}</span>,
      sortType: 'string',
    },
    {
      dataCol: 'reason_error_message',
      getSortValue: (row) => row.reason_error_message,
      key: 'reason_error_message',
      label: 'REASON / ERROR MESSAGE',
      renderCell: (row) => (
        <span className="fyers-failed-symbols__message" title={row.reason_error_message}>
          {row.reason_error_message || '-'}
        </span>
      ),
      sortType: 'string',
    },
    {
      dataCol: 'action',
      getSortValue: (row) => row.symbol,
      key: 'action',
      label: 'RE-RUN',
      renderCell: (row) => (
        <Button
          size="sm"
          variant="secondary"
          type="button"
          disabled={loading || Boolean(rerunBusyKey) || Boolean(deleteBusyKey)}
          onClick={() => { void handleRerun([row]); }}
        >
          {rerunBusyKey === `row-${row.row_id}` ? 'Re-Running...' : 'Re-Run'}
        </Button>
      ),
      sortType: 'string',
    },
    {
      dataCol: 'delete_action',
      getSortValue: (row) => row.symbol,
      key: 'delete_action',
      label: 'ACTION',
      renderCell: (row) => (
        <Button
          aria-label={`Delete ${row.symbol}`}
          className="h-9 w-9 rounded-full px-0"
          size="sm"
          variant="danger"
          type="button"
          disabled={loading || Boolean(rerunBusyKey) || Boolean(deleteBusyKey)}
          leadingIcon={<TrashIcon className="h-4 w-4" />}
          onClick={() => { void handleDelete([row]); }}
        >
          {deleteBusyKey === `row-${row.row_id}` ? '...' : ''}
        </Button>
      ),
      sortType: 'string',
    },
  ], [allVisibleSelected, deleteBusyKey, filters, handleRerun, loading, page, partiallySelected, rerunBusyKey, rows, selectedRowKeys, toggleVisibleSelection, visibleRowKeys]);

  return (
    <FyersMigrationLayout activeFyersPage="/app/fyers/failed-symbols" className="fyers-failed-symbols-page">
      <PageHero title="UNIFORM_DATA" />

      <section className="card database-fyers-card">
        <div className="database-fyers-card__header">
          <div>
            <h2>Uniform_Data</h2>
            <p className="fyers-react-subtitle">Review failed symbols, re-run all at once, or re-run one symbol across multiple failed dates using the existing single-stock insertion flow.</p>
          </div>
          <span className={`database-badge database-badge--${loading ? 'loading' : 'ok'}`}>{loading ? 'Refreshing' : 'Ready'}</span>
        </div>

        <KpiGrid items={kpis} />

        <section className="database-fyers-block fyers-failed-filters">
          <div className="fyers-failed-filters__grid">
            <label className="database-react-field">
              <span>Symbol Search</span>
              <Input
                variant="light"
                value={filters.symbol}
                placeholder="RELIANCE, TCS, NSE:SBIN-EQ"
                onChange={(event) => setFilters((current) => ({ ...current, symbol: event.currentTarget.value.toUpperCase() }))}
              />
            </label>
            <label className="database-react-field">
              <span>Status</span>
              <Select
                variant="light"
                value={filters.status}
                onChange={(event) => setFilters((current) => ({ ...current, status: event.currentTarget.value }))}
              >
                <option value="">All statuses</option>
                <option value="FAILED">FAILED</option>
                <option value="SKIPPED">SKIPPED</option>
                <option value="REJECTED">REJECTED</option>
                <option value="AUTH_FAILED">AUTH_FAILED</option>
                <option value="NO_DATA">NO_DATA</option>
                <option value="API_ERROR">API_ERROR</option>
              </Select>
            </label>
            <label className="database-react-field">
              <span>Source Mode</span>
              <Select
                variant="light"
                value={filters.sourceMode}
                onChange={(event) => setFilters((current) => ({ ...current, sourceMode: event.currentTarget.value }))}
              >
                <option value="">All sources</option>
                <option value="CSV_BATCH">CSV_BATCH</option>
                <option value="SINGLE_STOCK">SINGLE_STOCK</option>
                <option value="AUTO_BATCH">AUTO_BATCH</option>
                <option value="SINGLE_STOCK_RERUN">SINGLE_STOCK_RERUN</option>
              </Select>
            </label>
            <FyersDatePickerField
              allowEmpty
              label="From Date"
              value={filters.fromDate}
              onChange={(value) => setFilters((current) => ({ ...current, fromDate: value }))}
            />
            <FyersDatePickerField
              allowEmpty
              label="To Date"
              value={filters.toDate}
              onChange={(value) => setFilters((current) => ({ ...current, toDate: value }))}
            />
          </div>
          <div className="fyers-react-actions">
            <Button
              type="button"
              variant="secondary"
              disabled={loading}
              onClick={() => {
                setPage(1);
                void loadRows(1, filters);
              }}
            >
              Refresh
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={loading}
              onClick={() => {
                setFilters(EMPTY_FILTERS);
                setPage(1);
                setSelectedRowKeys(new Set());
                setSelectedRepeatSymbol('');
                void loadRows(1, EMPTY_FILTERS);
              }}
            >
              Reset
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={loading || !visibleRowKeys.length || Boolean(rerunBusyKey)}
              onClick={() => toggleVisibleSelection(!allVisibleSelected)}
            >
              {allVisibleSelected ? 'Uncheck All' : 'Check All'}
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={loading || Boolean(rerunBusyKey) || !totalCount}
              onClick={() => { void handleRerunAllFiltered(); }}
            >
              {rerunBusyKey === 'all' ? 'Re-Running All...' : 'Re-Run All Symbols'}
            </Button>
            <Button
              type="button"
              variant="primary"
              disabled={loading || Boolean(rerunBusyKey) || Boolean(deleteBusyKey) || !selectedRows.length}
              onClick={() => { void handleRerun(selectedRows); }}
            >
              {rerunBusyKey === 'bulk' ? 'Re-Running Selected...' : 'Re-Run Selected Symbols'}
            </Button>
            <Button
              type="button"
              variant="danger"
              disabled={loading || Boolean(rerunBusyKey) || Boolean(deleteBusyKey) || !selectedRows.length}
              leadingIcon={<TrashIcon className="h-4 w-4" />}
              onClick={() => { void handleDelete(selectedRows); }}
            >
              {deleteBusyKey === 'bulk' ? 'Deleting Selected...' : 'Delete Selected Symbols'}
            </Button>
          </div>
        </section>

        <section className="database-fyers-block fyers-failed-repeat">
          <div className="fyers-failed-repeat__header">
            <div>
              <h3>Repeating Failed Symbols</h3>
              <p>Select one symbol to re-run it across all failed dates/windows.</p>
            </div>
            <span className="count-pill">{repeatingSymbols.length.toLocaleString('en-IN')}</span>
          </div>
          <div className="fyers-react-form-grid fyers-react-form-grid--wide">
            <label className="database-react-field">
              <span>Symbol (Multiple Dates)</span>
              <Select
                variant="light"
                value={selectedRepeatSymbol}
                onChange={(event) => setSelectedRepeatSymbol(event.currentTarget.value)}
              >
                <option value="">Select repeating symbol</option>
                {repeatingSymbols.map((item) => (
                  <option key={item.symbol} value={item.symbol}>
                    {item.symbol} ({item.occurrences.toLocaleString('en-IN')})
                  </option>
                ))}
              </Select>
            </label>
            <label className="database-react-field">
              <span>Failed Dates</span>
              <Input
                variant="light"
                value={selectedRepeatEntry?.failed_dates || `${selectedRepeatEntry?.from_date || '-'} to ${selectedRepeatEntry?.to_date || '-'}`}
                placeholder="No symbol selected"
                readOnly
              />
            </label>
          </div>
          <div className="fyers-react-actions">
            <Button
              type="button"
              variant="primary"
              disabled={loading || Boolean(rerunBusyKey) || !selectedRepeatSymbol}
              onClick={() => { void handleRerunRepeatingSymbol(); }}
            >
              {rerunBusyKey === 'repeat-symbol' ? 'Re-Running Symbol...' : 'Re-Run Repeating Symbol'}
            </Button>
          </div>
        </section>

        {error ? <ErrorAlertCard message={error} /> : null}

        <section className="database-fyers-summary">
          <div className="table-title">
            <h3>Active Re-Run Job</h3>
            <div className="flex items-center gap-2">
              <span className="count-pill">{activeRerunJobId || 'No active job'}</span>
              <CopyTextButton text={rerunLogText} label="Copy logs" />
            </div>
          </div>
          <pre className="database-fyers-log" aria-live="polite">{rerunLogText}</pre>
        </section>

        <section className="database-fyers-summary">
          <div className="table-title flex flex-wrap items-center justify-between gap-3">
            <h3>Uniform_Data Failed Symbols</h3>
            <div className="flex flex-wrap items-center gap-2">
              <span className="count-pill">TOTAL: {totalCount.toLocaleString('en-IN')}</span>
              <span className="count-pill">SELECTED: {selectedRows.length.toLocaleString('en-IN')}</span>
              {selectedRows.length > 0 && (
                <>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="h-8 px-2 text-xs"
                    onClick={() => {
                      const text = Array.from(new Set(selectedRows.map((r) => r.symbol))).join(',');
                      copyToClipboard(text, 'Selected symbols');
                    }}
                  >
                    Copy Selected
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="h-8 px-2 text-xs"
                    onClick={() => {
                      const text = Array.from(new Set(selectedRows.map((r) => r.symbol))).join(',');
                      downloadTxtFile(text, 'selected_failed_symbols.txt', 'Selected symbols');
                    }}
                  >
                    Download Selected
                  </Button>
                </>
              )}
              {totalCount > 0 && (
                <>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="h-8 px-2 text-xs"
                    onClick={() => { void handleCopyAllFailedSymbols(); }}
                  >
                    Copy All Filtered
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="h-8 px-2 text-xs"
                    onClick={() => { void handleDownloadAllFailedSymbols(); }}
                  >
                    Download All Filtered
                  </Button>
                </>
              )}
            </div>
          </div>

          {loading ? (
            <div className="empty">Loading failed/skipped/rejected symbols...</div>
          ) : (
            <AppDataTable
              className="fyers-failed-symbols__table"
              columns={columns}
              currentPage={page}
              disableClientSort
              emptyMessage="No failed/skipped/rejected symbols found."
              getRowKey={(row) => failedSymbolRowKey(row)}
              onPageChange={setPage}
              pageSize={PAGE_SIZE}
              paginationSummaryLabel="failed symbols"
              rows={rows}
              showTopPagination
              tableClassName="fyers-failed-symbols__table-inner"
              tableId="fyers-failed-symbols-table"
              totalRows={totalCount}
            />
          )}
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
