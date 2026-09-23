import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CrosshairMode,
  createChart,
  type IChartApi,
  type Range,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import type { Bar, IndicatorPoint, OverlayAnnotation } from '../types';
import type { IndicatorState } from './IndicatorToggles';
import OverlayLayer from './OverlayLayer';

export type DrawingTool = 'none' | 'hline' | 'vline' | 'trendline' | 'rect';

export type TVChartProps = {
  resetKey: string;
  bars: Bar[];
  indicators: Record<string, IndicatorPoint[]>;
  overlays: OverlayAnnotation[];
  userAnnotations: OverlayAnnotation[];
  indicatorState: IndicatorState;
  onLoadMore: () => void;
  canLoadMore: boolean;
  isLoadingMore: boolean;
  drawingTool: DrawingTool;
  onAddAnnotation: (annotation: OverlayAnnotation) => void;
  onCompleteDrawing: () => void;
};

const UP_COLOR = '#34d399';
const DOWN_COLOR = '#fb7185';
const TEXT_COLOR = '#cbd5e1';
const GRID_COLOR = 'rgba(71, 85, 105, 0.18)';
const BORDER_COLOR = 'rgba(100, 116, 139, 0.24)';

function buildLineData(series?: IndicatorPoint[]) {
  if (!series) return [];
  return series.map((point) => ({ time: point.t as UTCTimestamp, value: point.v }));
}

function applyPaneTheme(chart: IChartApi) {
  chart.applyOptions({
    layout: {
      background: { color: 'transparent' },
      textColor: TEXT_COLOR,
      fontFamily: '"IBM Plex Sans", sans-serif',
      fontSize: 12,
    },
    grid: {
      vertLines: { color: GRID_COLOR },
      horzLines: { color: GRID_COLOR },
    },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: 'rgba(25, 170, 229, 0.22)', width: 1, labelBackgroundColor: '#102231' },
      horzLine: { color: 'rgba(148, 163, 184, 0.16)', width: 1, labelBackgroundColor: '#111827' },
    },
    rightPriceScale: { borderColor: BORDER_COLOR },
    timeScale: { borderColor: BORDER_COLOR },
  });
}

