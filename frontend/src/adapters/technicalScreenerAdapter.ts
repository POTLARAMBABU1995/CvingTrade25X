import type {
  TechnicalScreenerKind,
  TechnicalScreenerPayloadWire,
  TechnicalScreenerWireRow,
  TechnicalTimeframe,
} from '../types/api/technical';
import {
  firstPresentValue,
  formatMarketCapRankValue,
  formatMarketCapValue,
  getMarketCapCategory,
  normalizeMarketCapIndex,
  MARKET_CAP_INDEX_ALIASES,
  MARKET_CAP_RANK_ALIASES,
  MARKET_CAP_VALUE_ALIASES,
  toNumber,
} from './technicalMarketCap';
import { normalizeLatestDateKey, normalizeTimeframe } from './technicalEmaAdapter';

export type TechnicalScreenerColumnDef = {
  key: string;
  label: string;
  sortKey?: string;
  sortType: 'date' | 'number' | 'string';
};

export type TechnicalScreenerSummaryCard = {
  key: string;
  label: string;
};

export type TechnicalScreenerPageConfig = {
  activeTechnicalPage: string;
  columns: TechnicalScreenerColumnDef[];
  defaultSort: string;
  defaultSortDir: 'asc' | 'desc';
  emptyMessage: string;
  endpoint: string;
  fileName: string;
  kind: TechnicalScreenerKind;
  pageSize: number;
  summaryCards: TechnicalScreenerSummaryCard[];
  title: string;
  breakoutStatusOptions?: string[];
  initialForceRefresh?: boolean;
  patternOptions?: string[];
  trendlineStatusOptions?: string[];
};

export type TechnicalScreenerViewCell = {
  sort: number | string | null;
  text: string;
  title?: string;
  tone?: 'large' | 'mid' | 'negative' | 'positive' | 'small' | 'unknown';
};

export type TechnicalScreenerViewRow = {
  cells: Record<string, TechnicalScreenerViewCell>;
  id: string;
  raw: TechnicalScreenerWireRow;
  symbol: string;
};

export type TechnicalScreenerViewPayload = {
  cached?: boolean;
  cachedAt?: string | null;
  count: number;
  fallback?: boolean;
  latestLtcDateKey: string | null;
  page: number;
  refreshing?: boolean;
  rows: TechnicalScreenerViewRow[];
  stale?: boolean;
  summary: Record<string, unknown>;
  timeframe: TechnicalTimeframe;
  total: number;
  totalPages: number;
};

const MARKET_COLUMNS: TechnicalScreenerColumnDef[] = [
  { key: 'sNo', label: 'S.NO', sortType: 'number' },
  { key: 'symbol', label: 'SYMBOL', sortType: 'string' },
  { key: 'index', label: 'INDEX', sortType: 'string' },
  { key: 'mcap', label: 'MCAP', sortType: 'number' },
  { key: 'mcapRank', label: 'MCAP_RANK', sortType: 'number' },
  { key: 'price', label: 'PRICE', sortType: 'number' },
  { key: 'ltcDate', label: 'LTC_DATE', sortType: 'date' },
];

const PRICE_ACTION_MARKET_COLUMNS: TechnicalScreenerColumnDef[] = [
  { key: 'sNo', label: 'S.NO', sortType: 'number' },
  { key: 'symbol', label: 'SYMBOL', sortType: 'string' },
  { key: 'index', label: 'INDEX', sortType: 'string' },
  { key: 'mcap', label: 'MCAP', sortType: 'number' },
  { key: 'mcapRank', label: 'MCAP_RANK', sortType: 'number' },
  { key: 'price', label: 'PRICE', sortType: 'number' },
  { key: 'ath', label: 'ATH', sortType: 'number' },
  { key: 'gap', label: 'GAP', sortType: 'number' },
  { key: 'ltcDate', label: 'LTC_DATE', sortType: 'date' },
];

