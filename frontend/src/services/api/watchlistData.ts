import { fetchBars } from '../../api/bars';
import { fetchSymbols } from '../../api/symbols';
import { normalizeDisplaySymbol } from '../../utils/symbols';
import { fetchSectorWiseSymbol } from './sectorApi';
import { fetchDeliveryPayload, fetchPriceActionManualPayload, fetchSrLevelsPayload, fetchTechnicalIndicatorPayload, fetchTechnicalScreenerPayload } from './technicalApi';

export type WatchlistSetupState = 'BREAKOUT_CONFIRMED' | 'DEVELOPING' | 'NEAR_SUPPORT' | 'RETEST_ENTRY_ZONE' | 'RISK_WARNING';
export type WatchlistLevelSource = 'DYNAMIC' | 'MANUAL';
export type WatchlistSourceState = 'LOADED' | 'LOADING' | 'LOAD_FAILED' | 'NOT_AVAILABLE';
export type WatchlistSourceStatus = {
  bars: WatchlistSourceState;
  delivery: WatchlistSourceState;
  metadata: WatchlistSourceState;
  sectorWise: WatchlistSourceState;
  sr: WatchlistSourceState;
  targetHistory: WatchlistSourceState;
  technical: WatchlistSourceState;
  volume: WatchlistSourceState;
};

export type WatchlistDataRow = {
  confidence: number;
  delivery: number;
  entryHigh: number;
  entryLow: number;
  ffmc: string;
  index: string;
  ltp: number;
  mcap: string;
  pattern: string;
  resistance: [number, number, number];
  resistanceSources: [WatchlistLevelSource, WatchlistLevelSource, WatchlistLevelSource];
  sector: string;
  sectorTrend: string;
  setup: WatchlistSetupState;
  sourceStatus: WatchlistSourceStatus;
  strongResistance: number;
  strongResistanceSource: WatchlistLevelSource;
  strongSupport: number;
  strongSupportSource: WatchlistLevelSource;
  support: [number, number, number];
  supportSources: [WatchlistLevelSource, WatchlistLevelSource, WatchlistLevelSource];
  symbol: string;
  targetDays: [number, number, number];
  targetPrices: [number, number, number];
  targetSources: [WatchlistLevelSource, WatchlistLevelSource, WatchlistLevelSource];
  trend: string;
  volumeRatio: number;
};

type WatchlistSources = {
  bars?: Array<Record<string, unknown>>;
  delivery?: Record<string, unknown>;
  historyBars?: Array<Record<string, unknown>>;
  metadata?: Record<string, unknown>;
  sectorWise?: Record<string, unknown>;
  sr?: Record<string, unknown>;
  technical?: Record<string, unknown>;
  volume?: Record<string, unknown>;
  status?: Partial<WatchlistSourceStatus>;
};

type SourceUpdate = (row: WatchlistDataRow) => void;

type WatchlistFetchOptions = {
  returnAfterInitial?: boolean;
  signal?: AbortSignal;
};

type WatchlistLevel = {
  price: number;
  source: WatchlistLevelSource;
};

type Settled<T> =
  | { status: 'fulfilled'; value: T }
  | { reason: unknown; status: 'rejected' };

const VOLUME_CACHE_TTL_MS = 60_000;
const VOLUME_REFRESH_RETRY_DELAYS_MS = [1_000, 2_500, 5_000] as const;
const WATCHLIST_INITIAL_RENDER_BUDGET_MS = 750;
const WATCHLIST_OPTIONAL_SOURCE_TIMEOUT_MS = 15_000;
const WATCHLIST_TARGET_HISTORY_LIMIT = 800;
const WATCHLIST_TARGET_MAX_HORIZON_DAYS = 126;
const WATCHLIST_TARGET_MIN_SAMPLES = 3;
const DEFAULT_SOURCE_STATUS: WatchlistSourceStatus = {
  bars: 'NOT_AVAILABLE',
  delivery: 'NOT_AVAILABLE',
  metadata: 'NOT_AVAILABLE',
  sectorWise: 'NOT_AVAILABLE',
  sr: 'NOT_AVAILABLE',
  targetHistory: 'NOT_AVAILABLE',
  technical: 'NOT_AVAILABLE',
  volume: 'NOT_AVAILABLE',
};
let volumePayloadCache: { expiresAt: number; value: Awaited<ReturnType<typeof fetchTechnicalIndicatorPayload>> } | null = null;
let volumePayloadInflight: Promise<Awaited<ReturnType<typeof fetchTechnicalIndicatorPayload>>> | null = null;

