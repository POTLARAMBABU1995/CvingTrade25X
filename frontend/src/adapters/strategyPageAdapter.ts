export type StrategyWireRow = Record<string, unknown>;

export type StrategyTableColumn = {
  key: string;
  label: string;
  align?: 'left' | 'right' | 'center';
  dataCol?: string;
  fields?: readonly string[];
  renderAs?: 'ath' | 'gap' | 'marketCapIndex' | 'marketCapRank' | 'marketCapValue' | 'signedPercent' | 'srLevels';
  sortable?: boolean;
  sticky?: 'sno' | 'symbol';
  sortType?: 'date' | 'number' | 'string';
};

const EMPTY_TEXT = '-';

export function getStrategyFieldKeys(column: StrategyTableColumn): string[] {
  const keys = [column.key, ...(column.fields ?? []), column.key.toUpperCase()];
  const seen = new Set<string>();
  return keys.filter((key) => {
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function pickStrategyField(row: StrategyWireRow, keys: readonly string[]): unknown {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(row, key)) {
      const value = row[key];
      if (value !== null && value !== undefined && String(value).trim() !== '') {
        return value;
      }
    }
  }
  return undefined;
}

export function formatStrategyCell(value: unknown): string {
  if (value === null || value === undefined) return EMPTY_TEXT;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return EMPTY_TEXT;
    return value.toLocaleString('en-IN', {
      maximumFractionDigits: Math.abs(value) >= 1000 ? 0 : 2,
    });
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  const text = String(value).trim();
  return text || EMPTY_TEXT;
}

export function extractStrategyRows(payload: unknown): StrategyWireRow[] {
  if (Array.isArray(payload)) {
    return payload.filter((row): row is StrategyWireRow => row !== null && typeof row === 'object');
  }
  if (!payload || typeof payload !== 'object') return [];
  const source = payload as Record<string, unknown>;
  const candidates = [
    source.rows,
    source.data,
    source.items,
    source.results,
    (source.payload as Record<string, unknown> | undefined)?.rows,
  ];
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      return candidate.filter((row): row is StrategyWireRow => row !== null && typeof row === 'object');
    }
  }
  return [];
}

export function extractStrategyTotal(payload: unknown, rowsLength: number): number {
  if (!payload || typeof payload !== 'object') return rowsLength;
  const source = payload as Record<string, unknown>;
  const value = pickStrategyField(source, ['total', 'totalRows', 'total_rows', 'count', 'rowCount', 'row_count']);
  const numberValue = Number(value);
  return Number.isFinite(numberValue) && numberValue >= rowsLength ? numberValue : rowsLength;
}

export function isStrategyPayloadRefreshing(payload: unknown): boolean {
  if (!payload || typeof payload !== 'object') return false;
  const source = payload as Record<string, unknown>;
  const meta = extractStrategyMeta(payload);
  return source.refreshing === true || meta.refreshing === true;
}

export function extractStrategyMeta(payload: unknown): Record<string, unknown> {
  if (!payload || typeof payload !== 'object') return {};
  const source = payload as Record<string, unknown>;
  const meta = source.meta;
  return meta && typeof meta === 'object' ? meta as Record<string, unknown> : {};
}

function isTruthyFlag(value: unknown): boolean {
  if (value === true) return true;
  if (typeof value === 'number') return value === 1;
  if (typeof value !== 'string') return false;
  return ['1', 'true', 'yes', 'y', 'stale'].includes(value.trim().toLowerCase());
}

export function isStrategyPayloadStale(payload: unknown): boolean {
  if (!payload || typeof payload !== 'object') return false;
  const source = payload as Record<string, unknown>;
  const meta = extractStrategyMeta(payload);
  const staleReasons = source.staleReasons ?? source.stale_reasons ?? meta.staleReasons ?? meta.stale_reasons;
  return isTruthyFlag(source.stale)
    || isTruthyFlag(source.is_stale)
    || isTruthyFlag(meta.stale)
    || isTruthyFlag(meta.is_stale)
    || String(meta.status ?? source.status ?? '').trim().toLowerCase() === 'stale'
    || (Array.isArray(staleReasons) && staleReasons.length > 0);
}

export function extractStrategyMetaNumber(payload: unknown, keys: readonly string[]): number | null {
  const meta = extractStrategyMeta(payload);
  for (const key of keys) {
    const value = meta[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim()) {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return null;
}

export function getStrategySortValue(row: StrategyWireRow, column: StrategyTableColumn): number | string {
  const value = pickStrategyField(row, getStrategyFieldKeys(column));
  if (typeof value === 'number') return value;
  const numeric = Number(value);
  if (Number.isFinite(numeric) && String(value).trim() !== '') return numeric;
  return formatStrategyCell(value).toUpperCase();
}

export function normalizeYamunaRows(payload: unknown): {
  gainers: StrategyWireRow[];
  losers: StrategyWireRow[];
  volumeMovers: StrategyWireRow[];
  tradingDate: string;
} {
  const source = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {};
  return {
    gainers: extractStrategyRows(source.gainers),
    losers: extractStrategyRows(source.losers || source.loosers),
    volumeMovers: extractStrategyRows(source.volumeMovers || source.volume_movers || source.volume),
    tradingDate: formatStrategyCell(source.tradingDate || source.trading_date || source.latestDate || source.latest_date),
  };
}