export const TECHNICAL_SCREENER_CONFIGS = {
  breakout: {
    activeTechnicalPage: '/app/technical/breakout',
    breakoutStatusOptions: [
      'Resistance Breakout',
      'Volume Confirmed Breakout',
      'Retest Success',
      'Near Breakout',
      'ATH Breakout',
      'Failed Breakout',
      'No Breakout',
    ],
    columns: [
      ...MARKET_COLUMNS,
      { key: 'breakoutStatus', label: 'BREAKOUT_STATUS', sortType: 'string' },
      { key: 'breakoutType', label: 'BREAKOUT_TYPE', sortType: 'string' },
      { key: 'breakoutLevel', label: 'BREAKOUT_LEVEL', sortType: 'number' },
      { key: 'resistance', label: 'RESISTANCE', sortType: 'number' },
      { key: 'volumeRatio', label: 'VOLUME_RATIO', sortType: 'number' },
      { key: 'closePositionPct', label: 'CLOSE_POSITION_%', sortType: 'number' },
      { key: 'breakoutScore', label: 'BREAKOUT_SCORE', sortType: 'number' },
      { key: 'riskLevel', label: 'RISK_LEVEL', sortType: 'string' },
    ],
    defaultSort: 'breakoutScore',
    defaultSortDir: 'desc',
    emptyMessage: 'No breakout rows found for selected filters.',
    endpoint: '/api/technicals/breakout',
    fileName: 'Breakout',
    initialForceRefresh: false,
    kind: 'breakout',
    pageSize: 25,
    summaryCards: [
      { key: 'totalSymbols', label: 'Total Symbols' },
      { key: 'freshBreakouts', label: 'Fresh Breakouts' },
      { key: 'confirmedBreakouts', label: 'Confirmed Breakouts' },
      { key: 'retestSuccess', label: 'Retest Success' },
      { key: 'nearBreakout', label: 'Near Breakout' },
      { key: 'week52Breakouts', label: '52W Breakouts' },
      { key: 'athBreakouts', label: 'ATH Breakouts' },
      { key: 'failedBreakouts', label: 'Failed Breakouts' },
    ],
    title: 'Breakout Analysis',
  },
  chartPatterns: {
    activeTechnicalPage: '/app/technical/chart-patterns',
    columns: [
      ...MARKET_COLUMNS,
      { key: 'patternName', label: 'PATTERN_NAME', sortType: 'string' },
      { key: 'patternStatus', label: 'PATTERN_STATUS', sortType: 'string' },
      { key: 'confidenceScore', label: 'CONFIDENCE_SCORE', sortType: 'number' },
      { key: 'breakoutLevel', label: 'BREAKOUT_LEVEL', sortType: 'number' },
      { key: 'support', label: 'SUPPORT', sortType: 'number' },
      { key: 'resistance', label: 'RESISTANCE', sortType: 'number' },
      { key: 'volumeConfirmation', label: 'VOLUME_CONFIRMATION', sortType: 'string' },
      { key: 'riskLevel', label: 'RISK_LEVEL', sortType: 'string' },
    ],
    defaultSort: 'chartPatternScore',
    defaultSortDir: 'desc',
    emptyMessage: 'No chart pattern rows found for selected filters.',
    endpoint: '/api/technicals/chart-patterns',
    fileName: 'ChartPatterns',
    kind: 'chartPatterns',
    pageSize: 25,
    patternOptions: [
      'Ascending Triangle',
      'Rectangle / Box Consolidation',
      'Bullish Flag',
      'Uptrend Channel',
      'Falling Wedge Breakout',
      'Cup and Handle',
      'Inverse Head and Shoulders',
    ],
    summaryCards: [
      { key: 'totalSymbols', label: 'Total Symbols' },
      { key: 'bullishPatterns', label: 'Bullish Patterns' },
      { key: 'ascendingTriangle', label: 'Ascending Triangle' },
      { key: 'rectangleBox', label: 'Rectangle / Box' },
      { key: 'bullishFlag', label: 'Bullish Flag' },
      { key: 'uptrendChannel', label: 'Uptrend Channel' },
      { key: 'fallingWedge', label: 'Falling Wedge' },
      { key: 'breakoutPatterns', label: 'Breakout Patterns' },
    ],
    title: 'Chart Pattern Analysis',
  },
  priceActionAnalysis: {
    activeTechnicalPage: '/app/technical/price-action-analysis',
    columns: [
      ...PRICE_ACTION_MARKET_COLUMNS,
      { key: 'trendStructure', label: 'TREND_STRUCTURE', sortType: 'string' },
      { key: 'lastSwingHigh', label: 'LAST_SWING_HIGH', sortType: 'number' },
      { key: 'lastSwingLow', label: 'LAST_SWING_LOW', sortType: 'number' },
      { key: 'hhHlStatus', label: 'HH_HL_STATUS', sortType: 'string' },
      { key: 'support', label: 'SUPPORT', sortType: 'number' },
      { key: 'resistance', label: 'RESISTANCE', sortType: 'number' },
      { key: 'srLevels', label: 'Support & Resistance', sortType: 'string' },
      { key: 'priceActionScore', label: 'PRICE_ACTION_SCORE', sortType: 'number' },
      { key: 'riskLevel', label: 'RISK_LEVEL', sortType: 'string' },
    ],
    defaultSort: 'priceActionScore',
    defaultSortDir: 'desc',
    emptyMessage: 'No price action rows found for selected filters.',
    endpoint: '/api/technicals/price-action',
    fileName: 'PriceActionAnalysis',
    kind: 'priceActionAnalysis',
    pageSize: 25,
    summaryCards: [
      { key: 'totalSymbols', label: 'Total Symbols' },
      { key: 'strongUptrend', label: 'Strong Uptrend' },
      { key: 'hhHlStructure', label: 'HH/HL Structure' },
      { key: 'accumulation', label: 'Accumulation' },
      { key: 'rangeBound', label: 'Range Bound' },
      { key: 'downtrend', label: 'Downtrend' },
      { key: 'nearSupport', label: 'Near Support' },
      { key: 'weakStructure', label: 'Weak Structure' },
    ],
    title: 'Price Action Analysis',
  },
  strongTechnicals: {
    activeTechnicalPage: '/app/technical/strong-technicals',
    breakoutStatusOptions: [
      'Resistance Breakout',
      'Volume Confirmed Breakout',
      'Retest Success',
      'Near Breakout',
      'Failed Breakout',
      'No Breakout',
    ],
    columns: [
      { key: 'sNo', label: 'S.NO', sortType: 'number' },
      { key: 'symbol', label: 'SYMBOL', sortType: 'string' },
      { key: 'index', label: 'INDEX', sortType: 'string' },
      { key: 'mcap', label: 'MCAP', sortType: 'number' },
      { key: 'mcapRank', label: 'MCAP_RANK', sortType: 'number' },
      { key: 'ath', label: 'ATH', sortType: 'number' },
      { key: 'support', label: 'SUPPORT', sortType: 'number' },
      { key: 'resistance', label: 'RESISTANCE', sortType: 'number' },
      { key: 'trendDirection', label: 'TREND_DIRECTION', sortType: 'string' },
      { key: 'ema20', label: 'EMA20', sortType: 'number' },
      { key: 'ema50', label: 'EMA50', sortType: 'number' },
      { key: 'ema100', label: 'EMA100', sortType: 'number' },
      { key: 'ema200', label: 'EMA200', sortType: 'number' },
      { key: 'macdGt0', label: 'MACD>0', sortType: 'string' },
      { key: 'rsiGt50', label: 'RSI>50', sortType: 'string' },
      { key: 'adxGt25', label: 'ADX>25', sortType: 'string' },
      { key: 'atrGt14', label: 'ATR>14', sortType: 'string' },
      { key: 'score', label: 'Score', sortType: 'number' },
      { key: 'price', label: 'PRICE', sortType: 'number' },
      { key: 'ltcDate', label: 'LTC_DATE', sortType: 'date' },
      { key: 'techScore', label: 'TECH_SCORE', sortType: 'number' },
      { key: 'techStatus', label: 'TECH_STATUS', sortType: 'string' },
      { key: 'trendStructure', label: 'TREND_STRUCTURE', sortType: 'string' },
      { key: 'emaAlignment', label: 'EMA_ALIGNMENT', sortType: 'string' },
      { key: 'trendlineStatus', label: 'TRENDLINE_STATUS', sortType: 'string' },
      { key: 'patternName', label: 'PATTERN_NAME', sortType: 'string' },
      { key: 'breakoutStatus', label: 'BREAKOUT_STATUS', sortType: 'string' },
      { key: 'volumeRatio', label: 'VOLUME_RATIO', sortType: 'number' },
      { key: 'deliveryScore', label: 'DELIVERY_SCORE', sortType: 'number' },
      { key: 'riskLevel', label: 'RISK_LEVEL', sortType: 'string' },
      { key: 'nearestSupport', label: 'NEAREST_SUPPORT', sortType: 'number' },
      { key: 'nearestResistance', label: 'NEAREST_RESISTANCE', sortType: 'number' },
      { key: 'invalidationLevel', label: 'INVALIDATION_LEVEL', sortType: 'number' },
    ],
    defaultSort: 'techScoreSort',
    defaultSortDir: 'desc',
    emptyMessage: 'No strong technical rows found for selected filters.',
    endpoint: '/api/technicals/strong',
    fileName: 'StrongTechnicals',
    kind: 'strongTechnicals',
    pageSize: 25,
    patternOptions: [
      'Ascending Triangle',
      'Rectangle / Box Consolidation',
      'Bullish Flag',
      'Uptrend Channel',
      'Falling Wedge Breakout',
      'Cup and Handle',
      'Inverse Head and Shoulders',
    ],
    summaryCards: [
      { key: 'totalSymbols', label: 'Total Symbols' },
      { key: 'veryStrongTechnicals', label: 'Very Strong Technicals' },
      { key: 'strongTechnicals', label: 'Strong Technicals' },
      { key: 'freshBreakouts', label: 'Fresh Breakouts' },
      { key: 'trendlineSupport', label: 'Trendline Support' },
      { key: 'bullishPatterns', label: 'Bullish Patterns' },
      { key: 'volumeConfirmed', label: 'Volume Confirmed' },
      { key: 'highRiskAvoid', label: 'High Risk / Avoid' },
    ],
    title: 'Strong Technicals',
    trendlineStatusOptions: [
      'Strong Support Trendline',
      'Near Trendline Support',
      'Trendline Break Risk',
      'Trendline Broken',
      'No Clean Trendline',
    ],
  },
  trendline: {
    activeTechnicalPage: '/app/technical/trendline',
    columns: [
      ...PRICE_ACTION_MARKET_COLUMNS,
      { key: 'trendlineStatus', label: 'TRENDLINE_STATUS', sortType: 'string' },
      { key: 'trendlineType', label: 'TRENDLINE_TYPE', sortType: 'string' },
      { key: 'slope', label: 'SLOPE', sortType: 'number' },
      { key: 'touchCount', label: 'TOUCH_COUNT', sortType: 'number' },
      { key: 'distanceFromTrendlinePct', label: 'DISTANCE_FROM_TRENDLINE_%', sortType: 'number' },
      { key: 'support', label: 'SUPPORT', sortType: 'number' },
      { key: 'invalidationLevel', label: 'INVALIDATION_LEVEL', sortType: 'number' },
      { key: 'trendlineScore', label: 'TRENDLINE_SCORE', sortType: 'number' },
    ],
    defaultSort: 'trendlineScore',
    defaultSortDir: 'desc',
    emptyMessage: 'No trendline rows found for selected filters.',
    endpoint: '/api/technicals/trendline',
    fileName: 'Trendline',
    initialForceRefresh: false,
    kind: 'trendline',
    pageSize: 25,
    summaryCards: [
      { key: 'totalSymbols', label: 'Total Symbols' },
      { key: 'strongSupportTrendline', label: 'Strong Support Trendline' },
      { key: 'nearTrendlineSupport', label: 'Near Trendline Support' },
      { key: 'trendlineBreakRisk', label: 'Trendline Break Risk' },
      { key: 'trendlineBroken', label: 'Trendline Broken' },
      { key: 'positiveSlope', label: 'Positive Slope' },
      { key: 'touch3Trendlines', label: '3+ Touch Trendlines' },
      { key: 'noCleanTrendline', label: 'No Clean Trendline' },
    ],
    title: 'Trendline Analysis',
    trendlineStatusOptions: [
      'Strong Support Trendline',
      'Near Trendline Support',
      'Trendline Break Risk',
      'Trendline Broken',
      'No Clean Trendline',
    ],
  },
} satisfies Record<TechnicalScreenerKind, TechnicalScreenerPageConfig>;