function settle<T>(promise: Promise<T>): Promise<Settled<T>> {
  return promise.then(
    (value) => ({ status: 'fulfilled', value }),
    (reason) => ({ reason, status: 'rejected' }),
  );
}

function isEmptyRefreshingVolumePayload(
  value: Awaited<ReturnType<typeof fetchTechnicalIndicatorPayload>>,
): boolean {
  const rows = Array.isArray(value.rows) ? value.rows : [];
  return rows.length === 0 && Boolean(value.refreshing || value.stale);
}

function waitForVolumeRetry(delayMs: number): Promise<void> {
  return new Promise((resolve) => globalThis.setTimeout(resolve, delayMs));
}

async function loadWatchlistVolumePayload(): Promise<Awaited<ReturnType<typeof fetchTechnicalIndicatorPayload>>> {
  let value = await fetchTechnicalIndicatorPayload('volume', 'daily');
  for (const delayMs of VOLUME_REFRESH_RETRY_DELAYS_MS) {
    if (!isEmptyRefreshingVolumePayload(value)) break;
    await waitForVolumeRetry(delayMs);
    try {
      value = await fetchTechnicalIndicatorPayload('volume', 'daily');
    } catch {
      // Keep polling within the bounded retry budget. Volume is an optional
      // source, so the caller can still finish with the last placeholder.
    }
  }
  return value;
}

function fetchWatchlistVolumePayload(): Promise<Awaited<ReturnType<typeof fetchTechnicalIndicatorPayload>>> {
  if (volumePayloadCache && volumePayloadCache.expiresAt > Date.now()) {
    return Promise.resolve(volumePayloadCache.value);
  }
  if (volumePayloadInflight) return volumePayloadInflight;
  volumePayloadInflight = loadWatchlistVolumePayload()
    .then((value) => {
      if (!isEmptyRefreshingVolumePayload(value)) {
        volumePayloadCache = { expiresAt: Date.now() + VOLUME_CACHE_TTL_MS, value };
      }
      return value;
    })
    .finally(() => {
      volumePayloadInflight = null;
    });
  return volumePayloadInflight;
}

function first(source: Record<string, unknown> | undefined, keys: readonly string[]): unknown {
  if (!source) return undefined;
  for (const key of keys) {
    const value = source[key];
    if (value !== undefined && value !== null && String(value).trim() !== '') return value;
  }
  return undefined;
}

