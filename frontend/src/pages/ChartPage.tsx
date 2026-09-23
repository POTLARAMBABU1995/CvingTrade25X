import { useEffect, useMemo, useState, useTransition } from 'react';
import { motion } from 'framer-motion';
import { useMutation, useQuery } from '@tanstack/react-query';
import SymbolSearch from '../components/SymbolSearch';
import TimeframeSelector from '../components/TimeframeSelector';
import IndicatorToggles, { type IndicatorState } from '../components/IndicatorToggles';
import TVChart, { type DrawingTool } from '../components/TVChart';
import { BacktestPanel } from '../components/dashboard/BacktestPanel';
import { InsightsAccordion } from '../components/dashboard/InsightsAccordion';
import { KpiCard } from '../components/dashboard/KpiCard';
import { MoversTable } from '../components/dashboard/MoversTable';
import { SectorHeatmap } from '../components/dashboard/SectorHeatmap';
import { StrategyShelf } from '../components/dashboard/StrategyShelf';
import { WatchlistRail } from '../components/dashboard/WatchlistRail';
import { AsyncStateBoundary } from '../components/ui/AsyncStateBoundary';
import { Button } from '../components/ui/Button';
import { DataBadge } from '../components/ui/DataBadge';
import { FilterBar } from '../components/ui/FilterBar';
import { SectionHeading } from '../components/ui/SectionHeading';
import { SkeletonBlock } from '../components/ui/SkeletonBlock';
import { SkeletonCards } from '../components/ui/SkeletonCards';
import { Surface } from '../components/ui/Surface';
import { fetchUserAnnotations, upsertUserAnnotations } from '../api/annotations';
import { fetchIndicators } from '../api/indicators';
import { fetchOverlays } from '../api/overlays';
import { useInfiniteBars } from '../hooks/useInfiniteBars';
import { epochToDateString } from '../utils/range';
import type { IndicatorPoint, KpiCard as KpiCardModel, OverlayAnnotation, Timeframe } from '../types';
import { ChartIcon, LabIcon, LayersIcon, RadarIcon, SparkIcon } from '../components/ui/Icons';

const DEFAULT_SYMBOL = 'RELIANCE';
const USER_ID = 1;
const DRAWING_TOOLS: DrawingTool[] = ['hline', 'vline', 'trendline', 'rect'];

const SECTION_REVEAL = {
  initial: { opacity: 0, y: 18 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, amount: 0.18 },
  transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] as const },
};

type ChartPageProps = {
  onSaved?: () => void;
};

