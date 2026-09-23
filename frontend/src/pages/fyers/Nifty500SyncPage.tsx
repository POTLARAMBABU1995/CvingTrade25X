import { useEffect, useMemo, useState } from 'react';
import { CopyDiagnosticsButton } from '../../components/CopyDiagnosticsButton';
import { AppToolbar } from '../../components/app/AppToolbar';
import { AppPagination } from '../../components/app/AppPagination';
import { ErrorState } from '../../components/ui/ErrorState';
import { asRecord, formatLegacyCount, pickField, safeLegacyText, type UnknownRecord } from '../../adapters/databasePageAdapter';
import { extractNestedRows, formatFyersCell, pickFyersField } from '../../adapters/fyersPageAdapter';
import {
  addNifty500Rows,
  compareNifty500Sync,
  compareNifty500SyncForm,
  deleteNifty500Row,
  fetchNifty500Sync,
  mergeNifty500Sync,
  mergeNifty500SyncForm,
  updateNifty500Row,
} from '../../services/api/fyersApi';
import { ActionButton, KpiGrid, PageHero, TextField } from '../ops/opsPageHelpers';
import { FyersMigrationLayout } from './FyersMigrationLayout';

type LoadStatus = 'error' | 'loading' | 'online' | 'warn';
type Nifty500SyncAction = 'add' | 'compare' | 'delete' | 'load' | 'merge' | 'update' | 'upload';
type Nifty500SyncErrorState = {
  action: Nifty500SyncAction;
  message: string;
};

const PAGE_SIZE = 50;
const MAX_UPLOAD_FILES = 100;
const DISALLOWED_SYMBOLS = new Set([
  'SYMBOL', 'SHARES', 'CRORES', 'SNO', 'PARENTSECTOR', 'HEALTHCARE',
  'NIFTY500HEALTHCARE', 'NIFTYREITS&REALTY', 'NIFTYPRIVATEBANK', 'NIFTYPSUBANK',
  'NIFTYPHARMA', 'NIFTYOIL&GAS', 'NIFTYMIDSMALLIT&TELECOM', 'NIFTYMIDSMALLFINANCIALSERVICES',
  'NIFTYMIDSMALLHEALTHCARE', 'NIFTYMETAL', 'NIFTYMEDIA', 'NIFTYIT', 'NIFTYHEALTHCAREINDEX',
  'NIFTYFMCG', 'NIFTYFINANCIALSERVICESEX-BANK', 'NIFTYCONSUMERDURABLES', 'NIFTYCHEMICALS',
  'NIFTYCEMENT', 'NIFTYAUTO', 'NIFTYTOTALMARKET', 'NIFTYENERGY',
]);

function parseSymbols(input: string) {
  return Array.from(
    new Set(
      input
        .split(',')
        .map((symbol) => symbol.trim().toUpperCase())
        .filter((symbol) => isAllowedSymbol(symbol)),
    ),
  );
}

function isAllowedSymbol(symbol: string) {
  if (!symbol) return false;
  if (DISALLOWED_SYMBOLS.has(symbol)) return false;
  if (/^\d+$/.test(symbol)) return false;
  if (symbol.startsWith('NIFTY')) return false;
  return /^[A-Z][A-Z0-9&_-]*$/.test(symbol);
}

function nestedRecord(payload: UnknownRecord, key: string) {
  return asRecord(payload[key]);
}

export function normalizeNifty500SyncSnapshot(payload: unknown): UnknownRecord {
  const source = asRecord(payload);
  const enveloped = asRecord(source.data ?? source.payload ?? source.result);
  return Object.keys(enveloped).length ? enveloped : source;
}

