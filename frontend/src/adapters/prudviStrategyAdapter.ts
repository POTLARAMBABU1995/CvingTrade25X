import type {
  PrudviFlag,
  PrudviCandleDirection,
  PrudviSupportReaction,
  PrudviStrategyFilters,
  PrudviStrategyMeta,
  PrudviStrategyPayload,
  PrudviStrategyRow,
  PrudviTrend,
} from '../types/strategy/prudvi';
import {
  firstPresentValue,
  formatMarketCapRankValue,
  formatMarketCapValue,
  MARKET_CAP_INDEX_ALIASES,
  MARKET_CAP_RANK_ALIASES,
  MARKET_CAP_VALUE_ALIASES,
  normalizeMarketCapIndex,
} from './technicalMarketCap';

export type PrudviColumnKey = keyof PrudviStrategyRow;

export const PRUDVI_COLUMNS: Array<{ key: PrudviColumnKey; label: string; width: number }> = [
  { key: 'S_NO', label: 'S.NO', width: 72 },
  { key: 'SYMBOL', label: 'SYMBOL', width: 144 },
  { key: 'INDEX', label: 'INDEX', width: 96 },
  { key: 'MCAP', label: 'MCAP', width: 128 },
  { key: 'MCAP_RANK', label: 'MCAP_RANK', width: 112 },
  { key: 'ATH', label: 'ATH', width: 112 },
  { key: 'PRICE', label: 'PRICE', width: 112 },
  { key: 'GAP', label: 'GAP', width: 112 },
  { key: 'LTC_DATE', label: 'LTC_DATE', width: 120 },
  { key: 'SUPPORT', label: 'SUPPORT', width: 136 },
  { key: 'RESISTANCE', label: 'RESISTANCE', width: 136 },
  { key: 'SUPPORT_REACTION', label: 'SUPPORT_REACTION', width: 156 },
  { key: 'SUPPORT_CANDLE', label: 'SUPPORT_CANDLE', width: 176 },
  { key: 'CANDLE_DIRECTION', label: 'CANDLE_DIRECTION', width: 164 },
  { key: 'SUPPORT_REVERSAL', label: 'SUPPORT_REVERSAL', width: 160 },
  { key: 'BULLISH_CANDLE', label: 'BULLISH_CANDLE', width: 140 },
  { key: 'EMA_GT_20', label: 'EMA>20', width: 104 },
  { key: 'EMA_GT_50', label: 'EMA>50', width: 104 },
  { key: 'RSI_GT_50', label: 'RSI>50', width: 104 },
  { key: 'ADX_GT_25', label: 'ADX>25', width: 104 },
  { key: 'MACD_GT_0', label: 'MACD>0', width: 112 },
  { key: 'VOLUME_GT_20', label: 'VOLUME>20', width: 120 },
  { key: 'DELIVERY_GT_60', label: 'DELIVERY%>60', width: 132 },
  { key: 'TREND', label: 'TREND', width: 136 },
  { key: 'TREND_SCORE', label: 'TREND_SCORE', width: 124 },
];

const FLAG_VALUES: PrudviFlag[] = ['Y', 'N', '-'];
const TREND_VALUES: PrudviTrend[] = ['UPTREND', 'DOWNTREND', 'CONSOLIDATION', '-'];
const REACTION_VALUES: PrudviSupportReaction[] = ['BOUNCE', 'BREAKDOWN', 'HOLDING', 'NO_REACTION', '-'];
const DIRECTION_VALUES: PrudviCandleDirection[] = ['BULLISH', 'BEARISH', 'NEUTRAL', '-'];

export type PrudviFlagColumnKey =
  | 'BULLISH_CANDLE'
  | 'EMA_GT_20'
  | 'EMA_GT_50'
  | 'RSI_GT_50'
  | 'ADX_GT_25'
  | 'MACD_GT_0'
  | 'VOLUME_GT_20'
  | 'DELIVERY_GT_60';

