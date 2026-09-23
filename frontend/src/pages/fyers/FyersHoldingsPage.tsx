import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { AppToolbar } from '../../components/app/AppToolbar';
import { TechnicalMarketCapCell } from '../../components/app/TechnicalMarketCapCell';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { Toast } from '../../components/ui/Toast';
import { getMarketCapCategory, MARKET_CAP_INDEX_ALIASES, type MarketCapCategory } from '../../adapters/technicalMarketCap';
import {
  asRecord,
  formatLegacyCount,
  pickField,
  safeLegacyText,
  type UnknownRecord,
} from '../../adapters/databasePageAdapter';
import {
  buildCsvDownload,
  extractFyersRows,
  extractFyersStats,
  formatFyersCell,
  getFyersStatusMessage,
  pickFyersField,
} from '../../adapters/fyersPageAdapter';
import {
  createFyersHolding,
  deleteFyersHolding,
  fetchFyersHoldings,
  fetchFyersHoldingsImports,
  fetchFyersHoldingsReconciliation,
  fetchFyersHoldingsSummary,
  importFyersHoldings,
  updateFyersHolding,
} from '../../services/api/fyersApi';
import { ActionButton, KpiGrid, PageHero, SearchInput, TextField } from '../ops/opsPageHelpers';
import { FyersMigrationLayout } from './FyersMigrationLayout';
import { withFyersToast, type FyersPageToast } from './fyersPageUtils';

type LoadStatus = 'error' | 'loading' | 'online';

type HoldingForm = {
  buyPrice: string;
  currentValue: string;
  investedValue: string;
  isin: string;
  previousClose: string;
  quantity: string;
  symbol: string;
  unrealisedPnl: string;
  unrealisedPnlPct: string;
};

const emptyForm: HoldingForm = {
  buyPrice: '',
  currentValue: '',
  investedValue: '',
  isin: '',
  previousClose: '',
  quantity: '',
  symbol: '',
  unrealisedPnl: '',
  unrealisedPnlPct: '',
};

const holdingColumns = [
  { aliases: ['symbolRaw', 'symbol', 'symbolCode', 'SYMBOL'], dataCol: 'symbol', label: 'Symbol', kind: 'text' },
  { aliases: ['INDEX', 'index', 'mcapIndex', 'mcap_index'], dataCol: 'index', label: 'INDEX', kind: 'text' },
  { aliases: ['MCAP', 'mcap', 'marketCapCrores', 'market_cap_crores'], dataCol: 'mcap', label: 'MCAP', kind: 'number' },
  { aliases: ['MCAP_RANK', 'mcapRank', 'mcap_rank'], dataCol: 'mcapRank', label: 'MCAP_RANK', kind: 'count' },
  { aliases: ['score', 'SCORE', 'techScore', 'TECH_SCORE', 'signalScore', 'SIGNAL_SCORE', 'masterScore', 'MASTER_SCORE'], dataCol: 'score', label: 'Score', kind: 'number' },
  { aliases: ['quantity', 'qty'], dataCol: 'quantity', label: 'Qty', kind: 'number' },
  { aliases: ['buyPrice', 'buy_price'], dataCol: 'buyPrice', label: 'Buy Price', kind: 'number' },
  { aliases: ['investedValue', 'invested'], dataCol: 'investedValue', label: 'Invested', kind: 'number' },
  { aliases: ['currentValue', 'current'], dataCol: 'currentValue', label: 'Current', kind: 'number' },
  { aliases: ['unrealisedPnl', 'profitLoss'], dataCol: 'unrealisedPnl', label: 'P&L', kind: 'number' },
  { aliases: ['unrealisedPnlPct'], dataCol: 'unrealisedPnlPct', label: 'P&L %', kind: 'percent' },
  { aliases: ['previousClose'], dataCol: 'previousClose', label: 'Previous Close', kind: 'number' },
  { aliases: ['ema20Flag', 'EMA20_FLAG', 'ema20', 'EMA20'], dataCol: 'ema20', label: 'EMA20', kind: 'text' },
  { aliases: ['ema50Flag', 'EMA50_FLAG', 'ema50', 'EMA50'], dataCol: 'ema50', label: 'EMA50', kind: 'text' },
  { aliases: ['ema100Flag', 'EMA100_FLAG', 'ema100', 'EMA100'], dataCol: 'ema100', label: 'EMA100', kind: 'text' },
  { aliases: ['ema200Flag', 'EMA200_FLAG', 'ema200', 'EMA200'], dataCol: 'ema200', label: 'EMA200', kind: 'text' },
  { aliases: ['macdAboveZero', 'MACD_ABOVE_ZERO', 'macdFlag', 'MACD_FLAG'], dataCol: 'macdAboveZero', label: 'MACD>0', kind: 'text' },
  { aliases: ['rsiAbove50', 'RSI_ABOVE_50', 'rsiFlag', 'RSI_FLAG'], dataCol: 'rsiAbove50', label: 'RSI>50', kind: 'text' },
  { aliases: ['adxAbove25', 'ADX_ABOVE_25', 'adxFlag', 'ADX_FLAG'], dataCol: 'adxAbove25', label: 'ADX>25', kind: 'text' },
  { aliases: ['atrAbove14', 'ATR_ABOVE_14', 'atrFlag', 'ATR_FLAG'], dataCol: 'atrAbove14', label: 'ATR>14', kind: 'text' },
  { aliases: ['volumeAbove20', 'VOLUME_ABOVE_20', 'volumeFlag', 'VOLUME_FLAG'], dataCol: 'volumeAbove20', label: 'VOLUME>20', kind: 'text' },
  { aliases: ['fiftyTwoWeekLow', 'low52w'], dataCol: 'fiftyTwoWeekLow', label: '52WL', kind: 'number' },
  { aliases: ['fiftyTwoWeekHigh', 'high52w'], dataCol: 'fiftyTwoWeekHigh', label: '52WH', kind: 'number' },
  { aliases: ['ath', 'ATH'], dataCol: 'ath', label: 'ATH', kind: 'number' },
  { aliases: ['supportDisplay', 'support'], dataCol: 'supportDisplay', label: 'SUPPORT', kind: 'text' },
  { aliases: ['resistanceDisplay', 'resistance'], dataCol: 'resistanceDisplay', label: 'RESISTANCE', kind: 'text' },
  { aliases: ['trendDirection', 'trend_direction', 'TREND_DIRECTION', 'trend', 'TREND', 'masterTrend', 'MASTER_TREND'], dataCol: 'trendDirection', label: 'TREND_DIRECTION', kind: 'text' },
  { aliases: ['isin', 'ISIN'], dataCol: 'isin', label: 'ISIN', kind: 'text' },
] as const;

