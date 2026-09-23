import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { AppPagination } from '../../components/app/AppPagination';
import {
  adaptSectorWisePayload,
  formatSectorCount,
  formatSectorDate,
  formatSectorGap,
  formatSectorIndex,
  formatSectorMcap,
  formatSectorMcapRank,
  formatSectorPrice,
  sectorFlagClass,
  sectorGapClass,
  sectorHeatClass,
  sectorTrendClass,
  sectorTrendLabel,
  type SectorWiseRow,
} from '../../adapters/sectorPageAdapter';
import { copyText } from '../../lib/clipboard';
import {
  sectorPageItems,
  SECTOR_DIRECTORY_PAGE,
  type SectorPageItem,
} from '../../data/sectorNav';
import { technicalNavItems } from '../../data/technicalNav';
import {
  fetchSectorRotationSectors,
  fetchSectorWiseStocks,
  fetchDatabaseSyncStatus,
  type SectorDiscoveryPayload,
  type DatabaseSyncStatus,
} from '../../services/api/sectorApi';
import { SectorMigrationLayout } from './SectorMigrationLayout';
import { Select } from '../../components/ui/Select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/Tabs';
import { SectorHierarchyPanel } from '../../components/sector/SectorHierarchyPanel';
import { getInternalNavigationTarget, navigateToInternalRoute } from '../../utils/internalNavigation';
import { StrategyToolbar } from '../../components/strategy/StrategyToolbar';
import { resolveSectorLiveToolbarStatus } from './SectorRotationPage';
import { normalizeDisplaySymbol } from '../../utils/symbols';

type LoadStatus = 'error' | 'loading' | 'online';
type SortDir = 'asc' | 'desc';
type SectorWiseTab = 'hierarchy' | 'stocks';
type SectorSymbolMeta = {
  index: string;
  mcap: number | null;
  mcapRank: number | null;
};
type SectorWiseViewPayload = {
  asOfDate: string;
  generatedAt: string;
  isStale: boolean;
  loadedAt: string;
  modelVersion: string;
  page: number;
  parent: Record<string, unknown>;
  rows: SectorWiseRow[];
  runId: string;
  source: string;
  staleReason: string;
  technicalSourceDate: string;
  totalCount: number;
  totalPages: number;
  version: string;
};
type SectorWiseCacheEntry = {
  cachedAt: number;
  value: SectorWiseViewPayload;
};
type SectorSelectorStatus = 'error' | 'loading' | 'online';
type SectorTrendScoreLabel =
  | 'Strong Downtrend'
  | 'Downtrend'
  | 'Sideways'
  | 'Pullback in Uptrend'
  | 'Uptrend'
  | 'Strong Uptrend';
type SectorTrendScoreBand = {
  description: string;
  label: SectorTrendScoreLabel;
  max: number;
  min: number;
};
export type SectorTrendScoreResult = {
  band: SectorTrendScoreBand;
  description: string;
  label: SectorTrendScoreLabel;
  score: number;
};

const FIXED_PAGE_SIZE = 25;
const DATASET_PAGE_SIZE = 200;
const AUTO_POLL_INTERVAL_MS = 150000;
const SECTOR_WISE_CACHE_MAX_AGE_MS = 10 * 60 * 1000;
const SECTOR_WISE_REVALIDATE_AGE_MS = 45 * 1000;
const SECTOR_WISE_CACHE_VERSION = 'v3';

const SECTOR_WISE_CACHE_PREFIX = 'sector-wise-stocks:';
const IS_DEV = import.meta.env.DEV && import.meta.env.MODE !== 'test';
const sectorWiseMemoryCache = new Map<string, SectorWiseCacheEntry>();
const sectorWiseInflightRequests = new Map<string, { controller: AbortController; promise: Promise<SectorWiseCacheEntry> }>();

export type SectorWiseColumn = {
  dataCol: string;
  key: string;
  label: string;
};

const baseColumns: readonly SectorWiseColumn[] = [
  { key: 'S_NO', label: 'S.NO', dataCol: 'sno' },
  { key: 'STOCK', label: 'SYMBOL', dataCol: 'symbol' },
  { key: 'INDEX', label: 'INDEX', dataCol: 'index' },
  { key: 'MCAP', label: 'MCAP', dataCol: 'mcap' },
  { key: 'MCAP_RANK', label: 'MCAP_RANK', dataCol: 'mcap_rank' },
  { key: 'LTC_DATE', label: 'LTC_DATE', dataCol: 'ltc_date' },
  { key: 'PRICE', label: 'PRICE', dataCol: 'price' },
  { key: 'ATH', label: 'ATH', dataCol: 'ath' },
  { key: 'GAP', label: 'GAP', dataCol: 'gap' },
  { key: '52WH', label: '52WH', dataCol: '52wh' },
  { key: '52WL', label: '52WL', dataCol: '52wl' },
  { key: 'EMA20_FLAG', label: 'EMA20_FLAG', dataCol: 'ema20_flag' },
  { key: 'EMA50_FLAG', label: 'EMA50_FLAG', dataCol: 'ema50_flag' },
  { key: 'EMA100_FLAG', label: 'EMA100_FLAG', dataCol: 'ema100_flag' },
  { key: 'EMA200_FLAG', label: 'EMA200_FLAG', dataCol: 'ema200_flag' },
  { key: 'TREND', label: 'TREND', dataCol: 'trend' },
  { key: 'SCORE', label: 'SCORE', dataCol: 'score' },
] as const;

const analyticsColumns: readonly SectorWiseColumn[] = [
  { key: 'SECTOR_PHASE', label: 'SECTOR_PHASE', dataCol: 'sectorPhase' },
  { key: 'SECTOR_SCORE', label: 'SECTOR_SCORE', dataCol: 'sectorScore' },
  { key: 'RS_VS_SECTOR', label: 'RS_VS_SECTOR', dataCol: 'rsVsSector' },
  { key: 'RS_VS_BMARK', label: 'RS_VS_BMARK', dataCol: 'rsVsBenchmark' },
  { key: 'BREAKOUT', label: 'BREAKOUT', dataCol: 'breakoutStatus' },
  { key: 'VOL_DELIVERY', label: 'VOL_DELIVERY', dataCol: 'volumeDeliveryStatus' },
  { key: 'RISK', label: 'RISK', dataCol: 'riskStatus' },
  { key: 'CONFIDENCE', label: 'CONFIDENCE', dataCol: 'confidence' },
] as const;

const STOCK_TECHNICAL_PATHS = new Set([
  '/app/technical/ema',
  '/app/technical/rsi50',
  '/app/technical/macd',
  '/app/technical/adx',
  '/app/technical/atr14',
  '/app/technical/breakout',
  '/app/technical/volume',
  '/app/technical/delivery',
  '/app/technical/price-action-analysis',
  '/app/technical/strong-technicals',
]);
const stockTechnicalLinks = technicalNavItems.filter((item) => STOCK_TECHNICAL_PATHS.has(item.href));

function hasDisplayValue(value: unknown): boolean {
  const token = String(value ?? '').trim();
  return Boolean(token && token !== '-');
}

export function resolveSectorWiseVisibleColumns(rows: SectorWiseRow[]): readonly SectorWiseColumn[] {
  const populatedAnalyticsColumns = analyticsColumns.filter((column) => (
    rows.some((row) => hasDisplayValue(row[column.dataCol]))
  ));
  return [...baseColumns, ...populatedAnalyticsColumns];
}

export function isSectorWiseUnknownOrInsufficient(row: SectorWiseRow): boolean {
  const trend = sectorTrendLabel(row).trim().toUpperCase();
  return !trend || trend === '-' || trend === 'UNKNOWN' || trend.includes('UNKNOWN') || trend.includes('INSUFFICIENT');
}

