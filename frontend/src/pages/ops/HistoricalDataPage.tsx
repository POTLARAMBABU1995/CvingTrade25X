import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { AppDataTable, type AppDataTableColumn, type AppSortState, sortRowsForTable } from '../../components/app/AppDataTable';
import { StrategyToolbar } from '../../components/strategy/StrategyToolbar';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { TrashIcon } from '../../components/ui/Icons';
import { Toast } from '../../components/ui/Toast';
import {
  asRecord,
  extractRows,
  formatLegacyCount,
  formatLegacyDateOnly,
  pickField,
  safeLegacyText,
  type UnknownRecord,
} from '../../adapters/databasePageAdapter';
import { deleteHistoricalSymbols, downloadHistoricalSymbolBundle, fetchHistoricalSummary, fetchHistoricalTables } from '../../services/api/databaseApi';
import { cn } from '../../lib/cn';
import { OpsPageShell } from './OpsPageShell';
import { ActionButton, KpiGrid, PageHero, SelectField, TextField } from './opsPageHelpers';

type LoadStatus = 'error' | 'loading' | 'online';
type ToastTone = 'danger' | 'info' | 'success' | 'warn';

type ToastState = {
  description: string;
  title: string;
  tone: ToastTone;
};

type HistoricalRowView = {
  id: string;
  isDeleting: boolean;
  raw: UnknownRecord;
  selected: boolean;
  serialNo: number;
  symbol: string;
};

const PAGE_SIZE = 25;

const historicalColumns = [
  { key: 'symbol', label: 'Symbol', dataCol: 'symbol', aliases: ['symbol', 'SYMBOL', 'stock', 'STOCK'], format: 'text', sortType: 'string' },
  { key: 'tradingDays', label: 'Trading_Days', dataCol: 'tradingDays', aliases: ['trading_days', 'TRADING_DAYS'], format: 'count', sortType: 'number' },
  { key: 'ipoDate', label: 'IPO_Date', dataCol: 'ipoDate', aliases: ['ipo_date', 'IPO_DATE'], format: 'dateOnly', sortType: 'date' },
  { key: 'ipoPrice', label: 'IPO_Price', dataCol: 'ipoPrice', aliases: ['ipo_price', 'IPO_PRICE'], format: 'number', sortType: 'number' },
  { key: 'price', label: 'Price', dataCol: 'price', aliases: ['price', 'PRICE', 'close', 'CLOSE'], format: 'number', sortType: 'number' },
  { key: 'tradeDate', label: 'Trade_Date', dataCol: 'tradeDate', aliases: ['trade_date', 'TRADE_DATE', 'latest_trading_date', 'LATEST_TRADING_DATE', 'trading_date', 'TRADING_DATE'], format: 'dateOnly', sortType: 'date' },
  { key: 'ath', label: 'ATH', dataCol: 'ath', aliases: ['ath', 'ATH'], format: 'number', sortType: 'number' },
  { key: 'athDate', label: 'ATH Date', dataCol: 'athDate', aliases: ['ath_date', 'ATH_DATE'], format: 'dateOnly', sortType: 'date' },
  { key: 'existing', label: 'Existing', dataCol: 'existing', aliases: ['existing', 'EXISTING', 'has_existing'], format: 'text', sortType: 'string' },
] as const;

const DEFAULT_TABLE = 'NSE_NIFTY500_DAILY_RAW_DATA_DEV';
const KNOWN_TABLES = [
  'NSE_NIFTY500_DAILY_RAW_DATA_DEV',
  'NSE_NIFTY500_DAILY_RAW_DATA_ORACLE',
];