function formatPrice(value?: number) {
  if (value === undefined || Number.isNaN(value)) {
    return '--';
  }

  return new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: value > 999 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatSignedPrice(value?: number) {
  if (value === undefined || Number.isNaN(value)) {
    return '--';
  }

  const sign = value >= 0 ? '+' : '';
  return `${sign}${formatPrice(value)}`;
}

function formatSignedPercent(value?: number) {
  if (value === undefined || Number.isNaN(value)) {
    return '--';
  }

  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

function formatCompactNumber(value?: number) {
  if (value === undefined || Number.isNaN(value)) {
    return '--';
  }

  return new Intl.NumberFormat('en-IN', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
}

function getLatestPoint(series?: IndicatorPoint[]) {
  return series?.[series.length - 1]?.v;
}

function buildRegimeLabel(lastClose?: number, ema20?: number, ema50?: number, ema200?: number) {
  if ([lastClose, ema20, ema50, ema200].some((item) => item === undefined)) {
    return 'Waiting for full trend stack';
  }

  if (lastClose! > ema20! && ema20! > ema50! && ema50! > ema200!) {
    return 'Price above 20 / 50 / 200 EMA stack';
  }

  if (lastClose! < ema20! && ema20! < ema50! && ema50! < ema200!) {
    return 'Price below full EMA stack';
  }

  return 'Compression between major moving averages';
}

function buildMomentumLabel(rsi?: number, macd?: number) {
  if (rsi === undefined && macd === undefined) {
    return 'Enable RSI or MACD for momentum context';
  }

  if (rsi !== undefined && macd !== undefined) {
    if (rsi >= 55 && macd >= 0) {
      return 'Momentum confirms the trend impulse';
    }

    if (rsi <= 45 && macd < 0) {
      return 'Momentum remains defensive';
    }
  }

  if (rsi !== undefined) {
    return rsi >= 50 ? 'RSI holding above the balance line' : 'RSI below the balance line';
  }

  return macd !== undefined && macd >= 0 ? 'MACD remains above zero' : 'MACD remains below zero';
}

function buildSyncLabel(isTransitionPending: boolean, isSyncing: boolean, isSaving: boolean, hasError: boolean) {
  if (hasError) {
    return 'Feed attention required';
  }

  if (isSaving) {
    return 'Saving workspace';
  }

  if (isTransitionPending) {
    return 'Switching context';
  }

  if (isSyncing) {
    return 'Syncing market tape';
  }

  return 'Desk aligned';
}

export default function ChartPage({ onSaved }: ChartPageProps) {
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL);
  const [timeframe, setTimeframe] = useState<Timeframe>('1D');
  const [indicatorState, setIndicatorState] = useState<IndicatorState>({
    ema20: true,
    ema50: true,
    ema200: true,
    rsi: false,
    macd: false,
    atr: false,
  });
  const [drawingTool, setDrawingTool] = useState<DrawingTool>('none');
  const [userAnnotations, setUserAnnotations] = useState<OverlayAnnotation[]>([]);
  const [isTransitionPending, startTransition] = useTransition();

  useEffect(() => {
    setDrawingTool('none');
  }, [symbol, timeframe]);

  const barsQuery = useInfiniteBars({
    symbol,
    tf: timeframe,
    range: 'MAX',
    limit: 800,
  });

  const range = useMemo(() => {
    if (!barsQuery.bars.length) {
      return {
        from: 'MAX',
        to: 'Full history',
      };
    }

    return {
      from: epochToDateString(barsQuery.bars[0].t),
      to: epochToDateString(barsQuery.bars[barsQuery.bars.length - 1].t),
    };
  }, [barsQuery.bars]);

  const indicatorNames = useMemo(() => {
    const names: string[] = [];
    if (indicatorState.ema20) names.push('ema20');
    if (indicatorState.ema50) names.push('ema50');
    if (indicatorState.ema200) names.push('ema200');
    if (indicatorState.rsi) names.push('rsi14');
    if (indicatorState.macd) names.push('macd');
    if (indicatorState.atr) names.push('atr14');
    return names;
  }, [indicatorState]);

  const indicatorsQuery = useQuery({
    queryKey: ['indicators', symbol, timeframe, 'MAX', indicatorNames],
    queryFn: () => fetchIndicators({ symbol, tf: timeframe, names: indicatorNames, range: 'MAX' }),
    enabled: indicatorNames.length > 0 && barsQuery.bars.length > 0,
  });

  const overlaysQuery = useQuery({
    queryKey: ['overlays', symbol, timeframe, 'MAX'],
    queryFn: () => fetchOverlays({ symbol, tf: timeframe, range: 'MAX' }),
    enabled: barsQuery.bars.length > 0,
  });

  const annotationsQuery = useQuery({
    queryKey: ['annotations', USER_ID, symbol, timeframe],
    queryFn: () => fetchUserAnnotations({ userId: USER_ID, symbol, tf: timeframe }),
  });

  const saveMutation = useMutation({
    mutationFn: (payload: OverlayAnnotation[]) =>
      upsertUserAnnotations({ userId: USER_ID, symbol, tf: timeframe, annotations: payload }),
    onSuccess: (data) => {
      setUserAnnotations(data.annotations ?? []);
      onSaved?.();
    },
  });

  useEffect(() => {
    if (annotationsQuery.data?.annotations) {
      setUserAnnotations(annotationsQuery.data.annotations);
    }
  }, [annotationsQuery.data]);

  const indicatorSeries = indicatorsQuery.data?.series ?? {};
  const overlays = overlaysQuery.data?.annotations ?? [];

  const overlayStats = useMemo(
    () => ({
      zones: overlays.filter((item) => item.zoneType).length,
      patterns: overlays.filter((item) => item.patternType).length,
      lines: overlays.filter((item) => item.type === 'hline').length,
    }),
    [overlays],
  );

  const lastBar = barsQuery.bars[barsQuery.bars.length - 1];
  const previousBar = barsQuery.bars[barsQuery.bars.length - 2];
  const lastClose = lastBar?.c;
  const priceDelta = lastBar && previousBar ? lastBar.c - previousBar.c : undefined;
  const priceChangePercent = lastBar && previousBar ? ((lastBar.c - previousBar.c) / previousBar.c) * 100 : undefined;
  const ema20 = getLatestPoint(indicatorSeries.ema20);
  const ema50 = getLatestPoint(indicatorSeries.ema50);
  const ema200 = getLatestPoint(indicatorSeries.ema200);
  const atr14 = getLatestPoint(indicatorSeries.atr14);
  const rsi14 = getLatestPoint(indicatorSeries.rsi14);
  const macd = getLatestPoint(indicatorSeries.macd);

  const regimeLabel = useMemo(() => buildRegimeLabel(lastClose, ema20, ema50, ema200), [lastClose, ema20, ema50, ema200]);
  const momentumLabel = useMemo(() => buildMomentumLabel(rsi14, macd), [rsi14, macd]);

  const isSyncing = barsQuery.isFetching || indicatorsQuery.isFetching || overlaysQuery.isFetching;
  const hasError = Boolean(barsQuery.error || indicatorsQuery.error || overlaysQuery.error || annotationsQuery.error);
  const isChartBooting = (barsQuery.isPending || barsQuery.isFetching) && barsQuery.bars.length === 0;
  const syncLabel = buildSyncLabel(isTransitionPending, isSyncing, saveMutation.isPending, hasError);
  const timeframeLabel = timeframe === '1D' ? 'Session' : timeframe === '1W' ? 'Swing' : timeframe === '1M' ? 'Position' : 'Cycle';

  const kpiCards: KpiCardModel[] = [
    {
      id: 'spot-price',
      label: 'Spot price',
      value: formatPrice(lastClose),
      change: `${formatSignedPrice(priceDelta)} / ${formatSignedPercent(priceChangePercent)}`,
      trend: priceChangePercent !== undefined ? (priceChangePercent < 0 ? 'down' : 'up') : 'flat',
      tone: priceChangePercent !== undefined && priceChangePercent < 0 ? 'crimson' : 'cyan',
      icon: <ChartIcon className="h-5 w-5" />,
    },
    {
      id: 'signal-density',
      label: 'Signal density',
      value: `${overlayStats.zones + overlayStats.patterns}`,
      change: `${overlayStats.zones} zones, ${overlayStats.patterns} patterns`,
      tone: 'emerald',
      icon: <LayersIcon className="h-5 w-5" />,
    },
    {
      id: 'trend-regime',
      label: 'Trend regime',
      value: ema20 !== undefined && ema50 !== undefined ? `${formatPrice(ema20)} / ${formatPrice(ema50)}` : '--',
      change: regimeLabel,
      tone: 'amber',
      icon: <RadarIcon className="h-5 w-5" />,
    },
    {
      id: 'workspace-sync',
      label: 'Workspace sync',
      value: `${userAnnotations.length} drawings`,
      change: saveMutation.isPending ? 'Saving annotations now' : 'Manual save only, live feed preserved',
      status: saveMutation.isPending ? 'Saving' : 'Ready',
      tone: 'cyan',
      icon: <LabIcon className="h-5 w-5" />,
    },
  ];

  const statusRows = [
    { label: 'Bars cached', value: formatCompactNumber(barsQuery.bars.length), accent: 'text-text' },
    { label: 'Indicators active', value: `${indicatorNames.length}`, accent: 'text-cyan' },
    { label: 'Overlay objects', value: `${overlays.length}`, accent: 'text-emerald' },
    { label: 'ATR 14', value: atr14 !== undefined ? formatPrice(atr14) : '--', accent: 'text-amber' },
  ];

  const quickNotes = [
    `Momentum: ${momentumLabel}`,
    `Range loaded: ${range.from} to ${range.to}`,
    `Viewport mode: ${timeframeLabel}`,
  ];

  return (
    <div className="space-y-8 pb-10">
      <motion.section id="overview" {...SECTION_REVEAL} className="grid gap-6 2xl:grid-cols-[minmax(0,1.25fr)_minmax(0,0.95fr)]">
        <Surface className="perspective-soft p-6 md:p-7" glow>
          <div className="pointer-events-none absolute inset-0 bg-ambient-mesh opacity-60" />
          <div className="pointer-events-none absolute inset-x-0 top-0 h-48 bg-panel-glow opacity-40" />
          <div className="relative">
            <SectionHeading
              eyebrow="Market cockpit"
              title={`${symbol} intelligence deck`}
              subtitle="Premium charting, overlay intelligence, and decision-ready context composed on top of the existing CvingTrade25X market APIs."
              action={
                <FilterBar className="text-[10px] font-semibold uppercase tracking-[0.28em]">
                  <DataBadge>{syncLabel}</DataBadge>
                  <DataBadge tone="accent">{timeframe}</DataBadge>
                  <DataBadge>{range.from} to {range.to}</DataBadge>
                </FilterBar>
              }
            />

            <div className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
              <div className="space-y-4">
                <div>
                  <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.34em] text-dim">Symbol intake</p>
                  <SymbolSearch
                    value={symbol}
                    onSelect={(nextSymbol) => startTransition(() => setSymbol(nextSymbol))}
                  />
                </div>
                <div>
                  <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.34em] text-dim">Time horizon</p>
                  <TimeframeSelector
                    value={timeframe}
                    onChange={(nextTimeframe) => startTransition(() => setTimeframe(nextTimeframe))}
                  />
                </div>
              </div>

              <div className="rounded-[30px] border border-slate-200/70 bg-white/86 p-5 shadow-[0_24px_60px_rgba(15,23,42,0.08)] backdrop-blur-xl">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.34em] text-dim">Desk framing</p>
                    <h2 className="mt-2 text-[1.75rem] font-semibold tracking-[-0.05em] text-text">{formatPrice(lastClose)}</h2>
                  </div>
                  <span className={`rounded-full border px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.28em] ${hasError ? 'border-crimson/18 bg-crimson/10 text-crimson' : 'border-emerald/18 bg-emerald/10 text-emerald'}`}>
                    {hasError ? 'Attention' : 'Live'}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-6 text-muted">{regimeLabel}</p>
                <div className="mt-5 space-y-3">
                  {quickNotes.map((note) => (
                    <div key={note} className="rounded-[22px] border border-slate-200/70 bg-white/86 px-4 py-3 text-sm text-muted backdrop-blur-xl">
                      {note}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-6">
              <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.34em] text-dim">Signal stack</p>
              <IndicatorToggles value={indicatorState} onChange={setIndicatorState} />
            </div>
          </div>
        </Surface>

        <div className="grid gap-4 sm:grid-cols-2">
          {kpiCards.map((card) => (
            <KpiCard
              key={card.id}
              label={card.label}
              value={card.value}
              change={card.change}
              icon={card.icon}
              tone={card.tone}
            />
          ))}
        </div>
      </motion.section>

      <motion.section id="studio" {...SECTION_REVEAL} className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_360px]">
        <Surface className="overflow-hidden p-4 md:p-5" glow>
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200/70 px-1 pb-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.34em] text-dim">Chart studio</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-text">Multi-layer analysis workspace</h2>
              <p className="mt-2 text-sm leading-6 text-muted">Dense research controls, layered overlays, and manual annotations designed for fast scanning without touching the existing API contracts.</p>
            </div>
            <div className="flex flex-wrap gap-2 text-[10px] font-semibold uppercase tracking-[0.28em]">
              <span className="rounded-full border border-slate-200/70 bg-white/86 px-3 py-2 text-muted backdrop-blur-xl">{indicatorNames.length} indicators</span>
              <span className="rounded-full border border-slate-200/70 bg-white/86 px-3 py-2 text-muted backdrop-blur-xl">{overlays.length} overlays</span>
              <span className="rounded-full border border-slate-200/70 bg-white/86 px-3 py-2 text-muted backdrop-blur-xl">{userAnnotations.length} drawings</span>
            </div>
          </div>

          <div className="mt-5 h-[620px] md:h-[700px]">
            <AsyncStateBoundary
              isLoading={isChartBooting}
              isFetching={isSyncing && barsQuery.bars.length > 0}
              isError={hasError}
              isEmpty={barsQuery.bars.length === 0}
              errorMessage="Market context could not be assembled. Verify backend services and retry."
              onRetry={() => {
                barsQuery.refetch();
                indicatorsQuery.refetch();
                overlaysQuery.refetch();
                annotationsQuery.refetch();
              }}
              skeleton={
                <div className="grid h-full gap-3">
                  <SkeletonBlock className="h-[78%] rounded-[28px]" />
                  <SkeletonCards className="md:grid-cols-3" count={3} />
                </div>
              }
            >
              <TVChart
                resetKey={`${symbol}-${timeframe}`}
                bars={barsQuery.bars}
                indicators={indicatorSeries}
                overlays={overlays}
                userAnnotations={userAnnotations}
                indicatorState={indicatorState}
                onLoadMore={() => barsQuery.fetchNextPage()}
                canLoadMore={Boolean(barsQuery.hasNextPage)}
                isLoadingMore={barsQuery.isFetchingNextPage}
                drawingTool={drawingTool}
                onAddAnnotation={(annotation) => setUserAnnotations((previous) => [...previous, annotation])}
                onCompleteDrawing={() => setDrawingTool('none')}
              />
            </AsyncStateBoundary>
          </div>
        </Surface>

        <div className="space-y-5 xl:sticky xl:top-28 xl:self-start">
          <Surface className="p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.34em] text-dim">Session intelligence</p>
                <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-text">Signal readout</h3>
              </div>
              <span className={`rounded-full border px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.28em] ${hasError ? 'border-crimson/18 bg-crimson/10 text-crimson' : 'border-cyan/18 bg-cyan/10 text-cyan'}`}>
                {syncLabel}
              </span>
            </div>
            <div className="mt-5 space-y-3">
              {statusRows.map((row) => (
                <div key={row.label} className="flex items-center justify-between rounded-[22px] border border-slate-200/70 bg-white/86 px-4 py-3 text-sm backdrop-blur-xl">
                  <span className="text-muted">{row.label}</span>
                  <span className={`font-mono ${row.accent}`}>{row.value}</span>
                </div>
              ))}
            </div>
            <div className="mt-5 rounded-[24px] border border-slate-200/70 bg-gradient-to-br from-[rgb(var(--page-accent-rgb)/0.08)] to-white p-4 text-sm leading-6 text-muted backdrop-blur-xl">
              {momentumLabel}
            </div>
          </Surface>

          <Surface className="p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.34em] text-dim">Drawing rail</p>
                <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-text">Manual markup tools</h3>
              </div>
              <span className="rounded-full border border-slate-200/70 bg-white/86 px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.28em] text-muted backdrop-blur-xl">
                On chart
              </span>
            </div>
            <div className="mt-5 grid gap-2">
              {DRAWING_TOOLS.map((tool) => {
                const active = drawingTool === tool;
                return (
                  <Button
                    key={tool}
                    variant={active ? 'secondary' : 'chip'}
                    fullWidth
                    className={`justify-start rounded-[22px] px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.28em] ${
                      active
                        ? 'border-cyan/22 bg-cyan/10 text-text shadow-soft'
                        : 'border-slate-200/70 bg-white/82 text-muted hover:border-[rgb(var(--page-accent-rgb)/0.18)] hover:text-text'
                    }`}
                    onClick={() => setDrawingTool(tool)}
                  >
                    {tool}
                  </Button>
                );
              })}
              <Button
                variant="danger"
                fullWidth
                className="justify-start rounded-[22px] border-slate-200/70 bg-white/82 px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.28em] text-muted hover:border-crimson/22 hover:bg-crimson/8 hover:text-crimson"
                onClick={() => {
                  setDrawingTool('none');
                  setUserAnnotations([]);
                }}
              >
                Clear drawings
              </Button>
            </div>
          </Surface>

          <Surface className="p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.34em] text-dim">Workspace sync</p>
                <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-text">Save annotation state</h3>
              </div>
              <SparkIcon className="h-5 w-5 text-cyan" />
            </div>
            <p className="mt-3 text-sm leading-6 text-muted">Saving is explicit and scoped to user annotations only. Live bars, indicators, and overlays continue using the existing backend-driven data flow.</p>
            <Button
              variant="primary"
              fullWidth
              loading={saveMutation.isPending}
              className="mt-5 rounded-[22px] bg-gradient-to-r from-cyan via-cyan/80 to-emerald px-4 py-3 text-sm font-semibold text-slate-950 transition hover:brightness-110"
              onClick={() => saveMutation.mutate(userAnnotations)}
            >
              {saveMutation.isPending ? 'Saving workspace...' : 'Save annotations'}
            </Button>
            <div className="mt-4 flex items-center justify-between text-xs uppercase tracking-[0.24em] text-dim">
              <span>{annotationsQuery.isFetching ? 'Loading saved drawings' : 'Saved layout ready'}</span>
              <span>{formatCompactNumber(userAnnotations.length)}</span>
            </div>
          </Surface>
        </div>
      </motion.section>

      <motion.section id="strategies" {...SECTION_REVEAL} className="space-y-5">
        <SectionHeading
          eyebrow="Strategies"
          title="Decision shelves for momentum, compression, and defensive rotation"
          subtitle="Reusable cards frame the main playbooks so dense market data still scans like a premium product rather than a crowded admin panel."
        />
        <StrategyShelf />
      </motion.section>

      <motion.section id="rotation" {...SECTION_REVEAL} className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <div className="space-y-5">
          <SectionHeading
            eyebrow="Sector pulse"
            title="Leadership is surfaced as an at-a-glance rotation map"
            subtitle="Sector intensity, regime shifts, and portfolio context are framed inside premium containers with restrained depth and clean contrast."
          />
          <SectorHeatmap />
        </div>
        <div id="backtest" className="space-y-5">
          <SectionHeading
            eyebrow="Backtest"
            title="Execution quality remains visible beside live research"
            subtitle="Historical edge, drawdown framing, and holding-period context sit next to the live workspace so decisions stay grounded."
          />
          <BacktestPanel />
        </div>
      </motion.section>

      <motion.section id="watchlist" {...SECTION_REVEAL} className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_360px]">
        <div className="space-y-5">
          <SectionHeading
            eyebrow="Market pulse"
            title="Movers and watchlists are structured for rapid scanning"
            subtitle="Tables stay compact and readable, while shortlist panels highlight the names worth attention without sacrificing hierarchy."
          />
          <MoversTable />
          <InsightsAccordion />
        </div>
        <div className="space-y-5">
          <WatchlistRail />
        </div>
      </motion.section>
    </div>
  );
}