const FIELD_ALIASES: Record<string, string[]> = {
  adxGt25: ['adxGt25', 'ADX_GT_25', 'ADX>25', 'adx_gt_25'],
  atrGt14: ['atrGt14', 'ATR_GT_14', 'ATR>14', 'atr_gt_14'],
  ath: ['ath', 'ATH', 'athSort', 'ATH_SORT', 'allTimeHigh', 'ALL_TIME_HIGH'],
  breakoutLevel: ['breakoutLevel', 'BREAKOUT_LEVEL', 'breakout_level'],
  breakoutScore: ['breakoutScore', 'BREAKOUT_SCORE', 'score', 'SCORE'],
  breakoutStatus: ['breakoutStatus', 'BREAKOUT_STATUS', 'breakout_status'],
  breakoutType: ['breakoutType', 'BREAKOUT_TYPE', 'breakout_type'],
  chartPatternScore: ['chartPatternScore', 'CHART_PATTERN_SCORE', 'confidenceScore', 'CONFIDENCE_SCORE', 'score', 'SCORE'],
  closePositionPct: ['closePositionPct', 'CLOSE_POSITION_PCT', 'CLOSE_POSITION_%', 'close_position_pct'],
  confidenceScore: ['confidenceScore', 'CONFIDENCE_SCORE', 'chartPatternScore', 'CHART_PATTERN_SCORE', 'score', 'SCORE'],
  deliveryScore: ['delivery_score', 'DELIVERY_SCORE', 'deliveryScore', 'del_score', 'DEL_SCORE', 'delivery_strength_score', 'DELIVERY_STRENGTH_SCORE'],
  distanceFromTrendlinePct: ['distanceFromTrendlinePct', 'DISTANCE_FROM_TRENDLINE_PCT', 'DISTANCE_FROM_TRENDLINE_%', 'distance_from_trendline_pct'],
  ema20: ['ema20', 'EMA20', 'EMA_20'],
  ema50: ['ema50', 'EMA50', 'EMA_50'],
  ema100: ['ema100', 'EMA100', 'EMA_100'],
  ema200: ['ema200', 'EMA200', 'EMA_200'],
  emaAlignment: ['emaAlignment', 'EMA_ALIGNMENT', 'ema_alignment'],
  gap: ['gap', 'GAP'],
  hhHlStatus: ['hhHlStatus', 'HH_HL_STATUS', 'hh_hl_status'],
  index: ['INDEX', 'index', 'marketCapIndex', 'market_cap_index'],
  invalidationLevel: ['invalidationLevel', 'INVALIDATION_LEVEL', 'invalidation_level'],
  lastSwingHigh: ['lastSwingHigh', 'LAST_SWING_HIGH', 'last_swing_high'],
  lastSwingLow: ['lastSwingLow', 'LAST_SWING_LOW', 'last_swing_low'],
  ltcDate: ['ltcDate', 'LTC_DATE', 'trading_date', 'TRADING_DATE', 'date', 'DATE'],
  macdGt0: ['macdGt0', 'MACD_GT_0', 'MACD>0', 'macd_gt_0'],
  mcap: MARKET_CAP_VALUE_ALIASES,
  mcapRank: MARKET_CAP_RANK_ALIASES,
  price: ['price', 'PRICE', 'close', 'CLOSE', 'close_price', 'CLOSE_PRICE', 'current_price', 'CURRENT_PRICE', 'ltp', 'LTP'],
  priceActionScore: ['priceActionScore', 'PRICE_ACTION_SCORE', 'score', 'SCORE'],
  patternName: ['patternName', 'PATTERN_NAME', 'pattern_name'],
  patternStatus: ['patternStatus', 'PATTERN_STATUS', 'pattern_status'],
  resistance: ['resistance', 'RESISTANCE', 'nearestResistance', 'NEAREST_RESISTANCE'],
  riskLevel: ['riskLevel', 'RISK_LEVEL', 'risk_level'],
  rsiGt50: ['rsiGt50', 'RSI_GT_50', 'RSI>50', 'rsi_gt_50'],
  score: ['score', 'SCORE', 'scoreSort', 'SCORE_SORT', 'techScore', 'TECH_SCORE', 'techScoreSort', 'TECH_SCORE_SORT'],
  slope: ['slope', 'SLOPE', 'trendlineSlope', 'TRENDLINE_SLOPE'],
  srLevels: ['sr_levels', 'SR_LEVELS', 'srLevels', 'sr_level', 'SR_LEVEL', 'supportResistance'],
  support: ['support', 'SUPPORT', 'nearestSupport', 'NEAREST_SUPPORT'],
  symbol: ['symbol', 'SYMBOL', 'stock', 'ticker'],
  techScore: ['techScore', 'TECH_SCORE', 'score', 'SCORE'],
  techScoreSort: ['techScoreSort', 'TECH_SCORE_SORT', 'techScore', 'TECH_SCORE', 'score', 'SCORE'],
  techStatus: ['techStatus', 'TECH_STATUS', 'tech_status'],
  touchCount: ['touchCount', 'TOUCH_COUNT', 'trendlineTouchCount', 'TRENDLINE_TOUCH_COUNT'],
  trendlineScore: ['trendlineScore', 'TRENDLINE_SCORE', 'score', 'SCORE'],
  trendlineStatus: ['trendlineStatus', 'TRENDLINE_STATUS', 'trendline_status'],
  trendlineType: ['trendlineType', 'TRENDLINE_TYPE', 'trendline_type'],
  trendStructure: ['trendStructure', 'TREND_STRUCTURE', 'trend_structure'],
  trendDirection: ['trendDirection', 'TREND_DIRECTION', 'trend_direction', 'Trend_Direction'],
  volumeConfirmation: ['volumeConfirmation', 'VOLUME_CONFIRMATION', 'volume_confirmation'],
  volumeRatio: ['volumeRatio', 'VOLUME_RATIO', 'volume_ratio'],
  nearestSupport: ['nearestSupport', 'NEAREST_SUPPORT', 'support', 'SUPPORT'],
  nearestResistance: ['nearestResistance', 'NEAREST_RESISTANCE', 'resistance', 'RESISTANCE'],
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object';
}