function sortValue(row: UnknownRecord, column: typeof historicalColumns[number]): string | number | null {
  const value = pickField(row, column.aliases);
  if (value === null || value === undefined || value === '') return null;
  if (column.sortType === 'number') {
    const parsed = Number(String(value).replace(/,/g, '').replace(/%/g, ''));
    return Number.isFinite(parsed) ? parsed : null;
  }
  if (column.sortType === 'date') {
    const text = String(value).trim();
    const ddmmyyyy = text.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
    if (ddmmyyyy) {
      const parsed = Date.parse(`${ddmmyyyy[3]}-${ddmmyyyy[2].padStart(2, '0')}-${ddmmyyyy[1].padStart(2, '0')}`);
      return Number.isFinite(parsed) ? parsed : text;
    }
    const parsed = Date.parse(text);
    return Number.isFinite(parsed) ? parsed : text;
  }
  return String(value);
}

function toastIconLabel(tone: ToastTone): string {
  if (tone === 'success') return 'OK';
  if (tone === 'warn') return '!';
  if (tone === 'info') return 'i';
  return 'ERR';
}

function normalizeTables(payload: UnknownRecord): string[] {
  const raw = payload.tables;
  if (!Array.isArray(raw)) return [];
  return raw.map((item) => String(item || '').trim().toUpperCase()).filter(Boolean);
}

