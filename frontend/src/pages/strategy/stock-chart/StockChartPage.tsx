import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { UTCTimestamp } from 'lightweight-charts';
import { cn } from '@/lib/cn';
import { useTechnicalThemeMode } from '../../technical/technicalPageGuards';
import { StockChartCanvas } from './StockChartCanvas';
import { fetchStockChartOhlcv, fetchStockChartWatchlist } from './stockChartService';
import { normalizeDisplaySymbol } from '../../../utils/symbols';
import type {
  ChartBar,
  ChartOhlcvPayload,
  ChartWatchlistPayload,
  DrawingAnnotation,
  DrawingMode,
  EmaLineSeries,
  IndicatorId,
  IndicatorStat,
  StockChartStatus,
  StockChartTimeframe,
  WatchlistRow,
} from './chartTypes';

const DEFAULT_SYMBOL = 'RELIANCE';
const DEFAULT_TIMEFRAME: StockChartTimeframe = 'daily';
const DEFAULT_WATCHLIST = [
  'RELIANCE',
  'TCS',
  'INFY',
  'BASF',
  'ASTRAZEN',
  'HDFCBANK',
  'ICICIBANK',
  'SBIN',
  'ITC',
  'LT',
  'BHARTIARTL',
  'BAJAJ-AUTO',
  'M&M',
];

type IndicatorToggleState = Record<IndicatorId, boolean>;

type WatchlistSortKey = 'change' | 'changePct' | 'last' | 'symbol' | 'volume';

type WatchlistSort = {
  direction: 'asc' | 'desc';
  key: WatchlistSortKey;
};

type WatchlistColumnState = {
  change: boolean;
  changePct: boolean;
  last: boolean;
  symbol: boolean;
  volume: boolean;
};

type OverlayState = {
  message: string;
  mode: 'empty' | 'error' | 'loading' | null;
};

type NormalizedChartPayload = {
  bars: ChartBar[];
  latestDate: string;
  totalCandles: number;
};

const DEFAULT_INDICATORS: IndicatorToggleState = {
  adx: false,
  atr: false,
  ema100: false,
  ema20: false,
  ema200: false,
  ema50: false,
  macd: false,
  rsi: false,
  volume20: false,
};

const INDICATOR_ORDER: Array<{ id: IndicatorId; label: string; type: 'ema' | 'status' }> = [
  { id: 'ema20', label: 'EMA20', type: 'ema' },
  { id: 'ema50', label: 'EMA50', type: 'ema' },
  { id: 'ema100', label: 'EMA100', type: 'ema' },
  { id: 'ema200', label: 'EMA200', type: 'ema' },
  { id: 'macd', label: 'MACD > 0', type: 'status' },
  { id: 'rsi', label: 'RSI > 50', type: 'status' },
  { id: 'adx', label: 'ADX > 25', type: 'status' },
  { id: 'atr', label: 'ATR14', type: 'status' },
  { id: 'volume20', label: 'Volume > 20', type: 'status' },
];

const DRAWING_TOOLS: Array<{ label: string; mode: Exclude<DrawingMode, 'none'> }> = [
  { label: 'Trendline', mode: 'trendline' },
  { label: 'Ray', mode: 'ray' },
  { label: 'Horizontal Line', mode: 'horizontal-line' },
  { label: 'Horizontal Ray', mode: 'horizontal-ray' },
];

const CHART_STORAGE_PREFIX = 'cvingtrade25x:stock-chart-drawings:v1';

function normalizeSymbol(value: string): string {
  return normalizeDisplaySymbol(value);
}

function normalizeTimeframe(value: string | null): StockChartTimeframe {
  const token = String(value || DEFAULT_TIMEFRAME).trim().toLowerCase();
  if (token === 'weekly') return 'weekly';
  if (token === 'monthly') return 'monthly';
  return 'daily';
}