export const PRUDVI_REQUIRED_TREND_FLAG_KEYS: PrudviFlagColumnKey[] = [
  'EMA_GT_20',
  'EMA_GT_50',
  'RSI_GT_50',
  'ADX_GT_25',
  'MACD_GT_0',
];

export const PRUDVI_CONDITION_KPI_FLAGS: Array<{ key: PrudviFlagColumnKey; label: string }> = [
  { key: 'BULLISH_CANDLE', label: 'BULLISH_CANDLE' },
  { key: 'EMA_GT_20', label: 'EMA>20' },
  { key: 'EMA_GT_50', label: 'EMA>50' },
  { key: 'RSI_GT_50', label: 'RSI>50' },
  { key: 'ADX_GT_25', label: 'ADX>25' },
  { key: 'MACD_GT_0', label: 'MACD>0' },
  { key: 'VOLUME_GT_20', label: 'VOLUME>20' },
  { key: 'DELIVERY_GT_60', label: 'DELIVERY%>60' },
];

export type PrudviKpiCounts = {
  filteredOutStocks: number;
  flagCounts: Record<PrudviFlagColumnKey, number>;
  totalStocksLoaded: number;
  trendQualifiedStocks: number;
};

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function toText(value: unknown): string {
  return String(value ?? '').trim();
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const numeric = typeof value === 'number' ? value : Number(String(value).replace(/,/g, '').replace(/%/g, '').trim());
  return Number.isFinite(numeric) ? numeric : null;
}

function formatNumber(value: number | null, digits = 2): string {
  if (!Number.isFinite(value)) return '-';
  return (value as number).toLocaleString('en-IN', {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  });
}

function normalizeDateDisplay(value: unknown): string {
  const text = toText(value);
  if (!text) return '-';
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return `${iso[3]}-${iso[2]}-${iso[1]}`;
  return text;
}

export function normalizePrudviFlag(value: unknown): PrudviFlag {
  const token = toText(value).toUpperCase();
  if (FLAG_VALUES.includes(token as PrudviFlag)) return token as PrudviFlag;
  if (['TRUE', 'YES', '1'].includes(token)) return 'Y';
  if (['FALSE', 'NO', '0'].includes(token)) return 'N';
  return '-';
}

function normalizeTrend(value: unknown): PrudviTrend {
  const token = toText(value).toUpperCase();
  if (TREND_VALUES.includes(token as PrudviTrend)) return token as PrudviTrend;
  if (token.includes('UPTREND')) return 'UPTREND';
  if (token.includes('DOWNTREND')) return 'DOWNTREND';
  if (['RANGE', 'RANGE BOUND', 'RANGEBOUND', 'ACCUMULATION'].includes(token)) return 'CONSOLIDATION';
  return '-';
}

function normalizeSupportReaction(value: unknown): PrudviSupportReaction {
  const token = toText(value).toUpperCase().replace(/\s+/g, '_');
  if (REACTION_VALUES.includes(token as PrudviSupportReaction)) return token as PrudviSupportReaction;
  return '-';
}

function normalizeCandleDirection(value: unknown): PrudviCandleDirection {
  const token = toText(value).toUpperCase();
  if (DIRECTION_VALUES.includes(token as PrudviCandleDirection)) return token as PrudviCandleDirection;
  return '-';
}

function normalizeCandleName(value: unknown): string {
  const token = toText(value).toUpperCase().replace(/[\s-]+/g, '_');
  return token || '-';
}

function extractRows(payload: unknown): unknown[] {
  if (Array.isArray(payload)) return payload;
  if (!isObject(payload)) return [];
  if (Array.isArray(payload.data)) return payload.data;
  if (Array.isArray(payload.rows)) return payload.rows;
  if (isObject(payload.data) && Array.isArray(payload.data.rows)) return payload.data.rows;
  return [];
}