const marketCapToneLabels = new Set(['Symbol', 'INDEX', 'MCAP', 'MCAP_RANK']);
const indicatorColumnKeys = new Set(['ema20', 'ema50', 'ema100', 'ema200', 'macdAboveZero', 'rsiAbove50', 'adxAbove25', 'atrAbove14', 'volumeAbove20']);
const centeredCellClassName = 'px-4 py-3 text-center align-middle';
const tonePillBaseClassName = 'inline-flex items-center justify-center rounded-full border px-2.5 py-1 text-[12px] font-semibold leading-none whitespace-nowrap';
const positiveValueClassName = `${tonePillBaseClassName} border-emerald/25 bg-emerald/10 text-emerald dark:border-emerald/30 dark:bg-emerald/10 dark:text-emerald`;
const negativeValueClassName = `${tonePillBaseClassName} border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800/70 dark:bg-rose-950/35 dark:text-rose-200`;
const sidewaysValueClassName = `${tonePillBaseClassName} border-amber/20 bg-amber/10 text-amber`;
const consolidationValueClassName = `${tonePillBaseClassName} border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-700/70 dark:bg-orange-950/30 dark:text-orange-200`;
const holdingsFormPanelId = 'fyers-holdings-form-panel';
const reconciliationMismatchStatuses = new Set([
  'MISMATCH',
  'MISSING_LTP',
  'MISSING_PREVIOUS_CLOSE',
  'MISSING_AVG_PRICE',
  'MISSING_QTY',
  'SYMBOL_MAPPING_ISSUE',
  'STALE_PRICE',
  'CORPORATE_ACTION_CHECK_REQUIRED',
]);
const reconciliationColumns = [
  { aliases: ['serialNumber'], dataCol: 'serialNumber', label: 'S.NO', kind: 'count' },
  { aliases: ['symbol', 'symbolRaw'], dataCol: 'symbol', label: 'SYMBOL', kind: 'text' },
  { aliases: ['qty'], dataCol: 'qty', label: 'Qty', kind: 'number' },
  { aliases: ['avgPrice'], dataCol: 'avgPrice', label: 'Avg Price', kind: 'number' },
  { aliases: ['investedValueApp'], dataCol: 'investedValueApp', label: 'Invested App', kind: 'number' },
  { aliases: ['investedValueRecalculated'], dataCol: 'investedValueRecalculated', label: 'Invested Recalc', kind: 'number' },
  { aliases: ['ltp'], dataCol: 'ltp', label: 'LTP', kind: 'number' },
  { aliases: ['previousClose'], dataCol: 'previousClose', label: 'Previous Close', kind: 'number' },
  { aliases: ['currentValueApp'], dataCol: 'currentValueApp', label: 'Current App', kind: 'number' },
  { aliases: ['currentValueRecalculated'], dataCol: 'currentValueRecalculated', label: 'Current Recalc', kind: 'number' },
  { aliases: ['totalPnlApp'], dataCol: 'totalPnlApp', label: 'Total P&L App', kind: 'number' },
  { aliases: ['totalPnlRecalculated'], dataCol: 'totalPnlRecalculated', label: 'Total P&L Recalc', kind: 'number' },
  { aliases: ['totalPnlPercentApp'], dataCol: 'totalPnlPercentApp', label: 'Total P&L % App', kind: 'percent' },
  { aliases: ['totalPnlPercentRecalculated'], dataCol: 'totalPnlPercentRecalculated', label: 'Total P&L % Recalc', kind: 'percent' },
  { aliases: ['dayPnlApp'], dataCol: 'dayPnlApp', label: 'Day P&L App', kind: 'number' },
  { aliases: ['dayPnlRecalculated'], dataCol: 'dayPnlRecalculated', label: 'Day P&L Recalc', kind: 'number' },
  { aliases: ['dayPnlPercentApp'], dataCol: 'dayPnlPercentApp', label: 'Day P&L % App', kind: 'percent' },
  { aliases: ['dayPnlPercentRecalculated'], dataCol: 'dayPnlPercentRecalculated', label: 'Day P&L % Recalc', kind: 'percent' },
  { aliases: ['differenceAmount'], dataCol: 'differenceAmount', label: 'Diff Amount', kind: 'number' },
  { aliases: ['differencePercent'], dataCol: 'differencePercent', label: 'Diff %', kind: 'percent' },
  { aliases: ['dataSourceUsed'], dataCol: 'dataSourceUsed', label: 'Data Source Used', kind: 'text' },
  { aliases: ['dataDate', 'lastUpdated'], dataCol: 'dataDate', label: 'Data Date', kind: 'text' },
  { aliases: ['status'], dataCol: 'status', label: 'Status', kind: 'text' },
] as const;