function numberValue(value: unknown): number {
  const parsed = Number(String(value ?? '').replace(/,/g, '').replace(/%/g, '').trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

function displayNumber(value: unknown): string {
  const parsed = numberValue(value);
  return parsed > 0 ? parsed.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '-';
}

function textValue(value: unknown, fallback = '-'): string {
  const text = String(value ?? '').trim();
  const normalized = text.toLowerCase();
  // Backend/source failures belong in sourceStatus, never in business-data
  // cells. Keep the row usable and let the neutral status badge explain the
  // unavailable optional source without exposing an error message per cell.
  return text
    && normalized !== 'undefined'
    && normalized !== 'null'
    && !normalized.includes('load failed')
    && !normalized.includes('request failed')
    && !normalized.includes('error')
    ? text
    : fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function levelPrice(value: unknown): number {
  if (isRecord(value)) {
    return numberValue(first(value, ['price', 'value', 'level', 'supportPrice', 'resistancePrice']));
  }
  return numberValue(value);
}

function structuredLevels(source: Record<string, unknown> | undefined, keys: readonly string[]): Array<Record<string, unknown>> {
  const value = first(source, keys);
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function manualSrSource(row: Record<string, unknown>, anchorPrice: number): Record<string, unknown> | undefined {
  const rawLevels = Array.isArray(row.levels) ? row.levels : [];
  const levels = rawLevels.map((level) => {
    const item = isRecord(level) ? level : { value: level };
    return { ...item, value: numberValue(first(item, ['value', 'sr_level', 'SR_LEVEL'])), manual: true, source: 'MANUAL' };
  }).filter((level) => numberValue(level.value) > 0);
  if (!levels.length) return undefined;
  const supports = anchorPrice > 0 ? levels.filter((level) => numberValue(level.value) <= anchorPrice) : levels;
  const resistances = anchorPrice > 0 ? levels.filter((level) => numberValue(level.value) >= anchorPrice) : levels;
  return {
    supportLevels: supports.length ? supports : levels,
    resistanceLevels: resistances.length ? resistances : levels,
  };
}

function levelSource(value: unknown): WatchlistLevelSource {
  if (!isRecord(value)) return 'DYNAMIC';
  const source = textValue(first(value, ['source', 'levelSource', 'level_source']), '').toLowerCase();
  return value.manual === true || source.includes('manual') ? 'MANUAL' : 'DYNAMIC';
}

function uniqueLevels(values: readonly WatchlistLevel[]): WatchlistLevel[] {
  const result: WatchlistLevel[] = [];
  values.forEach((value) => {
    if (value.price <= 0 || result.some((existing) => Math.abs(existing.price - value.price) < 0.005)) return;
    result.push(value);
  });
  return result;
}

function asLevelTuple(values: readonly WatchlistLevel[]): {
  prices: [number, number, number];
  sources: [WatchlistLevelSource, WatchlistLevelSource, WatchlistLevelSource];
} {
  return {
    prices: [values[0]?.price || 0, values[1]?.price || 0, values[2]?.price || 0],
    sources: [values[0]?.source || 'DYNAMIC', values[1]?.source || 'DYNAMIC', values[2]?.source || 'DYNAMIC'],
  };
}

function percentageLevel(anchorPrice: number, percent: number): number {
  return anchorPrice > 0 ? Number((anchorPrice * (1 + (percent / 100))).toFixed(2)) : 0;
}

function buildSrLadder(
  source: Record<string, unknown> | undefined,
  structuredKeys: readonly string[],
  displayKeys: readonly string[],
  fallbackValue: unknown,
  direction: 'resistance' | 'support',
): { prices: [number, number, number]; sources: [WatchlistLevelSource, WatchlistLevelSource, WatchlistLevelSource] } {
  const structured = structuredLevels(source, structuredKeys)
    .map((value) => ({ price: levelPrice(value), source: levelSource(value) }))
    .filter((value) => value.price > 0);
  const manual = structured.filter((value) => value.source === 'MANUAL');
  const dynamic = structured.filter((value) => value.source === 'DYNAMIC');
  const display = parseLevels(first(source, displayKeys)).map((price) => ({ price, source: 'DYNAMIC' as const }));
  const fallbackPrice = levelPrice(fallbackValue);
  const selected = uniqueLevels([
    ...manual,
    ...dynamic,
    ...display,
    ...(fallbackPrice > 0 ? [{ price: fallbackPrice, source: levelSource(fallbackValue) }] : []),
  ]).slice(0, 3).sort((left, right) => direction === 'support' ? right.price - left.price : left.price - right.price);
  return asLevelTuple(selected);
}

function buildTargetLadder(
  source: Record<string, unknown> | undefined,
  anchorPrice: number,
): { prices: [number, number, number]; sources: [WatchlistLevelSource, WatchlistLevelSource, WatchlistLevelSource] } {
  const structured = structuredLevels(source, ['resistanceLevels', 'resistances']);
  const manual = structured
    .filter((value) => levelSource(value) === 'MANUAL')
    .map((value) => ({ price: levelPrice(value), source: 'MANUAL' as const }))
    .filter((value) => value.price > 0)
    .slice(0, 3);
  const generated = structured
    .filter((value) => levelSource(value) === 'DYNAMIC')
    .map((value) => ({ price: levelPrice(value), source: 'DYNAMIC' as const }))
    .filter((value) => value.price > anchorPrice)
    .sort((left, right) => left.price - right.price);
  const targets: WatchlistLevel[] = [...manual];
  const minimumPercents = [5, 10, 15, 20];
  for (const percent of minimumPercents) {
    if (targets.length >= 3) break;
    const minimumPrice = percentageLevel(anchorPrice, percent);
    const generatedMatch = generated.find((candidate) => (
      candidate.price >= minimumPrice
      && !targets.some((value) => Math.abs(value.price - candidate.price) < 0.005)
    ));
    const fallback = generatedMatch || { price: minimumPrice, source: 'DYNAMIC' as const };
    if (fallback.price > 0 && !targets.some((value) => Math.abs(value.price - fallback.price) < 0.005)) {
      targets.push(fallback);
    }
  }
  const selected = uniqueLevels(targets)
    .sort((left, right) => left.price - right.price)
    .slice(0, 3);
  return asLevelTuple(selected);
}

function parseLevels(value: unknown): number[] {
  if (typeof value === 'number') return value > 0 ? [value] : [];
  const text = String(value ?? '');
  const labelled = Array.from(text.matchAll(/\b(?:S|R)\d+\s*:?\s*([\d,.]+)/gi))
    .map((match) => numberValue(match[1]))
    .filter((item) => item > 0);
  if (labelled.length) return labelled;
  const single = numberValue(value);
  return single > 0 ? [single] : [];
}

function strongestLevel(
  source: Record<string, unknown> | undefined,
  explicitKeys: readonly string[],
  listKeys: readonly string[],
  anchorPrice: number,
  fallback: WatchlistLevel,
): WatchlistLevel {
  const explicitValue = first(source, explicitKeys);
  const explicit = levelPrice(explicitValue);
  if (explicit > 0) {
    const matchingLevel = structuredLevels(source, listKeys)
      .find((value) => Math.abs(levelPrice(value) - explicit) < 0.005);
    const explicitHasSource = isRecord(explicitValue)
      && (explicitValue.manual !== undefined || first(explicitValue, ['source', 'levelSource', 'level_source']) !== undefined);
    return { price: explicit, source: levelSource(explicitHasSource ? explicitValue : matchingLevel) };
  }

  const levels = structuredLevels(source, listKeys);
  if (!levels.length) return fallback;
  const strongest = [...levels].sort((left, right) => {
    const touchesDiff = numberValue(first(right, ['touchesTotal', 'touchesSupport', 'touchesResistance']))
      - numberValue(first(left, ['touchesTotal', 'touchesSupport', 'touchesResistance']));
    if (touchesDiff) return touchesDiff;
    const leftSource = textValue(first(left, ['source']), '').toLowerCase();
    const rightSource = textValue(first(right, ['source']), '').toLowerCase();
    const confluenceDiff = Number(Boolean(first(right, ['confluence', 'dynamic'])) || rightSource.includes('manual+generated'))
      - Number(Boolean(first(left, ['confluence', 'dynamic'])) || leftSource.includes('manual+generated'));
    if (confluenceDiff) return confluenceDiff;
    const breachDiff = numberValue(first(left, ['breaches'])) - numberValue(first(right, ['breaches']));
    if (breachDiff) return breachDiff;
    return Math.abs(levelPrice(left) - anchorPrice) - Math.abs(levelPrice(right) - anchorPrice);
  })[0];
  const price = levelPrice(strongest);
  return price > 0 ? { price, source: levelSource(strongest) } : fallback;
}

function sectorTrendValue(source: Record<string, unknown> | undefined): string {
  const direct = first(source, ['sectorTrend', 'sector_trend', 'sectorPhase', 'sector_phase', 'parentSectorPhase']);
  if (direct !== undefined) return textValue(direct);
  const parent = first(source, ['parent']);
  if (!isRecord(parent)) return '-';
  return textValue(first(parent, ['phase', 'band', 'rotationPhase', 'rotationBand']));
}

export function estimateTargetTradingDays(
  bars: readonly Record<string, unknown>[],
  anchorPrice: number,
  targetPrices: readonly number[],
): [number, number, number] {
  const orderedBars = bars
    .map((bar, index) => ({
      close: numberValue(first(bar, ['c', 'close', 'CLOSE'])),
      high: numberValue(first(bar, ['h', 'high', 'HIGH'])),
      order: numberValue(first(bar, ['t', 'time', 'timestamp', 'TRADING_DATE'])) || index,
    }))
    .filter((bar) => bar.close > 0 && bar.high > 0)
    .sort((left, right) => left.order - right.order);

  if (anchorPrice <= 0 || orderedBars.length <= WATCHLIST_TARGET_MIN_SAMPLES) return [0, 0, 0];

  const estimates = targetPrices.slice(0, 3).map((targetPrice) => {
    const targetRatio = targetPrice > anchorPrice ? targetPrice / anchorPrice : 0;
    if (targetRatio <= 1) return 0;

    const observedDurations: number[] = [];
    orderedBars.forEach((startBar, startIndex) => {
      const lastIndex = Math.min(
        orderedBars.length - 1,
        startIndex + WATCHLIST_TARGET_MAX_HORIZON_DAYS,
      );
      const historicalTarget = startBar.close * targetRatio;
      for (let targetIndex = startIndex + 1; targetIndex <= lastIndex; targetIndex += 1) {
        if (orderedBars[targetIndex].high >= historicalTarget) {
          observedDurations.push(targetIndex - startIndex);
          break;
        }
      }
    });

    if (observedDurations.length < WATCHLIST_TARGET_MIN_SAMPLES) return 0;
    observedDurations.sort((left, right) => left - right);
    const midpoint = Math.floor(observedDurations.length / 2);
    const median = observedDurations.length % 2
      ? observedDurations[midpoint]
      : (observedDurations[midpoint - 1] + observedDurations[midpoint]) / 2;
    return Math.max(1, Math.round(median));
  });

  return [estimates[0] || 0, estimates[1] || 0, estimates[2] || 0];
}

function setupState(technical: Record<string, unknown> | undefined, ltp: number, support: number): WatchlistSetupState {
  const breakout = textValue(first(technical, ['breakoutStatus', 'BREAKOUT_STATUS']), '').toLowerCase();
  const risk = textValue(first(technical, ['riskLevel', 'RISK_LEVEL', 'techStatus', 'TECH_STATUS']), '').toLowerCase();
  if (breakout.includes('retest success')) return 'RETEST_ENTRY_ZONE';
  if (breakout.includes('confirmed') || breakout.includes('breakout')) return 'BREAKOUT_CONFIRMED';
  if (breakout.includes('failed') || risk.includes('avoid') || risk.includes('high')) return 'RISK_WARNING';
  if (ltp > 0 && support > 0 && ((ltp - support) / ltp) * 100 <= 3) return 'NEAR_SUPPORT';
  return 'DEVELOPING';
}

export function buildWatchlistDataRow(symbolInput: string, sources: WatchlistSources): WatchlistDataRow {
  const symbol = normalizeDisplaySymbol(symbolInput);
  const technical = sources.technical;
  const sectorWise = sources.sectorWise;
  const sr = sources.sr;
  const delivery = sources.delivery;
  const metadata = sources.metadata;
  const volume = sources.volume;
  const latestBar = sources.bars?.[sources.bars.length - 1];
  const ltp = numberValue(first(sectorWise, ['price', 'PRICE', 'priceSort', 'close', 'CLOSE']))
    || numberValue(first(sr, ['price', 'PRICE', 'close', 'CLOSE']))
    || numberValue(first(volume, ['price', 'PRICE', 'priceSort']))
    || numberValue(first(technical, ['price', 'PRICE', 'priceSort', 'ltp', 'LTP']))
    || numberValue(first(latestBar, ['c', 'close', 'CLOSE']));
  const nearestSupport = levelPrice(first(sr, ['primarySupport', 'dominantSupport']))
    || numberValue(first(sr, ['support', 'supportValue', 'supportPrice']))
    || numberValue(first(technical, ['nearestSupport', 'NEAREST_SUPPORT', 'support', 'SUPPORT']));
  const nearestResistance = levelPrice(first(sr, ['primaryResistance', 'dominantResistance']))
    || numberValue(first(sr, ['resistance', 'resistanceValue', 'resistancePrice']))
    || numberValue(first(technical, ['nearestResistance', 'NEAREST_RESISTANCE', 'resistance', 'RESISTANCE']));
  const supportLadder = buildSrLadder(
    sr,
    ['supportLevels', 'supports'],
    ['supportDisplay', 'supportSummary', 'support_summary', 'support'],
    first(sr, ['primarySupport', 'dominantSupport']) ?? nearestSupport,
    'support',
  );
  const resistanceLadder = buildSrLadder(
    sr,
    ['resistanceLevels', 'resistances'],
    ['resistanceDisplay', 'resistanceSummary', 'resistance_summary', 'resistance'],
    first(sr, ['primaryResistance', 'dominantResistance']) ?? nearestResistance,
    'resistance',
  );
  const support = supportLadder.prices;
  const resistance = resistanceLadder.prices;
  const targets = buildTargetLadder(sr, ltp);
  const strongestResistance = strongestLevel(
    sr,
    ['strongestResistance', 'strongResistance'],
    ['resistanceLevels', 'resistances'],
    ltp,
    { price: nearestResistance || resistance[0], source: 'DYNAMIC' },
  );
  const strongestSupport = strongestLevel(
    sr,
    ['strongestSupport', 'strongSupport'],
    ['supportLevels', 'supports'],
    ltp,
    { price: nearestSupport || support[0], source: 'DYNAMIC' },
  );
  const trend = textValue(
    first(sectorWise, ['trend', 'trendState', 'trendDirection', 'TREND'])
      ?? first(technical, ['trendStructure', 'TREND_STRUCTURE', 'trendDirection', 'TREND_DIRECTION']),
  );
  const breakout = textValue(first(technical, ['breakoutStatus', 'BREAKOUT_STATUS']), '');
  const pattern = textValue(first(technical, ['patternName', 'PATTERN_NAME']), breakout || trend);

  return {
    confidence: numberValue(first(technical, ['techScore', 'TECH_SCORE', 'techScoreSort', 'score', 'SCORE']))
      || numberValue(first(sectorWise, ['stockEdgeScore', 'score', 'SCORE'])),
    delivery: numberValue(first(delivery, ['delivery_pct', 'DELIVERY_PCT', 'deliveryPct'])),
    entryHigh: numberValue(first(latestBar, ['h', 'high', 'HIGH'])) || ltp,
    entryLow: numberValue(first(latestBar, ['l', 'low', 'LOW'])) || ltp,
    ffmc: displayNumber(first(technical, ['FFMC', 'ffmc', 'ffmc_cr', 'FFMC_CR'])),
    index: textValue(
      first(sectorWise, ['INDEX', 'index', 'marketCapIndex', 'market_cap_index'])
        ?? first(technical, ['INDEX', 'index', 'marketCapIndex', 'market_cap_index']),
    ),
    ltp,
    mcap: displayNumber(
      first(sectorWise, ['MCAP', 'mcap', 'totalMcap', 'TOTAL_MCAP', 'TOTAL_MCAP_CR'])
        ?? first(technical, ['MCAP', 'mcap', 'marketCapCrores', 'market_cap_crores', 'TOTAL_MCAP_CR']),
    ),
    pattern: pattern === '-' ? 'Existing data loaded; no active technical pattern' : pattern,
    resistance,
    resistanceSources: resistanceLadder.sources,
    sector: textValue(
      first(sectorWise, ['sectorName', 'sector', 'SECTOR', 'sectorCode'])
        ?? first(metadata, ['sector', 'SECTOR'])
        ?? first(technical, ['sector', 'SECTOR']),
    ),
    sectorTrend: sectorTrendValue(sectorWise) !== '-'
      ? sectorTrendValue(sectorWise)
      : textValue(first(technical, ['sectorTrend', 'sector_trend', 'SECTOR_TREND'])),
    setup: setupState(technical, ltp, support[0]),
    sourceStatus: { ...DEFAULT_SOURCE_STATUS, ...sources.status },
    strongResistance: strongestResistance.price,
    strongResistanceSource: strongestResistance.source,
    strongSupport: strongestSupport.price,
    strongSupportSource: strongestSupport.source,
    support,
    supportSources: supportLadder.sources,
    symbol,
    targetDays: estimateTargetTradingDays(sources.historyBars || [], ltp, targets.prices),
    targetPrices: targets.prices,
    targetSources: targets.sources,
    trend,
    volumeRatio: numberValue(first(volume, ['volumeRatio', 'VOLUME_RATIO', 'volume_ratio']))
      || numberValue(first(technical, ['volumeRatio', 'VOLUME_RATIO', 'volume_ratio'])),
  };
}

function exactSymbolRow(rows: unknown, symbol: string): Record<string, unknown> | undefined {
  if (!Array.isArray(rows)) return undefined;
  return rows.find((row) => {
    if (!row || typeof row !== 'object') return false;
    const source = row as Record<string, unknown>;
    return normalizeDisplaySymbol(first(source, ['symbol', 'SYMBOL', 'stock', 'STOCK', 'ticker', 'TICKER', 'code', 'CODE'])) === symbol;
  }) as Record<string, unknown> | undefined;
}

export async function validateNseWatchlistSymbol(symbolInput: string): Promise<Record<string, unknown> | undefined> {
  const symbol = normalizeDisplaySymbol(symbolInput);
  const symbolsResult = await settle(fetchSymbols(symbol));
  if (symbolsResult.status === 'fulfilled') {
    const metadata = exactSymbolRow(symbolsResult.value.symbols, symbol);
    if (metadata && String(metadata.exchange || 'NSE').trim().toUpperCase() === 'NSE') return metadata;
  }

  const barsResult = await settle(fetchBars({ symbol, tf: '1D', limit: 1 }));
  if (barsResult.status === 'fulfilled' && barsResult.value.bars.length) {
    return { exchange: 'NSE', symbol };
  }
  return undefined;
}

export async function fetchWatchlistDataRow(
  symbolInput: string,
  onSourceUpdate?: SourceUpdate,
  options: WatchlistFetchOptions = {},
): Promise<WatchlistDataRow> {
  const symbol = normalizeDisplaySymbol(symbolInput);
  // The Watchlist table uses only the latest candle for its entry range.
  const barsPromise = settle(fetchBars(
    { symbol, tf: '1D', limit: 1 },
    { signal: options.signal, timeoutMs: 15_000 },
  ));
  const symbolsPromise = settle(fetchSymbols(symbol));
  const volumePromise = settle(fetchWatchlistVolumePayload());

  const sources: WatchlistSources = {
    status: {
      bars: 'LOADING',
      delivery: 'LOADING',
      metadata: 'LOADING',
      sectorWise: 'LOADING',
      sr: 'LOADING',
      targetHistory: 'LOADING',
      technical: 'LOADING',
      volume: 'LOADING',
    },
  };

  const setSourceState = (key: keyof WatchlistSourceStatus, state: WatchlistSourceState) => {
    if (sources.status) sources.status[key] = state;
  };

  const emitUpdate = () => {
    const row = buildWatchlistDataRow(symbol, sources);
    onSourceUpdate?.(row);
    return row;
  };

  // Do not hold the first visible Watchlist row behind the slowest metadata or
  // analytics source. Each existing source updates the same row as it arrives.
  const initialTasks = [
    barsPromise.then((result) => {
      if (result.status !== 'fulfilled') {
        setSourceState('bars', 'LOAD_FAILED');
        emitUpdate();
        return;
      }
      if (!result.value.bars.length) {
        setSourceState('bars', 'NOT_AVAILABLE');
        emitUpdate();
        return;
      }
      sources.bars = result.value.bars as unknown as Array<Record<string, unknown>>;
      setSourceState('bars', 'LOADED');
      emitUpdate();
    }),
    symbolsPromise.then((result) => {
      if (result.status !== 'fulfilled') {
        setSourceState('metadata', 'LOAD_FAILED');
        emitUpdate();
        return;
      }
      sources.metadata = exactSymbolRow(result.value.symbols, symbol);
      setSourceState('metadata', sources.metadata ? 'LOADED' : 'NOT_AVAILABLE');
      emitUpdate();
    }),
  ];
  const volumeCompletion = volumePromise.then((result) => {
      if (result.status !== 'fulfilled') {
        setSourceState('volume', 'LOAD_FAILED');
        emitUpdate();
        return;
      }
      sources.volume = exactSymbolRow(result.value.rows, symbol);
      setSourceState('volume', sources.volume ? 'LOADED' : 'NOT_AVAILABLE');
      emitUpdate();
    });

  const runOptionalSourcesSequentially = async () => {
    const optionalLoaders: Array<() => Promise<void>> = [
      async () => {
        const result = await settle(fetchSectorWiseSymbol(symbol, {
          signal: options.signal,
          timeoutMs: WATCHLIST_OPTIONAL_SOURCE_TIMEOUT_MS,
        }));
        if (options.signal?.aborted) return;
        if (result.status !== 'fulfilled') {
          setSourceState('sectorWise', 'LOAD_FAILED');
          emitUpdate();
          return;
        }
        if (!result.value.row) {
          setSourceState('sectorWise', 'NOT_AVAILABLE');
          emitUpdate();
          return;
        }
        sources.sectorWise = result.value.row;
        setSourceState('sectorWise', 'LOADED');
        emitUpdate();
      },
      async () => {
        const result = await settle(fetchTechnicalScreenerPayload('/api/technicals/strong', {
          tf: 'daily', page: 1, page_size: 5, latest_only: 1, sort_by: 'techScoreSort', sort_dir: 'desc', symbol,
        }, { signal: options.signal, timeoutMs: WATCHLIST_OPTIONAL_SOURCE_TIMEOUT_MS }));
        if (options.signal?.aborted) return;
        if (result.status !== 'fulfilled') {
          setSourceState('technical', 'LOAD_FAILED');
          emitUpdate();
          return;
        }
        sources.technical = exactSymbolRow(result.value.rows, symbol);
        setSourceState('technical', sources.technical ? 'LOADED' : 'NOT_AVAILABLE');
        emitUpdate();
      },
      async () => {
        const manualResult = typeof fetchPriceActionManualPayload === 'function'
          ? await settle(fetchPriceActionManualPayload({ signal: options.signal, search: symbol }))
          : { status: 'rejected' as const, reason: new Error('Manual S&R source unavailable') };
        if (options.signal?.aborted) return;
        if (manualResult.status === 'fulfilled') {
          const manualRow = manualResult.value.rows?.find((row) => normalizeDisplaySymbol(row.symbol || row.stock) === symbol);
          const manualSource = manualRow ? manualSrSource(manualRow as unknown as Record<string, unknown>, numberValue(first(sources.bars?.[sources.bars.length - 1], ['c', 'close', 'CLOSE']))) : undefined;
          if (manualSource) {
            sources.sr = manualSource;
            setSourceState('sr', 'LOADED');
            emitUpdate();
            return;
          }
        }
        const result = await settle(fetchSrLevelsPayload(
          { timeframe: 'daily', lookback_days: 'max', page: 1, page_size: 5, search: symbol, symbols: symbol },
          { signal: options.signal, timeoutMs: WATCHLIST_OPTIONAL_SOURCE_TIMEOUT_MS },
        ));
        if (result.status !== 'fulfilled') {
          setSourceState('sr', 'LOAD_FAILED');
          emitUpdate();
          return;
        }
        sources.sr = exactSymbolRow(result.value.rows, symbol);
        setSourceState('sr', sources.sr ? 'LOADED' : 'NOT_AVAILABLE');
        emitUpdate();
      },
      async () => {
        const result = await settle(fetchDeliveryPayload(
          { page: 1, page_size: 5, sort_by: 'TRADING_DATE', sort_dir: 'desc', latest_only: 'true', symbol },
          { signal: options.signal, timeoutMs: WATCHLIST_OPTIONAL_SOURCE_TIMEOUT_MS },
        ));
        if (options.signal?.aborted) return;
        if (result.status !== 'fulfilled') {
          setSourceState('delivery', 'LOAD_FAILED');
          emitUpdate();
          return;
        }
        sources.delivery = exactSymbolRow(result.value.data ?? result.value.rows, symbol);
        setSourceState('delivery', sources.delivery ? 'LOADED' : 'NOT_AVAILABLE');
        emitUpdate();
      },
      async () => {
        const result = await settle(fetchBars(
          { symbol, tf: '1D', limit: WATCHLIST_TARGET_HISTORY_LIMIT },
          { signal: options.signal, timeoutMs: WATCHLIST_OPTIONAL_SOURCE_TIMEOUT_MS },
        ));
        if (options.signal?.aborted) return;
        if (result.status !== 'fulfilled') {
          setSourceState('targetHistory', 'LOAD_FAILED');
          emitUpdate();
          return;
        }
        if (result.value.bars.length <= WATCHLIST_TARGET_MIN_SAMPLES) {
          setSourceState('targetHistory', 'NOT_AVAILABLE');
          emitUpdate();
          return;
        }
        sources.historyBars = result.value.bars as unknown as Array<Record<string, unknown>>;
        setSourceState('targetHistory', 'LOADED');
        emitUpdate();
      },
    ];

    for (const loadSource of optionalLoaders) {
      if (options.signal?.aborted) return;
      await loadSource();
    }
  };

  await Promise.race([
    Promise.all(initialTasks),
    waitForVolumeRetry(WATCHLIST_INITIAL_RENDER_BUDGET_MS),
  ]);
  const optionalCompletion = Promise.all([
    volumeCompletion,
    runOptionalSourcesSequentially(),
  ]);
  if (options.returnAfterInitial) {
    void optionalCompletion;
    return buildWatchlistDataRow(symbol, sources);
  }
  await optionalCompletion;

  if (!sources.bars?.length && !sources.sectorWise && !sources.technical && !sources.sr && !sources.volume && !sources.delivery) {
    throw new Error('No existing NSE market or technical data was returned.');
  }
  return buildWatchlistDataRow(symbol, sources);
}