export function buildNifty500SyncErrorContent(errorState: Nifty500SyncErrorState | null, uploadedFileName: string) {
  const action = errorState?.action || 'load';
  const message = safeLegacyText(errorState?.message, 'Unexpected NIFTY500 sync error.');
  const fileLabel = uploadedFileName || 'the uploaded CSV';
  const emptyCsvError = /no symbols were found in the uploaded (csv|file)/i.test(message);

  if (emptyCsvError) {
    return {
      description: `The compare request rejected ${fileLabel} because no valid NSE symbols were detected from a symbol column.`,
      guidance: 'Upload CSV, XLSX, or XLS files that contain a header named symbol. The app will read only that symbol column and ignore the rest.',
      retryLabel: action === 'merge' ? 'Retry Merge' : 'Retry Compare',
      title: 'Uploaded file has no valid symbols',
    };
  }

  const actionLabels: Record<Nifty500SyncAction, { retryLabel: string; title: string }> = {
    add: { retryLabel: 'Retry Add', title: 'Unable to add symbol' },
    compare: { retryLabel: 'Retry Compare', title: 'Compare request failed' },
    delete: { retryLabel: 'Retry Delete', title: 'Unable to delete symbol' },
    load: { retryLabel: 'Reload Existing CSV', title: 'Existing FYERS CSV is unavailable' },
    merge: { retryLabel: 'Retry Merge', title: 'Merge request failed' },
    update: { retryLabel: 'Retry Update', title: 'Unable to update symbol' },
    upload: { retryLabel: 'Retry Compare', title: 'Unable to process uploaded CSV' },
  };

  return {
    description: message,
    guidance: action === 'load'
      ? 'The page could not load the current FYERS NIFTY500 snapshot. Reload the existing CSV or retry after the backend is healthy.'
      : `The ${action} action did not complete successfully. Review the diagnostics, correct the input if needed, and retry.`,
    retryLabel: actionLabels[action].retryLabel,
    title: actionLabels[action].title,
  };
}

function metricCards(payload: UnknownRecord) {
  const summary = nestedRecord(payload, 'summary');
  const existing = nestedRecord(payload, 'existing');
  const newest = nestedRecord(payload, 'new');
  return [
    { label: 'Matched', value: formatLegacyCount(pickField(summary, ['matchedCount'], 0)) },
    { label: 'Missing In Existing', value: formatLegacyCount(pickField(summary, ['missingInExistingCount'], 0)) },
    { label: 'Existing Only', value: formatLegacyCount(pickField(summary, ['existingOnlyCount'], 0)) },
    { label: 'Merged', value: formatLegacyCount(pickField(summary, ['mergedCount'], 0)) },
    { label: 'Existing Total', value: formatLegacyCount(pickField(existing, ['totalCount'], 0)) },
    { label: 'New Total', value: formatLegacyCount(pickField(newest, ['totalCount'], 0)) },
  ];
}

function normalizeFlag(value: unknown) {
  const token = safeLegacyText(value, '').trim().toUpperCase();
  if (token === 'Y' || token === 'N') return token;
  if (!token) return 'N';
  if (token.includes('MATCH')) return 'Y';
  return 'N';
}

