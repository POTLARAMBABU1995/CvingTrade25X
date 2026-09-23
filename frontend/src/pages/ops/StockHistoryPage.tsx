import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { StrategyToolbar, type StrategyToolbarStatus } from '../../components/strategy/StrategyToolbar';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { Toast } from '../../components/ui/Toast';
import {
  asRecord,
  extractRows,
  formatLegacyDateOnly,
  getNestedDataRecord,
  pickField,
  safeLegacyText,
  type UnknownRecord,
} from '../../adapters/databasePageAdapter';
import {
  clearStockHistory,
  fetchStockHistoryStats,
  fetchStockHistorySummary,
  mergeLatestStockHistory,
} from '../../services/api/databaseApi';
import { OpsPageShell } from './OpsPageShell';
import { ActionButton, GenericDataTable, KpiGrid, PageHero, SelectField } from './opsPageHelpers';

type LoadStatus = 'error' | 'loading' | 'online';
type PageToast = {
  description: string;
  title: string;
  tone: 'danger' | 'info' | 'success' | 'warn';
};

type StockHistorySyncCards = {
  synchedRows: number;
  unsynchedRows: number;
};

const summaryColumns = [
  { key: 'sNo', label: 'S.No', dataCol: 's_no', aliases: ['s_no', 'S_NO'], format: 'count', sortType: 'number' },
  { key: 'stock', label: 'Stocks', dataCol: 'stocks', aliases: ['stocks', 'stock_count', 'stock', 'symbol', 'SYMBOL'], format: 'count', sortType: 'number' },
  { key: 'latestTradeDate', label: 'LTC_DATE', dataCol: 'latestTradeDate', aliases: ['latest_trade_date', 'latestTradeDate', 'LTC_DATE'], format: 'dateOnly', sortType: 'date' },
  { key: 'total', label: 'Total No. Of Trading Days', dataCol: 'total', aliases: ['total_no_of_trading_days', 'totalTradingDays', 'total', 'records'], format: 'count', sortType: 'number' },
] as const;

function optionalCount(stats: UnknownRecord, aliases: readonly string[]): number | null {
  const value = pickField(stats, aliases);
  if (value === null || value === undefined || value === '') return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric >= 0 ? numeric : null;
}

export function buildStockHistorySyncCards(stats: UnknownRecord): StockHistorySyncCards {
  const totalRows = optionalCount(stats, [
    'stock_eod_record_count',
    'recordsCount',
    'record_count',
    'records_count',
    'totalRecords',
  ]) ?? 0;
  const explicitSynchedRows = optionalCount(stats, [
    'stock_eod_synched_rows',
    'stock_eod_synced_rows',
    'stockEodSyncedRows',
    'synchedRows',
    'syncedRows',
  ]);
  const pendingRows = optionalCount(stats, [
    'stock_eod_pending_sync_count',
    'stock_eod_unsynched_rows',
    'stock_eod_unsynced_rows',
    'stockEodUnsyncedRows',
    'unsynchedRows',
    'unsyncedRows',
    'stock_eod_pending_dev_count',
    'stock_eod_latest_pending_dev_count',
    'pendingDevRows',
    'pending_dev_rows',
  ]) ?? 0;

  const unsynchedRows = explicitSynchedRows === null
    ? Math.min(totalRows, pendingRows)
    : Math.min(totalRows, Math.max(0, pendingRows));
  const synchedRows = explicitSynchedRows ?? Math.max(0, totalRows - unsynchedRows);

  return { synchedRows, unsynchedRows };
}

export function formatStockHistoryLtcDate(value: unknown): string {
  return formatLegacyDateOnly(value, '-');
}

function rowMetricMaximum(rows: UnknownRecord[], aliases: readonly string[]): number | null {
  let maximum: number | null = null;
  for (const row of rows) {
    const numeric = optionalCount(row, aliases);
    if (numeric === null) continue;
    maximum = maximum === null ? numeric : Math.max(maximum, numeric);
  }
  return maximum;
}

export function resolveStockHistoryTotalStocks(stats: UnknownRecord, rows: UnknownRecord[]): number {
  const explicitCount = optionalCount(stats, [
    'stock_eod_stock_count',
    'stockEodStockCount',
    'STOCK_EOD_STOCK_COUNT',
    'stocksCount',
    'stock_count',
    'stocks_count',
    'symbolsCount',
    'totalStocks',
    'TOTAL_STOCKS',
  ]);
  if (explicitCount !== null && explicitCount > 0) {
    return explicitCount;
  }
  return rowMetricMaximum(rows, ['stocks', 'stock_count', 'STOCKS', 'stock', 'symbol', 'SYMBOL']) ?? 0;
}

