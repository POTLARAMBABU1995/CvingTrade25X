import type { UTCTimestamp } from 'lightweight-charts';

export type StockChartTimeframe = 'daily' | 'monthly' | 'weekly';
export type StockChartStatus = 'error' | 'idle' | 'loading' | 'online';

export type IndicatorId =
  | 'adx'
  | 'atr'
  | 'ema100'
  | 'ema20'
  | 'ema200'
  | 'ema50'
  | 'macd'
  | 'rsi'
  | 'volume20';

export type DrawingMode = 'horizontal-line' | 'horizontal-ray' | 'none' | 'ray' | 'trendline';

export interface ChartCandlePayload {
  close: number | string;
  high: number | string;
  low: number | string;
  open: number | string;
  time: string;
}

export interface ChartVolumePayload {
  color?: string | null;
  time: string;
  value: number | string;
}

export interface ChartOhlcvPayload {
  candles?: ChartCandlePayload[];
  latest_date?: null | string;
  symbol?: string;
  timeframe?: string;
  total_candles?: number;
  volume?: ChartVolumePayload[];
}

export interface WatchlistRowPayload {
  change?: null | number;
  change_percent?: null | number;
  last?: null | number;
  symbol?: string;
  trading_date?: null | string;
  volume?: null | number;
}

export interface ChartWatchlistPayload {
  latest_trade_date?: null | string;
  rows?: WatchlistRowPayload[];
  total_symbols?: number;
}

export interface ChartBar {
  close: number;
  high: number;
  low: number;
  open: number;
  time: UTCTimestamp;
  timeKey: string;
  volume: number;
  volumeColor: string;
}

export interface WatchlistRow {
  change: null | number;
  changePct: null | number;
  last: null | number;
  symbol: string;
  tradingDate: null | string;
  volume: null | number;
}

export interface IndicatorStat {
  available: boolean;
  display: string;
  pass: boolean | null;
  value: null | number;
}

export interface DrawingAnnotation {
  color: string;
  id: string;
  mode: Exclude<DrawingMode, 'none'>;
  p1: number;
  p2?: number;
  t1: UTCTimestamp;
  t2?: UTCTimestamp;
  width: number;
}

export interface ChartSeriesData {
  candles: Array<{
    close: number;
    high: number;
    low: number;
    open: number;
    time: UTCTimestamp;
  }>;
  volume: Array<{
    color: string;
    time: UTCTimestamp;
    value: number;
  }>;
}

export interface EmaLineSeries {
  ema100: Array<{ time: UTCTimestamp; value: number }>;
  ema20: Array<{ time: UTCTimestamp; value: number }>;
  ema200: Array<{ time: UTCTimestamp; value: number }>;
  ema50: Array<{ time: UTCTimestamp; value: number }>;
}