function SymbolTable({
  actionHeader,
  actionLabel,
  onActionRow,
  onDeleteRow,
  onEditRow,
  onSelect,
  page,
  rows,
  selectedSymbol,
  setPage,
  title,
}: {
  actionHeader?: string;
  actionLabel?: string;
  onActionRow?: (symbol: string) => void;
  onDeleteRow?: (symbol: string) => void;
  onEditRow?: (symbol: string) => void;
  onSelect: (symbol: string) => void;
  page: number;
  rows: UnknownRecord[];
  selectedSymbol: string;
  setPage: (page: number) => void;
  title: string;
}) {
  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const start = (currentPage - 1) * PAGE_SIZE;
  const visibleRows = rows.slice(start, start + PAGE_SIZE);
  const pager = <AppPagination className="fyers-react-pagination" currentPage={currentPage} totalPages={totalPages} onPageChange={setPage} />;

  return (
    <section className="card nifty-sync-panel">
      <div className="table-title">
        <h3>{title}</h3>
        <span className="count-pill">TOTAL: {rows.length.toLocaleString('en-IN')}</span>
      </div>
      {pager}
      <div className="table-wrapper nifty-sync-table-wrap">
        <table className="app-data-table table-sticky-safe data-table nifty-sync-table">
          <colgroup>
            <col data-col="sno" />
            <col data-col="symbol" />
            <col />
            <col />
            {onActionRow || onEditRow || onDeleteRow ? <col /> : null}
          </colgroup>
          <thead>
            <tr>
              <th data-col="sno">S.No</th>
              <th data-col="symbol">SYMBOL</th>
              <th>FLAG</th>
              <th>COUNT</th>
              {onActionRow || onEditRow || onDeleteRow ? <th>{actionHeader || 'ACTION'}</th> : null}
            </tr>
          </thead>
          <tbody>
            {visibleRows.length ? visibleRows.map((row, index) => {
              const symbol = safeLegacyText(pickFyersField(row, ['symbol', 'SYMBOL']), '');
              return (
                <tr
                  key={`${symbol}-${start + index}`}
                  className={selectedSymbol === symbol ? 'fyers-react-selected-row' : undefined}
                  data-symbol={symbol}
                  onClick={() => onSelect(symbol)}
                >
                  <td data-col="sno">{start + index + 1}</td>
                  <td data-col="symbol">{symbol || '-'}</td>
                  <td>{normalizeFlag(pickField(row, ['matchState', 'flag', 'FLAG']))}</td>
                  <td>{formatFyersCell(pickField(row, ['symbolCount', 'symbol_count', 'SYMBOL_COUNT']), 'count')}</td>
                  {onActionRow || onEditRow || onDeleteRow ? (
                    <td>
                      <div className="fyers-react-actions fyers-react-actions--table">
                        {onActionRow ? (
                          <button
                            type="button"
                            className="page-btn"
                            title={`${actionLabel || 'Action'} ${symbol}`}
                            onClick={(event) => {
                              event.stopPropagation();
                              onActionRow(symbol);
                            }}
                          >
                            {actionLabel || '✎'}
                          </button>
                        ) : null}
                        {onEditRow ? (
                          <button
                            type="button"
                            className="page-btn"
                            title={`Edit ${symbol}`}
                            onClick={(event) => {
                              event.stopPropagation();
                              onEditRow(symbol);
                            }}
                          >
                            ✎
                          </button>
                        ) : null}
                        {onDeleteRow ? (
                          <button
                            type="button"
                            className="page-btn"
                            title={`Delete ${symbol}`}
                            onClick={(event) => {
                              event.stopPropagation();
                              onDeleteRow(symbol);
                            }}
                          >
                            🗑
                          </button>
                        ) : null}
                      </div>
                    </td>
                  ) : null}
                </tr>
              );
            }) : (
              <tr>
                <td className="empty" colSpan={onActionRow || onEditRow || onDeleteRow ? 5 : 4}>No rows returned.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {pager}
    </section>
  );
}

export function Nifty500SyncPage() {
  const [errorState, setErrorState] = useState<Nifty500SyncErrorState | null>(null);
  const [symbolInput, setSymbolInput] = useState('');
  const [editingOriginalSymbol, setEditingOriginalSymbol] = useState('');
  const [editingSymbolValue, setEditingSymbolValue] = useState('');
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [newCsvName, setNewCsvName] = useState('');
  const [newCsvText, setNewCsvText] = useState('');
  const [newSearch, setNewSearch] = useState('');
  const [existingSearch, setExistingSearch] = useState('');
  const [newPage, setNewPage] = useState(1);
  const [existingPage, setExistingPage] = useState(1);
  const [payload, setPayload] = useState<UnknownRecord>({});
  const [selectedExistingSymbol, setSelectedExistingSymbol] = useState('');
  const [selectedNewSymbol, setSelectedNewSymbol] = useState('');
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [statusMessage, setStatusMessage] = useState('Loading existing FYERS CSV');
  const [toast, setToast] = useState('');

  function pushToast(message: string) {
    setToast(message);
  }

  function clearErrorState() {
    setErrorState(null);
  }

  function captureError(action: Nifty500SyncAction, error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    setErrorState({ action, message });
  }

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(''), 3000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  async function loadSnapshot(signal?: AbortSignal, message = 'Loading existing FYERS CSV') {
    setStatus('loading');
    setStatusMessage(message);
    clearErrorState();
    try {
      const result = await fetchNifty500Sync(signal);
      setPayload(normalizeNifty500SyncSnapshot(result));
      setStatus('online');
      setStatusMessage('Live');
    } catch (loadError) {
      if (signal?.aborted) return;
      captureError('load', loadError);
      setStatus('error');
      setStatusMessage('Check');
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    loadSnapshot(controller.signal);
    return () => controller.abort();
  }, []);

  const newRows = useMemo(
    () => extractNestedRows(payload, 'new').filter((row) => isAllowedSymbol(safeLegacyText(pickFyersField(row, ['symbol', 'SYMBOL']), '').toUpperCase())),
    [payload],
  );
  const existingRows = useMemo(
    () => extractNestedRows(payload, 'existing').filter((row) => isAllowedSymbol(safeLegacyText(pickFyersField(row, ['symbol', 'SYMBOL']), '').toUpperCase())),
    [payload],
  );
  const existingSymbolSet = useMemo(
    () => new Set(existingRows.map((row) => safeLegacyText(pickFyersField(row, ['symbol', 'SYMBOL']), '').toUpperCase()).filter(Boolean)),
    [existingRows],
  );
  const filteredNewRows = useMemo(() => {
    const token = newSearch.trim().toUpperCase();
    if (!token) return newRows;
    return newRows.filter((row) => safeLegacyText(pickFyersField(row, ['symbol', 'SYMBOL']), '').toUpperCase().includes(token));
  }, [newRows, newSearch]);
  const filteredExistingRows = useMemo(() => {
    const token = existingSearch.trim().toUpperCase();
    if (!token) return existingRows;
    return existingRows.filter((row) => safeLegacyText(pickFyersField(row, ['symbol', 'SYMBOL']), '').toUpperCase().includes(token));
  }, [existingRows, existingSearch]);
  const existing = nestedRecord(payload, 'existing');
  const newest = nestedRecord(payload, 'new');

  function buildUploadFormData(files: File[]) {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file, file.name));
    if (files[0]?.name) {
      formData.append('filename', files[0].name);
    }
    return formData;
  }

  async function compareUpload(filesOverride?: File[]) {
    const activeFiles = filesOverride?.length ? filesOverride : uploadFiles;
    if (!activeFiles.length && !newCsvText) {
      setStatus('warn');
      setStatusMessage('Import a CSV, XLSX, or XLS file first.');
      return;
    }
    setStatus('loading');
    clearErrorState();
    try {
      const result = activeFiles.length
        ? await compareNifty500SyncForm(buildUploadFormData(activeFiles))
        : await compareNifty500Sync({ filename: newCsvName, newCsvContent: newCsvText });
      setPayload(normalizeNifty500SyncSnapshot(result));
      setSelectedExistingSymbol('');
      setSelectedNewSymbol('');
      setStatus('online');
      setStatusMessage('Compared');
    } catch (compareError) {
      captureError('compare', compareError);
      setStatus('error');
      setStatusMessage('Compare failed');
    }
  }

  async function mergeMissing() {
    if (!uploadFiles.length && !newCsvText) {
      setStatus('warn');
      setStatusMessage('Upload a CSV, XLSX, or XLS file before merging.');
      return;
    }
    setStatus('loading');
    clearErrorState();
    try {
      const result = uploadFiles.length
        ? await mergeNifty500SyncForm(buildUploadFormData(uploadFiles))
        : await mergeNifty500Sync({ filename: newCsvName, newCsvContent: newCsvText });
      setPayload(normalizeNifty500SyncSnapshot(result));
      setStatus('online');
      setStatusMessage('Merge complete');
    } catch (mergeError) {
      captureError('merge', mergeError);
      setStatus('error');
      setStatusMessage('Merge failed');
    }
  }

  async function addSymbols(symbols: string[]) {
    const normalized = parseSymbols(symbols.join(','));
    if (!normalized.length) {
      setStatus('warn');
      setStatusMessage('Symbol is nor present.');
      pushToast('Symbol is nor present');
      return;
    }
    setStatus('loading');
    clearErrorState();
    try {
      const result = await addNifty500Rows(normalized.length === 1 ? { symbol: normalized[0] } : { symbols: normalized });
      setPayload(normalizeNifty500SyncSnapshot(result));
      setSymbolInput('');
      setStatus('online');
      setStatusMessage('Symbol added');
      if (uploadFiles.length || newCsvText) await compareUpload();
    } catch (addError) {
      captureError('add', addError);
      setStatus('error');
      setStatusMessage('Add failed');
    }
  }

  async function deleteSymbols(symbols: string[]) {
    const normalized = parseSymbols(symbols.join(','));
    if (!normalized.length) {
      setStatus('warn');
      setStatusMessage('Enter at least one symbol to delete.');
      return;
    }
    if (!window.confirm(`Delete ${normalized.length} symbol(s) from existing FYERS CSV?`)) return;
    setStatus('loading');
    clearErrorState();
    try {
      let deletedCount = 0;
      let alreadyAbsentCount = 0;
      for (const symbol of normalized) {
        const result = asRecord(await deleteNifty500Row({ symbol }));
        if (result.deleted === false) alreadyAbsentCount += 1;
        else deletedCount += 1;
      }
      await loadSnapshot(undefined, `Updated existing FYERS CSV. Reloading current symbols`);
      setSymbolInput('');
      setStatus('online');
      setStatusMessage(
        alreadyAbsentCount
          ? `Deleted ${deletedCount}; ${alreadyAbsentCount} already absent.`
          : `Deleted ${deletedCount} symbol(s).`,
      );
      if (uploadFiles.length || newCsvText) await compareUpload();
    } catch (deleteError) {
      captureError('delete', deleteError);
      setStatus('error');
      setStatusMessage('Bulk delete failed');
    }
  }

  function beginEditExistingSymbol(originalSymbol: string) {
    setEditingOriginalSymbol(originalSymbol);
    setEditingSymbolValue(originalSymbol);
    clearErrorState();
  }

  function cancelEditExistingSymbol() {
    setEditingOriginalSymbol('');
    setEditingSymbolValue('');
  }

  async function saveExistingSymbol() {
    const originalSymbol = editingOriginalSymbol;
    const updatedSymbol = editingSymbolValue.trim().toUpperCase();
    if (!originalSymbol) return;
    if (!updatedSymbol || updatedSymbol === originalSymbol) return;
    if (!isAllowedSymbol(updatedSymbol)) {
      setStatus('warn');
      setStatusMessage('Symbol is nor present.');
      pushToast('Symbol is nor present');
      return;
    }
    if (existingSymbolSet.has(updatedSymbol)) {
      setStatus('warn');
      setStatusMessage(`Symbol ${updatedSymbol} already exists.`);
      pushToast(`Symbol ${updatedSymbol} already exists.`);
      return;
    }
    setStatus('loading');
    clearErrorState();
    try {
      const result = await updateNifty500Row({ originalSymbol, symbol: updatedSymbol });
      setPayload(normalizeNifty500SyncSnapshot(result));
      cancelEditExistingSymbol();
      setStatus('online');
      setStatusMessage('Symbol updated');
      if (uploadFiles.length || newCsvText) await compareUpload();
    } catch (updateError) {
      const message = updateError instanceof Error ? updateError.message : String(updateError);
      if (/not found in the existing FYERS CSV/i.test(message)) {
        setStatus('warn');
        setStatusMessage('Symbol is nor present.');
        pushToast('Symbol is nor present');
        return;
      }
      setErrorState({ action: 'update', message });
      setStatus('error');
      setStatusMessage('Update failed');
    }
  }

  async function deleteExistingSymbol(symbol: string) {
    await deleteSymbols([symbol]);
  }

  async function handleCsvFileSelection(fileList: FileList | null) {
    const files = fileList ? Array.from(fileList) : [];
    if (!files.length) return;
    if (files.length > MAX_UPLOAD_FILES) {
      setStatus('warn');
      setStatusMessage(`You can upload up to ${MAX_UPLOAD_FILES} files at once.`);
      return;
    }
    try {
      clearErrorState();
      const mergedName = files.length === 1
        ? (files[0]?.name || 'uploaded.csv')
        : `${files.length} files selected`;

      setUploadFiles(files);
      setNewCsvName(mergedName);
      setNewCsvText('__uploaded__');
      setNewPage(1);
      setStatusMessage(`Loaded ${files.length} file(s)`);
      await compareUpload(files);
    } catch (fileError) {
      captureError('upload', fileError);
      setStatus('error');
      setStatusMessage('Unable to read uploaded file');
    }
  }

  function clearUpload() {
    setUploadFiles([]);
    setNewCsvName('');
    setNewCsvText('');
    setSelectedNewSymbol('');
    clearErrorState();
    loadSnapshot(undefined, 'Upload cleared. Reloading existing FYERS CSV');
  }

  async function retryAfterError() {
    const action = errorState?.action || 'load';
    if (action === 'compare' || action === 'upload') {
      await compareUpload();
      return;
    }
    if (action === 'merge') {
      await mergeMissing();
      return;
    }
    await loadSnapshot();
  }

  const errorContent = buildNifty500SyncErrorContent(errorState, newCsvName);
  const showErrorPage = status === 'error' && Boolean(errorState);
  const diagnosticsMessage = [
    'FYERS NIFTY500 Sync route: /app/fyers/nifty500-sync',
    `Current upload: ${newCsvName || 'No file selected'}`,
    `Status label: ${statusMessage || '-'}`,
  ].join('\n');

  return (
    <FyersMigrationLayout activeFyersPage="/app/fyers/nifty500-sync" className="nifty-sync-react-page">
      <PageHero title="NIFTY500 CSV SYNC" />

      {showErrorPage ? (
        <section className="card space-y-5 border border-rose-200 bg-rose-50/70 p-5" role="alert">
          <ErrorState
            surface="light"
            eyebrow="FYERS NIFTY500 Sync"
            title={errorContent.title}
            description={errorContent.description}
            retryLabel={errorContent.retryLabel}
            onRetry={() => { void retryAfterError(); }}
          />
          <div className="rounded-2xl border border-rose-200 bg-white/90 p-4 text-sm text-slate-700">
            <p className="m-0 font-bold uppercase tracking-[0.14em] text-rose-700">What to check</p>
            <p className="mt-2 mb-0 leading-6">{errorContent.guidance}</p>
            {errorState?.message ? (
              <p className="mt-3 mb-0 break-words rounded-xl border border-rose-100 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-800">
                Backend message: {errorState.message}
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-3">
            <ActionButton onClick={() => { void retryAfterError(); }}>{errorContent.retryLabel}</ActionButton>
            <ActionButton onClick={() => { void loadSnapshot(); }}>Reload Existing CSV</ActionButton>
            <ActionButton disabled={!newCsvText} onClick={clearUpload}>Clear Upload</ActionButton>
            <CopyDiagnosticsButton compact={false} extraMessage={diagnosticsMessage} />
          </div>
        </section>
      ) : (
        <>

      <KpiGrid items={metricCards(payload)} />

      <section className="nifty-sync-grid">
        <article className="card nifty-sync-panel">
          <div className="table-title">
            <h3>New NIFTY500 File(s)</h3>
            <span className="count-pill">{newCsvName || 'No file selected'}</span>
          </div>
          <div className="nifty-sync-upload-row">
            <label className="database-react-field">
              <span className="sr-only">Upload file</span>
              <input type="file" accept=".csv,.xlsx,.xls,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" multiple onChange={(event) => handleCsvFileSelection(event.currentTarget.files)} />
            </label>
            <div className="nifty-sync-chip-row">
              <span className="nifty-sync-chip"><strong>Total</strong> {formatLegacyCount(pickField(newest, ['totalCount'], 0))}</span>
              <span className="nifty-sync-chip"><strong>Unique</strong> {formatLegacyCount(pickField(newest, ['uniqueCount'], 0))}</span>
            </div>
          </div>
          <div className="fyers-react-actions">
            <ActionButton disabled={status === 'loading' || !newCsvText} onClick={compareUpload}>Compare Files</ActionButton>
            <ActionButton disabled={status === 'loading' || !newCsvText} onClick={mergeMissing}>Merge Missing</ActionButton>
            <ActionButton disabled={!newCsvText} onClick={clearUpload}>Clear Upload</ActionButton>
            <ActionButton disabled={!selectedNewSymbol} onClick={() => addSymbols([selectedNewSymbol])}>Create Selected</ActionButton>
          </div>
          <div className="nifty-sync-search-row">
            <TextField
              label="Search New Symbols"
              value={newSearch}
              onChange={(value) => { setNewSearch(value); setNewPage(1); }}
              placeholder="RELIANCE"
            />
          </div>
        </article>

        <article className="card nifty-sync-panel">
          <div className="table-title">
            <h3>Existing FYERS CSV</h3>
            <span className="count-pill">{safeLegacyText(pickField(existing, ['path']), '-')}</span>
          </div>
          <div className="nifty-sync-chip-row">
            <span className="nifty-sync-chip"><strong>Total</strong> {formatLegacyCount(pickField(existing, ['totalCount'], 0))}</span>
            <span className="nifty-sync-chip"><strong>Unique</strong> {formatLegacyCount(pickField(existing, ['uniqueCount'], 0))}</span>
          </div>
          <AppToolbar aria-label="Existing CSV controls">
            <TextField label="" value={symbolInput} onChange={setSymbolInput} placeholder="AKZOINDIA, CIGNITITEC, DBREALTY" />
            <ActionButton disabled={status === 'loading'} onClick={() => addSymbols([symbolInput])}>Add</ActionButton>
            <ActionButton disabled={status === 'loading'} onClick={() => deleteSymbols([symbolInput])}>Delete</ActionButton>
            <ActionButton disabled={status === 'loading'} onClick={() => loadSnapshot()}>Reload Existing CSV</ActionButton>
          </AppToolbar>
          {editingOriginalSymbol ? (
            <div className="nifty-sync-edit-row" role="group" aria-label={`Update ${editingOriginalSymbol}`}>
              <TextField
                label={`Update ${editingOriginalSymbol}`}
                value={editingSymbolValue}
                onChange={setEditingSymbolValue}
                placeholder="NSE symbol"
              />
              <ActionButton disabled={status === 'loading'} onClick={() => { void saveExistingSymbol(); }}>Update</ActionButton>
              <ActionButton disabled={status === 'loading'} onClick={cancelEditExistingSymbol}>Cancel</ActionButton>
            </div>
          ) : null}
          <div className="nifty-sync-search-row">
            <TextField
              label="Search Existing Symbols"
              value={existingSearch}
              onChange={(value) => { setExistingSearch(value); setExistingPage(1); }}
              placeholder="TCS"
            />
          </div>
        </article>
      </section>
      {toast ? <span className="trend-sync-toast">{toast}</span> : null}

      <section className="nifty-sync-results">
        <SymbolTable
          title="New NIFTY500"
          rows={filteredNewRows}
          page={newPage}
          setPage={setNewPage}
          actionHeader="ACTION"
          actionLabel="✎"
          onActionRow={(symbol) => setSelectedNewSymbol(symbol)}
          selectedSymbol={selectedNewSymbol}
          onSelect={(symbol) => setSelectedNewSymbol(symbol)}
        />
        <SymbolTable
          title="Existing NIFTY500"
          rows={filteredExistingRows}
          page={existingPage}
          setPage={setExistingPage}
          onDeleteRow={(symbol) => { void deleteExistingSymbol(symbol); }}
          onEditRow={beginEditExistingSymbol}
          selectedSymbol={selectedExistingSymbol}
          onSelect={(symbol) => {
            setSelectedExistingSymbol(symbol);
          }}
        />
      </section>
        </>
      )}
    </FyersMigrationLayout>
  );
}