export function resolveStockHistoryTotalRows(stats: UnknownRecord): number {
  const explicitCount = optionalCount(stats, [
    'stock_eod_record_count',
    'stockEodRecordCount',
    'STOCK_EOD_RECORD_COUNT',
    'recordsCount',
    'recordCount',
    'record_count',
    'records_count',
    'totalRecords',
    'RECORD_COUNT',
  ]);
  if (explicitCount !== null && explicitCount >= 0) {
    return explicitCount;
  }
  return 0;
}

export function resolveStockHistoryTotalTradingDays(stats: UnknownRecord, rows: UnknownRecord[]): number {
  const explicitCount = optionalCount(stats, [
    'stock_eod_total_trading_days',
    'stockEodTotalTradingDays',
    'STOCK_EOD_TOTAL_TRADING_DAYS',
    'totalTradingDays',
    'total_trading_days',
    'TOTAL_TRADING_DAYS',
    'TRADING_DAY_COUNT',
    'trading_day_count',
  ]);
  if (explicitCount !== null && explicitCount >= 0) {
    return explicitCount;
  }
  return rowMetricMaximum(rows, [
    'total_no_of_trading_days',
    'totalTradingDays',
    'TOTAL_NO_OF_TRADING_DAYS',
    'total',
    'records',
  ]) ?? 0;
}

