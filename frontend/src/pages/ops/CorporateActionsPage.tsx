import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { AppDataTable, type AppDataTableColumn } from '../../components/app/AppDataTable';
import { LiveStatusPill } from '../../components/app/LiveStatusPill';
import { AppToolbar } from '../../components/app/AppToolbar';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { TrashIcon } from '../../components/ui/Icons';
import { Toast } from '../../components/ui/Toast';
import { extractRows, formatCellByKind, formatLegacyCount, pickField, safeLegacyText, type UnknownRecord } from '../../adapters/databasePageAdapter';
import { deleteCorporateActionSymbols, fetchCorporateActions } from '../../services/api/databaseApi';
import { OpsPageShell } from './OpsPageShell';
import { ActionButton, PageHero, SearchInput } from './opsPageHelpers';

type LoadStatus = 'error' | 'loading' | 'online';
type ToastTone = 'danger' | 'success' | 'warn';

type CorporateRowView = {
  id: string;
  isDeleting: boolean;
  raw: UnknownRecord;
  selected: boolean;
  serialNo: number;
  symbol: string;
};

type ToastState = {
  description: string;
  title: string;
  tone: ToastTone;
};

const IS_DEV = import.meta.env.DEV && import.meta.env.MODE !== 'test';
const PAGE_SIZE = 25;

const corporateColumns = [
  { key: 'sno', label: 'S.NO', dataCol: 'serialNo', aliases: ['serialNo', 'sno', 'SNO'], format: 'count', sortType: 'number' },
  { key: 'symbol', label: 'SYMBOL', dataCol: 'symbol', aliases: ['symbol', 'SYMBOL'], format: 'text', sortType: 'string' },
  { key: 'prevDate', label: 'PREV DATE', dataCol: 'prevDate', aliases: ['prev_date', 'prevDate', 'PREV_DATE', 'prev_trading_date', 'PREV_TRADING_DATE', 'previous_date', 'previousDate'], format: 'date', sortType: 'date' },
  { key: 'eventDate', label: 'EVENT DATE', dataCol: 'eventDate', aliases: ['event_date', 'eventDate', 'EVENT_DATE', 'trading_date', 'TRADING_DATE', 'action_date', 'corporate_action_date'], format: 'date', sortType: 'date' },
  { key: 'prevPrice', label: 'PREV PRICE', dataCol: 'prevPrice', aliases: ['prev_price', 'prevPrice', 'PREV_PRICE'], format: 'number', sortType: 'number' },
  { key: 'newPrice', label: 'NEW PRICE', dataCol: 'newPrice', aliases: ['new_price', 'newPrice', 'NEW_PRICE', 'price', 'PRICE', 'adjusted_price', 'post_action_price'], format: 'number', sortType: 'number' },
  { key: 'dropPct', label: 'DROP %', dataCol: 'dropPct', aliases: ['drop_pct', 'dropPct', 'DROP_PCT'], format: 'number', sortType: 'number' },
  { key: 'actions', label: 'POSSIBLE ACTIONS', dataCol: 'actions', aliases: ['possible_actions', 'possibleActions', 'POSSIBLE_ACTIONS'], format: 'text', sortType: 'string' },
  { key: 'expectedDrop', label: 'EXPECTED DROP %', dataCol: 'expectedDrop', aliases: ['expected_drop_pct', 'expectedDropPct', 'EXPECTED_DROP_PCT'], format: 'number', sortType: 'number' },
  { key: 'confidence', label: 'CONFIDENCE', dataCol: 'confidence', aliases: ['confidence', 'CONFIDENCE', 'confidence_score', 'confidenceScore', 'CONFIDENCE_SCORE', 'probability', 'probability_score'], format: 'text', sortType: 'string' },
] as const;

function sortValue(row: UnknownRecord, column: typeof corporateColumns[number]): string | number | null {
  const value = pickField(row, column.aliases);
  if (value === null || value === undefined || value === '') return null;
  if (column.sortType === 'number') {
    const parsed = Number(String(value).replace(/,/g, '').replace(/%/g, ''));
    return Number.isFinite(parsed) ? parsed : null;
  }
  return String(value);
}