export default function TVChart({
  resetKey,
  bars,
  indicators,
  overlays,
  userAnnotations,
  indicatorState,
  onLoadMore,
  canLoadMore,
  isLoadingMore,
  drawingTool,
  onAddAnnotation,
  onCompleteDrawing,
}: TVChartProps) {
  const mainContainerRef = useRef<HTMLDivElement | null>(null);
  const rsiContainerRef = useRef<HTMLDivElement | null>(null);
  const macdContainerRef = useRef<HTMLDivElement | null>(null);
  const mainChartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const ema20Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const ema50Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const ema200Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const atrRef = useRef<ISeriesApi<'Line'> | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const pendingPointsRef = useRef<OverlayAnnotation[]>([]);
  const hasFittedRef = useRef(false);
  const interactionRef = useRef({
    drawingTool,
    onAddAnnotation,
    onCompleteDrawing,
    onLoadMore,
    canLoadMore,
    isLoadingMore,
  });

  const [rsiChart, setRsiChart] = useState<IChartApi | null>(null);
  const [macdChart, setMacdChart] = useState<IChartApi | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const macdSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const macdSignalRef = useRef<ISeriesApi<'Line'> | null>(null);
  const macdHistRef = useRef<ISeriesApi<'Histogram'> | null>(null);

  const overlayData = useMemo(() => [...overlays, ...userAnnotations], [overlays, userAnnotations]);

  useEffect(() => {
    interactionRef.current = {
      drawingTool,
      onAddAnnotation,
      onCompleteDrawing,
      onLoadMore,
      canLoadMore,
      isLoadingMore,
    };
  }, [drawingTool, onAddAnnotation, onCompleteDrawing, onLoadMore, canLoadMore, isLoadingMore]);

  useEffect(() => {
    if (!mainContainerRef.current) return;
    const chart = createChart(mainContainerRef.current, {
      height: mainContainerRef.current.clientHeight,
      localization: {
        priceFormatter: (price: number) => price.toFixed(2),
      },
    });
    applyPaneTheme(chart);
    mainChartRef.current = chart;

    const candles = chart.addCandlestickSeries({
      upColor: UP_COLOR,
      downColor: DOWN_COLOR,
      borderVisible: false,
      wickUpColor: UP_COLOR,
      wickDownColor: DOWN_COLOR,
    });
    candleSeriesRef.current = candles;

    const volume = chart.addHistogramSeries({
      priceScaleId: '',
      priceFormat: { type: 'volume' },
      base: 0,
    });
    volumeSeriesRef.current = volume;
    chart.priceScale('').applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });

    ema20Ref.current = chart.addLineSeries({ color: '#fbbf24', lineWidth: 2 });
    ema50Ref.current = chart.addLineSeries({ color: '#19AAE5', lineWidth: 2 });
    ema200Ref.current = chart.addLineSeries({ color: '#e2e8f0', lineWidth: 2 });
    atrRef.current = chart.addLineSeries({ color: '#fb7185', lineWidth: 1, priceScaleId: 'atr' });
    chart.priceScale('atr').applyOptions({ scaleMargins: { top: 0.84, bottom: 0 }, borderVisible: false });

    const tooltip = tooltipRef.current;
    chart.subscribeCrosshairMove((param) => {
      if (!tooltip || !param.time || !param.seriesData) return;
      const candle = param.seriesData.get(candles) as { open: number; high: number; low: number; close: number } | undefined;
      if (!candle) return;
      tooltip.innerHTML = `O ${candle.open.toFixed(2)}<span class="mx-2 text-slate-500">|</span>H ${candle.high.toFixed(2)}<span class="mx-2 text-slate-500">|</span>L ${candle.low.toFixed(2)}<span class="mx-2 text-slate-500">|</span>C ${candle.close.toFixed(2)}`;
    });

    chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      const { canLoadMore: canLoad, isLoadingMore: loadingMore, onLoadMore: loadMore } = interactionRef.current;
      if (!range || !canLoad || loadingMore) return;
      if (range.from < 10) loadMore();
    });

    chart.subscribeClick((param) => {
      const { drawingTool: activeTool, onAddAnnotation: addAnnotation, onCompleteDrawing: complete } = interactionRef.current;
      if (activeTool === 'none') return;
      if (!param.time || !param.point) return;
      const price = candles.coordinateToPrice(param.point.y);
      if (price === null) return;
      const point: OverlayAnnotation = {
        type: activeTool === 'trendline' ? 'trendline' : activeTool === 'rect' ? 'rect' : activeTool,
        t1: param.time as number,
        p1: price,
      };
      if (activeTool === 'hline') {
        addAnnotation({ type: 'hline', price, label: 'Manual' });
        complete();
        return;
      }
      if (activeTool === 'vline') {
        addAnnotation({ type: 'vline', time: param.time as number, label: 'Manual' });
        complete();
        return;
      }
      const pending = pendingPointsRef.current;
      if (pending.length === 0) {
        pendingPointsRef.current = [point];
        return;
      }
      const first = pending[0];
      addAnnotation({
        type: activeTool === 'trendline' ? 'trendline' : 'rect',
        t1: first.t1,
        t2: param.time as number,
        p1: first.p1,
        p2: price,
        label: 'Manual',
      });
      pendingPointsRef.current = [];
      complete();
    });

    const resizeObserver = new ResizeObserver(() => {
      if (!mainContainerRef.current || !mainChartRef.current) return;
      mainChartRef.current.applyOptions({ height: mainContainerRef.current.clientHeight });
    });
    resizeObserver.observe(mainContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
    };
  }, []);

  useEffect(() => {
    hasFittedRef.current = false;
  }, [resetKey]);

  useEffect(() => {
    const chart = mainChartRef.current;
    const candles = candleSeriesRef.current;
    const volume = volumeSeriesRef.current;
    if (!chart || !candles || !volume) return;

    candles.setData(
      bars.map((bar) => ({
        time: bar.t as UTCTimestamp,
        open: bar.o,
        high: bar.h,
        low: bar.l,
        close: bar.c,
      })),
    );
    volume.setData(
      bars.map((bar) => ({
        time: bar.t as UTCTimestamp,
        value: bar.v,
        color: bar.c >= bar.o ? 'rgba(52, 211, 153, 0.5)' : 'rgba(251, 113, 133, 0.5)',
      })),
    );

    if (bars.length > 10 && !hasFittedRef.current) {
      chart.timeScale().fitContent();
      hasFittedRef.current = true;
    }
  }, [bars]);

  useEffect(() => {
    if (!ema20Ref.current || !ema50Ref.current || !ema200Ref.current || !atrRef.current) return;
    ema20Ref.current.setData(indicatorState.ema20 ? buildLineData(indicators.ema20) : []);
    ema50Ref.current.setData(indicatorState.ema50 ? buildLineData(indicators.ema50) : []);
    ema200Ref.current.setData(indicatorState.ema200 ? buildLineData(indicators.ema200) : []);
    atrRef.current.setData(indicatorState.atr ? buildLineData(indicators.atr14) : []);
  }, [indicators, indicatorState.ema20, indicatorState.ema50, indicatorState.ema200, indicatorState.atr]);

  useEffect(() => {
    if (!rsiContainerRef.current) return;
    if (indicatorState.rsi && !rsiChart) {
      const chart = createChart(rsiContainerRef.current, { height: rsiContainerRef.current.clientHeight });
      applyPaneTheme(chart);
      chart.applyOptions({ timeScale: { visible: false, borderColor: BORDER_COLOR }, rightPriceScale: { borderColor: BORDER_COLOR } });
      rsiSeriesRef.current = chart.addLineSeries({ color: '#34d399', lineWidth: 2 });
      setRsiChart(chart);
    }
    if (!indicatorState.rsi && rsiChart) {
      rsiChart.remove();
      setRsiChart(null);
      rsiSeriesRef.current = null;
    }
  }, [indicatorState.rsi, rsiChart]);

  useEffect(() => {
    if (!macdContainerRef.current) return;
    if (indicatorState.macd && !macdChart) {
      const chart = createChart(macdContainerRef.current, { height: macdContainerRef.current.clientHeight });
      applyPaneTheme(chart);
      chart.applyOptions({ timeScale: { visible: false, borderColor: BORDER_COLOR }, rightPriceScale: { borderColor: BORDER_COLOR } });
      macdSeriesRef.current = chart.addLineSeries({ color: '#19AAE5', lineWidth: 2 });
      macdSignalRef.current = chart.addLineSeries({ color: '#fbbf24', lineWidth: 2 });
      macdHistRef.current = chart.addHistogramSeries({ color: 'rgba(25, 170, 229, 0.55)' });
      setMacdChart(chart);
    }
    if (!indicatorState.macd && macdChart) {
      macdChart.remove();
      setMacdChart(null);
      macdSeriesRef.current = null;
      macdSignalRef.current = null;
      macdHistRef.current = null;
    }
  }, [indicatorState.macd, macdChart]);

  useEffect(() => {
    if (indicatorState.rsi && rsiSeriesRef.current) {
      rsiSeriesRef.current.setData(buildLineData(indicators.rsi14));
    }
  }, [indicatorState.rsi, indicators.rsi14]);

  useEffect(() => {
    if (indicatorState.macd && macdSeriesRef.current && macdSignalRef.current && macdHistRef.current) {
      macdSeriesRef.current.setData(buildLineData(indicators.macd));
      macdSignalRef.current.setData(buildLineData(indicators.macdSignal));
      macdHistRef.current.setData(
        (indicators.macdHist ?? []).map((point) => ({
          time: point.t as UTCTimestamp,
          value: point.v,
          color: point.v >= 0 ? 'rgba(52, 211, 153, 0.58)' : 'rgba(251, 113, 133, 0.58)',
        })),
      );
    }
  }, [indicatorState.macd, indicators.macd, indicators.macdSignal, indicators.macdHist]);

  useEffect(() => {
    const chart = mainChartRef.current;
    if (!chart || !rsiChart) return;
    const handler = (range: Range<Time> | null) => {
      if (range) rsiChart.timeScale().setVisibleRange(range);
    };
    chart.timeScale().subscribeVisibleTimeRangeChange(handler);
    return () => chart.timeScale().unsubscribeVisibleTimeRangeChange(handler);
  }, [rsiChart]);

  useEffect(() => {
    const chart = mainChartRef.current;
    if (!chart || !macdChart) return;
    const handler = (range: Range<Time> | null) => {
      if (range) macdChart.timeScale().setVisibleRange(range);
    };
    chart.timeScale().subscribeVisibleTimeRangeChange(handler);
    return () => chart.timeScale().unsubscribeVisibleTimeRangeChange(handler);
  }, [macdChart]);

  return (
    <div className="relative h-full w-full overflow-hidden rounded-[24px] border border-slate-200/70 bg-white/75 shadow-[0_18px_40px_rgba(15,23,42,0.08)] backdrop-blur-xl">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-white/70 to-transparent" />
      <div className="flex h-full flex-col">
        <div className="relative flex-1">
          <div ref={mainContainerRef} className="chart-canvas w-full" />
          <div
            ref={tooltipRef}
            className="pointer-events-none absolute left-4 top-4 rounded-2xl border border-slate-200/70 bg-white/90 px-3 py-2 text-[11px] font-semibold text-text shadow-soft backdrop-blur-xl"
          />
          <div className="pointer-events-none absolute right-4 top-4 rounded-full border border-slate-200/70 bg-white/80 px-3 py-2 text-[10px] uppercase tracking-[0.28em] text-dim backdrop-blur-xl">
            {isLoadingMore ? 'Loading history' : canLoadMore ? 'Infinite bars ready' : 'History loaded'}
          </div>
          <OverlayLayer chart={mainChartRef.current} series={candleSeriesRef.current} annotations={overlayData} />
        </div>
        {indicatorState.rsi ? <div className="h-32 border-t border-slate-200/70 bg-white/70" ref={rsiContainerRef} /> : null}
        {indicatorState.macd ? <div className="h-32 border-t border-slate-200/70 bg-white/70" ref={macdContainerRef} /> : null}
      </div>
    </div>
  );
}