export function StockHistoryPage() {
  const [confirmToken, setConfirmToken] = useState('');
  const [deleteMessage, setDeleteMessage] = useState('');
  const [error, setError] = useState('');
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isMerging, setIsMerging] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [loadTimeMs, setLoadTimeMs] = useState<number | null>(null);
  const [pageToast, setPageToast] = useState<PageToast | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [rows, setRows] = useState<UnknownRecord[]>([]);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [stats, setStats] = useState<UnknownRecord>({});
  const deferredSearch = useDeferredValue(search);
  const toastTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current !== null) {
        window.clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const startedAt = performance.now();
    setStatus('loading');
    setError('');
    Promise.allSettled([
      fetchStockHistoryStats(controller.signal),
      fetchStockHistorySummary({ timeframe: 'daily', refresh: refreshVersion > 0 }, controller.signal),
    ]).then(([statsResult, summaryResult]) => {
      if (controller.signal.aborted) return;
      if (summaryResult.status !== 'fulfilled') {
        throw summaryResult.reason;
      }

      setRows(extractRows(summaryResult.value, ['rows', 'data', 'items', 'summary']));
      if (statsResult.status === 'fulfilled') {
        setStats(getNestedDataRecord(statsResult.value));
      } else {
        setStats({});
      }
      setLastRefreshedAt(new Date());
      setLoadTimeMs(Math.max(0, Math.round(performance.now() - startedAt)));
      setStatus('online');
    }).catch((loadError: unknown) => {
      if (controller.signal.aborted) return;
      setError(loadError instanceof Error ? loadError.message : String(loadError));
      setLoadTimeMs(Math.max(0, Math.round(performance.now() - startedAt)));
      setStatus('error');
    });
    return () => controller.abort();
  }, [refreshVersion]);

  const filteredRows = useMemo(() => {
    const token = deferredSearch.trim().toLowerCase();
    if (!token) return rows;
    return rows.filter((row) => {
      const tradeDate = safeLegacyText(pickField(row, ['latest_trade_date', 'latestTradeDate', 'LTC_DATE']), '');
      const stocks = safeLegacyText(pickField(row, ['stocks', 'stock_count', 'stock', 'symbol', 'SYMBOL']), '');
      return `${tradeDate} ${stocks}`.toLowerCase().includes(token);
    });
  }, [deferredSearch, rows]);

  const totalStocks = useMemo(() => {
    return resolveStockHistoryTotalStocks(stats, rows);
  }, [rows, stats]);

  const totalRows = useMemo(() => {
    return resolveStockHistoryTotalRows(stats);
  }, [stats]);

  const totalTradingDays = useMemo(() => {
    return resolveStockHistoryTotalTradingDays(stats, rows);
  }, [rows, stats]);

  const syncCards = useMemo(() => buildStockHistorySyncCards(stats), [stats]);
  const synchedRows = syncCards.synchedRows;
  const unsynchedRows = syncCards.unsynchedRows;

  const latestTradeDate = useMemo(() => {
    const rawDate = safeLegacyText(
      pickField(stats, [
        'stock_eod_latest_trade_date',
        'latestTradeDate',
        'latest_trade_date',
        'latestDate',
      ]) ?? pickField(rows[0] ?? {}, ['latest_trade_date', 'latestTradeDate', 'LTC_DATE']),
      '',
    );
    return formatStockHistoryLtcDate(rawDate);
  }, [rows, stats]);

  const kpiItems = useMemo(() => ([
    { label: 'LATEST_LTC_DATE', value: latestTradeDate || '-' },
    { label: 'TOTAL NO OF ROWS', value: totalRows.toLocaleString('en-IN') },
    { label: 'TOTAL STOCKS', value: totalStocks.toLocaleString('en-IN') },
    { label: 'TOTAL TRADING DAYS', value: totalTradingDays.toLocaleString('en-IN') },
    { label: 'SYNCHED ROWS', value: synchedRows.toLocaleString('en-IN'), className: 'stock-history-sync-card--synched' },
    { label: 'UNSYNCHED ROWS', value: unsynchedRows.toLocaleString('en-IN'), className: 'stock-history-sync-card--pending' },
  ]), [latestTradeDate, synchedRows, totalRows, totalStocks, totalTradingDays, unsynchedRows]);

  const toolbarStatus: StrategyToolbarStatus = status === 'error'
    ? 'error'
    : status === 'loading'
      ? 'syncing'
      : 'live';
  const toolbarTotal = deferredSearch.trim() ? filteredRows.length : totalStocks;
  const refreshStockHistory = () => setRefreshVersion((current) => current + 1);

  function showPageToast(nextToast: PageToast) {
    if (toastTimerRef.current !== null) {
      window.clearTimeout(toastTimerRef.current);
    }
    setPageToast(nextToast);
    toastTimerRef.current = window.setTimeout(() => {
      setPageToast(null);
      toastTimerRef.current = null;
    }, 5200);
  }

  async function runMerge() {
    setError('');
    setIsMerging(true);
    setStatus('loading');
    if (unsynchedRows > 0) {
      showPageToast({
        title: 'Stock history merge started',
        description: `${unsynchedRows.toLocaleString('en-IN')} unsynched rows pending. Syncing DEV and Oracle tables.`,
        tone: 'info',
      });
    } else {
      showPageToast({
        title: 'Stock history merge',
        description: 'Already Up-to-Date',
        tone: 'info',
      });
    }
    try {
      const payload = await mergeLatestStockHistory();
      const responseStatus = String(pickField(payload, ['status']) || '').trim().toUpperCase();
      if (responseStatus === 'SKIPPED') {
        showPageToast({
          title: 'Stock history merge',
          description: safeLegacyText(pickField(payload, ['message']), 'Already Up-to-Date'),
          tone: 'info',
        });
      }
      setIsMerging(false);
      refreshStockHistory();
    } catch (mergeError) {
      setIsMerging(false);
      setError(mergeError instanceof Error ? mergeError.message : String(mergeError));
      setStatus('error');
      showPageToast({
        title: 'Stock history merge failed',
        description: mergeError instanceof Error ? mergeError.message : String(mergeError),
        tone: 'danger',
      });
    }
  }

  async function runDeleteAll() {
    if (confirmToken.trim().toUpperCase() !== 'DELETE') {
      const message = 'Select DELETE to confirm stock history deletion.';
      setDeleteMessage(message);
      showPageToast({
        title: 'Delete confirmation required',
        description: message,
        tone: 'warn',
      });
      return;
    }
    setDeleteMessage('Deleting STOCK_EOD_HISTORY rows. Please wait until completion.');
    setIsDeleting(true);
    setStatus('loading');
    try {
      const payload = await clearStockHistory('DELETE');
      const deletedRows = Number(pickField(payload, ['deleted_rows', 'deletedRows']) || 0);
      const remainingRows = Number(pickField(payload, ['remaining_rows', 'remainingRows']) || 0);
      const message = `Deleted ${deletedRows.toLocaleString('en-IN')} STOCK_EOD_HISTORY rows. Remaining rows: ${remainingRows.toLocaleString('en-IN')}.`;
      setConfirmToken('');
      setDeleteMessage(message);
      showPageToast({
        title: 'Stock EOD rows deleted',
        description: message,
        tone: 'success',
      });
      setRefreshVersion((current) => current + 1);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : String(deleteError));
      setDeleteMessage(deleteError instanceof Error ? deleteError.message : String(deleteError));
      setStatus('error');
      showPageToast({
        title: 'Stock EOD delete failed',
        description: deleteError instanceof Error ? deleteError.message : String(deleteError),
        tone: 'danger',
      });
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <OpsPageShell activeDatabasePage="/app/database/stock-history" className="stock-history-react-page">
      <PageHero title="STOCK EOD HISTORY" />

      <StrategyToolbar
        apiTimeMs={loadTimeMs}
        className="stock-history-toolbar mt-4"
        dbTimeMs={null}
        isLoading={status === 'loading'}
        inserting={isMerging}
        lastRefreshed={lastRefreshedAt}
        loadTimeMs={loadTimeMs}
        ltcDate={latestTradeDate || null}
        onInsertDb={runMerge}
        onLiveRefresh={refreshStockHistory}
        onRefresh={refreshStockHistory}
        onSearchChange={setSearch}
        refreshing={status === 'loading' && lastRefreshedAt !== null && !isMerging}
        searchPlaceholder="Search LTC_DATE or Stocks"
        searchValue={search}
        insertLabel="Merge"
        insertLoadingLabel="Merging..."
        showInsertDb
        showTotal
        status={toolbarStatus}
        timeframe="daily"
        total={toolbarTotal}
      />

      <KpiGrid items={kpiItems} />

      <section className="card database-react-danger-card">
        <div className="table-title">
          <h3>Delete Stock EOD Rows</h3>
        </div>
        <div className="database-react-inline-form">
          <ActionButton
            disabled={status === 'loading' || isDeleting}
            onClick={() => {
              setConfirmToken('');
              setDeleteMessage('This action deletes every row from STOCK_EOD_HISTORY only after DELETE is selected.');
              setIsDeleteDialogOpen(true);
            }}
          >
            Delete Rows
          </ActionButton>
        </div>
      </section>

      {isDeleteDialogOpen ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/90 px-4 py-8 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="stock-eod-delete-title">
          <section className="w-full max-w-lg rounded-lg border border-rose-300/30 bg-slate-950 p-6 text-white shadow-2xl">
            <div className="space-y-2">
              <p className="text-xs font-black uppercase tracking-[0.18em] text-rose-300">Danger action</p>
              <h3 id="stock-eod-delete-title" className="text-xl font-black">Delete Stock EOD Rows</h3>
              <p className="text-sm font-semibold leading-6 text-slate-300">
                Select DELETE to confirm. The request is sent to the existing backend delete endpoint and verifies that the source table is empty before commit succeeds.
              </p>
            </div>
            <div className="mt-5 space-y-4">
              <SelectField label="Confirmation" value={confirmToken} onChange={setConfirmToken}>
                <option value="">Select confirmation</option>
                <option value="DELETE">DELETE</option>
              </SelectField>
              {deleteMessage ? (
                <p className="rounded-md border border-white/10 bg-white/10 px-3 py-3 text-sm font-semibold leading-6 text-slate-200">
                  {deleteMessage}
                </p>
              ) : null}
            </div>
            <div className="mt-6 flex flex-wrap justify-end gap-3">
              <ActionButton
                disabled={isDeleting}
                onClick={() => {
                  setIsDeleteDialogOpen(false);
                  setConfirmToken('');
                }}
              >
                Close
              </ActionButton>
              <ActionButton disabled={isDeleting || confirmToken !== 'DELETE'} onClick={runDeleteAll}>
                {isDeleting ? 'Deleting...' : 'Confirm Delete'}
              </ActionButton>
            </div>
          </section>
        </div>
      ) : null}

      {error ? <ErrorAlertCard message={error} /> : null}

      <section className="card">
        <div className="table-title">
          <h3>Trading Day Coverage</h3>
          <span className="count-pill">Total stocks: {totalStocks.toLocaleString('en-IN')}</span>
        </div>
        <GenericDataTable
          columns={summaryColumns}
          emptyMessage="No stock-history summary rows returned."
          pageSize={25}
          rows={filteredRows}
          tableClassName="data-table--blue"
          tableId="stockHistorySummaryTable"
        />
      </section>

      <Toast
        open={Boolean(pageToast)}
        title={pageToast?.title || ''}
        description={pageToast?.description || ''}
        tone={pageToast?.tone || 'info'}
        placement="top-right"
        onClose={() => setPageToast(null)}
      />
    </OpsPageShell>
  );
}