function buildCsv(rows: UnknownRecord[]): string {
  const headers = corporateColumns.map((column) => column.label);
  const escape = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  const lines = [
    headers.map(escape).join(','),
    ...rows.map((row) => corporateColumns.map((column) => escape(pickField(row, column.aliases, ''))).join(',')),
  ];
  return lines.join('\n');
}

function downloadCsv(rows: UnknownRecord[]) {
  const blob = new Blob([buildCsv(rows)], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `corporate_actions_${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function formatRefreshTime(value: number | null): string {
  if (!value) return 'Last refreshed: -';
  return `Last refreshed: ${new Date(value).toLocaleString('en-IN', {
    day: '2-digit',
    hour: '2-digit',
    hour12: true,
    minute: '2-digit',
    month: 'short',
    year: 'numeric',
  })}`;
}

export function CorporateActionsPage() {
  const [deletePendingSymbols, setDeletePendingSymbols] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);
  const [lastLoadedAt, setLastLoadedAt] = useState<number | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [rows, setRows] = useState<UnknownRecord[]>([]);
  const [search, setSearch] = useState('');
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [toast, setToast] = useState<ToastState | null>(null);
  const deferredSearch = useDeferredValue(search);

  useEffect(() => {
    const controller = new AbortController();
    setStatus('loading');
    setError('');
    fetchCorporateActions(controller.signal).then((payload) => {
      const loadedRows = extractRows(payload, ['rows', 'data', 'items', 'candidates'])
        .map((row, index) => ({ serialNo: index + 1, ...row }));
      if (IS_DEV && loadedRows.length > 0) {
        const firstRow = loadedRows[0];
        const firstRowKeys = Object.keys(firstRow).sort();
        console.debug('[corporate-actions] first row keys', firstRowKeys);
        const missingColumns = [
          { label: 'PREV DATE', aliases: corporateColumns[2].aliases },
          { label: 'EVENT DATE', aliases: corporateColumns[3].aliases },
          { label: 'NEW PRICE', aliases: corporateColumns[5].aliases },
          { label: 'CONFIDENCE', aliases: corporateColumns[9].aliases },
        ].filter((column) => pickField(firstRow, column.aliases, null) === null);
        if (missingColumns.length > 0) {
          console.warn(
            '[corporate-actions] unresolved mapped columns in first row',
            missingColumns.map((column) => column.label),
          );
        }
      }
      setRows(loadedRows);
      setLastLoadedAt(Date.now());
      setStatus('online');
    }).catch((loadError) => {
      if (controller.signal.aborted) return;
      setError(loadError instanceof Error ? loadError.message : String(loadError));
      setStatus('error');
    });
    return () => controller.abort();
  }, [refreshVersion]);

  useEffect(() => {
    const availableSymbols = new Set(
      rows.map((row) => safeLegacyText(pickField(row, ['symbol', 'SYMBOL']), '').toUpperCase()).filter(Boolean),
    );
    setSelectedSymbols((current) => current.filter((symbol) => availableSymbols.has(symbol)));
  }, [rows]);

  const filteredRows = useMemo(() => {
    const token = deferredSearch.trim().toLowerCase();
    if (!token) return rows;
    return rows.filter((row) => safeLegacyText(pickField(row, ['symbol', 'SYMBOL']), '').toLowerCase().includes(token));
  }, [deferredSearch, rows]);

  const tableRows = useMemo<CorporateRowView[]>(() => filteredRows.map((row, index) => {
    const symbol = safeLegacyText(pickField(row, ['symbol', 'SYMBOL']), '');
    const normalizedSymbol = symbol.toUpperCase();
    return {
      id: `${normalizedSymbol || 'row'}-${safeLegacyText(pickField(row, ['trading_date', 'eventDate', 'EVENT_DATE']), String(index))}`,
      isDeleting: deletePendingSymbols.includes(normalizedSymbol),
      raw: row,
      selected: selectedSymbols.includes(normalizedSymbol),
      serialNo: index + 1,
      symbol,
    };
  }), [deletePendingSymbols, filteredRows, selectedSymbols]);

  const visibleSelection = useMemo(
    () => tableRows.map((row) => row.symbol.toUpperCase()).filter(Boolean),
    [tableRows],
  );
  const allVisibleSelected = visibleSelection.length > 0 && visibleSelection.every((symbol) => selectedSymbols.includes(symbol));
  const someVisibleSelected = visibleSelection.some((symbol) => selectedSymbols.includes(symbol));

  useEffect(() => {
    const checkbox = document.getElementById('corporate-actions-select-all') as HTMLInputElement | null;
    if (checkbox) checkbox.indeterminate = !allVisibleSelected && someVisibleSelected;
  }, [allVisibleSelected, someVisibleSelected]);

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
    const normalizedSymbols = Array.from(new Set(symbols.map((symbol) => symbol.trim().toUpperCase()).filter(Boolean)));
    if (!normalizedSymbols.length) return;
    const confirmation = normalizedSymbols.length === 1
      ? 'Are you sure you want to delete this corporate action symbol data?'
      : 'Are you sure you want to delete selected corporate action symbols data?';
    if (!window.confirm(confirmation)) return;

    setError('');
    setDeletePendingSymbols((current) => Array.from(new Set([...current, ...normalizedSymbols])));
    if (normalizedSymbols.length > 1) setIsBulkDeleting(true);
    try {
      const payload = await deleteCorporateActionSymbols({
        confirm_text: 'DELETE',
        symbols: normalizedSymbols,
      });
      const deletedRows = Number(payload.deleted_rows ?? payload.deletedRows ?? 0) || 0;
      setSelectedSymbols((current) => current.filter((symbol) => !normalizedSymbols.includes(symbol)));
      setRefreshVersion((current) => current + 1);
      setToast({
        description: deletedRows > 0
          ? `${label} deleted successfully. Rows: ${formatLegacyCount(deletedRows)}.`
          : `${label} matched no rows.`,
        title: normalizedSymbols.length === 1 ? 'Delete completed' : 'Bulk delete completed',
        tone: deletedRows > 0 ? 'success' : 'warn',
      });
    } catch (deleteError) {
      const message = deleteError instanceof Error ? deleteError.message : String(deleteError);
      setError(message);
      setToast({
        description: message,
        title: normalizedSymbols.length === 1 ? 'Delete failed' : 'Bulk delete failed',
        tone: 'danger',
      });
    } finally {
      setDeletePendingSymbols((current) => current.filter((symbol) => !normalizedSymbols.includes(symbol)));
      setIsBulkDeleting(false);
    }
  }

  const tableColumns = useMemo<Array<AppDataTableColumn<CorporateRowView>>>(() => ([
    {
      cellClassName: 'corporate-actions-table__checkbox-cell',
      dataCol: 'select',
      getSortValue: () => null,
      key: 'select',
      label: (
        <input
          id="corporate-actions-select-all"
          type="checkbox"
          className="corporate-actions-table__checkbox"
          checked={allVisibleSelected}
          aria-label="Select all visible rows"
          onChange={(event) => toggleVisibleSelection(event.currentTarget.checked)}
        />
      ),
      renderCell: (row) => (
        <input
          type="checkbox"
          className="corporate-actions-table__checkbox"
          checked={row.selected}
          aria-label={`Select ${row.symbol}`}
          onChange={(event) => setSymbolSelected(row.symbol, event.currentTarget.checked)}
        />
      ),
      sortable: false,
      sortType: 'string',
      sticky: true,
      stickyWidthPx: 56,
    },
    ...corporateColumns.map<AppDataTableColumn<CorporateRowView>>((column) => ({
      dataCol: column.dataCol,
      getSortValue: (row) => column.key === 'sno' ? row.serialNo : sortValue(row.raw, column),
      key: column.key,
      label: column.label,
      renderCell: (row) => column.key === 'sno'
        ? row.serialNo.toLocaleString('en-IN')
        : formatCellByKind(pickField(row.raw, column.aliases), column.format ?? 'text'),
      sortType: column.sortType ?? 'string',
    })),
    {
      cellClassName: 'corporate-actions-table__action-cell',
      dataCol: 'action',
      getSortValue: () => null,
      key: 'action',
      label: 'ACTION',
      renderCell: (row) => (
        <button
          type="button"
          className="corporate-actions-table__delete-button"
          aria-label={`Delete ${row.symbol} corporate action data`}
          title={`Delete ${row.symbol}`}
          disabled={row.isDeleting || isBulkDeleting}
          onClick={() => handleDelete([row.symbol], row.symbol)}
        >
          <TrashIcon aria-hidden="true" className="corporate-actions-table__delete-icon" />
        </button>
      ),
      sortable: false,
      sortType: 'string',
    },
  ]), [allVisibleSelected, isBulkDeleting, someVisibleSelected, tableRows, selectedSymbols]);

  const statusTitle = status === 'online'
    ? 'Corporate actions data is live from backend.'
    : status === 'loading'
      ? 'Corporate actions data is loading from backend.'
      : 'Corporate actions data could not be loaded.';
  const statusLabel = status === 'online' ? 'Live' : status === 'loading' ? 'Syncing' : 'Stale';
  const totalLabel = `Total rows: ${filteredRows.length.toLocaleString('en-IN')}`;

  return (
    <OpsPageShell activeDatabasePage="/app/database/corporate-actions" className="corporate-actions-react-page">
      <Toast
        open={Boolean(toast)}
        title={toast?.title || ''}
        description={toast?.description || ''}
        tone={toast?.tone || 'success'}
        placement="top-right"
        onClose={() => setToast(null)}
      />
      <PageHero title="Probable Split / Bonus Candidates" />

      <AppToolbar aria-label="Corporate actions controls" className="corporate-actions-toolbar">
        <div className="trend-toolbar__item trend-toolbar__item--status">
          <LiveStatusPill state={status === 'online' ? 'live' : status === 'loading' ? 'syncing' : 'stale'} title={statusTitle} label={statusLabel} />
          <div className="trend-toolbar__status-meta" aria-live="polite">
            <span>{totalLabel}</span>
            <span>{formatRefreshTime(lastLoadedAt)}</span>
          </div>
        </div>
        <div className="trend-toolbar__item trend-toolbar__item--search">
          <SearchInput value={search} onChange={setSearch} />
        </div>
        <div className="trend-toolbar__item trend-toolbar__item--actions">
          <ActionButton disabled={status === 'loading'} onClick={() => setRefreshVersion((current) => current + 1)}>Refresh</ActionButton>
          <ActionButton disabled={!filteredRows.length} onClick={() => downloadCsv(filteredRows)}>Download</ActionButton>
          {selectedSymbols.length > 0 ? (
            <ActionButton disabled={isBulkDeleting || status === 'loading'} onClick={() => handleDelete(selectedSymbols, `${selectedSymbols.length} symbol(s)`)}>
              {isBulkDeleting ? 'Deleting Selected...' : 'Delete Selected'}
            </ActionButton>
          ) : null}
          <span className="count-pill">TOTAL: {filteredRows.length.toLocaleString('en-IN')}</span>
          <span className="count-pill">{selectedSymbols.length.toLocaleString('en-IN')} selected</span>
        </div>
      </AppToolbar>

      {error ? <ErrorAlertCard message={error} /> : null}

      <section className="card">
        <div className="table-title">
          <h3>Probable Split / Bonus Candidates</h3>
          <span className="count-pill">TOTAL: {filteredRows.length.toLocaleString('en-IN')}</span>
        </div>
        <AppDataTable
          columns={tableColumns}
          emptyMessage="No split / bonus candidates returned."
          getRowKey={(row) => row.id}
          pageSize={PAGE_SIZE}
          rows={tableRows}
          showTopPagination
          tableClassName="corporate-actions-table"
          tableId="corporateActionsTable"
        />
      </section>
    </OpsPageShell>
  );
}