export function HistoricalDataPage() {
  const [athMax, setAthMax] = useState('');
  const [athMin, setAthMin] = useState('');
  const [error, setError] = useState('');
  const [listedFrom, setListedFrom] = useState('');
  const [listedTo, setListedTo] = useState('');
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [loadTimeMs, setLoadTimeMs] = useState<number | null>(null);
  const [minRecords, setMinRecords] = useState('');
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [rows, setRows] = useState<UnknownRecord[]>([]);
  const [search, setSearch] = useState('');
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [summaryCards, setSummaryCards] = useState<UnknownRecord>({});
  const [tableName, setTableName] = useState(DEFAULT_TABLE);
  const [tables, setTables] = useState<string[]>(KNOWN_TABLES);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [sortState, setSortState] = useState<AppSortState>({ key: null, direction: null });
  const [deletePendingSymbols, setDeletePendingSymbols] = useState<string[]>([]);
  const [downloadPendingSymbols, setDownloadPendingSymbols] = useState<string[]>([]);
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const forceRefreshRef = useRef(false);
  const toastTimerRef = useRef<number | null>(null);
  const clientCacheRef = useRef<Map<string, { cards: UnknownRecord; rows: UnknownRecord[]; totalCount: number }>>(new Map());

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(search.trim());
    }, 150);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => () => {
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
  }, []);

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

  useEffect(() => {
    const controller = new AbortController();
    fetchHistoricalTables(controller.signal).then((payload) => {
      const record = asRecord(payload);
      const tableList = normalizeTables(record);
      if (tableList.length > 0) {
        setTables(tableList);
        const preferred = safeLegacyText(pickField(record, ['default_table', 'defaultTable']), '').toUpperCase();
        setTableName((current) => (tableList.includes(current) ? current : (tableList.includes(preferred) ? preferred : tableList[0])));
      }
    }).catch((loadError) => {
      if (controller.signal.aborted) return;
      console.warn('[HistoricalDataPage] fetchHistoricalTables failed:', loadError);
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!tableName) return undefined;
    const controller = new AbortController();
    const startedAt = performance.now();
    const isForceRefresh = forceRefreshRef.current;
    forceRefreshRef.current = false;

    const cacheKey = [
      tableName,
      currentPage,
      debouncedSearch,
      minRecords,
      listedFrom,
      listedTo,
      athMin,
      athMax,
    ].join('|');

    if (!isForceRefresh && clientCacheRef.current.has(cacheKey)) {
      const cached = clientCacheRef.current.get(cacheKey)!;
      setRows(cached.rows);
      setSummaryCards(cached.cards);
      setTotalCount(cached.totalCount);
      setLoadTimeMs(1);
      setLastRefreshedAt(new Date());
      setStatus('online');
      setError('');
      return undefined;
    }

    setStatus('loading');
    setError('');
    fetchHistoricalSummary({
      table_name: tableName,
      page: currentPage,
      page_size: PAGE_SIZE,
      symbol: debouncedSearch,
      min_records: minRecords,
      listed_from: listedFrom,
      listed_to: listedTo,
      ath_min: athMin,
      ath_max: athMax,
      refresh: isForceRefresh,
    }, controller.signal).then((payload) => {
      const record = asRecord(payload);
      const extractedRows = extractRows(record, ['rows', 'data', 'items']);
      const extractedCards = asRecord(record.cards);
      const extractedCount = Number(record.total_count ?? record.totalCount ?? 0) || 0;
      setRows(extractedRows);
      setSummaryCards(extractedCards);
      setTotalCount(extractedCount);
      clientCacheRef.current.set(cacheKey, {
        cards: extractedCards,
        rows: extractedRows,
        totalCount: extractedCount,
      });
      setLoadTimeMs(Math.max(0, performance.now() - startedAt));
      setLastRefreshedAt(new Date());
      setStatus('online');
    }).catch((loadError) => {
      if (controller.signal.aborted) return;
      setLoadTimeMs(Math.max(0, performance.now() - startedAt));
      setError(loadError instanceof Error ? loadError.message : String(loadError));
      setStatus('error');
    });
    return () => controller.abort();
  }, [athMax, athMin, currentPage, debouncedSearch, listedFrom, listedTo, minRecords, refreshVersion, tableName]);

  useEffect(() => {
    setCurrentPage(1);
  }, [athMax, athMin, debouncedSearch, listedFrom, listedTo, minRecords, tableName]);

  const isInitialLoading = status === 'loading' && rows.length === 0;

  const skeletonRows = useMemo<HistoricalRowView[]>(() => (
    Array.from({ length: 10 }, (_, index) => ({
      id: `skeleton-${index}`,
      isDeleting: false,
      raw: {},
      selected: false,
      serialNo: index + 1,
      symbol: '',
    }))
  ), []);

  const sortedRows = useMemo(
    () => sortRowsForTable(rows, historicalColumns.map((column) => ({
      getSortValue: (row) => sortValue(row, column),
      key: column.key,
      sortType: column.sortType,
    })), sortState),
    [rows, sortState],
  );
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  useEffect(() => {
    if (currentPage > totalPages) setCurrentPage(totalPages);
  }, [currentPage, totalPages]);

  const pageOffset = (currentPage - 1) * PAGE_SIZE;
  const pageRows = useMemo<HistoricalRowView[]>(() => {
    if (isInitialLoading) return skeletonRows;
    return sortedRows.map((row, index) => {
      const symbol = safeLegacyText(pickField(row, ['symbol', 'SYMBOL', 'stock', 'STOCK']), '');
      const normalizedSymbol = symbol.toUpperCase();
      return {
        id: `${normalizedSymbol || 'row'}-${pageOffset + index}`,
        isDeleting: deletePendingSymbols.includes(normalizedSymbol),
        raw: row,
        selected: selectedSymbols.includes(normalizedSymbol),
        serialNo: pageOffset + index + 1,
        symbol,
      };
    });
  }, [deletePendingSymbols, isInitialLoading, pageOffset, selectedSymbols, skeletonRows, sortedRows]);

  const visibleSelection = useMemo(
    () => pageRows.map((row) => row.symbol.toUpperCase()).filter(Boolean),
    [pageRows],
  );
  const allVisibleSelected = visibleSelection.length > 0 && visibleSelection.every((symbol) => selectedSymbols.includes(symbol));
  const someVisibleSelected = visibleSelection.some((symbol) => selectedSymbols.includes(symbol));
  const latestDataDate = safeLegacyText(pickField(summaryCards, ['latest_data_date', 'latestDataDate', 'latest_date']), '');
  const tableLabel = tableName || '-';
  const toolbarStatus = status === 'online' ? 'live' : status === 'loading' ? 'syncing' : 'stale';

  useEffect(() => {
    const checkbox = document.getElementById('historical-data-select-all') as HTMLInputElement | null;
    if (checkbox) checkbox.indeterminate = !allVisibleSelected && someVisibleSelected;
  }, [allVisibleSelected, someVisibleSelected]);

  function refreshHistoricalData() {
    clientCacheRef.current.clear();
    forceRefreshRef.current = true;
    setRefreshVersion((current) => current + 1);
  }

  function handleTableChange(nextTable: string) {
    if (nextTable === tableName) return;
    clientCacheRef.current.clear();
    setTableName(nextTable);
    setCurrentPage(1);
  }

  function setSymbolSelected(symbol: string, checked: boolean) {
    const normalized = symbol.trim().toUpperCase();
    if (!normalized) return;
    setSelectedSymbols((current) => {
      if (checked) {
        if (current.includes(normalized)) return current;
        return [...current, normalized];
      }
      return current.filter((item) => item !== normalized);
    });
  }

  function toggleVisibleSelection(checked: boolean) {
    setSelectedSymbols((current) => {
      const next = new Set(current);
      visibleSelection.forEach((symbol) => {
        if (checked) next.add(symbol);
        else next.delete(symbol);
      });
      return Array.from(next);
    });
  }

  async function handleDelete(symbols: string[], label: string) {
    if (!tableName || !symbols.length) return;
    const normalizedSymbols = Array.from(new Set(symbols.map((symbol) => symbol.trim().toUpperCase()).filter(Boolean)));
    if (!normalizedSymbols.length) return;
    const confirmation = normalizedSymbols.length === 1
      ? 'Are you sure you want to delete this symbol historical data?'
      : 'Are you sure you want to delete selected symbols historical data?';
    if (!window.confirm(confirmation)) return;

    setError('');
    setDeletePendingSymbols((current) => Array.from(new Set([...current, ...normalizedSymbols])));
    if (normalizedSymbols.length > 1) setIsBulkDeleting(true);
    try {
      const payload = await deleteHistoricalSymbols({
        confirm_text: 'DELETE',
        symbols: normalizedSymbols,
        table_name: tableName,
      });
      const record = asRecord(payload);
      const deletedCount = Number(record.deleted_rows ?? record.deletedRows ?? normalizedSymbols.length) || 0;
      const deletedSymbolsCount = Number(record.deleted_symbols ?? record.deletedSymbols ?? normalizedSymbols.length) || 0;
      const devDeletedRows = Number(record.dev_deleted_rows ?? record.devDeletedRows ?? 0) || 0;
      const oracleDeletedRows = Number(record.oracle_deleted_rows ?? record.oracleDeletedRows ?? 0) || 0;
      setSelectedSymbols((current) => current.filter((symbol) => !normalizedSymbols.includes(symbol)));
      clientCacheRef.current.clear();
      setRefreshVersion((current) => current + 1);
      showToast({
        description: deletedCount > 0
          ? `${label} deleted successfully. Symbols: ${formatLegacyCount(deletedSymbolsCount)}. DEV rows: ${formatLegacyCount(devDeletedRows)}. ORACLE rows: ${formatLegacyCount(oracleDeletedRows)}. Total rows: ${formatLegacyCount(deletedCount)}.`
          : `${label} matched no rows.`,
        title: normalizedSymbols.length === 1 ? 'Delete completed' : 'Bulk delete completed',
        tone: deletedCount > 0 ? 'success' : 'warn',
      });
    } catch (deleteError) {
      const message = deleteError instanceof Error ? deleteError.message : String(deleteError);
      setError(message);
      showToast({
        description: message,
        title: normalizedSymbols.length === 1 ? 'Delete failed' : 'Bulk delete failed',
        tone: 'danger',
      });
    } finally {
      setDeletePendingSymbols((current) => current.filter((symbol) => !normalizedSymbols.includes(symbol)));
      setIsBulkDeleting(false);
    }
  }

  async function handleExportDownload(symbol: string, rowTradeDate?: unknown) {
    const normalizedSymbol = symbol.trim().toUpperCase();
    if (!normalizedSymbol || !tableName || downloadPendingSymbols.includes(normalizedSymbol)) return;
    setDownloadPendingSymbols((current) => [...current, normalizedSymbol]);
    try {
      const blob = await downloadHistoricalSymbolBundle(normalizedSymbol, tableName);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;

      let dateFormatted = '';
      if (rowTradeDate) {
        const text = String(rowTradeDate).trim();
        const m = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
        if (m) {
          dateFormatted = `${m[3]}-${m[2]}-${m[1]}`;
        } else {
          const ddmmyyyy = text.match(/^(\d{2})-(\d{2})-(\d{4})/);
          if (ddmmyyyy) {
            dateFormatted = text;
          }
        }
      }
      if (!dateFormatted) {
        const now = new Date();
        const dd = String(now.getDate()).padStart(2, '0');
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const yyyy = now.getFullYear();
        dateFormatted = `${dd}-${mm}-${yyyy}`;
      }
      const now = new Date();
      const hh = String(now.getHours()).padStart(2, '0');
      const min = String(now.getMinutes()).padStart(2, '0');
      const ss = String(now.getSeconds()).padStart(2, '0');
      const timestampFormatted = `${hh}${min}${ss}`;
      const exportName = `${normalizedSymbol}_${dateFormatted}_${timestampFormatted}`;

      anchor.download = `${exportName}.zip`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      showToast({
        description: `${normalizedSymbol} CSV, JSON, and TXT files downloaded in ${exportName}.zip.`,
        title: 'Download completed',
        tone: 'success',
      });
    } catch (downloadError) {
      const message = downloadError instanceof Error ? downloadError.message : String(downloadError);
      showToast({
        description: message,
        title: 'Download failed',
        tone: 'danger',
      });
    } finally {
      setDownloadPendingSymbols((current) => current.filter((item) => item !== normalizedSymbol));
    }
  }

  const tableColumns = useMemo<Array<AppDataTableColumn<HistoricalRowView>>>(() => ([
    {
      cellClassName: 'historical-data-table__sno-cell',
      dataCol: 'sno',
      getSortValue: (row) => row.serialNo,
      key: 'sno',
      label: (
        <span className="historical-data-table__sno-content">
          <input
            id="historical-data-select-all"
            type="checkbox"
            className="historical-data-table__checkbox"
            checked={allVisibleSelected}
            aria-label="Select all visible rows"
            onChange={(event) => toggleVisibleSelection(event.currentTarget.checked)}
          />
          <span>S.NO</span>
        </span>
      ),
      renderCell: (row) => {
        if (row.id.startsWith('skeleton-')) {
          return (
            <span className="historical-data-table__sno-content opacity-40">
              <span className="inline-block h-4 w-6 animate-pulse rounded bg-slate-300 dark:bg-slate-700" />
            </span>
          );
        }
        return (
          <span className="historical-data-table__sno-content">
            <input
              type="checkbox"
              className="historical-data-table__checkbox"
              checked={row.selected}
              aria-label={`Select ${row.symbol}`}
              onChange={(event) => setSymbolSelected(row.symbol, event.currentTarget.checked)}
            />
            <span>{row.serialNo.toLocaleString('en-IN')}</span>
          </span>
        );
      },
      sortable: false,
      sortType: 'number',
      sticky: true,
      stickyWidthPx: 104,
    },
    {
      cellClassName: 'historical-data-table__symbol-cell',
      dataCol: 'symbol',
      getSortValue: (row) => row.symbol,
      key: 'symbol',
      label: 'Symbol',
      renderCell: (row) => {
        if (row.id.startsWith('skeleton-')) {
          return <span className="inline-block h-4 w-20 animate-pulse rounded bg-slate-300 dark:bg-slate-700" />;
        }
        return row.symbol || '-';
      },
      sortType: 'string',
      sticky: true,
      stickyWidthPx: 140,
    },
    ...historicalColumns.filter((column) => column.key !== 'symbol').map<AppDataTableColumn<HistoricalRowView>>((column) => ({
      dataCol: column.dataCol,
      getSortValue: (row) => sortValue(row.raw, column),
      key: column.key,
      label: column.label,
      renderCell: (row) => {
        if (row.id.startsWith('skeleton-')) {
          return <span className="inline-block h-4 w-16 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />;
        }
        const value = pickField(row.raw, column.aliases);
        if (column.format === 'count') return formatLegacyCount(value, '-');
        if (column.format === 'dateOnly') return formatLegacyDateOnly(value);
        if (column.format === 'number') return value === null || value === undefined || value === '' ? '-' : Number(String(value).replace(/,/g, '')).toLocaleString('en-IN', { maximumFractionDigits: 2 });
        return safeLegacyText(value);
      },
      sortType: column.sortType,
    })),
    {
      cellClassName: 'historical-data-table__download-cell',
      dataCol: 'csvDownload',
      getSortValue: () => null,
      key: 'csvDownload',
      label: 'Download',
      renderCell: (row) => {
        if (row.id.startsWith('skeleton-')) {
          return <span className="inline-block h-6 w-6 animate-pulse rounded-full bg-slate-200 dark:bg-slate-800" />;
        }
        const normalizedSymbol = row.symbol.trim().toUpperCase();
        const isDownloading = downloadPendingSymbols.includes(normalizedSymbol);
        const rowTradeDate = pickField(row.raw, ['trade_date', 'TRADE_DATE', 'latest_trading_date', 'LATEST_TRADING_DATE', 'trading_date']);
        return (
          <button
            type="button"
            className="historical-data-table__download-button"
            aria-label={`Download ${row.symbol} historical data CSV JSON and TXT files`}
            title={`Download ${row.symbol} CSV, JSON, and TXT`}
            disabled={isDownloading}
            onClick={() => handleExportDownload(row.symbol, rowTradeDate)}
          >
            <span aria-hidden="true" className="historical-data-table__download-icon">↓</span>
          </button>
        );
      },
      sortable: false,
      sortType: 'string',
    },
    {
      cellClassName: 'historical-data-table__action-cell',
      dataCol: 'action',
      getSortValue: () => null,
      key: 'action',
      label: 'Action',
      renderCell: (row) => {
        if (row.id.startsWith('skeleton-')) {
          return <span className="inline-block h-6 w-6 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />;
        }
        return (
          <button
            type="button"
            className="historical-data-table__delete-button"
            aria-label={`Delete ${row.symbol} historical data`}
            title={`Delete ${row.symbol}`}
            disabled={row.isDeleting || isBulkDeleting}
            onClick={() => handleDelete([row.symbol], row.symbol)}
          >
            <TrashIcon aria-hidden="true" className="historical-data-table__delete-icon" />
          </button>
        );
      },
      sortable: false,
      sortType: 'string',
    },
  ]), [allVisibleSelected, downloadPendingSymbols, isBulkDeleting, someVisibleSelected, pageRows, selectedSymbols]);

  return (
    <OpsPageShell activeDatabasePage="/app/database/historical-data" className="historical-data-react-page">
      <Toast
        open={Boolean(toast)}
        title={toast?.title || ''}
        description={toast?.description || ''}
        tone={toast?.tone || 'info'}
        placement="top-right"
        icon={toast ? <span aria-hidden="true" className="text-[11px] font-semibold tracking-[0.14em]">{toastIconLabel(toast.tone)}</span> : undefined}
        onClose={dismissToast}
      />
      <PageHero title="Historical Data" />

      <StrategyToolbar
        apiTimeMs={loadTimeMs}
        className="historical-data-strategy-toolbar mt-4"
        dbTimeMs={null}
        isLoading={status === 'loading'}
        lastRefreshed={lastRefreshedAt}
        loadTimeMs={loadTimeMs}
        ltcDate={latestDataDate || null}
        onLiveRefresh={refreshHistoricalData}
        onRefresh={refreshHistoricalData}
        onSearchChange={setSearch}
        onTimeframeChange={() => undefined}
        refreshing={status === 'loading'}
        searchValue={search}
        showTimeframe
        showTotal
        status={toolbarStatus}
        timeframe="daily"
        timeframeOptions={['daily']}
        total={totalCount}
      />

      <section className="card database-react-filter-card">
        <div className="database-react-filter-grid">
          <SelectField label="Source Table" value={tableName} onChange={handleTableChange}>
            {tables.map((table) => <option key={table} value={table}>{table}</option>)}
          </SelectField>
          <TextField label="Min Total Records" type="number" value={minRecords} onChange={setMinRecords} />
          <TextField label="Listed Date From" type="date" value={listedFrom} onChange={setListedFrom} />
          <TextField label="Listed Date To" type="date" value={listedTo} onChange={setListedTo} />
          <TextField label="ATH Min" type="number" value={athMin} onChange={setAthMin} />
          <TextField label="ATH Max" type="number" value={athMax} onChange={setAthMax} />
        </div>
      </section>

      <KpiGrid items={[
        {
          label: 'Selected Table',
          value: <span className="historical-data-selected-table-value" title={tableLabel}>{tableLabel}</span>,
        },
        { label: 'Total Symbols', value: formatLegacyCount(pickField(summaryCards, ['total_symbols', 'totalSymbols']) ?? totalCount) },
        { label: 'Total Records', value: formatLegacyCount(pickField(summaryCards, ['total_records', 'totalRecords'])) },
        { label: 'Latest Data Date', value: formatLegacyDateOnly(pickField(summaryCards, ['latest_data_date', 'latestDataDate', 'latest_date'])) },
      ]} />

      {error ? (
        <div className="flex flex-col gap-2">
          <ErrorAlertCard message={error} />
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="inline-flex items-center gap-1.5 rounded-full border border-sky-300 bg-sky-100 px-4 py-1.5 text-xs font-bold text-sky-800 transition hover:bg-sky-200 dark:border-sky-700 dark:bg-sky-900/60 dark:text-sky-200"
              onClick={refreshHistoricalData}
            >
              Retry
            </button>
          </div>
        </div>
      ) : null}

      <section className="card">
        <div className="historical-data-table__toolbar">
          <div className="historical-data-table__selection-summary">
            <span className="count-pill">{formatLegacyCount(selectedSymbols.length)} selected</span>
            <span className="count-pill">{formatLegacyCount(totalCount)} total symbols</span>
          </div>
          {selectedSymbols.length > 0 ? (
            <ActionButton disabled={isBulkDeleting || status === 'loading'} onClick={() => handleDelete(selectedSymbols, `${selectedSymbols.length} symbol(s)`)}>
              {isBulkDeleting ? 'Deleting Selected...' : 'Delete Selected'}
            </ActionButton>
          ) : null}
        </div>
        <AppDataTable
          className="historical-data-table-shell"
          columns={tableColumns}
          currentPage={currentPage}
          disableClientSort
          emptyMessage={
            status === 'loading'
              ? 'Loading historical data...'
              : error
                ? `Unable to load historical summary data: ${error}. Click Retry above.`
                : 'No historical summary rows returned.'
          }
          getRowKey={(row) => row.id}
          onPageChange={setCurrentPage}
          onSortChange={setSortState}
          pageSize={PAGE_SIZE}
          paginationSummaryLabel="symbols"
          rows={pageRows}
          showTopPagination
          sortState={sortState}
          tableClassName={cn(
            'data-table--blue historical-data-table',
            status === 'loading' && rows.length > 0 ? 'opacity-75 transition-opacity' : undefined,
          )}
          tableId="historicalDataSummaryTable"
          totalRows={totalCount}
        />
      </section>
    </OpsPageShell>
  );
}


