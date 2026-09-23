import { useEffect, useMemo, useRef } from 'react';
import {
  createChart,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import type { ChartBar, DrawingAnnotation, DrawingMode, EmaLineSeries, StockChartTimeframe } from './chartTypes';

type StockChartCanvasProps = {
  annotations: DrawingAnnotation[];
  bars: ChartBar[];
  drawingMode: DrawingMode;
  emaSeries: EmaLineSeries;
  isDarkMode: boolean;
  onAnnotationsChange: (annotations: DrawingAnnotation[]) => void;
  onHoverBar: (bar: ChartBar | null) => void;
  resetToken: number;
  timeframe: StockChartTimeframe;
};

type PendingDrawingPoint = {
  mode: Exclude<DrawingMode, 'none'>;
  p1: number;
  t1: UTCTimestamp;
};

const LOOKBACK_BARS: Record<StockChartTimeframe, number> = {
  daily: 252,
  weekly: 52,
  monthly: 12,
};

const DRAWING_COLOR = '#60a5fa';
const DRAWING_WIDTH = 2;

function barAtTsLookup(bars: ChartBar[]) {
  const lookup = new Map<number, ChartBar>();
  bars.forEach((bar) => {
    lookup.set(Number(bar.time), bar);
  });
  return lookup;
}

function chartOptions(isDarkMode: boolean) {
  const crosshairColor = isDarkMode ? 'rgba(220, 230, 245, 0.55)' : 'rgba(40, 50, 70, 0.45)';
  return {
    crosshair: {
      horzLine: {
        color: crosshairColor,
        labelBackgroundColor: isDarkMode ? '#111827' : '#334155',
        labelVisible: true,
        style: LineStyle.Dashed,
        visible: true,
        width: 1,
      },
      mode: CrosshairMode.Normal,
      vertLine: {
        color: crosshairColor,
        labelBackgroundColor: isDarkMode ? '#111827' : '#0f6b93',
        labelVisible: true,
        style: LineStyle.Dashed,
        visible: true,
        width: 1,
      },
    },
    grid: {
      horzLines: {
        color: isDarkMode ? 'rgba(120, 144, 156, 0.16)' : 'rgba(100, 116, 139, 0.22)',
        visible: true,
      },
      vertLines: {
        color: isDarkMode ? 'rgba(120, 144, 156, 0.16)' : 'rgba(100, 116, 139, 0.22)',
        visible: true,
      },
    },
    handleScale: {
      axisPressedMouseMove: {
        price: true,
        time: true,
      },
      mouseWheel: true,
      pinch: true,
    },
    handleScroll: {
      horzTouchDrag: true,
      mouseWheel: true,
      pressedMouseMove: true,
      vertTouchDrag: true,
    },
    layout: {
      attributionLogo: false,
      background: {
        color: isDarkMode ? '#0b0f14' : '#ffffff',
      },
      fontFamily: 'Roboto, Arial, sans-serif',
      fontSize: 12,
      textColor: isDarkMode ? '#d1d5db' : '#334155',
    },
    leftPriceScale: {
      borderColor: isDarkMode ? 'rgba(203, 213, 225, 0.3)' : 'rgba(71, 85, 105, 0.28)',
      borderVisible: true,
      scaleMargins: { bottom: 0.2, top: 0.08 },
      visible: true,
    },
    rightPriceScale: {
      borderColor: isDarkMode ? 'rgba(203, 213, 225, 0.36)' : 'rgba(71, 85, 105, 0.34)',
      borderVisible: true,
      scaleMargins: { bottom: 0.2, top: 0.08 },
      visible: true,
    },
    timeScale: {
      borderColor: isDarkMode ? 'rgba(203, 213, 225, 0.36)' : 'rgba(71, 85, 105, 0.34)',
      borderVisible: true,
      lockVisibleTimeRangeOnResize: true,
      rightOffset: 0,
      secondsVisible: false,
      timeVisible: true,
      visible: true,
    },
  } as const;
}

function createDrawingId() {
  return `drawing-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function toPointTime(time: Time): UTCTimestamp | null {
  if (typeof time === 'number') {
    return time as UTCTimestamp;
  }
  if (time && typeof time === 'object' && 'year' in time && 'month' in time && 'day' in time) {
    const utc = Date.UTC(Number(time.year), Number(time.month) - 1, Number(time.day));
    return Math.floor(utc / 1000) as UTCTimestamp;
  }
  return null;
}

function findStartIndexForOneYear(bars: ChartBar[], timeframe: StockChartTimeframe): number {
  if (!bars.length) return 0;
  const latestIndex = bars.length - 1;
  const fallback = Math.max(0, latestIndex - LOOKBACK_BARS[timeframe] + 1);
  const latestMs = Number(bars[latestIndex].time) * 1000;
  if (!Number.isFinite(latestMs)) return fallback;
  const target = new Date(latestMs);
  target.setUTCFullYear(target.getUTCFullYear() - 1);
  const targetMs = target.getTime();

  for (let index = 0; index <= latestIndex; index += 1) {
    const barMs = Number(bars[index].time) * 1000;
    if (Number.isFinite(barMs) && barMs >= targetMs) {
      return index;
    }
  }
  return fallback;
}

function drawOverlay(
  canvas: HTMLCanvasElement,
  annotations: DrawingAnnotation[],
  pendingPoint: PendingDrawingPoint | null,
  chart: IChartApi,
  candleSeries: ISeriesApi<'Candlestick'>,
) {
  const context = canvas.getContext('2d');
  if (!context) return;
  context.clearRect(0, 0, canvas.width, canvas.height);

  const drawLine = (x1: number, y1: number, x2: number, y2: number, color: string, width: number) => {
    context.strokeStyle = color;
    context.lineWidth = width;
    context.beginPath();
    context.moveTo(x1, y1);
    context.lineTo(x2, y2);
    context.stroke();
  };

  const timeScale = chart.timeScale();
  const fullWidth = canvas.width;
  const fullHeight = canvas.height;

  annotations.forEach((annotation) => {
    const baseY = candleSeries.priceToCoordinate(annotation.p1);
    if (baseY === null) return;

    if (annotation.mode === 'horizontal-line') {
      drawLine(0, baseY, fullWidth, baseY, annotation.color, annotation.width);
      return;
    }

    if (annotation.mode === 'horizontal-ray') {
      const xStart = timeScale.timeToCoordinate(annotation.t1);
      if (xStart === null) return;
      drawLine(xStart, baseY, fullWidth, baseY, annotation.color, annotation.width);
      return;
    }

    if (!annotation.t2 || annotation.p2 === undefined) return;

    const x1 = timeScale.timeToCoordinate(annotation.t1);
    const x2 = timeScale.timeToCoordinate(annotation.t2);
    const y2 = candleSeries.priceToCoordinate(annotation.p2);
    if (x1 === null || x2 === null || y2 === null) return;

    if (annotation.mode === 'trendline') {
      drawLine(x1, baseY, x2, y2, annotation.color, annotation.width);
      return;
    }

    if (annotation.mode === 'ray') {
      if (Math.abs(x2 - x1) < 1) {
        drawLine(x1, baseY, x2, y2, annotation.color, annotation.width);
        return;
      }
      const slope = (y2 - baseY) / (x2 - x1);
      const endX = fullWidth;
      const endY = baseY + slope * (endX - x1);
      drawLine(x1, baseY, endX, endY, annotation.color, annotation.width);
    }
  });

  if (pendingPoint) {
    const pendingX = timeScale.timeToCoordinate(pendingPoint.t1);
    const pendingY = candleSeries.priceToCoordinate(pendingPoint.p1);
    if (pendingX !== null && pendingY !== null) {
      context.fillStyle = 'rgba(248, 250, 252, 0.9)';
      context.strokeStyle = 'rgba(56, 189, 248, 0.9)';
      context.lineWidth = 1.5;
      context.beginPath();
      context.arc(pendingX, pendingY, 4, 0, Math.PI * 2);
      context.fill();
      context.stroke();
    }
  }

  context.clearRect(0, fullHeight, fullWidth, 0);
}

export function StockChartCanvas({
  annotations,
  bars,
  drawingMode,
  emaSeries,
  isDarkMode,
  onAnnotationsChange,
  onHoverBar,
  resetToken,
  timeframe,
}: StockChartCanvasProps) {
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement | null>(null);

  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const ema20Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const ema50Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const ema100Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const ema200Ref = useRef<ISeriesApi<'Line'> | null>(null);

  const barsByTimeRef = useRef<Map<number, ChartBar>>(new Map());
  const annotationsRef = useRef<DrawingAnnotation[]>(annotations);
  const drawingModeRef = useRef<DrawingMode>('none');
  const onHoverBarRef = useRef(onHoverBar);
  const onAnnotationsChangeRef = useRef(onAnnotationsChange);
  const pendingPointRef = useRef<PendingDrawingPoint | null>(null);

  const drawOverlayCanvas = () => {
    const canvas = overlayCanvasRef.current;
    const chart = chartRef.current;
    const candleSeries = candleSeriesRef.current;
    if (!canvas || !chart || !candleSeries) return;
    drawOverlay(canvas, annotationsRef.current, pendingPointRef.current, chart, candleSeries);
  };

  const candleSeriesData = useMemo(
    () => bars.map((bar) => ({ close: bar.close, high: bar.high, low: bar.low, open: bar.open, time: bar.time })),
    [bars],
  );

  const volumeSeriesData = useMemo(
    () => bars.map((bar) => ({ color: bar.volumeColor, time: bar.time, value: bar.volume })),
    [bars],
  );

  useEffect(() => {
    onHoverBarRef.current = onHoverBar;
  }, [onHoverBar]);

  useEffect(() => {
    onAnnotationsChangeRef.current = onAnnotationsChange;
  }, [onAnnotationsChange]);

  useEffect(() => {
    annotationsRef.current = annotations;
    drawOverlayCanvas();
  }, [annotations]);

  useEffect(() => {
    drawingModeRef.current = drawingMode;
    pendingPointRef.current = null;
  }, [drawingMode]);

  useEffect(() => {
    barsByTimeRef.current = barAtTsLookup(bars);
  }, [bars]);

  useEffect(() => {
    if (!chartContainerRef.current) return;
    const container = chartContainerRef.current;

    const chart = createChart(container, {
      height: Math.max(420, container.clientHeight),
      width: Math.max(320, container.clientWidth),
      ...chartOptions(isDarkMode),
      localization: {
        priceFormatter: (value: number) => value.toFixed(2),
      },
    });

    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      borderDownColor: '#ef4444',
      borderUpColor: '#22c55e',
      downColor: '#ef4444',
      upColor: '#22c55e',
      wickDownColor: '#ef4444',
      wickUpColor: '#22c55e',
    });

    const volumeSeries = chart.addHistogramSeries({
      base: 0,
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });

    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    chart.priceScale('').applyOptions({
      borderVisible: false,
      scaleMargins: { bottom: 0, top: 0.82 },
    });

    ema20Ref.current = chart.addLineSeries({ color: '#22c55e', lineWidth: 2, title: 'EMA20' });
    ema50Ref.current = chart.addLineSeries({ color: '#38bdf8', lineWidth: 2, title: 'EMA50' });
    ema100Ref.current = chart.addLineSeries({ color: '#f59e0b', lineWidth: 2, title: 'EMA100' });
    ema200Ref.current = chart.addLineSeries({ color: '#a855f7', lineWidth: 2, title: 'EMA200' });

    const handleCrosshairMove = (param: unknown) => {
      const payload = param as {
        point?: { x: number; y: number };
        time?: Time;
      };
      const pointTime = payload.time ? toPointTime(payload.time) : null;
      if (pointTime === null) {
        onHoverBarRef.current(null);
        return;
      }
      const match = barsByTimeRef.current.get(Number(pointTime)) || null;
      onHoverBarRef.current(match);
    };

    const handleChartClick = (param: unknown) => {
      const payload = param as {
        point?: { x: number; y: number };
        time?: Time;
      };
      const mode = drawingModeRef.current;
      if (mode === 'none') return;
      if (!payload.time || !payload.point) return;
      const pointTime = toPointTime(payload.time);
      if (pointTime === null) return;
      const price = candleSeries.coordinateToPrice(payload.point.y);
      if (price === null) return;

      const append = (annotation: DrawingAnnotation) => {
        onAnnotationsChangeRef.current([...annotationsRef.current, annotation]);
      };

      if (mode === 'horizontal-line' || mode === 'horizontal-ray') {
        append({
          color: DRAWING_COLOR,
          id: createDrawingId(),
          mode,
          p1: price,
          t1: pointTime,
          width: DRAWING_WIDTH,
        });
        return;
      }

      const pending = pendingPointRef.current;
      if (!pending || pending.mode !== mode) {
        pendingPointRef.current = {
          mode,
          p1: price,
          t1: pointTime,
        };
        drawOverlayCanvas();
        return;
      }

      append({
        color: DRAWING_COLOR,
        id: createDrawingId(),
        mode,
        p1: pending.p1,
        p2: price,
        t1: pending.t1,
        t2: pointTime,
        width: DRAWING_WIDTH,
      });
      pendingPointRef.current = null;
      drawOverlayCanvas();
    };

    chart.subscribeCrosshairMove(handleCrosshairMove);
    chart.subscribeClick(handleChartClick);

    const drawOnRangeChange = () => drawOverlayCanvas();
    chart.timeScale().subscribeVisibleLogicalRangeChange(drawOnRangeChange);

    const resizeObserver = new ResizeObserver(() => {
      const width = Math.max(320, container.clientWidth);
      const height = Math.max(420, container.clientHeight);
      chart.applyOptions({ height, width });
      const canvas = overlayCanvasRef.current;
      if (canvas) {
        canvas.width = width;
        canvas.height = height;
      }
      drawOverlayCanvas();
    });

    resizeObserver.observe(container);
    const canvas = overlayCanvasRef.current;
    if (canvas) {
      canvas.width = Math.max(320, container.clientWidth);
      canvas.height = Math.max(420, container.clientHeight);
    }
    drawOverlayCanvas();

    return () => {
      resizeObserver.disconnect();
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(drawOnRangeChange);
      chart.unsubscribeClick(handleChartClick);
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      ema20Ref.current = null;
      ema50Ref.current = null;
      ema100Ref.current = null;
      ema200Ref.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.applyOptions(chartOptions(isDarkMode));
  }, [isDarkMode]);

  const applyLatestOneYearRange = () => {
    const chart = chartRef.current;
    if (!chart || !bars.length) return;
    const latestIndex = bars.length - 1;
    const fromIndex = findStartIndexForOneYear(bars, timeframe);
    chart.timeScale().setVisibleLogicalRange({
      from: Math.max(0, fromIndex - 0.5),
      to: Math.max(fromIndex + 1, latestIndex + 0.5),
    });
  };

  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    if (!candleSeries || !volumeSeries) return;
    candleSeries.setData(candleSeriesData);
    volumeSeries.setData(volumeSeriesData);

    const canvas = overlayCanvasRef.current;
    if (canvas && chartRef.current) {
      const width = Math.max(320, chartContainerRef.current?.clientWidth ?? 0);
      const height = Math.max(420, chartContainerRef.current?.clientHeight ?? 0);
      if (canvas.width !== width) canvas.width = width;
      if (canvas.height !== height) canvas.height = height;
      drawOverlay(canvas, annotationsRef.current, pendingPointRef.current, chartRef.current, candleSeries);
    }

    applyLatestOneYearRange();

    if (!bars.length) {
      onHoverBarRef.current(null);
      return;
    }
    onHoverBarRef.current(bars[bars.length - 1]);
  }, [bars, candleSeriesData, timeframe, volumeSeriesData]);

  useEffect(() => {
    const ema20 = ema20Ref.current;
    const ema50 = ema50Ref.current;
    const ema100 = ema100Ref.current;
    const ema200 = ema200Ref.current;
    if (!ema20 || !ema50 || !ema100 || !ema200) return;
    ema20.setData(emaSeries.ema20);
    ema50.setData(emaSeries.ema50);
    ema100.setData(emaSeries.ema100);
    ema200.setData(emaSeries.ema200);
  }, [emaSeries]);

  useEffect(() => {
    applyLatestOneYearRange();
  }, [resetToken]);

  return (
    <div className="relative h-full min-h-[540px] w-full overflow-hidden rounded-2xl border border-slate-200/60 bg-white dark:border-slate-700/60 dark:bg-[#0b0f14]">
      <div ref={chartContainerRef} className="h-full w-full" />
      <canvas ref={overlayCanvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />
    </div>
  );
}
