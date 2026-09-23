export type StrongUptrendSignal = 'STRONG_BUY_SETUP' | 'WATCHLIST' | 'WEAK_SETUP' | 'AVOID';

export type StrongUptrendReversalRow = {
  SYMBOL: string;
  INDEX: string;
  MCAP: number | null;
  MCAP_RANK: number | null;
  TRADING_DATE: string | null;
  CLOSE: number | null;
  EMA20: number | null;
  EMA50: number | null;
  EMA100: number | null;
  EMA200: number | null;
  RSI14: number | null;
  MACD: number | null;
  MACD_HIST: number | null;
  ADX14: number | null;
  PLUS_DI: number | null;
  MINUS_DI: number | null;
  VOLUME: number | null;
  VOLUME_SMA20: number | null;
  DELIVERY_PCT: number | null;
  HH_HL_STRUCTURE: boolean;
  SUPPORT_CONFIRMED: boolean;
  BULLISH_REVERSAL_CANDLE: boolean;
  BREAKOUT_OK: boolean;
  SCORE: number;
  SIGNAL: StrongUptrendSignal;
  ENTRY_TRIGGER: boolean;
  ENTRY_PRICE: number | null;
  STOP_LOSS: number | null;
  TARGET_1: number | null;
  TARGET_2: number | null;
  REJECT_REASON: string;
};

export type StrongUptrendReversalMeta = {
  tradingDate: string | null;
  rows: number;
  cacheState?: 'HIT' | 'MISS' | string;
  durationMs?: number;
  symbolUniverse?: number;
  refreshing?: boolean;
  stale?: boolean;
  deliveryHits?: number;
  deliveryMissing?: number;
  oracleLoadMs?: number;
  deliveryLoadMs?: number;
  computeMs?: number;
};

export type StrongUptrendReversalPayload = {
  rows: StrongUptrendReversalRow[];
  status: string;
  error: string;
  meta: StrongUptrendReversalMeta;
};

export type StrongUptrendReversalFilters = {
  entryTriggerOnly: boolean;
  minimumScore: string;
  search: string;
  signal: 'ALL' | StrongUptrendSignal;
  strongBuyOnly: boolean;
};
