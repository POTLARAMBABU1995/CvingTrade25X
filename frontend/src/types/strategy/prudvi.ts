export type PrudviFlag = 'Y' | 'N' | '-';
export type PrudviTrend = 'UPTREND' | 'DOWNTREND' | 'CONSOLIDATION' | '-';
export type PrudviSupportReaction = 'BOUNCE' | 'BREAKDOWN' | 'HOLDING' | 'NO_REACTION' | '-';
export type PrudviCandleDirection = 'BULLISH' | 'BEARISH' | 'NEUTRAL' | '-';

export type PrudviStrategyRow = {
  S_NO: number;
  SYMBOL: string;
  INDEX: string;
  MCAP: number | null;
  MCAP_RANK: number | null;
  ATH: number | null;
  PRICE: number | null;
  GAP: number | null;
  LTC_DATE: string;
  SUPPORT: string;
  RESISTANCE: string;
  SUPPORT_REACTION: PrudviSupportReaction;
  SUPPORT_CANDLE: string;
  CANDLE_DIRECTION: PrudviCandleDirection;
  SUPPORT_REVERSAL: PrudviFlag;
  BULLISH_CANDLE: PrudviFlag;
  EMA_GT_20: PrudviFlag;
  EMA_GT_50: PrudviFlag;
  RSI_GT_50: PrudviFlag;
  ADX_GT_25: PrudviFlag;
  MACD_GT_0: PrudviFlag;
  VOLUME_GT_20: PrudviFlag;
  DELIVERY_GT_60: PrudviFlag;
  TREND: PrudviTrend;
  TREND_SCORE: number;
};

export type PrudviStrategyMeta = {
  cacheState?: string;
  computeMs?: number;
  durationMs?: number;
  manualSrSymbols?: number;
  refreshing?: boolean;
  rows: number;
  stale?: boolean;
  tradingDate: string | null;
};

export type PrudviStrategyPayload = {
  error?: string;
  meta: PrudviStrategyMeta;
  rows: PrudviStrategyRow[];
  status: string;
};

export type PrudviTrendFilter = 'ALL' | PrudviTrend;

export type PrudviStrategyFilters = {
  minimumScore: string;
  search: string;
  trend: PrudviTrendFilter;
};
