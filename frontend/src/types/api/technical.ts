export type TechnicalTimeframe = 'daily' | 'weekly' | 'monthly' | 'yearly';
export type TechnicalIndicatorKind = 'adx' | 'atr14' | 'macd' | 'rsi50' | 'volume';
export type TechnicalScreenerKind = 'breakout' | 'chartPatterns' | 'priceActionAnalysis' | 'strongTechnicals' | 'trendline';

export type EmaTrendTableKey =
  | 'ema20'
  | 'ema50'
  | 'ema5020'
  | 'ema100'
  | 'ema200'
  | 'ema200100'
  | 'ema20010050'
  | 'ema2001005020';

export type LegacyTechnicalPayloadMeta = {
  cutoffMonths?: number;
  baseCutoffMonths?: number;
  timeframe?: TechnicalTimeframe;
  startDate?: string | null;
  endDate?: string | null;
  schemaVersion?: number | string;
  [key: string]: unknown;
};

export type LegacyTechnicalPayload<Row> = {
  rows: Row[];
  count: number;
  cachedAt?: string;
  meta?: LegacyTechnicalPayloadMeta;
  timeframe?: TechnicalTimeframe;
  cached?: boolean;
  refreshing?: boolean;
  stale?: boolean;
  fallback?: boolean;
  [key: string]: unknown;
};

export type TechnicalScreenerWireRow = {
  SYMBOL?: string;
  symbol?: string;
  COMPANY_NAME?: string | null;
  companyName?: string | null;
  INDEX?: string | null;
  MCAP?: number | string | null;
  MCAP_RANK?: number | string | null;
  LTC_DATE?: string | null;
  ltcDate?: string | null;
  TRADING_DATE?: string | null;
  tradingDate?: string | null;
  PRICE?: number | string | null;
  price?: number | string | null;
  CHANGE?: number | string | null;
  CHANGE_PCT?: number | string | null;
  VOLUME?: number | string | null;
  [key: string]: unknown;
};

export type EmaTrendWireRow = TechnicalScreenerWireRow & {
  sNo?: number | string | null;
  S_NO?: number | string | null;
  stock?: string | null;
  ticker?: string | null;
  name?: string | null;
  ATH?: number | string | null;
  ath?: number | string | null;
  ATH_SORT?: number | string | null;
  athSort?: number | string | null;
  ATH_DATE?: string | null;
  athDate?: string | null;
  ath_date?: string | null;
  GAP?: number | string | null;
  gap?: number | string | null;
  GAP_SORT?: number | string | null;
  gapSort?: number | string | null;
  tradingDays?: number | string | null;
  TRADING_DAYS?: number | string | null;
  calendarDays?: number | string | null;
  ltcDateSort?: number | string | null;
  LTC_DATE_SORT?: number | string | null;
  tradingDateSort?: number | string | null;
  TRADING_DATE_SORT?: number | string | null;
  d5?: number | string | null;
  d10?: number | string | null;
  d15?: number | string | null;
  d22?: number | string | null;
  d44?: number | string | null;
  d66?: number | string | null;
  d88?: number | string | null;
  d132?: number | string | null;
  d198?: number | string | null;
  y1?: number | string | null;
  y2?: number | string | null;
  y3?: number | string | null;
  y4?: number | string | null;
  y5?: number | string | null;
  y6?: number | string | null;
  y7?: number | string | null;
  y8?: number | string | null;
  y9?: number | string | null;
  y10?: number | string | null;
  y15?: number | string | null;
  y20?: number | string | null;
  y25?: number | string | null;
  y26?: number | string | null;
  y27?: number | string | null;
  [key: string]: unknown;
};

export type EmaTrendPayloadWire = Partial<Record<EmaTrendTableKey, EmaTrendWireRow[]>> & {
  cachedAt?: string | null;
  timeframe?: TechnicalTimeframe | string | null;
  athSource?: string | null;
  totalSymbols?: number | string | null;
  total_symbols?: number | string | null;
  returnColumns?: Array<string | Record<string, unknown>> | null;
  returnSchemaVersion?: number | string | null;
  yearReturnColumns?: Array<string | Record<string, unknown>> | null;
  yearReturnMaxYear?: number | string | null;
  cached?: boolean;
  refreshing?: boolean;
  stale?: boolean;
  fallback?: boolean;
  meta?: LegacyTechnicalPayloadMeta;
  summary?: {
    totalSymbols?: number | string | null;
    total_symbols?: number | string | null;
    [key: string]: unknown;
  } | null;
  [key: string]: unknown;
};

export type TrendTradingDaysPayloadWire = {
  rows?: EmaTrendWireRow[] | null;
  count?: number | string | null;
  timeframe?: TechnicalTimeframe | string | null;
  cachedAt?: string | null;
  queryMs?: number | string | null;
  cached?: boolean;
  refreshing?: boolean;
};

export type TrendLatestDateWireResponse = {
  ltc_date: string | null;
  ltcDate?: string | null;
  LTC_DATE?: string | null;
};

export type TrendPingWireResponse = {
  status?: string;
  ok?: boolean;
  message?: string;
  [key: string]: unknown;
};