function sectorWiseExportCell(row: SectorWiseRow, key: string): string {
  if (key === 'S_NO') return formatSectorCount(row.sNo);
  if (key === 'STOCK') return row.stock || '-';
  if (key === 'LTC_DATE') return formatSectorDate(row.ltcDate);
  if (key === 'PRICE') return formatSectorPrice(row.price);
  if (key === 'MCAP') return formatSectorMcap(row.totalMcap);
  if (key === 'MCAP_RANK') return formatSectorMcapRank(row.mcapRank);
  if (key === 'INDEX') return formatSectorIndex(row.index);
  if (key === 'ATH') return formatSectorPrice(row.ath);
  if (key === 'GAP') return formatSectorGap(row);
  if (key === '52WH') return formatSectorPrice(row.high52w);
  if (key === '52WL') return formatSectorPrice(row.low52w);
  if (key === 'EMA20_FLAG') return row.ema20Flag || '-';
  if (key === 'EMA50_FLAG') return row.ema50Flag || '-';
  if (key === 'EMA100_FLAG') return row.ema100Flag || '-';
  if (key === 'EMA200_FLAG') return row.ema200Flag || '-';
  if (key === 'TREND') return sectorTrendLabel(row) || '-';
  if (key === 'SCORE') {
    const result = calculateSectorTrendScore(row);
    return `${result.score}/100 ${result.label}`;
  }
  if (key === 'SECTOR_PHASE') return formatSectorAnalyticsValue(row.sectorPhase);
  if (key === 'SECTOR_SCORE') return formatSectorAnalyticsValue(row.sectorScore, true);
  if (key === 'RS_VS_SECTOR') return formatSectorAnalyticsValue(row.rsVsSector, true);
  if (key === 'RS_VS_BMARK') return formatSectorAnalyticsValue(row.rsVsBenchmark, true);
  if (key === 'BREAKOUT') return formatSectorAnalyticsValue(row.breakoutStatus);
  if (key === 'VOL_DELIVERY') return formatSectorAnalyticsValue(row.volumeDeliveryStatus);
  if (key === 'RISK') return formatSectorAnalyticsValue(row.riskStatus || row.riskLevel);
  if (key === 'CONFIDENCE') return formatSectorAnalyticsValue(row.confidence);
  return '-';
}

function escapeSectorWiseCsv(value: string): string {
  return `"${value.replace(/"/g, '""')}"`;
}

export function buildSectorWiseUnknownTxt(rows: SectorWiseRow[]): string {
  return rows.map((row) => row.stock.trim()).filter(Boolean).join(',');
}

export function buildSectorWiseUnknownCsv(rows: SectorWiseRow[], columns: readonly SectorWiseColumn[]): string {
  const header = columns.map((column) => escapeSectorWiseCsv(column.label)).join(',');
  const body = rows.map((row) => columns.map((column) => (
    escapeSectorWiseCsv(sectorWiseExportCell(row, column.key))
  )).join(','));
  return [header, ...body].join('\n');
}

function buildSectorWiseDownloadFilename(sectorName: string, extension: 'csv' | 'txt'): string {
  const sector = sectorName.trim().replace(/[^a-z0-9]+/gi, '') || 'Sector';
  const now = new Date();
  const timestamp = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
    String(now.getHours()).padStart(2, '0'),
    String(now.getMinutes()).padStart(2, '0'),
    String(now.getSeconds()).padStart(2, '0'),
  ].join('');
  return `${sector}${timestamp}.${extension}`;
}

