import { useEffect, useMemo, useState } from 'react';
import { AppToolbar } from '../../components/app/AppToolbar';
import { AppPagination } from '../../components/app/AppPagination';
import { ErrorState } from '../../components/ui/ErrorState';
import { asRecord, safeLegacyText, type UnknownRecord } from '../../adapters/databasePageAdapter';
import { fetchNifty500Sync } from '../../services/api/fyersApi';
import { ActionButton, PageHero, TextField } from '../ops/opsPageHelpers';
import { FyersMigrationLayout } from './FyersMigrationLayout';

type Nifty500SyncAction = 'add' | 'compare' | 'delete' | 'load' | 'merge' | 'update' | 'upload';
type Nifty500SyncErrorState = { action: Nifty500SyncAction; message: string };
const PAGE_SIZE = 50;

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
    load: { retryLabel: 'Retry', title: 'Symbol table is unavailable' },
    merge: { retryLabel: 'Retry Merge', title: 'Merge request failed' },
    update: { retryLabel: 'Retry Update', title: 'Unable to update symbol' },
    upload: { retryLabel: 'Retry Compare', title: 'Unable to process uploaded CSV' },
  };

  return {
    description: message,
    guidance: action === 'load'
      ? 'Check Oracle connectivity and access to NSE_SYMBOLS_COMMON_DATA, then retry.'
      : `The ${action} action did not complete successfully. Review the diagnostics, correct the input if needed, and retry.`,
    retryLabel: actionLabels[action].retryLabel,
    title: actionLabels[action].title,
  };
}

export function Nifty500SyncPage() {
  const [payload, setPayload] = useState<UnknownRecord>({});
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  async function load(signal?: AbortSignal) {
    setLoading(true);
    setError('');
    try {
      const result = await fetchNifty500Sync(signal);
      if (!signal?.aborted) setPayload(normalizeNifty500SyncSnapshot(result));
    } catch (cause) {
      if (!signal?.aborted) setError(cause instanceof Error ? cause.message : 'Unable to load symbols.');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, []);
  const rows = useMemo(() => {
    const existing = asRecord(payload.existing);
    const items = Array.isArray(existing.rows) ? existing.rows.map(asRecord) : [];
    return items.filter((row) => safeLegacyText(row.symbol, '').toUpperCase().includes(search.trim().toUpperCase()));
  }, [payload, search]);
  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const start = (currentPage - 1) * PAGE_SIZE;
  return (
    <FyersMigrationLayout activeFyersPage="/app/fyers/nifty500-sync" className="nifty-sync-react-page">
      <PageHero title="NIFTY500 SYMBOLS" />
      <section className="card nifty-sync-panel" aria-busy={loading}>
        <p>Source: <strong>NSE_SYMBOLS_COMMON_DATA</strong> · Read-only</p>
        <AppToolbar aria-label="Symbol table controls">
          <TextField label="Search Symbols" value={search} onChange={(value) => { setSearch(value); setPage(1); }} placeholder="TCS" />
          <ActionButton disabled={loading} onClick={() => { void load(); }}>Refresh Symbols</ActionButton>
        </AppToolbar>
        {loading ? <p role="status">Loading symbols…</p> : null}
        {error ? <ErrorState title="Symbol table is unavailable" description={error} retryLabel="Retry" onRetry={() => { void load(); }} /> : null}
        <p>Total: {rows.length.toLocaleString('en-IN')}</p>
        <div className="table-wrapper nifty-sync-table-wrap">
          <table className="app-data-table table-sticky-safe data-table">
            <thead><tr><th>S.No</th><th>SYMBOL</th></tr></thead>
            <tbody>
              {rows.slice(start, start + PAGE_SIZE).map((row, index) => (
                <tr key={safeLegacyText(row.symbol, '')}><td>{start + index + 1}</td><td>{safeLegacyText(row.symbol, '')}</td></tr>
              ))}
              {!rows.length && !loading && !error ? <tr><td colSpan={2}>No symbols found.</td></tr> : null}
            </tbody>
          </table>
        </div>
        <AppPagination currentPage={currentPage} totalPages={totalPages} onPageChange={setPage} />
      </section>
    </FyersMigrationLayout>
  );
}