function firstValue(row: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    const value = row[key];
    if (value === undefined || value === null) continue;
    if (String(value).trim() === '') continue;
    return value;
  }
  return null;
}

function numberValue(value: unknown): number | null {
  return toNumber(value);
}

function formatNumber(value: number): string {
  return value.toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function formatFixedNumber(value: number): string {
  return Number.isInteger(value)
    ? value.toLocaleString('en-IN')
    : value.toLocaleString('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: 2 });
}

function toneFromNumber(value: number | null): TechnicalScreenerViewCell['tone'] {
  if (!Number.isFinite(value)) return undefined;
  if ((value as number) > 0) return 'positive';
  if ((value as number) < 0) return 'negative';
  return undefined;
}

function textValue(value: unknown): string {
  if (value === undefined || value === null || String(value).trim() === '') return '-';
  if (Array.isArray(value)) return value.length ? value.join(', ') : '-';
  if (typeof value === 'number') return Number.isFinite(value) ? formatNumber(value) : '-';
  return String(value);
}

function normalizedIndex(value: unknown): string {
  return normalizeMarketCapIndex(value);
}

function cellForKey(
  source: Record<string, unknown>,
  key: string,
  fallbackIndex: number,
  column: TechnicalScreenerColumnDef,
): TechnicalScreenerViewCell {
  if (key === 'sNo') return { text: String(fallbackIndex), sort: fallbackIndex };
  const raw = firstValue(source, FIELD_ALIASES[key] ?? [key, key.toUpperCase()]);
  if (key === 'index') {
    const text = normalizedIndex(raw);
    return { text, sort: text, tone: getMarketCapCategory(raw) };
  }
  if (key === 'symbol') {
    const text = textValue(raw);
    return { text, sort: text, tone: getMarketCapCategory(firstPresentValue(source, FIELD_ALIASES.index)) };
  }
  if (column.sortType === 'number') {
    const sort = numberValue(firstValue(source, [`${key}Sort`, `${key.toUpperCase()}_SORT`, ...(FIELD_ALIASES[key] ?? [])])) ?? numberValue(raw);
    if (key === 'mcap') {
      return { text: formatMarketCapValue(raw), sort, tone: getMarketCapCategory(firstPresentValue(source, FIELD_ALIASES.index)) };
    }
    if (key === 'mcapRank') {
      return { text: formatMarketCapRankValue(raw), sort, tone: getMarketCapCategory(firstPresentValue(source, FIELD_ALIASES.index)) };
    }
    if (key === 'ath') {
      const athDate = firstValue(source, ['ath_date', 'athDate', 'ATH_DATE']);
      return {
        text: sort === null ? textValue(raw) : formatFixedNumber(sort),
        sort,
        title: athDate ? `ATH Date: ${String(athDate)}` : undefined,
      };
    }
    if (key === 'gap') {
      const price = numberValue(firstValue(source, ['priceSort', 'PRICE_SORT', ...(FIELD_ALIASES.price ?? [])]));
      const ath = numberValue(firstValue(source, ['athSort', 'ATH_SORT', ...(FIELD_ALIASES.ath ?? [])]));
      const computed = sort ?? (price !== null && ath !== null && ath !== 0 ? ((price - ath) / ath) * 100 : null);
      return {
        text: computed === null ? textValue(raw) : `${computed > 0 ? '+' : ''}${computed.toFixed(2)}%`,
        sort: computed,
        tone: toneFromNumber(computed),
      };
    }
    return { text: sort === null ? textValue(raw) : formatNumber(sort), sort };
  }
  return { text: textValue(raw), sort: raw === null ? null : String(raw) };
}

function ensureRows(value: unknown): TechnicalScreenerWireRow[] {
  return Array.isArray(value) ? value.filter(isRecord) as TechnicalScreenerWireRow[] : [];
}

function numericMeta(value: unknown, fallback: number): number {
  const parsed = numberValue(value);
  return parsed === null ? fallback : parsed;
}

function latestDateFromRows(rows: TechnicalScreenerWireRow[]): string | null {
  let latestKey: string | null = null;
  rows.forEach((row) => {
    const source = row as Record<string, unknown>;
    const candidate = firstValue(source, [
      'ltcDate',
      'LTC_DATE',
      'ltc_date',
      'latestTradingDate',
      'latest_trade_date',
      'tradingDateMax',
      'TRADING_DATE',
      'tradingDate',
      'trading_date',
    ]);
    const key = normalizeLatestDateKey(candidate);
    if (key && (!latestKey || key > latestKey)) {
      latestKey = key;
    }
  });
  return latestKey;
}

export function adaptTechnicalScreenerRow(
  row: TechnicalScreenerWireRow,
  rowIndex: number,
  page: number,
  pageSize: number,
  config: TechnicalScreenerPageConfig,
): TechnicalScreenerViewRow {
  const source = row as Record<string, unknown>;
  const absoluteIndex = ((page - 1) * pageSize) + rowIndex + 1;
  const cells: Record<string, TechnicalScreenerViewCell> = {};

  config.columns.forEach((column) => {
    cells[column.key] = cellForKey(source, column.key, absoluteIndex, column);
  });

  const symbol = cells.symbol?.text === '-' ? '' : cells.symbol.text;
  return {
    cells,
    id: `${symbol || 'row'}-${absoluteIndex}`,
    raw: row,
    symbol,
  };
}

export function adaptTechnicalScreenerPayload(
  payload: TechnicalScreenerPayloadWire | null | undefined,
  config: TechnicalScreenerPageConfig,
  currentPage: number,
  pageSize: number,
): TechnicalScreenerViewPayload {
  const source: Record<string, unknown> = payload && isRecord(payload) ? payload : {};
  const page = numericMeta(source.page, currentPage);
  const rawRows = ensureRows(source.rows);
  const rows = rawRows.map((row, index) => adaptTechnicalScreenerRow(row, index, page, pageSize, config));
  const total = numericMeta(source.total ?? source.count, rows.length);
  const totalPages = Math.max(1, numericMeta(source.total_pages ?? source.totalPages, Math.ceil(total / pageSize) || 1));
  const summary = isRecord(source.summary) ? source.summary : {};
  const meta = isRecord(source.meta) ? source.meta : {};
  const latestLtcDateKey = normalizeLatestDateKey(
    firstValue(meta, ['latestTradingDate', 'latest_trade_date', 'LTC_DATE', 'ltc_date']),
  ) ?? latestDateFromRows(rawRows);

  return {
    cached: Boolean(source.cached),
    cachedAt: typeof source.cachedAt === 'string' ? source.cachedAt : null,
    count: numericMeta(source.count, rows.length),
    fallback: Boolean(source.fallback),
    latestLtcDateKey,
    page,
    refreshing: Boolean(source.refreshing),
    rows,
    stale: Boolean(source.stale),
    summary,
    timeframe: normalizeTimeframe(source.timeframe),
    total,
    totalPages,
  };
}