export type TechnicalIndicatorScreenWireRow = TechnicalScreenerWireRow & {
  sNo?: number | string | null;
  S_NO?: number | string | null;
  stock?: string | null;
  ticker?: string | null;
  priceSort?: number | string | null;
  PRICE_SORT?: number | string | null;
  tradingDays?: number | string | null;
  TRADING_DAYS?: number | string | null;
  trading_days?: number | string | null;
  tradingDaysSort?: number | string | null;
  TRADING_DAYS_SORT?: number | string | null;
  td?: number | string | null;
  T_D?: number | string | null;
  tdSort?: number | string | null;
  ltcDateSort?: number | string | null;
  LTC_DATE_SORT?: number | string | null;
  ltc_date_sort?: number | string | null;
  tradingDateSort?: number | string | null;
  TRADING_DATE_SORT?: number | string | null;
  trading_date_sort?: number | string | null;
  rsi?: number | string | null;
  RSI?: number | string | null;
  rsiScore?: number | string | null;
  RSI_SCORE?: number | string | null;
  macdScore?: number | string | null;
  MACD_SCORE?: number | string | null;
  macdScoreSort?: number | string | null;
  MACD_SCORE_SORT?: number | string | null;
  atr?: number | string | null;
  ATR?: number | string | null;
  atrScore?: number | string | null;
  ATR_SCORE?: number | string | null;
  atrScoreSort?: number | string | null;
  ATR_SCORE_SORT?: number | string | null;
  adxGt20?: number | string | null;
  ADX_GT20?: number | string | null;
  adxGt20Sort?: number | string | null;
  ADX_GT20_SORT?: number | string | null;
  adxGt25?: number | string | null;
  ADX_GT25?: number | string | null;
  adxGt25Sort?: number | string | null;
  ADX_GT25_SORT?: number | string | null;
  plusDm?: number | string | null;
  PLUS_DM?: number | string | null;
  plusDmSort?: number | string | null;
  PLUS_DM_SORT?: number | string | null;
  minusDm?: number | string | null;
  MINUS_DM?: number | string | null;
  minusDmSort?: number | string | null;
  MINUS_DM_SORT?: number | string | null;
  adxScore?: number | string | null;
  ADX_SCORE?: number | string | null;
  adxScoreSort?: number | string | null;
  ADX_SCORE_SORT?: number | string | null;
  adxValue?: number | string | null;
  ADX_VALUE?: number | string | null;
  adxValueSort?: number | string | null;
  ADX_VALUE_SORT?: number | string | null;
  volume?: number | string | null;
  VOLUME?: number | string | null;
  volumeAvg20?: number | string | null;
  VOLUME_AVG20?: number | string | null;
  volumeAvg20Sort?: number | string | null;
  VOLUME_AVG20_SORT?: number | string | null;
  volumeRatio?: number | string | null;
  VOLUME_RATIO?: number | string | null;
  volumeRatioSort?: number | string | null;
  VOLUME_RATIO_SORT?: number | string | null;
  volumeScore?: number | string | null;
  VOLUME_SCORE?: number | string | null;
  volumeScoreSort?: number | string | null;
  VOLUME_SCORE_SORT?: number | string | null;
  d5?: number | string | null;
  d10?: number | string | null;
  d15?: number | string | null;
  d22?: number | string | null;
  d44?: number | string | null;
  d66?: number | string | null;
  d88?: number | string | null;
  d132?: number | string | null;
  d198?: number | string | null;
  y1?: number | string | null;
  y2?: number | string | null;
  y3?: number | string | null;
  y4?: number | string | null;
  y5?: number | string | null;
  y6?: number | string | null;
  y7?: number | string | null;
  y8?: number | string | null;
  y9?: number | string | null;
  y10?: number | string | null;
  y15?: number | string | null;
  y20?: number | string | null;
  y25?: number | string | null;
  d5Sort?: number | string | null;
  d10Sort?: number | string | null;
  d15Sort?: number | string | null;
  d22Sort?: number | string | null;
  d44Sort?: number | string | null;
  d66Sort?: number | string | null;
  d88Sort?: number | string | null;
  d132Sort?: number | string | null;
  d198Sort?: number | string | null;
  y1Sort?: number | string | null;
  y2Sort?: number | string | null;
  y3Sort?: number | string | null;
  y4Sort?: number | string | null;
  y5Sort?: number | string | null;
  y6Sort?: number | string | null;
  y7Sort?: number | string | null;
  y8Sort?: number | string | null;
  y9Sort?: number | string | null;
  y10Sort?: number | string | null;
  y15Sort?: number | string | null;
  y20Sort?: number | string | null;
  y25Sort?: number | string | null;
  [key: string]: unknown;
};

export type TechnicalIndicatorPayloadWire = LegacyTechnicalPayload<TechnicalIndicatorScreenWireRow>;

export type TechnicalScreenerPayloadWire = Omit<LegacyTechnicalPayload<TechnicalScreenerWireRow>, 'count' | 'rows'> & {
  count?: number | string | null;
  ok?: boolean;
  rows?: TechnicalScreenerWireRow[];
  total?: number | string | null;
  page?: number | string | null;
  page_size?: number | string | null;
  total_pages?: number | string | null;
  summary?: Record<string, unknown> | null;
};