function timeframeCode(timeframe: StockChartTimeframe): '1D' | '1M' | '1W' {
  if (timeframe === 'weekly') return '1W';
  if (timeframe === 'monthly') return '1M';
  return '1D';
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseIsoToTimestamp(value: string): UTCTimestamp | null {
  const match = String(value || '').trim().match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return null;
  const utc = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  if (!Number.isFinite(utc)) return null;
  return Math.floor(utc / 1000) as UTCTimestamp;
}

function formatNumber(value: number | null, digits = 2): string {
  if (value === null || !Number.isFinite(value)) return '-';
  return value.toLocaleString('en-IN', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function formatSigned(value: number | null, digits = 2): string {
  if (value === null || !Number.isFinite(value)) return '-';
  const sign = value > 0 ? '+' : '';
  return `${sign}${formatNumber(value, digits)}`;
}

function formatSignedPercent(value: number | null, digits = 2): string {
  if (value === null || !Number.isFinite(value)) return '-';
  return `${formatSigned(value, digits)}%`;
}

function formatVolumeCompact(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '-';
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(2)}K`;
  return Math.round(value).toLocaleString('en-IN');
}

function normalizeChartPayload(payload: ChartOhlcvPayload): NormalizedChartPayload {
  const rawCandles = Array.isArray(payload.candles) ? payload.candles : [];
  const rawVolume = Array.isArray(payload.volume) ? payload.volume : [];

  const volumeByTime = new Map<string, { color: string; value: number }>();
  rawVolume.forEach((row) => {
    if (!row || typeof row.time !== 'string') return;
    const value = toNumber(row.value) ?? 0;
    const color = typeof row.color === 'string' && row.color.trim() ? row.color : 'rgba(34,197,94,0.45)';
    volumeByTime.set(row.time, { color, value });
  });

  const bars: ChartBar[] = [];
  rawCandles.forEach((row) => {
    if (!row || typeof row.time !== 'string') return;
    const time = parseIsoToTimestamp(row.time);
    const open = toNumber(row.open);
    const high = toNumber(row.high);
    const low = toNumber(row.low);
    const close = toNumber(row.close);
    if (time === null || open === null || high === null || low === null || close === null) return;
    const matchedVolume = volumeByTime.get(row.time);
    bars.push({
      close,
      high,
      low,
      open,
      time,
      timeKey: row.time,
      volume: matchedVolume?.value ?? 0,
      volumeColor: matchedVolume?.color ?? (close >= open ? 'rgba(34,197,94,0.45)' : 'rgba(239,68,68,0.45)'),
    });
  });

  bars.sort((a, b) => Number(a.time) - Number(b.time));
  const latestDate = typeof payload.latest_date === 'string' && payload.latest_date.trim()
    ? payload.latest_date
    : bars.length
      ? bars[bars.length - 1].timeKey
      : '-';
  const totalCandles = Number(payload.total_candles ?? bars.length) || bars.length;

  return {
    bars,
    latestDate,
    totalCandles,
  };
}

function normalizeWatchlistPayload(payload: ChartWatchlistPayload): {
  latestTradeDate: string;
  rows: WatchlistRow[];
  totalSymbols: number;
} {
  const rows = (Array.isArray(payload.rows) ? payload.rows : [])
    .map((row) => {
      const symbol = normalizeSymbol(String(row?.symbol || ''));
      if (!symbol) return null;
      return {
        change: toNumber(row?.change),
        changePct: toNumber(row?.change_percent),
        last: toNumber(row?.last),
        symbol,
        tradingDate: typeof row?.trading_date === 'string' ? row.trading_date : null,
        volume: toNumber(row?.volume),
      } as WatchlistRow;
    })
    .filter((row): row is WatchlistRow => Boolean(row));

  return {
    latestTradeDate: typeof payload.latest_trade_date === 'string' && payload.latest_trade_date.trim() ? payload.latest_trade_date : '-',
    rows,
    totalSymbols: Number(payload.total_symbols ?? rows.length) || rows.length,
  };
}

function calculateEmaValues(values: number[], period: number): Array<number | null> {
  if (period <= 0 || values.length < period) return values.map(() => null);
  const multiplier = 2 / (period + 1);
  const result: Array<number | null> = [];
  let current: number | null = null;

  values.forEach((value, index) => {
    if (index + 1 < period) {
      result.push(null);
      return;
    }
    if (current === null) {
      const window = values.slice(index + 1 - period, index + 1);
      current = window.reduce((sum, part) => sum + part, 0) / period;
    } else {
      current = (value - current) * multiplier + current;
    }
    result.push(current);
  });

  return result;
}

function computeRsi(values: number[], period = 14): number | null {
  if (values.length <= period) return null;
  const gains: number[] = [];
  const losses: number[] = [];

  for (let index = 1; index <= period; index += 1) {
    const change = values[index] - values[index - 1];
    gains.push(Math.max(change, 0));
    losses.push(Math.abs(Math.min(change, 0)));
  }

  let avgGain = gains.reduce((sum, value) => sum + value, 0) / period;
  let avgLoss = losses.reduce((sum, value) => sum + value, 0) / period;

  for (let index = period + 1; index < values.length; index += 1) {
    const change = values[index] - values[index - 1];
    avgGain = ((avgGain * (period - 1)) + Math.max(change, 0)) / period;
    avgLoss = ((avgLoss * (period - 1)) + Math.abs(Math.min(change, 0))) / period;
  }

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

function computeAtr(bars: ChartBar[], period = 14): number | null {
  if (bars.length <= period) return null;
  const trueRanges: number[] = [];
  let previousClose: number | null = null;
  bars.forEach((bar) => {
    const range = previousClose === null
      ? bar.high - bar.low
      : Math.max(bar.high - bar.low, Math.abs(bar.high - previousClose), Math.abs(bar.low - previousClose));
    trueRanges.push(range);
    previousClose = bar.close;
  });

  const ema = calculateEmaValues(trueRanges, period);
  for (let index = ema.length - 1; index >= 0; index -= 1) {
    if (ema[index] !== null) return ema[index];
  }
  return null;
}

function computeAdx(bars: ChartBar[], period = 14): number | null {
  if (bars.length <= period * 2) return null;

  const trs: number[] = [];
  const plusDm: number[] = [];
  const minusDm: number[] = [];

  for (let index = 1; index < bars.length; index += 1) {
    const current = bars[index];
    const previous = bars[index - 1];

    const highDiff = current.high - previous.high;
    const lowDiff = previous.low - current.low;

    plusDm.push(highDiff > lowDiff && highDiff > 0 ? highDiff : 0);
    minusDm.push(lowDiff > highDiff && lowDiff > 0 ? lowDiff : 0);

    const tr = Math.max(
      current.high - current.low,
      Math.abs(current.high - previous.close),
      Math.abs(current.low - previous.close),
    );
    trs.push(tr);
  }

  if (trs.length <= period) return null;

  let smTr = trs.slice(0, period).reduce((sum, value) => sum + value, 0);
  let smPlus = plusDm.slice(0, period).reduce((sum, value) => sum + value, 0);
  let smMinus = minusDm.slice(0, period).reduce((sum, value) => sum + value, 0);
  const dxValues: number[] = [];

  for (let index = period; index < trs.length; index += 1) {
    if (index > period) {
      smTr = smTr - (smTr / period) + trs[index];
      smPlus = smPlus - (smPlus / period) + plusDm[index];
      smMinus = smMinus - (smMinus / period) + minusDm[index];
    }
    if (!smTr) continue;
    const plusDi = 100 * (smPlus / smTr);
    const minusDi = 100 * (smMinus / smTr);
    const total = plusDi + minusDi;
    if (!total) continue;
    dxValues.push(100 * (Math.abs(plusDi - minusDi) / total));
  }

  if (dxValues.length < period) return null;

  let adx = dxValues.slice(0, period).reduce((sum, value) => sum + value, 0) / period;
  for (let index = period; index < dxValues.length; index += 1) {
    adx = ((adx * (period - 1)) + dxValues[index]) / period;
  }

  return adx;
}

function computeVolume20(bars: ChartBar[]): { average: number; latest: number; pass: boolean } | null {
  if (bars.length < 21) return null;
  const latest = bars[bars.length - 1];
  const windowBars = bars.slice(Math.max(0, bars.length - 21), bars.length - 1);
  if (windowBars.length < 20) return null;
  const average = windowBars.reduce((sum, bar) => sum + bar.volume, 0) / windowBars.length;
  return {
    average,
    latest: latest.volume,
    pass: latest.volume > average,
  };
}

function buildIndicatorStats(bars: ChartBar[], toggles: IndicatorToggleState): Record<IndicatorId, IndicatorStat> {
  const latest = bars.length ? bars[bars.length - 1] : null;
  const latestClose = latest?.close ?? null;
  const closes = bars.map((bar) => bar.close);
  const stats: Record<IndicatorId, IndicatorStat> = {
    adx: { available: false, display: '-', pass: null, value: null },
    atr: { available: false, display: '-', pass: null, value: null },
    ema100: { available: false, display: 'Off', pass: null, value: null },
    ema20: { available: false, display: 'Off', pass: null, value: null },
    ema200: { available: false, display: 'Off', pass: null, value: null },
    ema50: { available: false, display: 'Off', pass: null, value: null },
    macd: { available: false, display: '-', pass: null, value: null },
    rsi: { available: false, display: '-', pass: null, value: null },
    volume20: { available: false, display: '-', pass: null, value: null },
  };

  const emaPeriods: Array<{ id: 'ema20' | 'ema50' | 'ema100' | 'ema200'; period: number }> = [
    { id: 'ema20', period: 20 },
    { id: 'ema50', period: 50 },
    { id: 'ema100', period: 100 },
    { id: 'ema200', period: 200 },
  ];

  emaPeriods.forEach(({ id, period }) => {
    const series = calculateEmaValues(closes, period);
    const value = series[series.length - 1] ?? null;
    const available = value !== null && latestClose !== null;
    stats[id] = {
      available,
      display: toggles[id] ? 'On' : 'Off',
      pass: available ? latestClose >= value : null,
      value,
    };
  });

  const ema12 = calculateEmaValues(closes, 12);
  const ema26 = calculateEmaValues(closes, 26);
  const macdSeries = ema12.map((value, index) => {
    const slow = ema26[index];
    if (value === null || slow === null) return null;
    return value - slow;
  });
  const macdValue = macdSeries[macdSeries.length - 1];
  stats.macd = {
    available: macdValue !== null,
    display: macdValue !== null && macdValue > 0 ? 'Pass' : macdValue !== null ? 'Fail' : '-',
    pass: macdValue !== null ? macdValue > 0 : null,
    value: macdValue,
  };

  const rsiValue = computeRsi(closes, 14);
  stats.rsi = {
    available: rsiValue !== null,
    display: rsiValue !== null && rsiValue > 50 ? 'Pass' : rsiValue !== null ? 'Fail' : '-',
    pass: rsiValue !== null ? rsiValue > 50 : null,
    value: rsiValue,
  };

  const adxValue = computeAdx(bars, 14);
  stats.adx = {
    available: adxValue !== null,
    display: adxValue !== null && adxValue > 25 ? 'Pass' : adxValue !== null ? 'Fail' : '-',
    pass: adxValue !== null ? adxValue > 25 : null,
    value: adxValue,
  };

  const atrValue = computeAtr(bars, 14);
  stats.atr = {
    available: atrValue !== null,
    display: atrValue !== null ? formatNumber(atrValue, 2) : '-',
    pass: null,
    value: atrValue,
  };

  const volume20 = computeVolume20(bars);
  stats.volume20 = {
    available: Boolean(volume20),
    display: volume20 ? (volume20.pass ? 'Pass' : 'Fail') : '-',
    pass: volume20 ? volume20.pass : null,
    value: volume20 ? volume20.latest : null,
  };

  return stats;
}

function buildEmaSeries(bars: ChartBar[], toggles: IndicatorToggleState): EmaLineSeries {
  const result: EmaLineSeries = {
    ema100: [],
    ema20: [],
    ema200: [],
    ema50: [],
  };

  const closes = bars.map((bar) => bar.close);

  const append = (id: keyof EmaLineSeries, period: number) => {
    if (!toggles[id]) return;
    const values = calculateEmaValues(closes, period);
    const points = values
      .map((value, index) => {
        if (value === null) return null;
        return { time: bars[index].time, value: Number(value.toFixed(4)) };
      })
      .filter((point): point is { time: UTCTimestamp; value: number } => point !== null);
    result[id] = points;
  };

  append('ema20', 20);
  append('ema50', 50);
  append('ema100', 100);
  append('ema200', 200);

  return result;
}

function chartErrorMessage(error: unknown): string {
  const status = typeof error === 'object' && error !== null && 'status' in error
    ? Number((error as { status?: unknown }).status || 0)
    : 0;
  const message = error instanceof Error ? error.message : String(error || '');

  if (status === 0 || /failed to fetch|unable to connect|networkerror|load failed/i.test(message)) {
    return 'Backend unavailable. Start the backend on http://127.0.0.1:5055 and retry.';
  }
  if (status === 404) {
    return 'API route missing: /api/chart/ohlcv.';
  }
  if (status === 400 && /timeframe/i.test(message)) {
    return 'Invalid timeframe. Use Daily, Weekly, or Monthly.';
  }
  if (status === 401 || status === 403) {
    return 'Session expired. Please login again.';
  }
  return message || 'Unable to load chart data.';
}

function chartDrawingStorageKey(symbol: string, timeframe: StockChartTimeframe): string {
  return `${CHART_STORAGE_PREFIX}:${symbol}:${timeframe}`;
}

function normalizeDrawing(raw: unknown): DrawingAnnotation | null {
  if (!raw || typeof raw !== 'object') return null;
  const record = raw as Record<string, unknown>;
  const modeToken = String(record.mode || '').trim();
  if (!['trendline', 'ray', 'horizontal-line', 'horizontal-ray'].includes(modeToken)) return null;
  const mode = modeToken as Exclude<DrawingMode, 'none'>;
  const t1 = toNumber(record.t1);
  const p1 = toNumber(record.p1);
  const width = toNumber(record.width) ?? 2;
  const color = typeof record.color === 'string' && record.color.trim() ? record.color : '#60a5fa';
  if (t1 === null || p1 === null) return null;

  const t2 = toNumber(record.t2);
  const p2 = toNumber(record.p2);
  return {
    color,
    id: typeof record.id === 'string' && record.id.trim() ? record.id : `drawing-${Math.random().toString(36).slice(2, 9)}`,
    mode,
    p1,
    p2: p2 === null ? undefined : p2,
    t1: Math.round(t1) as UTCTimestamp,
    t2: t2 === null ? undefined : (Math.round(t2) as UTCTimestamp),
    width: Math.max(1, Math.min(4, Math.round(width))),
  };
}

export function StockChartPage() {
  const search = new URLSearchParams(window.location.search);
  const initialSymbol = normalizeSymbol(search.get('symbol') || DEFAULT_SYMBOL) || DEFAULT_SYMBOL;
  const initialTimeframe = normalizeTimeframe(search.get('timeframe'));
  const themeMode = useTechnicalThemeMode();
  const isDarkMode = themeMode === 'dark';

  const [symbolInput, setSymbolInput] = useState(initialSymbol);
  const [symbol, setSymbol] = useState(initialSymbol);
  const [timeframe, setTimeframe] = useState<StockChartTimeframe>(initialTimeframe);

  const [status, setStatus] = useState<StockChartStatus>('loading');
  const [statusMessage, setStatusMessage] = useState('Loading chart data');
  const [overlay, setOverlay] = useState<OverlayState>({ mode: 'loading', message: 'Loading chart...' });

  const [bars, setBars] = useState<ChartBar[]>([]);
  const [hoverBar, setHoverBar] = useState<ChartBar | null>(null);
  const [latestDate, setLatestDate] = useState('-');
  const [totalCandles, setTotalCandles] = useState(0);

  const [watchlistRows, setWatchlistRows] = useState<WatchlistRow[]>([]);
  const [watchlistTotal, setWatchlistTotal] = useState(0);
  const [watchlistLatestDate, setWatchlistLatestDate] = useState('-');
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [watchlistError, setWatchlistError] = useState('');

  const [watchlistSort, setWatchlistSort] = useState<WatchlistSort>({ direction: 'asc', key: 'symbol' });
  const [watchlistColumns, setWatchlistColumns] = useState<WatchlistColumnState>({
    change: true,
    changePct: true,
    last: true,
    symbol: true,
    volume: true,
  });
  const [watchlistColumnPanelOpen, setWatchlistColumnPanelOpen] = useState(false);
  const [watchlistCollapsed, setWatchlistCollapsed] = useState(false);

  const [indicators, setIndicators] = useState<IndicatorToggleState>(DEFAULT_INDICATORS);
  const [drawingMode, setDrawingMode] = useState<DrawingMode>('none');
  const [drawings, setDrawings] = useState<DrawingAnnotation[]>([]);
  const [toolsCollapsed, setToolsCollapsed] = useState(true);
  const [resetToken, setResetToken] = useState(0);

  const [isFullscreen, setIsFullscreen] = useState(Boolean(document.fullscreenElement));

  const chartPanelRef = useRef<HTMLDivElement | null>(null);
  const chartAbortRef = useRef<AbortController | null>(null);
  const watchlistAbortRef = useRef<AbortController | null>(null);
  const chartCacheRef = useRef<Map<string, NormalizedChartPayload>>(new Map());

  const activeBar = hoverBar || (bars.length ? bars[bars.length - 1] : null);

  const barIndexByTime = useMemo(() => {
    const map = new Map<number, number>();
    bars.forEach((bar, index) => map.set(Number(bar.time), index));
    return map;
  }, [bars]);

  const symbolMetric = useMemo(() => {
    if (!bars.length) return null;
    const latest = bars[bars.length - 1];
    const previous = bars.length > 1 ? bars[bars.length - 2] : null;
    const change = previous ? latest.close - previous.close : null;
    const changePct = previous && previous.close !== 0 && change !== null ? (change / previous.close) * 100 : null;
    return {
      change,
      changePct,
      last: latest.close,
      tradingDate: latest.timeKey,
      volume: latest.volume,
    };
  }, [bars]);

  const mergedWatchlistRows = useMemo(() => {
    const bySymbol = new Map<string, WatchlistRow>();

    watchlistRows.forEach((row) => {
      bySymbol.set(row.symbol, { ...row });
    });

    const fallbackSymbols = new Set([...DEFAULT_WATCHLIST, symbol]);
    fallbackSymbols.forEach((item) => {
      const normalized = normalizeSymbol(item);
      if (!normalized || bySymbol.has(normalized)) return;
      bySymbol.set(normalized, {
        change: null,
        changePct: null,
        last: null,
        symbol: normalized,
        tradingDate: null,
        volume: null,
      });
    });

    if (symbolMetric) {
      const existing = bySymbol.get(symbol);
      bySymbol.set(symbol, {
        ...(existing || {}),
        change: symbolMetric.change,
        changePct: symbolMetric.changePct,
        last: symbolMetric.last,
        symbol,
        tradingDate: symbolMetric.tradingDate,
        volume: symbolMetric.volume,
      });
    }

    const rows = Array.from(bySymbol.values());

    const sortValue = (row: WatchlistRow): number | string | null => {
      if (watchlistSort.key === 'symbol') return row.symbol;
      if (watchlistSort.key === 'last') return row.last;
      if (watchlistSort.key === 'change') return row.change;
      if (watchlistSort.key === 'changePct') return row.changePct;
      return row.volume;
    };

    rows.sort((left, right) => {
      const leftValue = sortValue(left);
      const rightValue = sortValue(right);

      if (leftValue === null && rightValue === null) return left.symbol.localeCompare(right.symbol);
      if (leftValue === null) return 1;
      if (rightValue === null) return -1;

      const direction = watchlistSort.direction === 'asc' ? 1 : -1;
      if (typeof leftValue === 'string' && typeof rightValue === 'string') {
        return leftValue.localeCompare(rightValue) * direction;
      }

      if (leftValue === rightValue) return left.symbol.localeCompare(right.symbol);
      return (Number(leftValue) - Number(rightValue)) * direction;
    });

    return rows;
  }, [symbol, symbolMetric, watchlistRows, watchlistSort.direction, watchlistSort.key]);

  const indicatorStats = useMemo(() => buildIndicatorStats(bars, indicators), [bars, indicators]);
  const emaSeries = useMemo(() => buildEmaSeries(bars, indicators), [bars, indicators]);

  const symbolOptions = useMemo(() => {
    const list = new Set<string>([...DEFAULT_WATCHLIST, symbol]);
    watchlistRows.forEach((row) => list.add(row.symbol));
    return Array.from(list).filter(Boolean).sort((left, right) => left.localeCompare(right));
  }, [symbol, watchlistRows]);

  const watchlistMetaText = useMemo(() => {
    const count = watchlistTotal || watchlistRows.length;
    return `Symbols: ${count.toLocaleString('en-IN')} | Latest: ${watchlistLatestDate}`;
  }, [watchlistLatestDate, watchlistRows.length, watchlistTotal]);

  const chartTitle = `${symbol} - ${timeframeCode(timeframe)} - NSE`;
  const rangeText = bars.length ? `${bars[0].timeKey} to ${bars[bars.length - 1].timeKey}` : '-';

  const chartStatusLabel = status === 'loading' ? 'Loading' : status === 'error' ? 'Offline' : 'Live';

  const ohlcvLine = useMemo(() => {
    if (!activeBar) {
      return {
        base: `${chartTitle}   O -  H -  L -  C -`,
        changeClass: 'text-slate-500',
        changeText: '- (-)',
        volumeText: 'V -',
      };
    }

    const index = barIndexByTime.get(Number(activeBar.time));
    const previous = typeof index === 'number' && index > 0 ? bars[index - 1] : null;
    const change = previous ? activeBar.close - previous.close : null;
    const changePct = previous && previous.close !== 0 && change !== null ? (change / previous.close) * 100 : null;

    return {
      base: `${chartTitle}   O ${formatNumber(activeBar.open, 2)}  H ${formatNumber(activeBar.high, 2)}  L ${formatNumber(activeBar.low, 2)}  C ${formatNumber(activeBar.close, 2)}`,
      changeClass: change === null || change === 0 ? 'text-slate-500' : change > 0 ? 'text-emerald-600' : 'text-rose-600',
      changeText: `${formatSigned(change, 2)} (${formatSignedPercent(changePct, 2)})`,
      volumeText: `V ${formatVolumeCompact(activeBar.volume)}`,
    };
  }, [activeBar, barIndexByTime, bars, chartTitle]);

  const visibleWatchlistColumns = useMemo(
    () => [
      { key: 'symbol', label: 'Symbol', show: true },
      { key: 'last', label: 'Last', show: watchlistColumns.last },
      { key: 'change', label: 'Chg', show: watchlistColumns.change },
      { key: 'changePct', label: 'Chg%', show: watchlistColumns.changePct },
      { key: 'volume', label: 'Vol', show: watchlistColumns.volume },
    ].filter((column) => column.show),
    [watchlistColumns.change, watchlistColumns.changePct, watchlistColumns.last, watchlistColumns.volume],
  );

  const drawingStorageKey = useMemo(() => chartDrawingStorageKey(symbol, timeframe), [symbol, timeframe]);

  const applyChartData = useCallback((normalized: NormalizedChartPayload) => {
    setBars(normalized.bars);
    setLatestDate(normalized.latestDate || '-');
    setTotalCandles(normalized.totalCandles);
    if (!normalized.bars.length) {
      setOverlay({ mode: 'empty', message: `No candles found for ${symbol}.` });
      setStatus('error');
      setStatusMessage('No chart rows found');
      return;
    }
    setOverlay({ mode: null, message: '' });
    setStatus('online');
    setStatusMessage(`${normalized.bars.length.toLocaleString('en-IN')} candles loaded`);
    setHoverBar(normalized.bars[normalized.bars.length - 1]);
  }, [symbol]);

  const loadChart = useCallback(async (forceRefresh = false) => {
    const nextSymbol = normalizeSymbol(symbol);
    if (!nextSymbol) {
      setStatus('error');
      setStatusMessage('symbol is required');
      setOverlay({ mode: 'error', message: 'Enter a symbol.' });
      return;
    }

    const cacheKey = `${nextSymbol}:${timeframe}`;
    if (!forceRefresh) {
      const cached = chartCacheRef.current.get(cacheKey);
      if (cached) {
        applyChartData(cached);
        return;
      }
    }

    chartAbortRef.current?.abort();
    const controller = new AbortController();
    chartAbortRef.current = controller;

    setStatus('loading');
    setStatusMessage(`Loading ${nextSymbol} ${timeframe}`);
    if (!bars.length) {
      setOverlay({ mode: 'loading', message: `Loading ${nextSymbol} ${timeframe} candles...` });
    }

    try {
      const payload = await fetchStockChartOhlcv(nextSymbol, timeframe, controller.signal);
      const normalized = normalizeChartPayload(payload);
      chartCacheRef.current.set(cacheKey, normalized);
      applyChartData(normalized);
    } catch (error) {
      if (controller.signal.aborted) return;
      const message = chartErrorMessage(error);
      setStatus('error');
      setStatusMessage(message);
      setOverlay({ mode: 'error', message });
      setBars([]);
      setHoverBar(null);
      setTotalCandles(0);
      setLatestDate('-');
    }
  }, [applyChartData, bars.length, symbol, timeframe]);

  const loadWatchlist = useCallback(async () => {
    watchlistAbortRef.current?.abort();
    const controller = new AbortController();
    watchlistAbortRef.current = controller;

    setWatchlistLoading(true);
    setWatchlistError('');
    try {
      const payload = await fetchStockChartWatchlist(controller.signal);
      const normalized = normalizeWatchlistPayload(payload);
      setWatchlistRows(normalized.rows);
      setWatchlistTotal(normalized.totalSymbols);
      setWatchlistLatestDate(normalized.latestTradeDate);
    } catch (error) {
      if (controller.signal.aborted) return;
      const message = error instanceof Error ? error.message : 'Watchlist unavailable.';
      setWatchlistError(message || 'Watchlist unavailable.');
    } finally {
      if (watchlistAbortRef.current === controller) {
        setWatchlistLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    loadWatchlist();
    return () => {
      watchlistAbortRef.current?.abort();
    };
  }, [loadWatchlist]);

  useEffect(() => {
    loadChart(false);
    return () => {
      chartAbortRef.current?.abort();
    };
  }, [symbol, timeframe]);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set('symbol', symbol);
    url.searchParams.set('timeframe', timeframe);
    window.history.replaceState(null, document.title, url.toString());
  }, [symbol, timeframe]);

  useEffect(() => {
    const onFullscreenChange = () => {
      setIsFullscreen(Boolean(document.fullscreenElement));
    };
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(drawingStorageKey);
      if (!raw) {
        setDrawings([]);
        return;
      }
      const parsed = JSON.parse(raw);
      const list = Array.isArray(parsed)
        ? parsed.map((item) => normalizeDrawing(item)).filter((item): item is DrawingAnnotation => item !== null)
        : [];
      setDrawings(list);
    } catch {
      setDrawings([]);
    }
  }, [drawingStorageKey]);

  useEffect(() => {
    try {
      window.localStorage.setItem(drawingStorageKey, JSON.stringify(drawings));
    } catch {
      // Drawing persistence is best-effort.
    }
  }, [drawings, drawingStorageKey]);

  const handleToggleFullscreen = async () => {
    const panel = chartPanelRef.current;
    if (!panel || !document.fullscreenEnabled) return;
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await panel.requestFullscreen();
      }
    } catch {
      // Fullscreen can be blocked by browser policies.
    }
  };

  const handleWatchlistSort = (key: WatchlistSortKey) => {
    setWatchlistSort((current) => {
      if (current.key === key) {
        return {
          direction: current.direction === 'asc' ? 'desc' : 'asc',
          key,
        };
      }
      return {
        direction: key === 'symbol' ? 'asc' : 'desc',
        key,
      };
    });
  };

  const handleToggleIndicator = (id: IndicatorId) => {
    if (!indicatorStats[id].available) return;
    setIndicators((current) => ({
      ...current,
      [id]: !current[id],
    }));
  };

  const submitSymbol = () => {
    const normalized = normalizeSymbol(symbolInput || symbol);
    if (!normalized) {
      setStatus('error');
      setStatusMessage('symbol is required');
      setOverlay({ mode: 'error', message: 'Enter a symbol.' });
      return;
    }
    setSymbolInput(normalized);
    if (normalized !== symbol) {
      setSymbol(normalized);
      return;
    }
    void loadChart(true);
  };

  const statusToneClass = status === 'loading'
    ? 'border-amber-200 bg-amber-50 text-amber-700'
    : status === 'error'
      ? 'border-rose-200 bg-rose-50 text-rose-700'
      : 'border-emerald-200 bg-emerald-50 text-emerald-700';

  return (
    <div
      ref={chartPanelRef}
      className={cn(
        'relative min-h-[76vh] overflow-hidden rounded-[20px] border p-3 shadow-[0_20px_45px_rgba(15,23,42,0.14)]',
        isDarkMode
          ? 'border-slate-700/70 bg-slate-950 text-slate-100'
          : 'border-slate-200/80 bg-white text-slate-900',
      )}
    >
      <div className={cn(
        'mb-3 flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2',
        isDarkMode ? 'border-slate-700/70 bg-slate-900/80' : 'border-slate-200/80 bg-slate-50/90',
      )}>
        <span className={cn('inline-flex min-h-9 items-center rounded-full border px-3 text-xs font-bold uppercase tracking-[0.08em]', statusToneClass)} title={statusMessage}>
          {chartStatusLabel}
        </span>

        <label className="relative min-w-[240px] flex-1">
          <input
            value={symbolInput}
            list="stock-chart-symbol-list"
            onChange={(event) => setSymbolInput(event.target.value.toUpperCase())}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                submitSymbol();
              }
            }}
            className={cn(
              'h-9 w-full rounded-full border px-4 text-sm font-semibold uppercase outline-none',
              isDarkMode
                ? 'border-slate-600 bg-slate-900 text-slate-100 placeholder:text-slate-400'
                : 'border-slate-300 bg-white text-slate-900 placeholder:text-slate-500',
            )}
            placeholder="Search NSE/BSE symbols"
            aria-label="Chart symbol"
          />
          <datalist id="stock-chart-symbol-list">
            {symbolOptions.map((option) => (
              <option key={option} value={option} />
            ))}
          </datalist>
        </label>

        <select
          className={cn(
            'h-9 rounded-full border px-3 text-sm font-semibold outline-none',
            isDarkMode ? 'border-slate-600 bg-slate-900 text-slate-100' : 'border-slate-300 bg-white text-slate-900',
          )}
          value={timeframe}
          onChange={(event) => setTimeframe(normalizeTimeframe(event.target.value))}
          aria-label="Chart timeframe"
        >
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>

        <button
          type="button"
          className={cn(
            'h-9 rounded-full border px-4 text-xs font-semibold uppercase tracking-[0.08em]',
            isDarkMode ? 'border-cyan-600/70 bg-slate-900 text-cyan-200' : 'border-cyan-300 bg-white text-cyan-700',
          )}
          onClick={() => void loadChart(true)}
        >
          Refresh
        </button>

        <div className={cn('ml-auto inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold', isDarkMode ? 'border-slate-700 text-slate-300' : 'border-slate-300 text-slate-600')}>
          Total: {totalCandles.toLocaleString('en-IN')}
        </div>
        <div className={cn('inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold', isDarkMode ? 'border-slate-700 text-slate-300' : 'border-slate-300 text-slate-600')}>
          Latest: {latestDate}
        </div>
      </div>

      <div className={cn('grid min-h-[68vh] gap-3', watchlistCollapsed ? 'grid-cols-[minmax(48px,56px)_minmax(0,1fr)] xl:grid-cols-[minmax(48px,56px)_minmax(0,1fr)]' : 'grid-cols-[minmax(48px,56px)_minmax(0,1fr)] xl:grid-cols-[minmax(48px,56px)_minmax(0,1fr)_300px]')}>
        <aside
          className={cn(
            'overflow-hidden rounded-xl border transition-all',
            toolsCollapsed ? 'w-[52px]' : 'w-[220px]',
            isDarkMode ? 'border-slate-700 bg-slate-900/80' : 'border-slate-200 bg-slate-50/95',
          )}
        >
          <div className="flex items-center justify-between border-b border-inherit px-2 py-2">
            {!toolsCollapsed ? <span className="text-[11px] font-bold uppercase tracking-[0.14em]">Tools</span> : null}
            <button
              type="button"
              className={cn('h-8 w-8 rounded-lg border text-xs font-bold', isDarkMode ? 'border-slate-600 text-slate-200' : 'border-slate-300 text-slate-700')}
              onClick={() => setToolsCollapsed((current) => !current)}
              aria-label={toolsCollapsed ? 'Expand tools' : 'Collapse tools'}
            >
              {toolsCollapsed ? '>' : '<'}
            </button>
          </div>

          <div className="space-y-3 p-2">
            {DRAWING_TOOLS.map((tool) => {
              const active = drawingMode === tool.mode;
              return (
                <button
                  key={tool.mode}
                  type="button"
                  className={cn(
                    'w-full rounded-lg border px-2 py-2 text-left text-[11px] font-semibold uppercase tracking-[0.06em]',
                    active
                      ? 'border-cyan-400/70 bg-cyan-500/12 text-cyan-600'
                      : isDarkMode
                        ? 'border-slate-600 text-slate-200 hover:border-slate-400'
                        : 'border-slate-300 text-slate-700 hover:border-slate-400',
                  )}
                  title={tool.label}
                  onClick={() => setDrawingMode((current) => (current === tool.mode ? 'none' : tool.mode))}
                >
                  {toolsCollapsed ? tool.label.slice(0, 2) : tool.label}
                </button>
              );
            })}

            <button
              type="button"
              className={cn(
                'w-full rounded-lg border px-2 py-2 text-left text-[11px] font-semibold uppercase tracking-[0.06em]',
                isDarkMode ? 'border-slate-600 text-slate-200 hover:border-rose-400' : 'border-slate-300 text-slate-700 hover:border-rose-400',
              )}
              onClick={() => setDrawings([])}
            >
              {toolsCollapsed ? 'CL' : 'Clear Drawings'}
            </button>

            {!toolsCollapsed ? (
              <div className="space-y-2 pt-2">
                <p className={cn('text-[10px] font-bold uppercase tracking-[0.18em]', isDarkMode ? 'text-slate-300' : 'text-slate-600')}>
                  Indicators
                </p>
                {INDICATOR_ORDER.map((indicator) => {
                  const stat = indicatorStats[indicator.id];
                  const active = indicators[indicator.id];
                  return (
                    <button
                      key={indicator.id}
                      type="button"
                      className={cn(
                        'flex w-full items-center justify-between rounded-lg border px-2 py-2 text-[11px] font-semibold',
                        !stat.available
                          ? isDarkMode
                            ? 'cursor-not-allowed border-slate-700 text-slate-500'
                            : 'cursor-not-allowed border-slate-200 text-slate-400'
                          : active
                            ? 'border-cyan-400/70 bg-cyan-500/12 text-cyan-600'
                            : isDarkMode
                              ? 'border-slate-600 text-slate-200 hover:border-slate-400'
                              : 'border-slate-300 text-slate-700 hover:border-slate-400',
                      )}
                      onClick={() => handleToggleIndicator(indicator.id)}
                      disabled={!stat.available}
                    >
                      <span>{indicator.label}</span>
                      <span
                        className={cn(
                          'rounded-full px-2 py-[2px] text-[10px] font-bold',
                          stat.pass === true
                            ? 'bg-emerald-500/12 text-emerald-600'
                            : stat.pass === false
                              ? 'bg-rose-500/12 text-rose-600'
                              : isDarkMode
                                ? 'bg-slate-700 text-slate-200'
                                : 'bg-slate-200 text-slate-700',
                        )}
                      >
                        {indicator.type === 'ema' ? (active ? 'On' : 'Off') : stat.display}
                      </span>
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>
        </aside>

        <section className={cn('relative flex min-h-0 flex-col overflow-hidden rounded-xl border', isDarkMode ? 'border-slate-700 bg-slate-900/80' : 'border-slate-200 bg-slate-50/95')}>
          <div className={cn('flex flex-wrap items-start justify-between gap-2 border-b px-3 py-2', isDarkMode ? 'border-slate-700' : 'border-slate-200')}>
            <div>
              <strong className="text-sm font-bold">{chartTitle}</strong>
              <div className="mt-1 text-xs">
                <span>{ohlcvLine.base}</span>
                <span className={cn('ml-2 font-semibold', ohlcvLine.changeClass)}>{ohlcvLine.changeText}</span>
                <span className="ml-2 font-semibold">{ohlcvLine.volumeText}</span>
              </div>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className={cn('rounded-full border px-2 py-1 font-semibold', isDarkMode ? 'border-slate-700 text-slate-300' : 'border-slate-300 text-slate-600')}>
                {rangeText}
              </span>
              <a
                href="/app/dashboard"
                className={cn('rounded-full border px-2 py-1 font-semibold', isDarkMode ? 'border-slate-600 text-slate-200 hover:border-slate-400' : 'border-slate-300 text-slate-700 hover:border-slate-400')}
                aria-label="Back to Dashboard"
              >
                Dashboard
              </a>
              <button
                type="button"
                className={cn('rounded-full border px-2 py-1 font-semibold', isDarkMode ? 'border-slate-600 text-slate-200 hover:border-slate-400' : 'border-slate-300 text-slate-700 hover:border-slate-400')}
                onClick={() => void handleToggleFullscreen()}
                title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
                aria-label={isFullscreen ? 'Exit fullscreen' : 'Toggle fullscreen'}
              >
                {isFullscreen ? 'Exit' : 'Full'}
              </button>
            </div>
          </div>

          <div className="relative min-h-0 flex-1 p-2">
            <StockChartCanvas
              annotations={drawings}
              bars={bars}
              drawingMode={drawingMode}
              emaSeries={emaSeries as EmaLineSeries}
              isDarkMode={isDarkMode}
              onAnnotationsChange={setDrawings}
              onHoverBar={setHoverBar}
              resetToken={resetToken}
              timeframe={timeframe}
            />

            <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
              <button
                type="button"
                onClick={() => setResetToken((current) => current + 1)}
                className={cn('pointer-events-auto rounded-full border px-3 py-1 text-xs font-semibold', isDarkMode ? 'border-slate-600 bg-slate-900 text-slate-200' : 'border-slate-300 bg-white text-slate-700')}
                aria-label="Reset chart view"
                title="Reset chart view"
              >
                Reset
              </button>
            </div>

            {overlay.mode ? (
              <div
                className={cn(
                  'absolute inset-0 flex items-center justify-center rounded-2xl text-sm font-semibold',
                  overlay.mode === 'error'
                    ? 'bg-rose-500/18 text-rose-100'
                    : overlay.mode === 'empty'
                      ? isDarkMode
                        ? 'bg-slate-900/88 text-slate-200'
                        : 'bg-white/92 text-slate-700'
                      : isDarkMode
                        ? 'bg-slate-900/78 text-slate-200'
                        : 'bg-white/88 text-slate-700',
                )}
              >
                {overlay.message}
              </div>
            ) : null}
          </div>
        </section>

        {!watchlistCollapsed ? (
          <aside className={cn('hidden min-h-0 flex-col overflow-hidden rounded-xl border xl:flex', isDarkMode ? 'border-slate-700 bg-slate-900/80' : 'border-slate-200 bg-slate-50/95')}>
            <div className={cn('flex items-center justify-between border-b px-3 py-2', isDarkMode ? 'border-slate-700' : 'border-slate-200')}>
              <div>
                <strong className="text-sm font-bold">Watchlist</strong>
                <p className="text-[11px] text-slate-500">{watchlistMetaText}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className={cn('rounded-md border px-2 py-1 text-[11px] font-semibold', isDarkMode ? 'border-slate-600 text-slate-200' : 'border-slate-300 text-slate-700')}
                  onClick={() => setWatchlistColumnPanelOpen((current) => !current)}
                >
                  Columns
                </button>
                <button
                  type="button"
                  className={cn('rounded-md border px-2 py-1 text-[11px] font-semibold', isDarkMode ? 'border-slate-600 text-slate-200' : 'border-slate-300 text-slate-700')}
                  onClick={() => setWatchlistCollapsed(true)}
                >
                  Hide
                </button>
              </div>
            </div>

            {watchlistColumnPanelOpen ? (
              <div className={cn('grid grid-cols-2 gap-2 border-b px-3 py-2 text-xs', isDarkMode ? 'border-slate-700' : 'border-slate-200')}>
                <label className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={watchlistColumns.last}
                    onChange={(event) => setWatchlistColumns((current) => ({ ...current, last: event.target.checked }))}
                  />
                  Last
                </label>
                <label className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={watchlistColumns.change}
                    onChange={(event) => setWatchlistColumns((current) => ({ ...current, change: event.target.checked }))}
                  />
                  Chg
                </label>
                <label className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={watchlistColumns.changePct}
                    onChange={(event) => setWatchlistColumns((current) => ({ ...current, changePct: event.target.checked }))}
                  />
                  Chg%
                </label>
                <label className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={watchlistColumns.volume}
                    onChange={(event) => setWatchlistColumns((current) => ({ ...current, volume: event.target.checked }))}
                  />
                  Vol
                </label>
              </div>
            ) : null}

            <div className="min-h-0 flex-1 overflow-auto">
              <div className={cn('sticky top-0 z-10 grid border-b px-2 py-2 text-[11px] font-bold uppercase tracking-[0.08em]', isDarkMode ? 'border-slate-700 bg-slate-900 text-slate-300' : 'border-slate-200 bg-slate-100 text-slate-600')} style={{ gridTemplateColumns: `repeat(${visibleWatchlistColumns.length}, minmax(64px, 1fr))` }}>
                {visibleWatchlistColumns.map((column) => (
                  <button
                    key={column.key}
                    type="button"
                    onClick={() => handleWatchlistSort(column.key as WatchlistSortKey)}
                    className="text-left"
                  >
                    {column.label}
                    {watchlistSort.key === column.key ? (watchlistSort.direction === 'asc' ? ' ^' : ' v') : ''}
                  </button>
                ))}
              </div>

              {watchlistLoading && !mergedWatchlistRows.length ? (
                <div className="px-3 py-4 text-xs text-slate-500">Loading symbols...</div>
              ) : null}

              {watchlistError && !mergedWatchlistRows.length ? (
                <div className="px-3 py-4 text-xs text-rose-600">{watchlistError}</div>
              ) : null}

              {mergedWatchlistRows.map((row) => (
                <button
                  key={row.symbol}
                  type="button"
                  className={cn(
                    'grid w-full border-b px-2 py-2 text-left text-xs',
                    row.symbol === symbol
                      ? isDarkMode
                        ? 'border-slate-700 bg-cyan-500/10'
                        : 'border-slate-200 bg-cyan-50'
                      : isDarkMode
                        ? 'border-slate-800 hover:bg-slate-800/70'
                        : 'border-slate-100 hover:bg-slate-100/80',
                  )}
                  style={{ gridTemplateColumns: `repeat(${visibleWatchlistColumns.length}, minmax(64px, 1fr))` }}
                  onClick={() => {
                    setSymbol(row.symbol);
                    setSymbolInput(row.symbol);
                  }}
                  title={row.tradingDate ? `${row.symbol} latest ${row.tradingDate}` : row.symbol}
                >
                  {visibleWatchlistColumns.map((column) => {
                    if (column.key === 'symbol') return <span key={column.key} className="font-semibold">{row.symbol}</span>;
                    if (column.key === 'last') return <span key={column.key}>{formatNumber(row.last, 2)}</span>;
                    if (column.key === 'change') {
                      const cls = row.change === null || row.change === 0 ? '' : row.change > 0 ? 'text-emerald-600' : 'text-rose-600';
                      return <span key={column.key} className={cls}>{formatSigned(row.change, 2)}</span>;
                    }
                    if (column.key === 'changePct') {
                      const cls = row.changePct === null || row.changePct === 0 ? '' : row.changePct > 0 ? 'text-emerald-600' : 'text-rose-600';
                      return <span key={column.key} className={cls}>{formatSignedPercent(row.changePct, 2)}</span>;
                    }
                    return <span key={column.key}>{formatVolumeCompact(row.volume)}</span>;
                  })}
                </button>
              ))}
            </div>
          </aside>
        ) : (
          <button
            type="button"
            className={cn('hidden rounded-xl border px-2 py-1 text-xs font-semibold xl:inline-flex xl:self-start', isDarkMode ? 'border-slate-600 bg-slate-900 text-slate-200' : 'border-slate-300 bg-white text-slate-700')}
            onClick={() => setWatchlistCollapsed(false)}
          >
            Show Watchlist
          </button>
        )}
      </div>

      {watchlistError && mergedWatchlistRows.length ? (
        <p className="mt-2 text-xs text-rose-600">{watchlistError}</p>
      ) : null}
    </div>
  );
}
