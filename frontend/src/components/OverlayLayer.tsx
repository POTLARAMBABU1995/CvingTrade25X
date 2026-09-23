import { useEffect, useRef } from 'react';
import type { IChartApi, ISeriesApi, UTCTimestamp } from 'lightweight-charts';
import type { OverlayAnnotation } from '../types';

export type OverlayLayerProps = {
  chart: IChartApi | null;
  series: ISeriesApi<'Candlestick'> | null;
  annotations: OverlayAnnotation[];
};

const COLORS = {
  demand: 'rgba(52, 211, 153, 0.16)',
  supply: 'rgba(251, 113, 133, 0.16)',
  sr: 'rgba(25, 170, 229, 0.56)',
  fib: 'rgba(251, 191, 36, 0.58)',
  pattern: 'rgba(147, 197, 253, 0.16)',
  text: '#dbe7f5',
  edge: 'rgba(226, 232, 240, 0.24)',
};
const LABEL_FONT = '12px "IBM Plex Sans", sans-serif';

function resolveRectColor(annotation: OverlayAnnotation) {
  if (annotation.zoneType?.toUpperCase() === 'DEMAND') return COLORS.demand;
  if (annotation.zoneType?.toUpperCase() === 'SUPPLY') return COLORS.supply;
  if (annotation.patternType) return COLORS.pattern;
  return COLORS.sr;
}

export default function OverlayLayer({ chart, series, annotations }: OverlayLayerProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const annotationsRef = useRef<OverlayAnnotation[]>(annotations);
  const drawRef = useRef<() => void>(() => {});

  useEffect(() => {
    annotationsRef.current = annotations;
    drawRef.current();
  }, [annotations]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!chart || !series || !canvas) return;
    const container = canvas.parentElement;
    if (!container) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resize = () => {
      canvas.width = container.clientWidth;
      canvas.height = container.clientHeight;
      draw();
    };

    const drawLine = (x1: number, y1: number, x2: number, y2: number, color: string, width = 1) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    };

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const timeScale = chart.timeScale();

      annotationsRef.current.forEach((annotation) => {
        if (annotation.type === 'meta') return;

        if (annotation.type === 'rect' && annotation.t1 && annotation.t2 && annotation.p1 !== undefined && annotation.p2 !== undefined) {
          const x1 = timeScale.timeToCoordinate(annotation.t1 as UTCTimestamp);
          const x2 = timeScale.timeToCoordinate(annotation.t2 as UTCTimestamp);
          const y1 = series.priceToCoordinate(annotation.p1) ?? null;
          const y2 = series.priceToCoordinate(annotation.p2) ?? null;
          if (x1 === null || x2 === null || y1 === null || y2 === null) return;
          const left = Math.min(x1, x2);
          const top = Math.min(y1, y2);
          const width = Math.abs(x2 - x1);
          const height = Math.abs(y2 - y1);
          ctx.fillStyle = resolveRectColor(annotation);
          ctx.fillRect(left, top, width, height);
          ctx.strokeStyle = COLORS.edge;
          ctx.strokeRect(left, top, width, height);
          if (annotation.label) {
            ctx.fillStyle = COLORS.text;
            ctx.font = LABEL_FONT;
            ctx.fillText(annotation.label, left + 8, top + 16);
          }
          return;
        }

        if (annotation.type === 'hline' && annotation.price !== undefined) {
          const y = series.priceToCoordinate(annotation.price) ?? null;
          if (y === null) return;
          drawLine(0, y, canvas.width, y, annotation.style === 'dashed' ? COLORS.fib : COLORS.sr, 1.4);
          if (annotation.label) {
            ctx.fillStyle = COLORS.text;
            ctx.font = LABEL_FONT;
            ctx.fillText(annotation.label, 10, y - 6);
          }
          return;
        }

        if (annotation.type === 'vline' && annotation.time) {
          const x = timeScale.timeToCoordinate(annotation.time as UTCTimestamp);
          if (x === null) return;
          drawLine(x, 0, x, canvas.height, 'rgba(148, 163, 184, 0.3)');
          if (annotation.label) {
            ctx.fillStyle = COLORS.text;
            ctx.font = LABEL_FONT;
            ctx.fillText(annotation.label, x + 8, 16);
          }
          return;
        }

        if (annotation.type === 'trendline' && annotation.t1 && annotation.t2 && annotation.p1 !== undefined && annotation.p2 !== undefined) {
          const x1 = timeScale.timeToCoordinate(annotation.t1 as UTCTimestamp);
          const x2 = timeScale.timeToCoordinate(annotation.t2 as UTCTimestamp);
          const y1 = series.priceToCoordinate(annotation.p1) ?? null;
          const y2 = series.priceToCoordinate(annotation.p2) ?? null;
          if (x1 === null || x2 === null || y1 === null || y2 === null) return;
          drawLine(x1, y1, x2, y2, COLORS.sr, 1.6);
          if (annotation.label) {
            ctx.fillStyle = COLORS.text;
            ctx.font = LABEL_FONT;
            ctx.fillText(annotation.label, x2 + 8, y2);
          }
          return;
        }

        if (annotation.type === 'marker' && annotation.time && annotation.price !== undefined) {
          const x = timeScale.timeToCoordinate(annotation.time as UTCTimestamp);
          const y = series.priceToCoordinate(annotation.price) ?? null;
          if (x === null || y === null) return;
          ctx.fillStyle = annotation.shape === 'arrowDown' ? COLORS.supply : COLORS.demand;
          ctx.beginPath();
          ctx.arc(x, y, 4.5, 0, Math.PI * 2);
          ctx.fill();
        }
      });
    };

    const handleRangeChange = () => draw();
    chart.timeScale().subscribeVisibleTimeRangeChange(handleRangeChange);

    const resizeObserver = new ResizeObserver(() => resize());
    resizeObserver.observe(container);
    resize();
    drawRef.current = draw;

    return () => {
      chart.timeScale().unsubscribeVisibleTimeRangeChange(handleRangeChange);
      resizeObserver.disconnect();
    };
  }, [chart, series]);

  return <canvas ref={canvasRef} style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }} />;
}