export type PriceActionManualLevelWire = {
  level_id?: string | number | null;
  value?: string | number | null;
  created_at?: string | null;
  updated_at?: string | null;
  level_type?: string | null;
  [key: string]: unknown;
};

export type PriceActionManualRowWire = TechnicalScreenerWireRow & {
  td?: string | number | null;
  levels?: PriceActionManualLevelWire[] | null;
  level_count?: number | string | null;
  sr_level?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type PriceActionManualPayloadWire = {
  ok?: boolean;
  rows?: PriceActionManualRowWire[];
  meta?: {
    total_rows?: number | string | null;
    search?: string | null;
    [key: string]: unknown;
  };
  error?: string;
  detail?: string;
  [key: string]: unknown;
};

export type PriceActionManualSaveResponse = {
  ok?: boolean;
  error?: string;
  detail?: string;
  inserted_count?: number | string | null;
  updated_count?: number | string | null;
  deleted_count?: number | string | null;
  [key: string]: unknown;
};

export type SrLevelsWireRow = TechnicalScreenerWireRow & {
  close?: number | string | null;
  CLOSE?: number | string | null;
  tradingDateMin?: string | null;
  tradingDateMax?: string | null;
  latestTradingDate?: string | null;
  tradingDays?: number | string | null;
  T_D?: number | string | null;
  td?: number | string | null;
  trading_days?: number | string | null;
  supportDisplay?: string | null;
  supportSummary?: string | null;
  support_summary?: string | null;
  support?: string | number | null;
  resistanceDisplay?: string | null;
  resistanceSummary?: string | null;
  resistance_summary?: string | null;
  resistance?: string | number | null;
  score?: number | string | null;
  SCORE?: number | string | null;
  scoreSort?: number | string | null;
  SCORE_SORT?: number | string | null;
  score_sort?: number | string | null;
  trendDirection?: string | null;
  trend_direction?: string | null;
  trendDirectionSort?: number | string | null;
  trend_direction_sort?: number | string | null;
  priceAction?: string | { label?: string | null; state?: string | null; tooltip?: string | null; [key: string]: unknown } | null;
  priceActionSummary?: string | { label?: string | null; state?: string | null; tooltip?: string | null; [key: string]: unknown } | null;
  [key: string]: unknown;
};

export type SrLevelsPayloadWire = {
  rows?: SrLevelsWireRow[];
  meta?: {
    page?: number | string | null;
    page_size?: number | string | null;
    pageSize?: number | string | null;
    total_rows?: number | string | null;
    totalRows?: number | string | null;
    total_pages?: number | string | null;
    totalPages?: number | string | null;
    trendCounts?: Record<string, unknown> | null;
    timeframe?: TechnicalTimeframe | string | null;
    [key: string]: unknown;
  };
  status?: string;
  error?: string;
  detail?: string;
  [key: string]: unknown;
};

export type TechnicalDeliveryWireRow = TechnicalScreenerWireRow & {
  s_no?: number | string | null;
  trading_date?: string | null;
  ltc_date?: string | null;
  latestTradingDate?: string | null;
  T_D?: number | string | null;
  t_d?: number | string | null;
  td?: number | string | null;
  tradingDays?: number | string | null;
  trading_days?: number | string | null;
  delivery_qty?: number | string | null;
  delivery_qty_rising?: boolean | string | number | null;
  delivery_pct?: number | string | null;
  delivery_score?: number | string | null;
  [key: string]: unknown;
};

export type DeliveryPayloadWire = {
  status?: string;
  data?: TechnicalDeliveryWireRow[];
  rows?: TechnicalDeliveryWireRow[];
  total_records?: number | string | null;
  totalRecords?: number | string | null;
  ltc_date?: string | null;
  LTC_DATE?: string | null;
  summary?: {
    total_stocks?: number | string | null;
    delivery_pct_eq_100_count?: number | string | null;
    delivery_pct_gt_90_count?: number | string | null;
    delivery_pct_gt_80_count?: number | string | null;
    delivery_pct_gt_70_count?: number | string | null;
    delivery_pct_gt_60_count?: number | string | null;
    delivery_pct_gt_50_count?: number | string | null;
    delivery_pct_gt_40_count?: number | string | null;
    delivery_score_gt_100_count?: number | string | null;
    delivery_score_gt_90_count?: number | string | null;
    delivery_score_gt_80_count?: number | string | null;
    delivery_score_gt_70_count?: number | string | null;
    delivery_score_gt_60_count?: number | string | null;
    delivery_score_gt_50_count?: number | string | null;
    strong_accumulation_count?: number | string | null;
    ltc_date?: string | null;
    [key: string]: unknown;
  };
  meta?: {
    latest_ltc_date?: string | null;
    [key: string]: unknown;
  };
  cached?: boolean;
  refreshing?: boolean;
  error?: string;
  detail?: string;
  [key: string]: unknown;
};