function normalizeRow(row: unknown, index: number): PrudviStrategyRow | null {
  if (!isObject(row)) return null;
  const symbol = toText(row.SYMBOL ?? row.symbol ?? row.stock);
  if (!symbol) return null;
  const score = toNumber(row.TREND_SCORE ?? row.trendScore ?? row.score) ?? 0;
  return {
    S_NO: Math.round(toNumber(row.S_NO ?? row.s_no ?? row.sNo) ?? index + 1),
    SYMBOL: symbol,
    INDEX: normalizeMarketCapIndex(firstPresentValue(row, MARKET_CAP_INDEX_ALIASES)),
    MCAP: toNumber(firstPresentValue(row, MARKET_CAP_VALUE_ALIASES)),
    MCAP_RANK: toNumber(firstPresentValue(row, MARKET_CAP_RANK_ALIASES)),
    ATH: toNumber(row.ATH ?? row.ath ?? row.athSort),
    PRICE: toNumber(row.PRICE ?? row.price ?? row.CLOSE ?? row.close),
    GAP: toNumber(row.GAP_SORT ?? row.gapSort ?? row.GAP ?? row.gap),
    LTC_DATE: normalizeDateDisplay(row.LTC_DATE ?? row.ltcDate ?? row.latestTradingDate ?? row.TRADING_DATE),
    SUPPORT: toText(row.SUPPORT ?? row.support) || '-',
    RESISTANCE: toText(row.RESISTANCE ?? row.resistance) || '-',
    SUPPORT_REACTION: normalizeSupportReaction(row.SUPPORT_REACTION ?? row.supportReaction),
    SUPPORT_CANDLE: normalizeCandleName(row.SUPPORT_CANDLE ?? row.supportCandle),
    CANDLE_DIRECTION: normalizeCandleDirection(row.CANDLE_DIRECTION ?? row.candleDirection),
    SUPPORT_REVERSAL: normalizePrudviFlag(row.SUPPORT_REVERSAL ?? row.supportReversal),
    BULLISH_CANDLE: normalizePrudviFlag(row.BULLISH_CANDLE ?? row.bullishCandle),
    EMA_GT_20: normalizePrudviFlag(row.EMA_GT_20 ?? row.emaGt20),
    EMA_GT_50: normalizePrudviFlag(row.EMA_GT_50 ?? row.emaGt50),
    RSI_GT_50: normalizePrudviFlag(row.RSI_GT_50 ?? row.rsiGt50),
    ADX_GT_25: normalizePrudviFlag(row.ADX_GT_25 ?? row.adxGt25),
    MACD_GT_0: normalizePrudviFlag(row.MACD_GT_0 ?? row.macdGt0),
    VOLUME_GT_20: normalizePrudviFlag(row.VOLUME_GT_20 ?? row.volumeGt20),
    DELIVERY_GT_60: normalizePrudviFlag(row.DELIVERY_GT_60 ?? row.deliveryGt60),
    TREND: normalizeTrend(row.TREND ?? row.trend),
    TREND_SCORE: Math.max(0, Math.min(100, Math.round(score))),
  };
}

function normalizeMeta(payload: unknown, rowCount: number): PrudviStrategyMeta {
  const meta = isObject(payload) && isObject(payload.meta) ? payload.meta : {};
  return {
    cacheState: toText(meta.cacheState) || undefined,
    computeMs: toNumber(meta.computeMs) ?? undefined,
    durationMs: toNumber(meta.durationMs) ?? undefined,
    manualSrSymbols: toNumber(meta.manualSrSymbols) ?? undefined,
    refreshing: Boolean(meta.refreshing || (isObject(payload) && payload.refreshing === true)),
    rows: toNumber(meta.rows) ?? rowCount,
    stale: Boolean(meta.stale || meta.is_stale || (isObject(payload) && (payload.stale === true || payload.is_stale === true))),
    tradingDate: toText(meta.tradingDate) || null,
  };
}

export function adaptPrudviStrategyPayload(payload: unknown): PrudviStrategyPayload {
  const rows = extractRows(payload)
    .map(normalizeRow)
    .filter((row): row is PrudviStrategyRow => Boolean(row));
  return {
    error: isObject(payload) ? toText(payload.error) || undefined : undefined,
    meta: normalizeMeta(payload, rows.length),
    rows,
    status: isObject(payload) ? toText(payload.status) || 'success' : 'success',
  };
}