function toNumberOrNull(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function formToPayload(form: HoldingForm) {
  return {
    buyPrice: toNumberOrNull(form.buyPrice),
    currentValue: toNumberOrNull(form.currentValue),
    investedValue: toNumberOrNull(form.investedValue),
    isin: form.isin.trim(),
    previousClose: toNumberOrNull(form.previousClose),
    quantity: toNumberOrNull(form.quantity),
    symbol: form.symbol.trim(),
    symbolRaw: form.symbol.trim(),
    unrealisedPnl: toNumberOrNull(form.unrealisedPnl),
    unrealisedPnlPct: toNumberOrNull(form.unrealisedPnlPct),
  };
}

function numericValue(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const text = safeLegacyText(value, '').trim();
  if (!text || text === '-' || text === '--') return null;
  const normalized = text.replace(/[^0-9.+-]/g, '');
  if (!normalized || ['+', '-', '.', '+.', '-.'].includes(normalized)) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function pnlKpiClass(value: unknown, base: string) {
  const parsed = numericValue(value);
  if (parsed === null || parsed === 0) return `${base} fyers-kpi-card--neutral`;
  return parsed > 0 ? `${base} fyers-kpi-card--profit` : `${base} fyers-kpi-card--loss`;
}

function formatCountValue(value: unknown): string | null {
  const parsed = numericValue(value);
  if (parsed === null) return null;
  return Math.trunc(parsed).toLocaleString('en-IN');
}

function normalizeDisplayToken(value: unknown): string {
  const text = safeLegacyText(value, '').trim();
  if (!text || text === '-' || text === '--') return '';
  return text.toUpperCase();
}

function getProfitLossClass(value: unknown) {
  const parsed = numericValue(value);
  if (parsed === null || parsed === 0) return '';
  return parsed > 0 ? positiveValueClassName : negativeValueClassName;
}

function getCurrentVsInvestedClass(invested: unknown, current: unknown) {
  const investedValue = numericValue(invested);
  const currentValue = numericValue(current);
  if (investedValue === null || currentValue === null || investedValue === currentValue) return '';
  return currentValue > investedValue ? positiveValueClassName : negativeValueClassName;
}

function getYesNoClass(value: unknown) {
  const normalized = normalizeDisplayToken(formatFyersCell(value, 'text'));
  if (!normalized) return '';
  if (normalized === 'YES') return positiveValueClassName;
  if (normalized === 'NO') return negativeValueClassName;
  return '';
}

function getTrendDirectionClass(value: unknown) {
  const normalized = safeLegacyText(value, '').trim().toLowerCase();
  if (!normalized || normalized === '-' || normalized === '--') return '';
  if (normalized === 'uptrend') return positiveValueClassName;
  if (normalized === 'downtrend') return negativeValueClassName;
  if (normalized === 'sideways') return sidewaysValueClassName;
  if (normalized === 'consolidation') return consolidationValueClassName;
  return '';
}

type HoldingColumn = (typeof holdingColumns)[number];

function getHoldingValueClass(column: HoldingColumn, row: UnknownRecord, rawValue: unknown) {
  if (column.dataCol === 'currentValue') {
    return getCurrentVsInvestedClass(
      pickFyersField(row, ['investedValue', 'invested']),
      rawValue,
    );
  }
  if (column.dataCol === 'unrealisedPnl' || column.dataCol === 'unrealisedPnlPct') {
    return getProfitLossClass(rawValue);
  }
  if (indicatorColumnKeys.has(column.dataCol)) {
    return getYesNoClass(rawValue);
  }
  if (column.dataCol === 'trendDirection') {
    return getTrendDirectionClass(rawValue);
  }
  return '';
}

function isSuccessfulImportPayload(payload: UnknownRecord) {
  if (typeof payload.ok === 'boolean') return payload.ok;
  if (typeof payload.success === 'boolean') return payload.success;
  const status = safeLegacyText(pickField(payload, ['status', 'state']), '').trim().toLowerCase();
  if (status) return status === 'success' || status === 'ok';
  return Object.keys(payload).length > 0;
}

function buildImportSuccessDescription(payload: UnknownRecord) {
  const stats = extractFyersStats(payload);
  const backendMessage = safeLegacyText(pickField(payload, ['message', 'detail']), '');
  const countParts = [
    ['Inserted', formatCountValue(pickField(stats, ['inserted', 'insertedCount']))],
    ['Updated', formatCountValue(pickField(stats, ['updated', 'updatedCount']))],
    ['Skipped', formatCountValue(pickField(stats, ['skipped', 'skippedCount', 'unchanged']))],
    ['Deleted', formatCountValue(pickField(stats, ['deleted', 'deletedCount']))],
    ['Failed', formatCountValue(pickField(stats, ['failed', 'errors', 'errorCount', 'failedCount']))],
  ]
    .filter(([, value]) => value !== null)
    .map(([label, value]) => `${label}: ${value}`);
  if (countParts.length) {
    const prefix = backendMessage && backendMessage !== 'FYERS holdings import completed.' ? `${backendMessage}. ` : '';
    return `${prefix}${countParts.join(', ')}`;
  }
  return getFyersStatusMessage(payload, 'Holdings data refreshed.');
}

function buildImportFailureDescription(payload: UnknownRecord) {
  return getFyersStatusMessage(payload, 'CSV import failed. Please check file format or backend logs.');
}

function rowToForm(row: UnknownRecord): HoldingForm {
  const read = (aliases: readonly string[]) => safeLegacyText(pickFyersField(row, aliases, ''), '');
  return {
    buyPrice: read(['buyPrice']),
    currentValue: read(['currentValue']),
    investedValue: read(['investedValue']),
    isin: read(['isin']),
    previousClose: read(['previousClose']),
    quantity: read(['quantity']),
    symbol: read(['symbolRaw', 'symbol', 'symbolCode']),
    unrealisedPnl: read(['unrealisedPnl', 'profitLoss']),
    unrealisedPnlPct: read(['unrealisedPnlPct']),
  };
}

function summaryKpis(summary: UnknownRecord, rows: UnknownRecord[]) {
  const totals = asRecord(summary.liveTotals);
  const profitLoss = pickField(totals, ['profitLoss']);
  const profitLossPct = pickField(totals, ['unrealisedPnlPct']);
  return [
    { className: 'fyers-kpi-card fyers-kpi-card--rows', label: 'Rows', value: formatLegacyCount(pickField(totals, ['rowCount'], rows.length)) },
    { className: 'fyers-kpi-card fyers-kpi-card--invested', label: 'Invested', value: formatFyersCell(pickField(totals, ['totalInvested']), 'number') },
    { className: 'fyers-kpi-card fyers-kpi-card--current', label: 'Current', value: formatFyersCell(pickField(totals, ['totalCurrent']), 'number') },
    { className: pnlKpiClass(profitLoss, 'fyers-kpi-card'), label: 'P&L', value: formatFyersCell(profitLoss, 'number') },
    { className: pnlKpiClass(profitLossPct, 'fyers-kpi-card'), label: 'P&L %', value: formatFyersCell(profitLossPct, 'percent') },
    { className: 'fyers-kpi-card fyers-kpi-card--client', label: 'Client ID', value: safeLegacyText(pickField(summary, ['clientId']), '-') },
  ];
}

function reconciliationSummaryKpis(summary: UnknownRecord) {
  return [
    { className: 'fyers-kpi-card fyers-kpi-card--rows', label: 'Total Symbols', value: formatLegacyCount(pickField(summary, ['totalSymbolsChecked'])) },
    { className: 'fyers-kpi-card fyers-kpi-card--profit', label: 'Matched', value: formatLegacyCount(pickField(summary, ['matchedSymbolsCount'])) },
    { className: 'fyers-kpi-card fyers-kpi-card--loss', label: 'Mismatched', value: formatLegacyCount(pickField(summary, ['mismatchedSymbolsCount'])) },
    { className: 'fyers-kpi-card fyers-kpi-card--neutral', label: 'Missing LTP', value: formatLegacyCount(pickField(summary, ['missingLtpCount'])) },
    { className: 'fyers-kpi-card fyers-kpi-card--neutral', label: 'Missing Previous Close', value: formatLegacyCount(pickField(summary, ['missingPreviousCloseCount'])) },
    { className: 'fyers-kpi-card fyers-kpi-card--neutral', label: 'Stale Price', value: formatLegacyCount(pickField(summary, ['stalePriceCount'])) },
  ];
}

function reconciliationStatus(row: UnknownRecord) {
  return safeLegacyText(pickField(row, ['status']), '').trim().toUpperCase();
}

function reconciliationReason(row: UnknownRecord) {
  const details = row.statusDetails;
  if (Array.isArray(details)) {
    return details.map((item) => safeLegacyText(item, '')).filter(Boolean).join('; ');
  }
  return safeLegacyText(details, '');
}

function marketCapToneForRow(row: UnknownRecord): MarketCapCategory {
  return getMarketCapCategory(pickFyersField(row, MARKET_CAP_INDEX_ALIASES));
}

function shouldUseMarketCapTone(label: string) {
  return marketCapToneLabels.has(label);
}

export function getNextHoldingFormExpandedState(current: boolean, action: 'edit' | 'toggle') {
  return action === 'edit' ? true : !current;
}

export function FyersHoldingsPage() {
  const [editingId, setEditingId] = useState<string>('');
  const [error, setError] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState<HoldingForm>(emptyForm);
  const [imports, setImports] = useState<UnknownRecord[]>([]);
  const [rows, setRows] = useState<UnknownRecord[]>([]);
  const [search, setSearch] = useState('');
  const [reconciliation, setReconciliation] = useState<UnknownRecord | null>(null);
  const [reconcileError, setReconcileError] = useState('');
  const [isReconciling, setReconciling] = useState(false);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [statusMessage, setStatusMessage] = useState('Loading holdings');
  const [summary, setSummary] = useState<UnknownRecord>({});
  const [toast, setToast] = useState<FyersPageToast | null>(null);
  const [isHoldingFormExpanded, setHoldingFormExpanded] = useState(true);
  const deferredSearch = useDeferredValue(search);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), 5000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  async function loadHoldings(signal?: AbortSignal, message = 'Loading holdings') {
    setStatus('loading');
    setStatusMessage(message);
    setError('');
    try {
      const [holdingsPayload, summaryPayload, importsPayload] = await Promise.all([
        fetchFyersHoldings(signal),
        fetchFyersHoldingsSummary(signal),
        fetchFyersHoldingsImports({ limit: 3 }, signal),
      ]);
      setRows(extractFyersRows(holdingsPayload, ['holdings', 'rows', 'data']));
      setSummary(asRecord(asRecord(summaryPayload).summary ?? summaryPayload));
      setImports(extractFyersRows(importsPayload, ['imports', 'rows', 'data']));
      setStatus('online');
      setStatusMessage('Live');
    } catch (loadError) {
      if (signal?.aborted) return;
      setError(loadError instanceof Error ? loadError.message : String(loadError));
      setStatus('error');
      setStatusMessage('Check');
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    loadHoldings(controller.signal);
    return () => controller.abort();
  }, []);

  const filteredRows = useMemo(() => {
    const token = deferredSearch.trim().toLowerCase();
    if (!token) return rows;
    return rows.filter((row) => safeLegacyText(pickFyersField(row, ['symbolRaw', 'symbol', 'symbolCode']), '').toLowerCase().includes(token));
  }, [deferredSearch, rows]);
  const reconciliationRows = useMemo(
    () => (reconciliation ? extractFyersRows(reconciliation, ['rows', 'data', 'items']) : []),
    [reconciliation],
  );
  const reconciliationSummary = useMemo(
    () => asRecord(reconciliation?.summary),
    [reconciliation],
  );
  const reconciliationMismatchRows = useMemo(
    () => reconciliationRows.filter((row) => reconciliationMismatchStatuses.has(reconciliationStatus(row))),
    [reconciliationRows],
  );
  const holdingFormModeLabel = editingId ? 'edit' : 'create';
  const holdingFormToggleLabel = `${isHoldingFormExpanded ? 'Hide' : 'Show'} ${holdingFormModeLabel} holding form`;

  function updateForm(key: keyof HoldingForm, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function resetSelectedFile() {
    setFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }

  async function submitHolding() {
    if (!form.symbol.trim()) {
      setError('Symbol is required.');
      return;
    }
    setStatus('loading');
    try {
      const payload = formToPayload(form);
      if (editingId) {
        await updateFyersHolding(editingId, payload);
      } else {
        await createFyersHolding(payload);
      }
      setEditingId('');
      setForm(emptyForm);
      await loadHoldings(undefined, editingId ? 'Refreshing updated holding' : 'Refreshing created holding');
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : String(saveError));
      setStatus('error');
      setStatusMessage('Save failed');
    }
  }

  async function deleteHolding(row: UnknownRecord) {
    const holdingId = safeLegacyText(pickField(row, ['holdingId', 'id']), '');
    if (!holdingId) {
      setError('Holding id is missing for selected row.');
      return;
    }
    if (!window.confirm(`Delete ${safeLegacyText(pickFyersField(row, ['symbolRaw', 'symbol']), 'holding')}?`)) return;
    setStatus('loading');
    try {
      await deleteFyersHolding(holdingId);
      if (editingId === holdingId) {
        setEditingId('');
        setForm(emptyForm);
      }
      await loadHoldings(undefined, 'Refreshing deleted holding');
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : String(deleteError));
      setStatus('error');
      setStatusMessage('Delete failed');
    }
  }

  async function importSelectedFile() {
    if (!file) {
      setError('Select a FYERS holdings CSV file first.');
      return;
    }
    const formData = new FormData();
    formData.set('file', file);
    formData.set('replaceMissing', 'true');
    setStatus('loading');
    setStatusMessage('Importing CSV');
    try {
      const importPayload = asRecord(await importFyersHoldings(formData));
      if (!isSuccessfulImportPayload(importPayload)) {
        const message = buildImportFailureDescription(importPayload);
        setError(message);
        setStatus('error');
        setStatusMessage('Import failed');
        setToast(withFyersToast('CSV import failed. Please check file format or backend logs.', message, 'danger'));
        return;
      }
      resetSelectedFile();
      setToast(withFyersToast('Successfully imported CSV file', buildImportSuccessDescription(importPayload), 'success'));
      await loadHoldings(undefined, 'Refreshing imported holdings');
    } catch (importError) {
      const message = importError instanceof Error ? importError.message : String(importError);
      setError(message);
      setStatus('error');
      setStatusMessage('Import failed');
      setToast(withFyersToast('CSV import failed. Please check file format or backend logs.', message, 'danger'));
    }
  }

  function downloadCsv() {
    const csv = buildCsvDownload(rows, holdingColumns.map((column) => ({ aliases: column.aliases, label: column.label })));
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'fyers-holdings.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  function downloadReconciliationCsv() {
    const columns = [
      ...reconciliationColumns.map((column) => ({ aliases: column.aliases, label: column.label })),
      { aliases: ['statusDetails'], label: 'Reason' },
    ];
    const exportRows = reconciliationRows.map((row) => ({ ...row, statusDetails: reconciliationReason(row) }));
    const csv = buildCsvDownload(exportRows, columns);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'fyers-holdings-reconciliation.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  async function verifyPnl() {
    setReconciling(true);
    setReconcileError('');
    try {
      const payload = asRecord(await fetchFyersHoldingsReconciliation());
      setReconciliation(payload);
      setToast(withFyersToast('P&L verification completed', getFyersStatusMessage(payload, 'Reconciliation report refreshed.'), 'success'));
    } catch (verifyError) {
      const message = verifyError instanceof Error ? verifyError.message : String(verifyError);
      setReconcileError(message);
      setToast(withFyersToast('P&L verification failed', message, 'danger'));
    } finally {
      setReconciling(false);
    }
  }

  async function copyRow(row: UnknownRecord) {
    const text = holdingColumns
      .map((column) => `${column.label}: ${formatFyersCell(pickFyersField(row, column.aliases), column.kind)}`)
      .join('\n');
    await navigator.clipboard.writeText(text);
  }

  return (
    <FyersMigrationLayout activeFyersPage="/app/fyers/holdings" className="fyers-holdings-react-page">
      <PageHero title="FYERS HOLDINGS" />

      <AppToolbar aria-label="Holdings controls">
        <div className="trend-toolbar__item trend-toolbar__item--search">
          <SearchInput value={search} onChange={setSearch} placeholder="Search holding symbol" />
        </div>
        <label className="database-react-field">
          <span>FYERS CSV</span>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => setFile(event.currentTarget.files?.[0] ?? null)}
          />
        </label>
        <ActionButton disabled={status === 'loading'} onClick={importSelectedFile}>Import CSV</ActionButton>
        <ActionButton disabled={status === 'loading'} onClick={() => loadHoldings()}>Reload Data</ActionButton>
        <ActionButton disabled={!rows.length} onClick={downloadCsv}>Download CSV</ActionButton>
        <ActionButton disabled={isReconciling || !rows.length} onClick={verifyPnl}>{isReconciling ? 'Verifying...' : 'Verify P&L'}</ActionButton>
      </AppToolbar>

      <KpiGrid items={summaryKpis(summary, rows)} />

      {reconcileError ? <ErrorAlertCard message={reconcileError} /> : null}

      {reconciliation ? (
        <>
        <section className="fyers-holdings-panel">
          <div className="table-title">
            <h3>P&L Verification</h3>
            <div className="fyers-react-actions">
              <span className="count-pill">Checked: {formatLegacyCount(pickField(reconciliationSummary, ['totalSymbolsChecked']))}</span>
              <ActionButton disabled={!reconciliationRows.length} onClick={downloadReconciliationCsv}>Export CSV</ActionButton>
            </div>
          </div>
          <KpiGrid items={reconciliationSummaryKpis(reconciliationSummary)} />
        </section>
        {reconciliationMismatchRows.length ? (
          <section className="card fyers-holdings-panel">
            <div className="table-wrapper fyers-holdings-table-wrap">
              <table className="app-data-table table-sticky-safe data-table fyers-holdings-table" data-sticky-has-sno="true">
                <thead>
                  <tr>
                    {reconciliationColumns.map((column) => (
                      <th key={column.label} className={centeredCellClassName} data-col={column.dataCol}>
                        {column.label}
                      </th>
                    ))}
                    <th className={centeredCellClassName}>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {reconciliationMismatchRows.map((row, index) => (
                    <tr key={`${safeLegacyText(pickField(row, ['symbol', 'symbolRaw']), String(index))}-${index}`}>
                      {reconciliationColumns.map((column) => {
                        const rawValue = pickFyersField(row, column.aliases);
                        const valueClassName = column.dataCol.includes('Pnl') || column.dataCol.includes('difference')
                          ? getProfitLossClass(rawValue)
                          : '';
                        return (
                          <td key={column.label} className={centeredCellClassName} data-col={column.dataCol}>
                            <span className={valueClassName || undefined}>{formatFyersCell(rawValue, column.kind)}</span>
                          </td>
                        );
                      })}
                      <td className={centeredCellClassName}>{reconciliationReason(row) || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : (
          <section className="card fyers-holdings-panel">
            <div className="empty">No formula mismatches returned by reconciliation.</div>
          </section>
        )}
        </>
      ) : null}

      <section className="card fyers-holdings-panel">
        <div className="table-title">
          <h3>Stable Fields</h3>
          <span className="count-pill">{safeLegacyText(file?.name, 'No file selected')}</span>
        </div>
        <dl className="fyers-react-definition-grid">
          {(Array.isArray(summary.stableFields) ? summary.stableFields : []).map((item) => {
            const record = asRecord(item);
            const key = safeLegacyText(record.key ?? record.label, 'field');
            return (
              <div key={key}>
                <dt>{safeLegacyText(record.label ?? record.key)}</dt>
                <dd>{formatFyersCell(record.value)}</dd>
              </div>
            );
          })}
          {!Array.isArray(summary.stableFields) || summary.stableFields.length === 0 ? (
            <div>
              <dt>Waiting</dt>
              <dd>Import a FYERS holdings CSV to populate the Oracle-backed view.</dd>
            </div>
          ) : null}
        </dl>
      </section>

      <section className="card fyers-holdings-form-card">
        <div className="table-title">
          <h3>{editingId ? 'Edit Holding' : 'Create Holding'}</h3>
          <div className="fyers-holdings-form-card__controls">
            <span className="database-badge database-badge--warn">{editingId ? `Edit mode ${editingId}` : 'Create mode'}</span>
            <button
              aria-controls={holdingsFormPanelId}
              aria-expanded={isHoldingFormExpanded}
              aria-label={holdingFormToggleLabel}
              className="preset-btn fyers-holdings-form-toggle"
              title={holdingFormToggleLabel}
              type="button"
              onClick={() => setHoldingFormExpanded((current) => getNextHoldingFormExpandedState(current, 'toggle'))}
            >
              {isHoldingFormExpanded ? '-' : '+'}
            </button>
          </div>
        </div>
        <div id={holdingsFormPanelId} hidden={!isHoldingFormExpanded}>
          <div className="fyers-react-form-grid fyers-react-form-grid--wide">
            <TextField label="Symbol" value={form.symbol} onChange={(value) => updateForm('symbol', value)} placeholder="NSE:TCS-EQ" />
            <TextField label="Qty" type="number" value={form.quantity} onChange={(value) => updateForm('quantity', value)} />
            <TextField label="Buy Price" type="number" value={form.buyPrice} onChange={(value) => updateForm('buyPrice', value)} />
            <TextField label="Invested" type="number" value={form.investedValue} onChange={(value) => updateForm('investedValue', value)} />
            <TextField label="Current" type="number" value={form.currentValue} onChange={(value) => updateForm('currentValue', value)} />
            <TextField label="Unrealised P&L" type="number" value={form.unrealisedPnl} onChange={(value) => updateForm('unrealisedPnl', value)} />
            <TextField label="Unrealised P&L %" type="number" value={form.unrealisedPnlPct} onChange={(value) => updateForm('unrealisedPnlPct', value)} />
            <TextField label="Previous Close" type="number" value={form.previousClose} onChange={(value) => updateForm('previousClose', value)} />
            <TextField label="ISIN" value={form.isin} onChange={(value) => updateForm('isin', value)} />
          </div>
          <div className="fyers-react-actions">
            <ActionButton disabled={status === 'loading'} onClick={submitHolding}>Save Holding</ActionButton>
            <ActionButton onClick={() => { setEditingId(''); setForm(emptyForm); }}>Reset Form</ActionButton>
          </div>
        </div>
      </section>

      {error ? <ErrorAlertCard message={error} /> : null}

      <section className="card">
        <div className="table-title">
          <h3>Holdings</h3>
          <span className="count-pill">TOTAL: {filteredRows.length.toLocaleString('en-IN')}</span>
        </div>
        <div className="table-wrapper fyers-holdings-table-wrap">
          <table className="app-data-table table-sticky-safe data-table fyers-holdings-table" data-sticky-has-sno="true">
            <colgroup>
              <col data-col="sno" />
              {holdingColumns.map((column) => <col key={column.label} data-col={column.dataCol} />)}
              <col data-col="actions" />
            </colgroup>
            <thead>
              <tr>
                <th className={centeredCellClassName} data-col="sno">S.NO</th>
                {holdingColumns.map((column) => (
                  <th key={column.label} className={centeredCellClassName} data-col={column.dataCol}>
                    {column.label}
                  </th>
                ))}
                <th className={centeredCellClassName}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.length ? filteredRows.map((row, index) => {
                const holdingId = safeLegacyText(pickField(row, ['holdingId', 'id']), `${index}`);
                const marketCapTone = marketCapToneForRow(row);
                return (
                  <tr key={`${holdingId}-${index}`}>
                    <td className={centeredCellClassName} data-col="sno">{(index + 1).toLocaleString('en-IN')}</td>
                    {holdingColumns.map((column) => {
                      const rawValue = pickFyersField(row, column.aliases);
                      const value = formatFyersCell(rawValue, column.kind);
                      const valueClassName = getHoldingValueClass(column, row, rawValue);
                      return (
                        <td key={column.label} className={centeredCellClassName} data-col={column.dataCol}>
                          {shouldUseMarketCapTone(column.label) ? (
                            <TechnicalMarketCapCell className={valueClassName || undefined} tone={marketCapTone}>
                              {value}
                            </TechnicalMarketCapCell>
                          ) : (
                            <span className={valueClassName || undefined}>{value}</span>
                          )}
                        </td>
                      );
                    })}
                    <td className={centeredCellClassName}>
                      <div className="fyers-react-actions fyers-react-actions--table justify-center">
                        <button className="preset-btn" type="button" aria-label="Copy holding row" onClick={() => copyRow(row)}>Copy</button>
                        <button className="preset-btn" type="button" onClick={() => { setEditingId(holdingId); setForm(rowToForm(row)); setHoldingFormExpanded((current) => getNextHoldingFormExpandedState(current, 'edit')); }}>Edit</button>
                        <button className="preset-btn" type="button" onClick={() => deleteHolding(row)}>Delete</button>
                      </div>
                    </td>
                  </tr>
                );
              }) : (
                <tr>
                  <td className="empty" colSpan={holdingColumns.length + 2}>No holdings returned.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <Toast
        open={Boolean(toast)}
        title={toast?.title || ''}
        description={toast?.description || ''}
        tone={toast?.tone || 'info'}
        onClose={() => setToast(null)}
      />

      <section className="card fyers-holdings-panel">
        <div className="table-title">
          <h3>Loaded File</h3>
          <span className="count-pill">Recent imports: {imports.length}</span>
        </div>
        <div className="fyers-react-import-list">
          {imports.length ? imports.map((item, index) => (
            <article key={`${safeLegacyText(item.importId, String(index))}-${index}`} className="fyers-react-import-card">
              <strong>{safeLegacyText(pickField(item, ['sourceFilename', 'filename']), 'Manual entry')}</strong>
              <span>Rows {formatLegacyCount(pickField(item, ['rowCount', 'rows']))}</span>
              <span>Inserted {formatLegacyCount(pickField(item, ['insertedCount', 'inserted']))}</span>
              <span>Updated {formatLegacyCount(pickField(item, ['updatedCount', 'updated']))}</span>
              <span>Deleted {formatLegacyCount(pickField(item, ['deletedCount', 'deleted']))}</span>
            </article>
          )) : <div className="empty">No imports stored yet.</div>}
        </div>
      </section>
    </FyersMigrationLayout>
  );
}