function triggerSectorWiseDownload(contents: string, filename: string, contentType: string) {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const blob = new Blob([contents], { type: contentType });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

export function filterSectorWiseRows(rows: SectorWiseRow[], search: string): SectorWiseRow[] {
  const token = search.trim().toUpperCase();
  if (!token) return rows;
  return rows.filter((row) => String(row.stock || '').toUpperCase().includes(token));
}

type StickyColumnRole = 'sno' | 'symbol';

function stickyColumnRole(columnKey: string): StickyColumnRole | null {
  if (columnKey === 'S_NO') return 'sno';
  if (columnKey === 'STOCK') return 'symbol';
  return null;
}

function stickyHeaderClass(columnKey: string): string {
  const role = stickyColumnRole(columnKey);
  return ['sortable', role ? 'sticky-header-cell' : '', role ? `sticky-${role}` : ''].filter(Boolean).join(' ');
}

function stickyCellClass(columnKey: string, baseClass?: string): string | undefined {
  const role = stickyColumnRole(columnKey);
  const className = [baseClass, role ? 'sticky-cell' : '', role ? `sticky-${role}` : ''].filter(Boolean).join(' ');
  return className || undefined;
}

const SECTOR_TREND_SCORE_BANDS: readonly SectorTrendScoreBand[] = [
  {
    label: 'Strong Downtrend',
    min: 0,
    max: 20,
    description: 'Broad bearish structure with limited positive confirmation on the page.',
  },
  {
    label: 'Downtrend',
    min: 21,
    max: 40,
    description: 'Weak structure with some recovery signs, but the dominant bias remains negative.',
  },
  {
    label: 'Sideways',
    min: 41,
    max: 60,
    description: 'Balanced or mixed signals with no decisive directional advantage.',
  },
  {
    label: 'Pullback in Uptrend',
    min: 61,
    max: 70,
    description: 'The broader trend is constructive, but short-term momentum is cooling or correcting.',
  },
  {
    label: 'Uptrend',
    min: 71,
    max: 85,
    description: 'Bullish technical structure with broad positive confirmation from visible page fields.',
  },
  {
    label: 'Strong Uptrend',
    min: 86,
    max: 100,
    description: 'Highest-quality bullish alignment with strong confirmation from visible page fields.',
  },
] as const;
const SECTOR_TREND_SCORE_BAND_BY_LABEL = Object.fromEntries(
  SECTOR_TREND_SCORE_BANDS.map((band) => [band.label, band]),
) as Record<SectorTrendScoreLabel, SectorTrendScoreBand>;

function perfLog(stage: string, details: Record<string, number | string>) {
  if (!IS_DEV) return;
  try {
    // eslint-disable-next-line no-console
    console.debug(`[sector-wise-perf] ${stage}`, details);
  } catch {
    // Debug timing is best-effort only.
  }
}

function buildSectorWiseRequestKey(sectorCode: string) {
  return `v3:${sectorCode.toUpperCase()}:dataset:${SECTOR_WISE_CACHE_VERSION}`;
}

function buildSectorWiseSnapshotKey(cacheKey: string, view: SectorWiseViewPayload) {
  return [
    cacheKey,
    view.runId || 'no-run',
    view.asOfDate || 'no-date',
    view.technicalSourceDate || 'no-technical-date',
  ].join(':');
}

function readCachedSectorWiseEntry(cacheKey: string): SectorWiseCacheEntry | null {
  const now = Date.now();
  const pointerKey = `${cacheKey}:latest`;
  const memoryPointer = sectorWiseMemoryCache.get(pointerKey);
  const memoryIdentity = memoryPointer?.value.runId
    ? buildSectorWiseSnapshotKey(cacheKey, memoryPointer.value)
    : cacheKey;
  const memoryHit = sectorWiseMemoryCache.get(memoryIdentity) ?? memoryPointer;
  if (memoryHit && now - memoryHit.cachedAt <= SECTOR_WISE_CACHE_MAX_AGE_MS) {
    return memoryHit;
  }
  if (typeof window === 'undefined') return null;
  try {
    const identity = window.sessionStorage.getItem(`${SECTOR_WISE_CACHE_PREFIX}${pointerKey}`);
    const raw = window.sessionStorage.getItem(`${SECTOR_WISE_CACHE_PREFIX}${identity || cacheKey}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SectorWiseCacheEntry | null;
    if (!parsed || typeof parsed.cachedAt !== 'number') return null;
    if (now - parsed.cachedAt > SECTOR_WISE_CACHE_MAX_AGE_MS) return null;
    sectorWiseMemoryCache.set(identity || cacheKey, parsed);
    return parsed;
  } catch {
    return null;
  }
}

function writeCachedSectorWiseEntry(cacheKey: string, entry: SectorWiseCacheEntry) {
  const identity = buildSectorWiseSnapshotKey(cacheKey, entry.value);
  const pointerKey = `${cacheKey}:latest`;
  sectorWiseMemoryCache.set(identity, entry);
  sectorWiseMemoryCache.set(pointerKey, entry);
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(`${SECTOR_WISE_CACHE_PREFIX}${pointerKey}`, identity);
    window.sessionStorage.setItem(`${SECTOR_WISE_CACHE_PREFIX}${identity}`, JSON.stringify(entry));
  } catch {
    // Session storage cache is optional.
  }
}

function abortStaleSectorWiseInflight(activeKey: string) {
  for (const [key, inflight] of sectorWiseInflightRequests) {
    if (key === activeKey) continue;
    inflight.controller.abort('Superseded sector-wise request');
    sectorWiseInflightRequests.delete(key);
  }
}

function toSortableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(String(value).replace(/,/g, '').replace(/%/g, ''));
  return Number.isFinite(parsed) ? parsed : null;
}

function resolveLatestLtcDate(rows: SectorWiseRow[]): string {
  return rows.reduce((latest, row) => {
    const text = String(row.ltcDate ?? '').trim();
    const normalized = /^\d{4}-\d{2}-\d{2}/.test(text) ? text.slice(0, 10) : text;
    return normalized && normalized > latest ? normalized : latest;
  }, '');
}

function uniqueSectorRows(rows: SectorWiseRow[]): SectorWiseRow[] {
  const seen = new Set<string>();
  const result: SectorWiseRow[] = [];
  rows.forEach((row, index) => {
    const stock = String(row.stock || '').trim().toUpperCase();
    const key = stock || `row-${index}`;
    if (seen.has(key)) return;
    seen.add(key);
    result.push(row);
  });
  return result;
}

function trendSortRank(row: SectorWiseRow): number {
  const explicit = toSortableNumber(row.trendSort);
  if (explicit !== null) return explicit;
  const token = sectorTrendLabel(row).toUpperCase();
  if (token.includes('STRONG') && token.includes('UP')) return 0;
  if (token === 'UPTREND') return 1;
  if (token.includes('PULLBACK') && token.includes('UP')) return 2;
  if (token.includes('POSSIBLE') && token.includes('REVERSAL')) return 3;
  if (token.includes('SIDEWAYS')) return 4;
  if (token.includes('CONSOLIDATION') || token.includes('RANGE')) return 5;
  if (token.includes('DOWN')) return 6;
  return 7;
}

function clampNumber(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function normalizeFlag(value: unknown): 'Y' | 'N' | '' {
  const token = String(value ?? '').trim().toUpperCase();
  if (token === 'Y') return 'Y';
  if (token === 'N') return 'N';
  return '';
}

function countBullishEmaFlags(row: SectorWiseRow): number {
  return [
    normalizeFlag(row.ema20Flag),
    normalizeFlag(row.ema50Flag),
    normalizeFlag(row.ema100Flag),
    normalizeFlag(row.ema200Flag),
  ].filter((flag) => flag === 'Y').length;
}

function isPullbackStructure(row: SectorWiseRow): boolean {
  return (
    normalizeFlag(row.ema20Flag) === 'N'
    && normalizeFlag(row.ema50Flag) === 'Y'
    && normalizeFlag(row.ema100Flag) === 'Y'
    && normalizeFlag(row.ema200Flag) === 'Y'
  );
}

function isBullishEmaStack(row: SectorWiseRow): boolean {
  const ema20Flag = normalizeFlag(row.ema20Flag);
  const ema50Flag = normalizeFlag(row.ema50Flag);
  const ema100Flag = normalizeFlag(row.ema100Flag);
  const ema200Flag = normalizeFlag(row.ema200Flag);
  if (ema20Flag !== 'Y' || ema50Flag !== 'Y' || ema100Flag !== 'Y' || ema200Flag !== 'Y') {
    return false;
  }
  const price = toSortableNumber(row.price);
  const ema20 = toSortableNumber(row.ema20);
  const ema50 = toSortableNumber(row.ema50);
  const ema100 = toSortableNumber(row.ema100);
  const ema200 = toSortableNumber(row.ema200);
  if (
    price === null
    || ema20 === null
    || ema50 === null
    || ema100 === null
    || ema200 === null
  ) {
    return false;
  }
  return price > ema20 && ema20 > ema50 && ema50 > ema100 && ema100 > ema200;
}

function resolveAthProximity(row: SectorWiseRow): number {
  const gapPct = toSortableNumber(row.gapPct);
  if (gapPct === null) return 0.5;
  return clampNumber((100 + gapPct) / 100, 0, 1);
}

function resolvePositiveSignalStrength(row: SectorWiseRow): number {
  const emaStrength = countBullishEmaFlags(row) / 4;
  const athProximity = resolveAthProximity(row);
  const stackBonus = isBullishEmaStack(row) ? 0.15 : 0;
  return clampNumber((emaStrength * 0.8) + (athProximity * 0.2) + stackBonus, 0, 1);
}

function resolveSidewaysStrength(row: SectorWiseRow): number {
  const bullishCount = countBullishEmaFlags(row);
  const balanceStrength = bullishCount === 2
    ? 1
    : bullishCount === 1 || bullishCount === 3
      ? 0.7
      : 0.35;
  const athProximity = resolveAthProximity(row);
  const middleZoneBonus = athProximity >= 0.35 && athProximity <= 0.8 ? 0.15 : 0;
  return clampNumber((balanceStrength * 0.85) + middleZoneBonus, 0, 1);
}

function resolvePullbackStrength(row: SectorWiseRow): number {
  const bullishCount = countBullishEmaFlags(row);
  const structureStrength = isPullbackStructure(row) ? 0.6 : 0.35;
  const athProximity = resolveAthProximity(row) * 0.25;
  const longTrendSupport = bullishCount >= 3 ? 0.15 : bullishCount >= 2 ? 0.08 : 0;
  return clampNumber(structureStrength + athProximity + longTrendSupport, 0, 1);
}

function mapStrengthToBand(strength: number, band: SectorTrendScoreBand): number {
  const normalized = clampNumber(strength, 0, 1);
  return clampNumber(
    Math.round(band.min + ((band.max - band.min) * normalized)),
    band.min,
    band.max,
  );
}

function resolveSectorTrendScoreLabel(row: SectorWiseRow): SectorTrendScoreLabel {
  const trend = sectorTrendLabel(row);
  const positiveStrength = resolvePositiveSignalStrength(row);
  const bullishCount = countBullishEmaFlags(row);
  if (trend === 'Strong Uptrend') return 'Strong Uptrend';
  if (trend === 'Pullback in Uptrend') return 'Pullback in Uptrend';
  if (trend === 'Uptrend') return 'Uptrend';
  if (trend === 'Downtrend') {
    return bullishCount === 0 || positiveStrength <= 0.2 ? 'Strong Downtrend' : 'Downtrend';
  }
  if (trend === 'Possible Reversal') {
    return positiveStrength >= 0.45 ? 'Sideways' : 'Downtrend';
  }
  return 'Sideways';
}

export function getSectorTrendBand(score: number): SectorTrendScoreBand {
  const safeScore = clampNumber(Math.round(score), 0, 100);
  return SECTOR_TREND_SCORE_BANDS.find((band) => safeScore >= band.min && safeScore <= band.max)
    ?? SECTOR_TREND_SCORE_BAND_BY_LABEL.Sideways;
}

export function getSectorTrendBadgeClass(label: SectorTrendScoreLabel): string {
  if (label === 'Strong Uptrend') return 'ui-data-badge ui-data-badge--success';
  if (label === 'Uptrend') return 'ui-data-badge ui-data-badge--success';
  if (label === 'Pullback in Uptrend') return 'ui-data-badge ui-data-badge--accent';
  if (label === 'Sideways') return 'ui-data-badge ui-data-badge--warn';
  return 'ui-data-badge ui-data-badge--danger';
}

function getSectorTrendScoreClass(label: SectorTrendScoreLabel): string {
  if (label === 'Strong Uptrend') return 'sector-score sector-score--strong';
  if (label === 'Uptrend' || label === 'Pullback in Uptrend') return 'sector-score sector-score--medium';
  if (label === 'Sideways') return 'sector-score sector-score--watch';
  return 'sector-score sector-score--weak';
}

export function calculateSectorTrendScore(row: SectorWiseRow): SectorTrendScoreResult {
  const label = resolveSectorTrendScoreLabel(row);
  const band = SECTOR_TREND_SCORE_BAND_BY_LABEL[label];
  const positiveStrength = resolvePositiveSignalStrength(row);
  let score = band.min;
  if (label === 'Strong Uptrend' || label === 'Uptrend') {
    score = mapStrengthToBand(positiveStrength, band);
  } else if (label === 'Pullback in Uptrend') {
    score = mapStrengthToBand(resolvePullbackStrength(row), band);
  } else if (label === 'Sideways') {
    score = mapStrengthToBand(resolveSidewaysStrength(row), band);
  } else {
    score = mapStrengthToBand(positiveStrength, band);
  }
  const resolvedBand = getSectorTrendBand(score);
  return {
    score,
    label: resolvedBand.label,
    band: resolvedBand,
    description: resolvedBand.description,
  };
}

function sectorWisePageScoreTitle(row: SectorWiseRow): string {
  const score = calculateSectorTrendScore(row);
  return [
    `Label: ${score.label}`,
    `Score: ${score.score}/100`,
    score.description,
    'Score is derived from trend label and available page-level technical confirmation signals.',
  ].join(' | ');
}

function sectorSortValue(row: SectorWiseRow, sortKey: string): string | number | null {
  if (sortKey === 'S_NO') return row.stock || '';
  if (sortKey === 'STOCK') return row.stock || '';
  if (sortKey === 'LTC_DATE') return String(row.ltcDate || '');
  if (sortKey === 'PRICE') return toSortableNumber(row.price);
  if (sortKey === 'MCAP') return toSortableNumber(row.totalMcap);
  if (sortKey === 'MCAP_RANK') return toSortableNumber(row.mcapRank);
  if (sortKey === 'INDEX') {
    const order: Record<string, number> = { LARGE: 0, MID: 1, SMALL: 2, '-': 3 };
    return order[formatSectorIndex(row.index)] ?? 3;
  }
  if (sortKey === 'GAP') return toSortableNumber(row.gapPct);
  if (sortKey === '52WH') return toSortableNumber(row.high52w);
  if (sortKey === '52WL') return toSortableNumber(row.low52w);
  if (sortKey === 'ATH') return toSortableNumber(row.ath);
  if (sortKey === 'EMA20_FLAG') return row.ema20Flag;
  if (sortKey === 'EMA50_FLAG') return row.ema50Flag;
  if (sortKey === 'EMA100_FLAG') return row.ema100Flag;
  if (sortKey === 'EMA200_FLAG') return row.ema200Flag;
  if (sortKey === 'TREND') return trendSortRank(row);
  if (sortKey === 'SCORE') return calculateSectorTrendScore(row).score;
  if (sortKey === 'SECTOR_PHASE') return String(row.sectorPhase || '');
  if (sortKey === 'SECTOR_SCORE') return toSortableNumber(row.sectorScore);
  if (sortKey === 'RS_VS_SECTOR') return toSortableNumber(row.rsVsSector);
  if (sortKey === 'RS_VS_BMARK') return toSortableNumber(row.rsVsBenchmark);
  if (sortKey === 'BREAKOUT') return String(row.breakoutStatus || '');
  if (sortKey === 'VOL_DELIVERY') return String(row.volumeDeliveryStatus || '');
  if (sortKey === 'RISK') return String(row.riskStatus || '');
  if (sortKey === 'CONFIDENCE') return String(row.confidence || '');
  if (sortKey === 'TREND_STATE') return String(row.trendState || '');
  if (sortKey === 'STOCK_EDGE_SCORE') return toSortableNumber(row.stockEdgeScore);
  if (sortKey === 'COVERAGE') return toSortableNumber(row.coverage);
  if (sortKey === 'RETURN21') return toSortableNumber(row.return21);
  if (sortKey === 'RETURN63') return toSortableNumber(row.return63);
  if (sortKey === 'RETURN126') return toSortableNumber(row.return126);
  if (sortKey === 'RSI') return toSortableNumber(row.rsi);
  if (sortKey === 'MACD') return toSortableNumber(row.macd);
  if (sortKey === 'ADX') return toSortableNumber(row.adx14);
  return row.stock || '';
}

function compareSectorRows(left: SectorWiseRow, right: SectorWiseRow, sortKey: string, sortDir: SortDir): number {
  const leftValue = sectorSortValue(left, sortKey);
  const rightValue = sectorSortValue(right, sortKey);
  let result = 0;
  if (leftValue === null && rightValue === null) {
    result = 0;
  } else if (leftValue === null) {
    result = 1;
  } else if (rightValue === null) {
    result = -1;
  } else if (typeof leftValue === 'number' && typeof rightValue === 'number') {
    result = leftValue < rightValue ? -1 : leftValue > rightValue ? 1 : 0;
  } else {
    const leftText = String(leftValue).toUpperCase();
    const rightText = String(rightValue).toUpperCase();
    result = leftText < rightText ? -1 : leftText > rightText ? 1 : 0;
  }

  if (sortDir === 'desc') result *= -1;
  if (result !== 0) return result;
  return String(left.stock || '').toUpperCase().localeCompare(String(right.stock || '').toUpperCase());
}

function buildDatasetView(views: SectorWiseViewPayload[]): SectorWiseViewPayload {
  const first = views[0];
  const rows = uniqueSectorRows(views.flatMap((view) => view.rows));
  const totalCount = Math.max(...views.map((view) => view.totalCount), rows.length, 0);
  const staleReasons = views.map((view) => view.staleReason).filter(Boolean);
  return {
    asOfDate: first?.asOfDate ?? '',
    generatedAt: first?.generatedAt ?? '',
    isStale: views.some((view) => view.isStale || view.source === 'stale_snapshot' || view.staleReason),
    loadedAt: first?.loadedAt ?? '',
    modelVersion: first?.modelVersion ?? '',
    page: 1,
    parent: first?.parent ?? {},
    rows,
    runId: first?.runId ?? '',
    source: Array.from(new Set(views.map((view) => view.source).filter(Boolean))).join('+'),
    staleReason: Array.from(new Set(staleReasons)).join(','),
    technicalSourceDate: first?.technicalSourceDate ?? '',
    totalCount,
    totalPages: Math.max(1, Math.ceil(totalCount / FIXED_PAGE_SIZE)),
    version: first?.version ?? '',
  };
}

async function fetchSectorWiseDataset(
  sectorCode: string,
  options: { forceRefresh: boolean; signal?: AbortSignal },
): Promise<SectorWiseCacheEntry> {
  const requestStartedAt = performance.now();
  const firstPayload = await fetchSectorWiseStocks(sectorCode, {
    dir: 'DESC',
    page: 1,
    pageSize: DATASET_PAGE_SIZE,
    refresh: options.forceRefresh ? 1 : undefined,
    sort: 'STOCK_EDGE_SCORE',
    version: 'v3',
  }, {
    diagnostic: {
      action: options.forceRefresh ? 'refresh-sector-wise-dataset' : 'load-sector-wise-dataset',
      component: 'SectorWiseStocksPage',
      page: `/app/sector/stocks/${sectorCode.toLowerCase()}`,
    },
    signal: options.signal,
  });
  const firstView = adaptSectorWisePayload(firstPayload);
  const views = [firstView];
  const backendPages = Math.max(1, firstView.totalPages);

  if (backendPages > 1) {
    const remainingViews = await Promise.all(Array.from({ length: backendPages - 1 }, (_, index) => (
      fetchSectorWiseStocks(sectorCode, {
        dir: 'DESC',
        page: index + 2,
        pageSize: DATASET_PAGE_SIZE,
        sort: 'STOCK_EDGE_SCORE',
        version: 'v3',
      }, {
        diagnostic: {
          action: 'load-sector-wise-dataset-page',
          component: 'SectorWiseStocksPage',
          page: `/app/sector/stocks/${sectorCode.toLowerCase()}`,
        },
        signal: options.signal,
      }).then(adaptSectorWisePayload)
    )));
    views.push(...remainingViews);
  }

  const view = buildDatasetView(views);
  const entry: SectorWiseCacheEntry = { cachedAt: Date.now(), value: view };
  perfLog('network-dataset-complete', {
    backendPages,
    latestLtcDate: resolveLatestLtcDate(view.rows) || '-',
    requestMs: Math.round(performance.now() - requestStartedAt),
    rows: view.rows.length,
    totalCount: view.totalCount,
  });
  return entry;
}

function renderSectorScoreCell(row: SectorWiseRow) {
  const result = calculateSectorTrendScore(row);
  return (
    <div className="sector-score-cell" data-score-label={result.label}>
      <span className={getSectorTrendScoreClass(result.label)}>{result.score}/100</span>
      <span className={getSectorTrendBadgeClass(result.label)}>{result.label}</span>
    </div>
  );
}

function formatV3Metric(value: unknown, suffix = ''): string {
  const parsed = toSortableNumber(value);
  return parsed === null ? '-' : `${parsed.toLocaleString('en-IN', { maximumFractionDigits: 2 })}${suffix}`;
}

function renderTechnicalLinks(symbol: string) {
  const encodedSymbol = encodeURIComponent(symbol);
  return (
    <details className="relative">
      <summary className="cursor-pointer whitespace-nowrap text-xs font-bold text-sky-700 dark:text-sky-300">
        Open
      </summary>
      <div className="mt-2 grid min-w-40 gap-1 rounded-lg border border-slate-200 bg-white p-2 shadow-lg dark:border-slate-700 dark:bg-slate-900">
        {stockTechnicalLinks.map((item) => (
          <a
            className="whitespace-nowrap text-xs text-slate-700 hover:text-sky-700 dark:text-slate-200 dark:hover:text-sky-300"
            href={`${item.href}?symbol=${encodedSymbol}`}
            key={item.href}
          >
            {item.label}
          </a>
        ))}
      </div>
    </details>
  );
}

export function formatSectorAnalyticsValue(value: unknown, numeric = false): string {
  if (numeric) {
    const parsed = toSortableNumber(value);
    return parsed === null
      ? '-'
      : parsed.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  }
  const token = String(value ?? '').trim();
  return token && token !== '-' ? token : '-';
}

export function renderSectorWiseCell(row: SectorWiseRow, key: string) {
  if (key === 'S_NO') return formatSectorCount(row.sNo);
  if (key === 'STOCK') return row.stock || '-';
  if (key === 'LTC_DATE') return formatSectorDate(row.ltcDate);
  if (key === 'PRICE') return formatSectorPrice(row.price);
  if (key === 'MCAP') return formatSectorMcap(row.totalMcap);
  if (key === 'MCAP_RANK') return formatSectorMcapRank(row.mcapRank);
  if (key === 'INDEX') return formatSectorIndex(row.index);
  if (key === 'ATH') return formatSectorPrice(row.ath);
  if (key === 'GAP') return formatSectorGap(row);
  if (key === '52WH') return formatSectorPrice(row.high52w);
  if (key === '52WL') return formatSectorPrice(row.low52w);
  if (key === 'EMA20_FLAG') return row.ema20Flag;
  if (key === 'EMA50_FLAG') return row.ema50Flag;
  if (key === 'EMA100_FLAG') return row.ema100Flag;
  if (key === 'EMA200_FLAG') return row.ema200Flag;
  if (key === 'TREND') return sectorTrendLabel(row);
  if (key === 'SCORE') return renderSectorScoreCell(row);
  if (key === 'SECTOR_PHASE') return formatSectorAnalyticsValue(row.sectorPhase);
  if (key === 'SECTOR_SCORE') return formatSectorAnalyticsValue(row.sectorScore, true);
  if (key === 'RS_VS_SECTOR') return formatSectorAnalyticsValue(row.rsVsSector, true);
  if (key === 'RS_VS_BMARK') return formatSectorAnalyticsValue(row.rsVsBenchmark, true);
  if (key === 'BREAKOUT') return formatSectorAnalyticsValue(row.breakoutStatus);
  if (key === 'VOL_DELIVERY') {
    const legacyValue = formatSectorAnalyticsValue(row.volumeDeliveryStatus);
    return legacyValue !== '-'
      ? legacyValue
      : `${formatV3Metric(row.volumeRatio, 'x')} / ${formatV3Metric(row.deliveryScore)}`;
  }
  if (key === 'RISK') return formatSectorAnalyticsValue(row.riskStatus || row.riskLevel);
  if (key === 'CONFIDENCE') return formatSectorAnalyticsValue(row.confidence);
  if (key === 'TREND_STATE') return formatSectorAnalyticsValue(row.trendState);
  if (key === 'STOCK_EDGE_SCORE') return (
    <div className="sector-score-cell">
      <span className={`heat-pill ${sectorHeatClass(row.stockEdgeScore)}`}>{formatV3Metric(row.stockEdgeScore)}</span>
      <span className="text-[10px] font-bold text-slate-500 dark:text-slate-400">{formatSectorAnalyticsValue(row.stockEdgeBand)}</span>
    </div>
  );
  if (key === 'COVERAGE') return formatV3Metric(row.coverage, '%');
  if (key === 'RETURN21') return formatV3Metric(row.return21, '%');
  if (key === 'RETURN63') return formatV3Metric(row.return63, '%');
  if (key === 'RETURN126') return formatV3Metric(row.return126, '%');
  if (key === 'RSI') return formatV3Metric(row.rsi);
  if (key === 'MACD') return `${formatV3Metric(row.macd)} / ${formatV3Metric(row.macdHist)}`;
  if (key === 'ADX') return formatV3Metric(row.adx14);
  if (key === 'TECHNICALS') return renderTechnicalLinks(row.stock);
  return '-';
}

function renderSkeletonRows(columnCount: number) {
  return Array.from({ length: FIXED_PAGE_SIZE }, (_, rowIndex) => (
    <tr key={`sector-skeleton-${rowIndex}`}>
      {Array.from({ length: columnCount }, (_, columnIndex) => (
        <td key={columnIndex}>
          <span className="ui-skeleton-line" aria-hidden="true" />
        </td>
      ))}
    </tr>
  ));
}

function getIndexCategoryClass(indexValue: unknown): string {
  const value = String(indexValue ?? '').trim().toUpperCase();
  if (value === 'LARGE') return 'sector-index-pill sector-index-pill--large';
  if (value === 'MID') return 'sector-index-pill sector-index-pill--mid';
  if (value === 'SMALL') return 'sector-index-pill sector-index-pill--small';
  return 'sector-index-pill sector-index-pill--unknown';
}

function normalizeSymbolToken(value: unknown): string {
  return normalizeDisplaySymbol(value);
}

function parseRequestedDynamicSectorCode(fallback = ''): string {
  if (typeof window === 'undefined') return '';
  try {
    const params = new URLSearchParams(window.location.search || '');
    return String(params.get('sector') || fallback).trim().toUpperCase();
  } catch {
    return fallback.trim().toUpperCase();
  }
}

function parseRequestedSectorTab(): SectorWiseTab {
  if (typeof window === 'undefined') return 'stocks';
  try {
    const params = new URLSearchParams(window.location.search || '');
    return String(params.get('tab') || '').trim().toLowerCase() === 'hierarchy' ? 'hierarchy' : 'stocks';
  } catch {
    return 'stocks';
  }
}

function syncSectorTabInUrl(tab: SectorWiseTab) {
  if (typeof window === 'undefined') return;
  try {
    const url = new URL(window.location.href);
    if (tab === 'hierarchy') {
      url.searchParams.set('tab', 'hierarchy');
    } else {
      url.searchParams.delete('tab');
    }
    window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
  } catch {
    // URL sync is best-effort and must never break page flow.
  }
}

function buildDynamicSectorHref(sectorCode: string, page: string): string {
  return `${page}?sector=${encodeURIComponent(sectorCode)}`;
}

function buildDynamicSectorPageItem(code: string, label: string, page: string): SectorPageItem {
  const normalizedCode = String(code || '').trim().toUpperCase();
  const normalizedLabel = String(label || normalizedCode).trim() || normalizedCode;
  return {
    code: normalizedCode,
    href: buildDynamicSectorHref(normalizedCode, page),
    label: normalizedLabel,
    page,
    slug: normalizedCode.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, ''),
  };
}

function adaptDynamicSectorOptions(payload: SectorDiscoveryPayload, page: string): SectorPageItem[] {
  const rows = Array.isArray(payload.sectors) ? payload.sectors : [];
  const seen = new Set<string>();
  const options: SectorPageItem[] = [];
  rows.forEach((row) => {
    const code = String(row.sectorCode || row.sector || '').trim().toUpperCase();
    const label = String(row.sectorName || row.label || code).trim() || code;
    if (!code || seen.has(code)) return;
    seen.add(code);
    options.push(buildDynamicSectorPageItem(code, label, page));
  });
  return options;
}

function formatSectorSelectOptionLabel(label: string, index: number): string {
  return `${index + 1}. ${label}`;
}

function cellClass(row: SectorWiseRow, key: string): string | undefined {
  if (key.startsWith('EMA')) return sectorFlagClass(String(renderSectorWiseCell(row, key)));
  if (key === 'GAP') return sectorGapClass(row);
  if (key === 'TREND') return sectorTrendClass(row);
  if (key === 'SCORE') return 'sector-score-cell-container';
  if (key === 'STOCK_EDGE_SCORE') return 'sector-score-cell-container';
  if (key === 'TREND_STATE') {
    const state = String(row.trendState || '').toUpperCase();
    if (state === 'STRONG_UPTREND') return 'text-emerald-700 font-black dark:text-emerald-300';
    if (state === 'UPTREND') return 'text-green-700 font-bold dark:text-green-300';
    if (state === 'DOWNTREND') return 'text-red-700 font-bold dark:text-red-300';
    if (state === 'DATA_WEAK') return 'text-amber-700 font-bold dark:text-amber-300';
  }
  return undefined;
}

function cellTitle(row: SectorWiseRow, key: string): string | undefined {
  if (key === 'ATH') {
    const athDate = formatSectorDate(row.athDate);
    return athDate === '-' ? undefined : `ATH Date: ${athDate}`;
  }
  if (key === 'SCORE') return sectorWisePageScoreTitle(row) || undefined;
  return undefined;
}

function Pagination({
  page,
  setPage,
  totalPages,
}: {
  page: number;
  setPage: (page: number) => void;
  totalPages: number;
}) {
  const resolvedTotal = Math.max(1, totalPages);
  const current = Math.min(Math.max(1, page), resolvedTotal);
  return (
    <AppPagination currentPage={current} totalPages={resolvedTotal} onPageChange={setPage} />
  );
}

type SectorWiseStocksPageProps = {
  dynamicMode?: boolean;
  sectorPage?: SectorPageItem;
  initialSectorCode?: string;
};

export function SectorWiseStocksPage({
  dynamicMode = false,
  sectorPage,
  initialSectorCode = '',
}: SectorWiseStocksPageProps) {
  const dynamicPage = SECTOR_DIRECTORY_PAGE;
  const [dynamicSectorOptions, setDynamicSectorOptions] = useState<SectorPageItem[]>([]);
  const [dynamicSectorError, setDynamicSectorError] = useState('');
  const [dynamicSectorStatus, setDynamicSectorStatus] = useState<SectorSelectorStatus>(
    dynamicMode ? 'loading' : 'online',
  );

  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [refreshRequest, setRefreshRequest] = useState({ force: false, version: 0 });
  const [rawRows, setRawRows] = useState<SectorWiseRow[]>([]);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('STOCK');
  const [dir, setDir] = useState<SortDir>('asc');
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [statusMessage, setStatusMessage] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastLoadedAt, setLastLoadedAt] = useState('');
  const [totalCount, setTotalCount] = useState(0);
  const [activeTab, setActiveTab] = useState<SectorWiseTab>(() => parseRequestedSectorTab());
  const [syncStatus, setSyncStatus] = useState<DatabaseSyncStatus | null>(null);
  const [snapshotInfo, setSnapshotInfo] = useState({
    asOfDate: '',
    runId: '',
    technicalSourceDate: '',
    parent: {} as Record<string, unknown>,
  });
  const deferredSearch = useDeferredValue(search);
  const requestSequenceRef = useRef(0);
  const committedRequestKeyRef = useRef('');
  const lastCommitStartedAtRef = useRef(0);
  const rawRowCountRef = useRef(0);
  const requestedDynamicSectorCode = useMemo(
    () => (dynamicMode ? parseRequestedDynamicSectorCode(initialSectorCode) : ''),
    [dynamicMode, initialSectorCode],
  );

  const sectorOptions = useMemo(() => {
    const baseOptions = dynamicMode ? dynamicSectorOptions : sectorPageItems;
    const uniqueMap = new Map<string, typeof baseOptions[0]>();
    baseOptions.forEach((item) => {
      const normalizedCode = item.code.trim().toUpperCase();
      if (!uniqueMap.has(normalizedCode)) {
        uniqueMap.set(normalizedCode, item);
      }
    });
    return Array.from(uniqueMap.values()).sort((a, b) => a.label.localeCompare(b.label));
  }, [dynamicMode, dynamicSectorOptions]);

  const activePage = useMemo(() => {
    if (dynamicMode) {
      const preferredCode = requestedDynamicSectorCode || sectorPage?.code || '';
      return sectorOptions.find((item) => item.code === preferredCode)
        ?? (requestedDynamicSectorCode
          ? undefined
          : sectorOptions.find((item) => item.code === 'AUTO') ?? sectorOptions[0]);
    }
    if (!sectorPage) return undefined;
    return sectorPageItems.find((item) => item.code === sectorPage.code) ?? sectorPage;
  }, [dynamicMode, requestedDynamicSectorCode, sectorOptions, sectorPage]);

  const sectorCode = activePage?.code ?? '';
  const requestKey = useMemo(
    () => (sectorCode ? buildSectorWiseRequestKey(sectorCode) : ''),
    [sectorCode],
  );
  const requestSectorReload = useCallback((force: boolean) => {
    setRefreshRequest((current) => ({ force, version: current.version + 1 }));
  }, []);

  /* ---- Fetch Database Sync Status ---- */
  useEffect(() => {
    fetchDatabaseSyncStatus({
      diagnostic: {
        action: 'GET /api/database/sync-status',
        component: 'SectorWiseStocksPage',
        page: `CvingTrade25X - Sector Wise Stocks - ${sectorCode}`,
      }
    })
      .then((res) => {
        setSyncStatus(res);
      })
      .catch((err) => {
        console.error('Failed to fetch DB sync status', err);
      });
  }, [refreshRequest.version, sectorCode]);

  useEffect(() => {
    if (!dynamicMode) return undefined;
    let cancelled = false;
    setDynamicSectorStatus('loading');
    setDynamicSectorError('');
    fetchSectorRotationSectors(refreshRequest.force ? { refresh: 1 } : undefined, {
      diagnostic: {
        action: refreshRequest.force ? 'refresh-sector-stocks-v3-sectors' : 'load-sector-stocks-v3-sectors',
        component: 'SectorWiseStocksPage',
        page: dynamicPage,
      },
    }).then((payload) => {
      if (cancelled) return;
      const options = adaptDynamicSectorOptions(payload, dynamicPage);
      setDynamicSectorOptions(options);
      if (!options.length) {
        setDynamicSectorStatus('error');
        setDynamicSectorError('No sectors were returned from the database-backed sector discovery endpoint.');
        return;
      }
      setDynamicSectorStatus('online');
      setDynamicSectorError('');
    }).catch((loadError: unknown) => {
      if (cancelled) return;
      setDynamicSectorStatus('error');
      setDynamicSectorError(loadError instanceof Error ? loadError.message : String(loadError));
      setDynamicSectorOptions([]);
    });
    return () => {
      cancelled = true;
    };
  }, [dynamicMode, dynamicPage, refreshRequest.force, refreshRequest.version]);

  useEffect(() => {
    if (!dynamicMode || !activePage || !sectorCode || typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    const currentCode = String(url.searchParams.get('sector') || '').trim().toUpperCase();
    if (currentCode === sectorCode) return;
    url.searchParams.set('sector', sectorCode);
    window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
  }, [activePage, dynamicMode, sectorCode]);

  useEffect(() => {
    if (!sectorCode) return;
    perfLog('route-mount', {
      page: dynamicMode ? dynamicPage : `/app/sector/stocks/${sectorCode.toLowerCase()}`,
      sector: sectorCode,
    });
  }, [dynamicMode, dynamicPage, sectorCode]);

  useEffect(() => {
    rawRowCountRef.current = rawRows.length;
  }, [rawRows.length]);

  useEffect(() => {
    if (!sectorCode || !requestKey) {
      setRawRows([]);
      setTotalCount(0);
      if (dynamicMode && dynamicSectorStatus === 'error') {
        setStatus('error');
        setError(dynamicSectorError || 'Unable to load sector selector data.');
      } else {
        setStatus('loading');
        setError('');
      }
      return undefined;
    }

    const forceRefresh = refreshRequest.force;
    const lifecycleStartedAt = performance.now();
    const requestId = ++requestSequenceRef.current;
    const hadVisibleRows = rawRowCountRef.current > 0 && committedRequestKeyRef.current === requestKey;
    let cancelled = false;

    const commitView = (view: SectorWiseViewPayload, source: 'cache' | 'network') => {
      if (cancelled || requestId !== requestSequenceRef.current) return;
      lastCommitStartedAtRef.current = performance.now();
      setLastLoadedAt(view.loadedAt || '');
      setRawRows(view.rows);
      setTotalCount(view.totalCount);
      committedRequestKeyRef.current = requestKey;
      setSnapshotInfo({
        asOfDate: view.asOfDate,
        runId: view.runId,
        technicalSourceDate: view.technicalSourceDate,
        parent: view.parent,
      });
      setStatus('online');
      setError('');
      perfLog('commit', {
        latestLtcDate: resolveLatestLtcDate(view.rows) || '-',
        rows: view.rows.length,
        source,
        totalCount: view.totalCount,
      });
    };

    const cachedEntry = forceRefresh ? null : readCachedSectorWiseEntry(requestKey);
    if (cachedEntry) {
      commitView(cachedEntry.value, 'cache');
      perfLog('cache-hit', {
        ageMs: Date.now() - cachedEntry.cachedAt,
        key: requestKey,
      });
    } else {
      if (committedRequestKeyRef.current !== requestKey) {
        setRawRows([]);
        setTotalCount(0);
      }
      setStatus('loading');
      setError('');
      perfLog('cache-miss', { key: requestKey, sector: sectorCode });
    }

    const cacheAgeMs = cachedEntry ? Date.now() - cachedEntry.cachedAt : Number.POSITIVE_INFINITY;
    const shouldRevalidate = forceRefresh || !cachedEntry || cacheAgeMs >= SECTOR_WISE_REVALIDATE_AGE_MS;
    if (!shouldRevalidate) {
      perfLog('revalidate-skipped', {
        ageMs: cacheAgeMs,
        key: requestKey,
      });
      return () => {
        cancelled = true;
      };
    }

    const directController = forceRefresh ? new AbortController() : null;
    abortStaleSectorWiseInflight(requestKey);
    setIsRefreshing(true);

    let loadPromise: Promise<SectorWiseCacheEntry>;
    const existingInflight = !forceRefresh ? sectorWiseInflightRequests.get(requestKey) : null;
    if (existingInflight) {
      loadPromise = existingInflight.promise;
      perfLog('inflight-dedupe-hit', { key: requestKey });
    } else if (forceRefresh) {
      loadPromise = fetchSectorWiseDataset(sectorCode, {
        forceRefresh: true,
        signal: directController?.signal,
      }).then((entry) => {
        writeCachedSectorWiseEntry(requestKey, entry);
        perfLog('network-refresh-complete', {
          key: requestKey,
          rows: entry.value.rows.length,
          totalMs: Math.round(performance.now() - lifecycleStartedAt),
        });
        return entry;
      });
    } else {
      const sharedController = new AbortController();
      loadPromise = fetchSectorWiseDataset(sectorCode, {
        forceRefresh: false,
        signal: sharedController.signal,
      }).then((entry) => {
        writeCachedSectorWiseEntry(requestKey, entry);
        perfLog('network-complete', {
          key: requestKey,
          rows: entry.value.rows.length,
          totalMs: Math.round(performance.now() - lifecycleStartedAt),
        });
        return entry;
      }).finally(() => {
        sectorWiseInflightRequests.delete(requestKey);
      });
      sectorWiseInflightRequests.set(requestKey, { controller: sharedController, promise: loadPromise });
    }

    loadPromise
      .then((entry) => commitView(entry.value, 'network'))
      .catch((loadError: unknown) => {
        if (cancelled) return;
        const isAbort = loadError instanceof Error && /abort/i.test(loadError.message);
        if (isAbort) return;
        if (!cachedEntry && !hadVisibleRows) {
          setRawRows([]);
          setStatus('error');
          setError(loadError instanceof Error ? loadError.message : String(loadError));
        } else {
          setStatus('online');
          setError(loadError instanceof Error ? loadError.message : String(loadError));
        }
        perfLog('network-error', {
          key: requestKey,
          message: loadError instanceof Error ? loadError.message : String(loadError),
        });
      })
      .finally(() => {
        if (!cancelled && requestId === requestSequenceRef.current) {
          setIsRefreshing(false);
        }
      });

    return () => {
      cancelled = true;
      if (directController) {
        directController.abort('Cancelled sector-wise refresh request');
      }
    };
  }, [
    dynamicMode,
    dynamicSectorError,
    dynamicSectorStatus,
    refreshRequest.force,
    refreshRequest.version,
    requestKey,
    sectorCode,
  ]);

  useEffect(() => {
    if (!IS_DEV || !rawRows.length || lastCommitStartedAtRef.current <= 0) return;
    perfLog('render-commit', {
      rows: rawRows.length,
      renderMs: Math.round(performance.now() - lastCommitStartedAtRef.current),
      totalCount,
    });
  }, [rawRows, totalCount]);

  useEffect(() => {
    if (!statusMessage) return undefined;
    const timer = window.setTimeout(() => setStatusMessage(''), 2500);
    return () => window.clearTimeout(timer);
  }, [statusMessage]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState && document.visibilityState !== 'visible') return;
      setRefreshRequest((current) => ({ force: false, version: current.version + 1 }));
    }, AUTO_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, []);

  const normalizedRows = useMemo(() => rawRows, [rawRows]);
  const visibleColumns = useMemo(
    () => resolveSectorWiseVisibleColumns(normalizedRows),
    [normalizedRows],
  );
  const unknownOrInsufficientRows = useMemo(() => normalizedRows
    .filter(isSectorWiseUnknownOrInsufficient)
    .map((row, index) => ({ ...row, sNo: index + 1 })), [normalizedRows]);

  const filteredRows = useMemo(() => {
    const startedAt = performance.now();
    const token = deferredSearch.trim().toUpperCase();
    const result = filterSectorWiseRows(normalizedRows, token);
    perfLog('filter-selector', {
      filterMs: Math.round(performance.now() - startedAt),
      rows: result.length,
      search: token || '-',
    });
    return result;
  }, [deferredSearch, normalizedRows]);

  const sortedRows = useMemo(() => {
    const startedAt = performance.now();
    const result = [...filteredRows].sort((left, right) => compareSectorRows(left, right, sort, dir));
    perfLog('sort-selector', {
      dir,
      rows: result.length,
      sort,
      sortMs: Math.round(performance.now() - startedAt),
    });
    return result;
  }, [dir, filteredRows, sort]);

  const totalPages = Math.max(1, Math.ceil(sortedRows.length / FIXED_PAGE_SIZE));

  const paginatedRows = useMemo(() => {
    const startedAt = performance.now();
    const current = Math.min(Math.max(1, page), totalPages);
    const start = (current - 1) * FIXED_PAGE_SIZE;
    const result = sortedRows.slice(start, start + FIXED_PAGE_SIZE).map((row, index) => ({
      ...row,
      sNo: start + index + 1,
    }));
    perfLog('pagination-selector', {
      page: current,
      paginationMs: Math.round(performance.now() - startedAt),
      renderedRows: result.length,
      totalPages,
    });
    return result;
  }, [page, sortedRows, totalPages]);

  const symbolMetaBySymbol = useMemo<Record<string, SectorSymbolMeta>>(() => {
    const out: Record<string, SectorSymbolMeta> = {};
    normalizedRows.forEach((row) => {
      const key = normalizeSymbolToken(row.stock);
      if (!key) return;
      out[key] = {
        index: formatSectorIndex(row.index),
        mcap: toSortableNumber(row.totalMcap),
        mcapRank: toSortableNumber(row.mcapRank),
      };
    });
    return out;
  }, [normalizedRows]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  function toggleSort(columnKey: string) {
    setPage(1);
    setSort((current) => {
      if (current !== columnKey) {
        setDir('asc');
        return columnKey;
      }
      setDir((currentDir) => currentDir === 'asc' ? 'desc' : 'asc');
      return current;
    });
  }

  const activeSectorPage = activePage?.page ?? (dynamicMode ? dynamicPage : '');
  const activeSectorLabel = activePage?.label ?? '';
  const latestLtcDate = useMemo(() => resolveLatestLtcDate(normalizedRows), [normalizedRows]);
  const toolbarStatus = resolveSectorLiveToolbarStatus(Boolean(dynamicSectorError || error));
  const toolbarLastRefreshed = lastLoadedAt || syncStatus?.last_sync_time || null;
  const toolbarLtcDate = snapshotInfo.asOfDate || syncStatus?.dev_ltc_date || latestLtcDate || null;
  const canExportUnknownOrInsufficient = unknownOrInsufficientRows.length > 0;

  function downloadUnknownOrInsufficientTxt() {
    if (!canExportUnknownOrInsufficient) return;
    triggerSectorWiseDownload(
      buildSectorWiseUnknownTxt(unknownOrInsufficientRows),
      buildSectorWiseDownloadFilename(activeSectorLabel, 'txt'),
      'text/plain;charset=utf-8;',
    );
  }

  function downloadUnknownOrInsufficientCsv() {
    if (!canExportUnknownOrInsufficient) return;
    triggerSectorWiseDownload(
      buildSectorWiseUnknownCsv(unknownOrInsufficientRows, visibleColumns),
      buildSectorWiseDownloadFilename(activeSectorLabel, 'csv'),
      'text/csv;charset=utf-8;',
    );
  }

  return (
    <SectorMigrationLayout activeSectorPage={activeSectorPage} className="sector-wise-react-page">
      <StrategyToolbar
        className="mb-4"
        isLoading={status === 'loading'}
        lastRefreshed={toolbarLastRefreshed}
        ltcDate={toolbarLtcDate}
        onLive={() => requestSectorReload(true)}
        onRefresh={() => requestSectorReload(true)}
        onSearchChange={(value) => { setSearch(value); setPage(1); }}
        refreshing={isRefreshing}
        searchPlaceholder="Search Card"
        searchValue={search}
        showTotal
        singleSurface
        status={toolbarStatus}
        total={filteredRows.length}
      />

      <Tabs
        value={activeTab}
        onValueChange={(value) => {
          const nextTab: SectorWiseTab = value === 'hierarchy' ? 'hierarchy' : 'stocks';
          setActiveTab(nextTab);
          syncSectorTabInUrl(nextTab);
        }}
      >
        <div className="sector-compact-page-header">
          <h1 className="sector-compact-page-title">{activeSectorLabel.toUpperCase()}</h1>
          <div className="sector-compact-controls sector-wise-compact-controls" aria-label="Sector wise controls">
            <Select
              className="sr-select sector-wise-compact-select w-auto max-w-[350px]"
              variant="light"
              value={sectorCode}
              disabled={dynamicMode && dynamicSectorStatus !== 'online'}
              onChange={(event) => {
                const nextPage = sectorOptions.find((item) => item.code === event.currentTarget.value);
                const currentHref = `${window.location.pathname}${window.location.search}`;
                if (!nextPage || nextPage.href === currentHref) return;
                const target = getInternalNavigationTarget(nextPage.href);
                if (target) {
                  navigateToInternalRoute(target);
                } else {
                  window.location.assign(nextPage.href);
                }
              }}
              aria-label="Select sector"
            >
              {sectorOptions.map((item, index) => (
                <option key={item.code} value={item.code}>
                  {formatSectorSelectOptionLabel(item.label, index)}
                </option>
              ))}
            </Select>
            <div className="sector-hierarchy-actions">
              <TabsList className="sector-hierarchy-tab-list">
                <TabsTrigger value="stocks">Existing Sector Wise Stocks</TabsTrigger>
                <TabsTrigger value="hierarchy">Sector Hierarchy</TabsTrigger>
              </TabsList>
              <div className="sector-overview-download-actions" aria-label="Unknown or insufficient data downloads">
                <button
                  className="sector-overview-download-button sector-overview-download-button--txt"
                  type="button"
                  onClick={downloadUnknownOrInsufficientTxt}
                  disabled={!canExportUnknownOrInsufficient}
                >
                  Download TXT
                </button>
                <button
                  className="sector-overview-download-button sector-overview-download-button--csv"
                  type="button"
                  onClick={downloadUnknownOrInsufficientCsv}
                  disabled={!canExportUnknownOrInsufficient}
                >
                  Download CSV
                </button>
              </div>
            </div>
          </div>
        </div>

        <TabsContent value="stocks">
          <div className="sector-compact-controls sector-wise-compact-controls" aria-label="Sector wise stock controls">
            {isRefreshing ? <span className="count-pill">Refreshing...</span> : statusMessage ? <span className="count-pill">{statusMessage}</span> : null}
          </div>
          {dynamicMode && dynamicSectorError ? <p className="sector-rotation-page-meta is-error" aria-live="polite">{dynamicSectorError}</p> : null}
          {error ? <p className="sector-rotation-page-meta is-error" aria-live="polite">{error}</p> : null}
          <section className="card sr-card sector-wise-card">
            <div className="table-title">
              <h3>{activeSectorLabel.toUpperCase()}</h3>
              <Pagination page={page} setPage={setPage} totalPages={totalPages} />
            </div>
            <div className="table-wrapper sector-react-table-wrapper">
              <table className="app-data-table table-sticky-safe data-table sr-table sector-wise-react-table">
                <colgroup>
                  {visibleColumns.map((column) => (
                    <col
                      key={column.key}
                      data-col={column.dataCol}
                      data-sticky-role={stickyColumnRole(column.key) || undefined}
                    />
                  ))}
                </colgroup>
                <thead>
                  <tr>
                    {visibleColumns.map((column) => (
                      <th
                        key={column.key}
                        className={stickyHeaderClass(column.key)}
                        data-col={column.dataCol}
                        data-sort={column.key}
                        data-sticky-col={stickyColumnRole(column.key) ? 'left' : undefined}
                        data-sticky-role={stickyColumnRole(column.key) || undefined}
                        onClick={() => toggleSort(column.key)}
                      >
                        {column.label}{sort === column.key && column.key !== 'STOCK' ? (dir === 'asc' ? ' ^' : ' v') : ''}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {paginatedRows.length ? paginatedRows.map((row, index) => (
                    <tr key={`${row.stock}-${row.ltcDate || index}`}>
                      {visibleColumns.map((column) => {
                        const rendered = renderSectorWiseCell(row, column.key);
                        const indexClass = (column.key === 'STOCK' || column.key === 'INDEX' || column.key === 'MCAP' || column.key === 'MCAP_RANK')
                          ? getIndexCategoryClass(row.index)
                          : undefined;
                        return (
                          <td
                            key={column.key}
                            data-col={column.dataCol}
                            data-sticky-col={stickyColumnRole(column.key) ? 'left' : undefined}
                            data-sticky-role={stickyColumnRole(column.key) || undefined}
                            className={stickyCellClass(column.key, cellClass(row, column.key))}
                            title={cellTitle(row, column.key)}
                          >
                            {column.key === 'STOCK' ? (
                              <span
                                className={`trend-symbol-copy sector-symbol-copy ${indexClass || ''}`}
                                role="button"
                                tabIndex={0}
                                title={`Copy ${row.stock || '-'}`}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  copyText(row.stock || '').then(() => setStatusMessage(`Copied: ${row.stock || '-'}`)).catch(() => undefined);
                                }}
                                onKeyDown={(event) => {
                                  if (event.key !== 'Enter' && event.key !== ' ') return;
                                  event.preventDefault();
                                  event.stopPropagation();
                                  copyText(row.stock || '').then(() => setStatusMessage(`Copied: ${row.stock || '-'}`)).catch(() => undefined);
                                }}
                              >
                                {row.stock || '-'}
                              </span>
                            ) : indexClass ? (
                              <span className={indexClass}>{rendered}</span>
                            ) : (
                              rendered
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  )) : status === 'loading' ? renderSkeletonRows(visibleColumns.length) : (
                    <tr>
                      <td className="sector-stock-status" colSpan={visibleColumns.length}>
                        No sector stocks found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <Pagination page={page} setPage={setPage} totalPages={totalPages} />
          </section>
        </TabsContent>

        <TabsContent value="hierarchy">
          <SectorHierarchyPanel symbolMetaBySymbol={symbolMetaBySymbol} />
        </TabsContent>
      </Tabs>
    </SectorMigrationLayout>
  );
}
