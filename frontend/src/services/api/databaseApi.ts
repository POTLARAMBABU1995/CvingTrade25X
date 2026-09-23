import { legacyApiGet, legacyApiGetBlob, legacyApiPost, type QueryParams, type RequestOptions } from '../../api/client';

export type DatabaseApiPayload = Record<string, unknown>;

export function getDatabasePayload(path: string, params?: QueryParams, options: RequestOptions = {}) {
  return legacyApiGet<DatabaseApiPayload>(path, params, options);
}

export function postDatabasePayload(path: string, body: unknown = {}, options: RequestOptions = {}) {
  return legacyApiPost<DatabaseApiPayload>(path, body, options);
}

export function fetchStockHistorySymbols(signal?: AbortSignal) {
  return getDatabasePayload('/api/marketdata/symbols', { source: 'stock_eod_history', limit: 5000 }, {
    signal,
    timeoutMs: 30000,
  });
}

export function fetchStockHistoryStats(signal?: AbortSignal) {
  return getDatabasePayload('/api/marketdata/stats', { source: 'stock_eod_history' }, {
    signal,
    timeoutMs: 45000,
  });
}

export function fetchStockHistorySummary(params: QueryParams, signal?: AbortSignal) {
  return getDatabasePayload('/api/marketdata/summary/table', {
    source: 'stock_eod_history',
    ...params,
  }, {
    signal,
    timeoutMs: 60000,
  });
}

export function mergeLatestStockHistory() {
  return postDatabasePayload('/api/marketdata/merge-latest', {}, { timeoutMs: 180000 });
}

export function clearStockHistory(confirmToken: string) {
  return postDatabasePayload('/api/marketdata/stock-eod/clear', { confirm_text: confirmToken }, { timeoutMs: 180000 });
}

export function fetchHistoricalTables(signal?: AbortSignal) {
  return getDatabasePayload('/api/historical-data/tables', undefined, { signal, timeoutMs: 120000 });
}

export function fetchHistoricalSummary(params: QueryParams, signal?: AbortSignal) {
  return getDatabasePayload('/api/historical-data/summary', params, { signal, timeoutMs: 120000 });
}

export function downloadHistoricalSymbolBundle(symbol: string, tableName: string) {
  return legacyApiGetBlob(
    `/api/historical-data/symbol/${encodeURIComponent(symbol)}/download`,
    { table_name: tableName },
    { timeoutMs: 120000 },
  );
}

export function deleteHistoricalSymbols(body: unknown) {
  return postDatabasePayload('/api/historical-data/delete-symbols', body, { timeoutMs: 120000 });
}

export function fetchCorporateActions(signal?: AbortSignal) {
  return getDatabasePayload('/api/corporate-actions/split-bonus-candidates', undefined, {
    signal,
    timeoutMs: 60000,
  });
}

export function deleteCorporateActionSymbols(body: unknown) {
  return postDatabasePayload('/api/corporate-actions/split-bonus-candidates/delete-symbols', body, { timeoutMs: 120000 });
}
