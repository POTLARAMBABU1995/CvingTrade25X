import { legacyApiGet, type RequestOptions } from '../../api/client';
import type {
  SectorHierarchyApiResponse,
  SectorHierarchyIndustry,
  SectorHierarchyParent,
  SectorHierarchyStocksPayload,
  SectorHierarchySubSector,
  SectorHierarchySummary,
  SectorHierarchyTree,
} from '../../types/sectorHierarchy';

type CacheEnvelope<T> = {
  cachedAt: number;
  value: SectorHierarchyApiResponse<T>;
};

type LoadOptions = {
  refresh?: boolean;
  signal?: AbortSignal;
};

const CACHE_TTL_MS = 15 * 60 * 1000;
const CACHE_PREFIX = 'sectorHierarchy.';
const CACHE_VERSION = 'v2';

const memoryCache = new Map<string, CacheEnvelope<unknown>>();

function nowMs() {
  return Date.now();
}

function cacheKey(parts: string[]) {
  return `${CACHE_PREFIX}${parts.join('.')}.${CACHE_VERSION}`;
}

function readCache<T>(key: string): CacheEnvelope<T> | null {
  const now = nowMs();
  const memoryHit = memoryCache.get(key) as CacheEnvelope<T> | undefined;
  if (memoryHit && now - memoryHit.cachedAt <= CACHE_TTL_MS) {
    return memoryHit;
  }
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CacheEnvelope<T>;
    if (!parsed || typeof parsed.cachedAt !== 'number') return null;
    if (now - parsed.cachedAt > CACHE_TTL_MS) return null;
    memoryCache.set(key, parsed as CacheEnvelope<unknown>);
    return parsed;
  } catch {
    return null;
  }
}

function writeCache<T>(key: string, value: SectorHierarchyApiResponse<T>) {
  const envelope: CacheEnvelope<T> = {
    cachedAt: nowMs(),
    value,
  };
  memoryCache.set(key, envelope as CacheEnvelope<unknown>);
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(key, JSON.stringify(envelope));
  } catch {
    // Session storage is best-effort.
  }
}

function clearKey(key: string) {
  memoryCache.delete(key);
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    // Ignore storage errors.
  }
}

async function fetchCached<T>(
  key: string,
  loader: () => Promise<SectorHierarchyApiResponse<T>>,
  options: LoadOptions,
): Promise<SectorHierarchyApiResponse<T>> {
  if (options.refresh) {
    clearKey(key);
  } else {
    const cached = readCache<T>(key);
    if (cached) return cached.value;
  }

  const response = await loader();
  if (response?.success) {
    writeCache(key, response);
  }
  return response;
}

function requestOptions(options: LoadOptions, action: string): RequestOptions {
  return {
    signal: options.signal,
    diagnostic: {
      action,
      component: 'sectorHierarchyApi',
      page: 'CvingTrade25X - Sector Hierarchy',
    },
    timeoutMs: 45000,
  };
}

export function clearSectorHierarchyCache() {
  memoryCache.clear();
  if (typeof window === 'undefined') return;
  try {
    const keysToRemove: string[] = [];
    for (let index = 0; index < window.sessionStorage.length; index += 1) {
      const key = window.sessionStorage.key(index);
      if (key && key.startsWith(CACHE_PREFIX)) {
        keysToRemove.push(key);
      }
    }
    keysToRemove.forEach((key) => window.sessionStorage.removeItem(key));
  } catch {
    // Ignore storage errors.
  }
}

export function getParents(options: LoadOptions = {}) {
  const key = cacheKey(['parents']);
  return fetchCached<SectorHierarchyParent[]>(
    key,
    () => legacyApiGet<SectorHierarchyApiResponse<SectorHierarchyParent[]>>(
      '/api/sector-hierarchy/parents',
      options.refresh ? { refresh: true } : undefined,
      requestOptions(options, 'GET /api/sector-hierarchy/parents'),
    ),
    options,
  );
}

export function getIndustries(parentSector: string, options: LoadOptions = {}) {
  const parent = String(parentSector || '').trim();
  const key = cacheKey(['industries', encodeURIComponent(parent)]);
  return fetchCached<SectorHierarchyIndustry[]>(
    key,
    () => legacyApiGet<SectorHierarchyApiResponse<SectorHierarchyIndustry[]>>(
      '/api/sector-hierarchy/industries',
      {
        parentSector: parent,
        ...(options.refresh ? { refresh: true } : {}),
      },
      requestOptions(options, 'GET /api/sector-hierarchy/industries'),
    ),
    options,
  );
}

export function getSubSectors(parentSector: string, industrySector: string, options: LoadOptions = {}) {
  const parent = String(parentSector || '').trim();
  const industry = String(industrySector || '').trim();
  const key = cacheKey(['subSectors', encodeURIComponent(parent), encodeURIComponent(industry)]);
  return fetchCached<SectorHierarchySubSector[]>(
    key,
    () => legacyApiGet<SectorHierarchyApiResponse<SectorHierarchySubSector[]>>(
      '/api/sector-hierarchy/sub-sectors',
      {
        parentSector: parent,
        industrySector: industry,
        ...(options.refresh ? { refresh: true } : {}),
      },
      requestOptions(options, 'GET /api/sector-hierarchy/sub-sectors'),
    ),
    options,
  );
}

export function getStocks(
  params: {
    parentSector?: string;
    industrySector?: string;
    subSector?: string;
  },
  options: LoadOptions = {},
) {
  const parent = String(params.parentSector || '').trim();
  const industry = String(params.industrySector || '').trim();
  const sub = String(params.subSector || '').trim();
  const key = cacheKey(['stocks', encodeURIComponent(parent), encodeURIComponent(industry), encodeURIComponent(sub)]);
  return fetchCached<SectorHierarchyStocksPayload>(
    key,
    () => legacyApiGet<SectorHierarchyApiResponse<SectorHierarchyStocksPayload>>(
      '/api/sector-hierarchy/stocks',
      {
        ...(parent ? { parentSector: parent } : {}),
        ...(industry ? { industrySector: industry } : {}),
        ...(sub ? { subSector: sub } : {}),
        ...(options.refresh ? { refresh: true } : {}),
      },
      requestOptions(options, 'GET /api/sector-hierarchy/stocks'),
    ),
    options,
  );
}

export function getSummary(parentSector: string, options: LoadOptions = {}) {
  const parent = String(parentSector || '').trim();
  const key = cacheKey(['summary', encodeURIComponent(parent)]);
  return fetchCached<SectorHierarchySummary>(
    key,
    () => legacyApiGet<SectorHierarchyApiResponse<SectorHierarchySummary>>(
      '/api/sector-hierarchy/summary',
      {
        parentSector: parent,
        ...(options.refresh ? { refresh: true } : {}),
      },
      requestOptions(options, 'GET /api/sector-hierarchy/summary'),
    ),
    options,
  );
}

export function getTree(parentSector: string, options: LoadOptions = {}) {
  const parent = String(parentSector || '').trim();
  const key = cacheKey(['tree', encodeURIComponent(parent)]);
  return fetchCached<SectorHierarchyTree>(
    key,
    () => legacyApiGet<SectorHierarchyApiResponse<SectorHierarchyTree>>(
      '/api/sector-hierarchy/tree',
      {
        parentSector: parent,
        ...(options.refresh ? { refresh: true } : {}),
      },
      requestOptions(options, 'GET /api/sector-hierarchy/tree'),
    ),
    options,
  );
}