export function filterPrudviRows(rows: PrudviStrategyRow[], filters: PrudviStrategyFilters): PrudviStrategyRow[] {
  const query = filters.search.trim().toUpperCase();
  const minimumScore = Number(filters.minimumScore);
  const hasMinimumScore = Number.isFinite(minimumScore);
  return rows.filter((row) => {
    if (query && !row.SYMBOL.toUpperCase().includes(query)) return false;
    if (filters.trend !== 'ALL' && row.TREND !== filters.trend) return false;
    if (hasMinimumScore && row.TREND_SCORE < minimumScore) return false;
    return true;
  });
}

export function isPrudviTrendQualifiedRow(row: PrudviStrategyRow): boolean {
  return PRUDVI_REQUIRED_TREND_FLAG_KEYS.every((key) => row[key] === 'Y');
}

export function calculatePrudviKpiCounts(rows: PrudviStrategyRow[]): PrudviKpiCounts {
  const flagCounts = PRUDVI_CONDITION_KPI_FLAGS.reduce((counts, item) => {
    counts[item.key] = rows.filter((row) => row[item.key] === 'Y').length;
    return counts;
  }, {} as Record<PrudviFlagColumnKey, number>);
  const trendQualifiedStocks = rows.filter(isPrudviTrendQualifiedRow).length;
  return {
    filteredOutStocks: Math.max(0, rows.length - trendQualifiedStocks),
    flagCounts,
    totalStocksLoaded: rows.length,
    trendQualifiedStocks,
  };
}

export function isStrongPrudviUptrendRow(row: PrudviStrategyRow): boolean {
  return row.TREND === 'UPTREND' && row.TREND_SCORE >= 80;
}

function prudviDisplayRank(row: PrudviStrategyRow): number {
  if (isStrongPrudviUptrendRow(row)) return 0;
  if (row.TREND === 'UPTREND') return 1;
  if (row.TREND === 'CONSOLIDATION') return 2;
  if (row.TREND === 'DOWNTREND') return 3;
  return 4;
}

function prudviReactionRank(row: PrudviStrategyRow): number {
  if (row.SUPPORT_REVERSAL === 'Y') return 0;
  if (row.SUPPORT_REACTION === 'BOUNCE') return 1;
  if (row.SUPPORT_REACTION === 'HOLDING') return 2;
  if (row.SUPPORT_REACTION === 'BREAKDOWN') return 3;
  return 4;
}

export function prioritizePrudviRowsForDisplay(rows: PrudviStrategyRow[]): PrudviStrategyRow[] {
  return [...rows].sort((left, right) => {
    const trendRank = prudviDisplayRank(left) - prudviDisplayRank(right);
    if (trendRank !== 0) return trendRank;
    const reactionRank = prudviReactionRank(left) - prudviReactionRank(right);
    if (reactionRank !== 0) return reactionRank;
    const scoreRank = right.TREND_SCORE - left.TREND_SCORE;
    if (scoreRank !== 0) return scoreRank;
    return left.SYMBOL.localeCompare(right.SYMBOL);
  });
}

export function formatPrudviCell(row: PrudviStrategyRow, key: PrudviColumnKey): string {
  if (key === 'MCAP') return formatMarketCapValue(row.MCAP);
  if (key === 'MCAP_RANK') return formatMarketCapRankValue(row.MCAP_RANK);
  if (key === 'ATH' || key === 'PRICE') return formatNumber(row[key]);
  if (key === 'GAP') {
    if (!Number.isFinite(row.GAP)) return '-';
    const value = row.GAP as number;
    return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
  }
  return String(row[key] ?? '-') || '-';
}

export function prudviScoreTone(score: number): 'green' | 'amber' | 'blue' | 'muted' {
  if (score >= 80) return 'green';
  if (score >= 65) return 'amber';
  if (score >= 50) return 'blue';
  return 'muted';
}
