import { legacyApiGet, legacyApiPost, type QueryParams, type RequestOptions } from '../../api/client';

export type SectorApiPayload = Record<string, unknown>;
export type SectorWiseUnknownSymbolsPayload = {
  asOfDate?: string;
  source?: string;
  symbols: string[];
  total: number;
};
export type SectorWiseSymbolPayload = {
  asOfDate?: string;
  matches?: Array<Record<string, unknown>>;
  row?: Record<string, unknown>;
  sectorCodes?: string[];
  source?: string;
  symbol?: string;
  totalMatches?: number;
  version?: string;
};
export type SectorDiscoveryPayload = {
  sectors?: Array<Record<string, unknown>>;
  source?: string;
  status?: string;
  totalSectors?: number;
};

export type SectorHierarchy = {
  parentSector?: string | null;
  industry?: string | null;
  sectorCode?: string | null;
  sectorName?: string | null;
};

export type SectorOverviewRow = {
  ltc_date?: string;
  price?: number | null;
  stock?: string;
  trend?: string;
};

export type SectorOverviewPayload = {
  dynamic_trend_counts?: Record<string, number>;
  generated_at?: string;
  is_stale?: boolean;
  ltc_date?: string;
  ltc_date_consistent?: boolean;
  ltc_date_count?: number;
  rows?: SectorOverviewRow[];
  sector_data_source?: string;
  source_dev_ltc_date?: string;
  status?: string;
  success?: boolean;
  total_sectors?: number;
  total_stocks?: number;
  trend_counts?: Record<string, number>;
};

export function fetchSectorBreadth(params?: QueryParams, options: RequestOptions = {}) {
  return legacyApiGet<SectorApiPayload>('/api/sectors/breadth', params, {
    timeoutMs: 330000,
    ...options,
  });
}

export function fetchSectorRotationSectors(params?: QueryParams, options: RequestOptions = {}) {
  return legacyApiGet<SectorDiscoveryPayload>('/api/sector-rotation/sectors', params, {
    timeoutMs: 240000,
    ...options,
  });
}

export type SectorRefreshPayload = {
  ok?: boolean;
  refreshed?: string[];
  v3?: {
    asOfDate?: string | null;
    durationMs?: number;
    modelVersion?: string | null;
    rowCount?: number;
    runId?: string;
  };
};

export function refreshSectorData(version?: 'v2' | 'v3', options: RequestOptions = {}) {
  return legacyApiPost<SectorRefreshPayload>(
    `/api/sectors/refresh${version ? `?version=${encodeURIComponent(version)}` : ''}`,
    {},
    {
      timeoutMs: version === 'v3' ? 330000 : 120000,
      ...options,
    },
  );
}

export function fetchSectorOverview(params?: QueryParams, options: RequestOptions = {}) {
  return legacyApiGet<SectorOverviewPayload>('/api/sectors/overview', params, {
    timeoutMs: params?.refresh ? 300000 : 5000,
    ...options,
  });
}

export function fetchSectorWiseStocks(sectorCode: string, params: QueryParams, options: RequestOptions = {}) {
  return legacyApiGet<SectorApiPayload>(`/api/sector/${encodeURIComponent(sectorCode)}/stocks/sector-wise`, params, {
    timeoutMs: params.refresh ? 300000 : 240000,
    ...options,
  });
}

export function fetchSectorWiseSymbol(symbol: string, options: RequestOptions = {}) {
  return legacyApiGet<SectorWiseSymbolPayload>('/api/sectors/sector-wise-symbol', { symbol }, {
    timeoutMs: 60000,
    ...options,
  });
}

export function fetchSectorWiseUnknownSymbols(options: RequestOptions = {}) {
  return legacyApiGet<SectorWiseUnknownSymbolsPayload>('/api/sectors/sector-wise-unknown-symbols', undefined, {
    timeoutMs: 10000,
    ...options,
  });
}

export type DatabaseSyncStatus = {
  dev_ltc_date: string | null;
  mcap_ltc_date: string | null;
  ffmc_ltc_date: string | null;
  delivery_ltc_date: string | null;
  is_fully_synced: boolean;
  is_stale?: boolean;
  missing_mcap_count: number;
  missing_ffmc_count: number;
  missing_delivery_count: number;
  stale?: boolean;
  stale_tables: string[];
  missing_symbols: Record<string, string[]>;
  last_sync_time: string;
  message: string;
  status?: string;
};

export function fetchDatabaseSyncStatus(options: RequestOptions = {}) {
  return legacyApiGet<DatabaseSyncStatus>('/api/database/sync-status', undefined, options);
}

function isTruthyStatusFlag(value: unknown): boolean {
  if (value === true) return true;
  if (typeof value === 'number') return Number.isFinite(value) && value > 0;
  if (typeof value !== 'string') return false;
  return ['1', 'true', 'yes', 'y', 'stale'].includes(value.trim().toLowerCase());
}

export function isDatabaseSyncStatusStale(status?: DatabaseSyncStatus | null): boolean {
  if (!status) return false;
  if (status.is_fully_synced === false) return true;
  if (isTruthyStatusFlag(status.stale) || isTruthyStatusFlag(status.is_stale)) return true;
  if (String(status.status ?? '').trim().toLowerCase() === 'stale') return true;
  if (Array.isArray(status.stale_tables) && status.stale_tables.length > 0) return true;
  return [
    status.missing_mcap_count,
    status.missing_ffmc_count,
    status.missing_delivery_count,
  ].some((count) => Number(count || 0) > 0);
}
