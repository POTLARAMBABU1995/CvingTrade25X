import { startTransition, useDeferredValue, useEffect, useMemo, useState } from 'react';
import { AppDataTable, type AppDataTableColumn, type AppSortState } from '../../components/app/AppDataTable';
import { CopyDiagnosticsButton } from '../../components/CopyDiagnosticsButton';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { ErrorState } from '../../components/ui/ErrorState';
import { Input } from '../../components/ui/Input';
import { PageHeader } from '../../components/ui/PageHeader';
import { Select } from '../../components/ui/Select';
import { SkeletonCards } from '../../components/ui/SkeletonCards';
import { SkeletonTable } from '../../components/ui/SkeletonTable';
import { cn } from '../../lib/cn';
import {
  fetchAsuraV3CostSummary,
  fetchAsuraV3DashboardSummary,
  fetchAsuraV3Health,
  fetchAsuraV3LatestSignals,
  fetchAsuraV3RiskSummary,
  fetchAsuraV3SymbolRatings,
  fetchAsuraV3YearlySummary,
  normalizeAsuraV3Error,
} from '../../services/asuraV3Service';
import type {
  AsuraV3CostSummaryRow,
  AsuraV3DashboardSummary,
  AsuraV3HealthPayload,
  AsuraV3LatestSignalRow,
  AsuraV3LatestSignalsResponse,
  AsuraV3RiskSummaryRow,
  AsuraV3SymbolRatingRow,
  AsuraV3YearlySummaryRow,
} from '../../types/asuraV3';
import { StrategyMigrationLayout } from './StrategyMigrationLayout';

const PAGE_SIZE = 25;
const DEFAULT_SORT: AppSortState = { key: 'signalDate', direction: 'desc' };

const RATING_FILTER_OPTIONS = [
  { label: 'Eligible (Premium/Strong/Normal)', value: 'ELIGIBLE' },
  { label: 'All Ratings', value: 'ALL' },
  { label: 'PREMIUM', value: 'PREMIUM' },
  { label: 'STRONG', value: 'STRONG' },
  { label: 'NORMAL', value: 'NORMAL' },
  { label: 'WEAK', value: 'WEAK' },
  { label: 'AVOID', value: 'AVOID' },
] as const;

const SORT_COLUMN_MAP: Record<string, string> = {
  adx14: 'ADX14',
  athGapPct: 'ATH_GAP_PCT',
  athPrice: 'ATH_PRICE',
  atrPercent: 'ATR_PERCENT',
  emaStack: 'EMA_STACK',
  entryPrice: 'ENTRY_PRICE',
  macdHist: 'MACD_HIST',
  move1dPct: 'MOVE_1D_PCT',
  move1mPct: 'MOVE_1M_PCT',
  move1wPct: 'MOVE_1W_PCT',
  price: 'PRICE',
  resistanceGapPct: 'RESISTANCE_GAP_PCT',
  riskAtr: 'RISK_ATR',
  rsi14: 'RSI14',
  rsiPrev1d: 'RSI_PREV_1D',
  rsiPrev5d: 'RSI_PREV_5D',
  signalDate: 'SIGNAL_DATE',
  signalGrade: 'SIGNAL_GRADE',
  signalScore: 'SIGNAL_SCORE',
  stopLoss: 'STOP_LOSS',
  supportGapPct: 'SUPPORT_GAP_PCT',
  symbol: 'SYMBOL',
  symbolRating: 'SYMBOL_RATING',
  target1R: 'TARGET_1R',
  trendDirection: 'TREND_DIRECTION',
  volumeRatio20: 'VOLUME_RATIO_20',
};

type LatestSignalViewRow = AsuraV3LatestSignalRow & {
  rrrComputed: number | null;
  serialNo: number;
};

const EMPTY_LATEST: AsuraV3LatestSignalsResponse = {
  items: [],
  limit: PAGE_SIZE,
  offset: 0,
  total: 0,
};

function formatNumber(value: number | null, digits = 2): string {
  if (value === null || !Number.isFinite(value)) return '-';
  return value.toLocaleString('en-IN', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function formatInteger(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '-';
  return Math.trunc(value).toLocaleString('en-IN');
}

function formatPercent(value: number | null, digits = 2): string {
  if (value === null || !Number.isFinite(value)) return '-';
  return `${formatNumber(value, digits)}%`;
}

function formatDate(value: string | null): string {
  const text = String(value || '').trim();
  if (!text) return '-';
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  const month = date.toLocaleString('en-IN', { month: 'short' }).toUpperCase();
  const day = String(date.getDate()).padStart(2, '0');
  return `${day}-${month}-${date.getFullYear()}`;
}

function formatDateTime(value: string | null): string {
  const text = String(value || '').trim();
  if (!text) return '-';
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  const datePart = formatDate(text);
  const timePart = date.toLocaleTimeString('en-IN', { hour12: false });
  return `${datePart} ${timePart}`;
}

function formatLoadTime(ms: number | null): string {
  if (!Number.isFinite(ms ?? NaN) || (ms ?? 0) < 0) return '-';
  if ((ms ?? 0) < 1000) return `${Math.round(ms ?? 0)} ms`;
  return `${((ms ?? 0) / 1000).toFixed(2)} s`;
}

function computeRrr(row: AsuraV3LatestSignalRow): number | null {
  if (
    row.entryPrice === null
    || row.stopLoss === null
    || row.target1R === null
  ) {
    const parsed = Number(row.rrrRaw);
    return Number.isFinite(parsed) ? parsed : null;
  }
  const risk = row.entryPrice - row.stopLoss;
  if (!Number.isFinite(risk) || risk <= 0) return null;
  const reward = row.target1R - row.entryPrice;
  const ratio = reward / risk;
  return Number.isFinite(ratio) ? ratio : null;
}

function formatRrr(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '-';
  if (Math.abs(value - 1) <= 0.015) return '1:1';
  return `${value.toFixed(2)}:1`;
}

function formatDateRange(startDate: string | null, endDate: string | null): string {
  const start = formatDate(startDate);
  const end = formatDate(endDate);
  if (start === '-' && end === '-') return '-';
  return `${start} to ${end}`;
}

function ratingTone(value: string): string {
  const token = String(value || '').toUpperCase();
  if (token === 'PREMIUM') return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200';
  if (token === 'STRONG') return 'bg-cyan-100 text-cyan-800 dark:bg-cyan-950/40 dark:text-cyan-200';
  if (token === 'NORMAL') return 'bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200';
  if (token === 'WEAK') return 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200';
  if (token === 'AVOID') return 'bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-200';
  return 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200';
}

function writeCsv(filename: string, header: readonly string[], rows: readonly LatestSignalViewRow[]) {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const escape = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  const lines: string[] = [header.map(escape).join(',')];
  rows.forEach((row) => {
    lines.push([
      row.serialNo,
      row.symbol,
      row.signalDate || '',
      row.symbolRating,
      row.price ?? '',
      row.entryPrice ?? '',
      row.stopLoss ?? '',
      row.target1R ?? '',
      formatRrr(row.rrrComputed),
      row.signalScore ?? '',
      row.signalGrade,
      row.rsi14 ?? '',
      row.rsiPrev1d ?? '',
      row.rsiPrev5d ?? '',
      row.macdHist ?? '',
      row.adx14 ?? '',
      row.atrPercent ?? '',
      row.riskAtr ?? '',
      row.volumeRatio20 ?? '',
      row.move1dPct ?? '',
      row.move1wPct ?? '',
      row.move1mPct ?? '',
      row.supportGapPct ?? '',
      row.resistanceGapPct ?? '',
      row.trendDirection,
      row.emaStack,
      row.athPrice ?? '',
      row.athGapPct ?? '',
    ].map(escape).join(','));
  });

  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

function RefreshIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M20 6v5h-5" />
      <path d="M4 18v-5h5" />
      <path d="M5 11a7 7 0 0 1 12.1-4.9L20 9" />
      <path d="M19 13a7 7 0 0 1-12.1 4.9L4 15" />
    </svg>
  );
}

function DownloadIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M12 4v11" />
      <path d="m7 10 5 5 5-5" />
      <path d="M4 20h16" />
    </svg>
  );
}

function KpiCard({ label, value, tone }: { label: string; value: string; tone: 'good' | 'muted' | 'risk' | 'strong' }) {
  const toneClass = tone === 'good'
    ? 'border-emerald-200/80 bg-emerald-50/80 dark:border-emerald-700/60 dark:bg-emerald-950/30'
    : tone === 'risk'
      ? 'border-rose-200/80 bg-rose-50/75 dark:border-rose-800/60 dark:bg-rose-950/25'
      : tone === 'strong'
        ? 'border-cyan-200/80 bg-cyan-50/80 dark:border-cyan-700/60 dark:bg-cyan-950/30'
        : 'border-slate-200/80 bg-white/85 dark:border-slate-700/70 dark:bg-slate-900/82';

  return (
    <Card variant="light" padding="md" className={cn('rounded-2xl', toneClass)}>
      <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-2 text-2xl font-black tracking-tight text-slate-950 dark:text-slate-100">{value}</p>
    </Card>
  );
}

function SectionTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">{title}</h2>
      {subtitle ? <p className="text-sm text-slate-500 dark:text-slate-400">{subtitle}</p> : null}
    </div>
  );
}

export function AsuraV3StrategyPage() {
  const [dashboardSummary, setDashboardSummary] = useState<AsuraV3DashboardSummary | null>(null);
  const [yearlyRows, setYearlyRows] = useState<AsuraV3YearlySummaryRow[]>([]);
  const [costRows, setCostRows] = useState<AsuraV3CostSummaryRow[]>([]);
  const [riskRows, setRiskRows] = useState<AsuraV3RiskSummaryRow[]>([]);
  const [symbolRatingRows, setSymbolRatingRows] = useState<AsuraV3SymbolRatingRow[]>([]);
  const [health, setHealth] = useState<AsuraV3HealthPayload | null>(null);

  const [latestSignals, setLatestSignals] = useState<AsuraV3LatestSignalsResponse>(EMPTY_LATEST);
  const [sortState, setSortState] = useState<AppSortState>(DEFAULT_SORT);
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [ratingFilter, setRatingFilter] = useState<string>('ELIGIBLE');
  const [gradeFilter, setGradeFilter] = useState<string>('ALL');
  const [gradeOptions, setGradeOptions] = useState<string[]>([]);
  const [page, setPage] = useState(1);

  const [overviewLoading, setOverviewLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(true);
  const [overviewError, setOverviewError] = useState('');
  const [tableError, setTableError] = useState('');
  const [exporting, setExporting] = useState(false);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [lastApiLoadTimeMs, setLastApiLoadTimeMs] = useState<number | null>(null);
  const [lastApiLoadedAt, setLastApiLoadedAt] = useState<Date | null>(null);

  const isBusy = overviewLoading || tableLoading;

  useEffect(() => {
    const controller = new AbortController();
    const startedAt = performance.now();
    setOverviewLoading(true);
    setOverviewError('');

    Promise.all([
      fetchAsuraV3DashboardSummary({ signal: controller.signal }),
      fetchAsuraV3YearlySummary({ signal: controller.signal }),
      fetchAsuraV3CostSummary({ signal: controller.signal }),
      fetchAsuraV3RiskSummary({ signal: controller.signal }),
      fetchAsuraV3SymbolRatings({ signal: controller.signal }),
      fetchAsuraV3Health({ signal: controller.signal }),
    ])
      .then(([summary, yearly, cost, risk, ratings, status]) => {
        if (controller.signal.aborted) return;
        startTransition(() => {
          setDashboardSummary(summary);
          setYearlyRows(yearly);
          setCostRows(cost);
          setRiskRows(risk);
          setSymbolRatingRows(ratings);
          setHealth(status);
        });
        setLastApiLoadTimeMs(Math.max(0, Math.round(performance.now() - startedAt)));
        setLastApiLoadedAt(new Date());
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setOverviewError(normalizeAsuraV3Error(error, 'Asura V3 overview is unavailable right now. Please retry.'));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setOverviewLoading(false);
        }
      });

    return () => controller.abort();
  }, [refreshVersion]);

  useEffect(() => {
    setPage(1);
  }, [deferredSearch, gradeFilter, ratingFilter]);

  useEffect(() => {
    const controller = new AbortController();
    const startedAt = performance.now();
    setTableLoading(true);
    setTableError('');

    fetchAsuraV3LatestSignals(
      {
        q: deferredSearch.trim() || undefined,
        rating: ratingFilter === 'ELIGIBLE' ? undefined : ratingFilter,
        grade: gradeFilter === 'ALL' ? undefined : gradeFilter,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
        sortBy: SORT_COLUMN_MAP[sortState.key || 'signalDate'] || 'SIGNAL_DATE',
        sortDir: sortState.direction ?? 'desc',
      },
      { signal: controller.signal },
    )
      .then((payload) => {
        if (controller.signal.aborted) return;
        setLatestSignals(payload);
        const nextOptions = Array.from(new Set(payload.items.map((item) => item.signalGrade).filter((value) => value))).sort();
        setGradeOptions((current) => Array.from(new Set([...current, ...nextOptions])).sort());
        setLastApiLoadTimeMs(Math.max(0, Math.round(performance.now() - startedAt)));
        setLastApiLoadedAt(new Date());
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setLatestSignals(EMPTY_LATEST);
        setTableError(normalizeAsuraV3Error(error, 'Asura V3 latest signals are unavailable right now. Please retry.'));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setTableLoading(false);
        }
      });

    return () => controller.abort();
  }, [deferredSearch, gradeFilter, page, ratingFilter, refreshVersion, sortState.direction, sortState.key]);

  const latestRows = useMemo<LatestSignalViewRow[]>(
    () => latestSignals.items.map((row, index) => ({
      ...row,
      rrrComputed: computeRrr(row),
      serialNo: latestSignals.offset + index + 1,
    })),
    [latestSignals.items, latestSignals.offset],
  );

  const latestSignalDate = dashboardSummary?.latestSignalDate || health?.latestSignalDate || null;
  const strategyName = dashboardSummary?.strategyName || 'ASURA_V3_3_HIGH_WIN_MODE';
  const strategyCode = dashboardSummary?.strategyCode || 'ASURA_V3_TECH';
  const runId = dashboardSummary?.runId || 'BT_ASURA_V3_TEST_28Y';

  const diagnosticsMessage = [
    `Strategy route: /app/strategy/asura-v3`,
    `Backend status: ${health?.dbReachable ? 'UP' : 'DOWN'}`,
    `Latest signal date: ${formatDate(latestSignalDate)}`,
    `Last API load time: ${formatLoadTime(lastApiLoadTimeMs)}`,
    `Last loaded at: ${lastApiLoadedAt ? formatDateTime(lastApiLoadedAt.toISOString()) : '-'}`,
  ].join('\n');

  const latestColumns = useMemo<Array<AppDataTableColumn<LatestSignalViewRow>>>(() => [
    {
      key: 'sNo',
      dataCol: 'sno',
      label: <span className="block text-center">S.NO</span>,
      sortType: 'number',
      getSortValue: (row) => row.serialNo,
      renderCell: (row) => <span className="block text-center font-semibold">{row.serialNo}</span>,
      sticky: true,
      stickyWidthPx: 88,
      sortable: false,
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'symbol',
      dataCol: 'symbol',
      label: <span>SYMBOL</span>,
      sortType: 'string',
      getSortValue: (row) => row.symbol,
      renderCell: (row) => <span className="font-semibold">{row.symbol || '-'}</span>,
      sticky: true,
      stickyWidthPx: 190,
      cellClassName: 'whitespace-nowrap align-middle',
    },
    {
      key: 'signalDate',
      dataCol: 'signal_date',
      label: 'SIGNAL_DATE',
      sortType: 'date',
      getSortValue: (row) => row.signalDate || '',
      renderCell: (row) => formatDate(row.signalDate),
      cellClassName: 'whitespace-nowrap text-center',
    },
    {
      key: 'symbolRating',
      dataCol: 'symbol_rating',
      label: 'SYMBOL_RATING',
      sortType: 'string',
      getSortValue: (row) => row.symbolRating,
      renderCell: (row) => (
        <span className={cn('inline-flex rounded-full px-3 py-1 text-xs font-bold tracking-wide', ratingTone(row.symbolRating))}>
          {row.symbolRating || '-'}
        </span>
      ),
      cellClassName: 'text-center whitespace-nowrap',
    },
    {
      key: 'price',
      dataCol: 'price',
      label: 'PRICE',
      sortType: 'number',
      getSortValue: (row) => row.price ?? null,
      renderCell: (row) => formatNumber(row.price),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'entryPrice',
      dataCol: 'entry_price',
      label: 'ENTRY_PRICE',
      sortType: 'number',
      getSortValue: (row) => row.entryPrice ?? null,
      renderCell: (row) => formatNumber(row.entryPrice),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'stopLoss',
      dataCol: 'stop_loss',
      label: 'STOP_LOSS',
      sortType: 'number',
      getSortValue: (row) => row.stopLoss ?? null,
      renderCell: (row) => formatNumber(row.stopLoss),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'target1R',
      dataCol: 'target_1r',
      label: 'TARGET_1R',
      sortType: 'number',
      getSortValue: (row) => row.target1R ?? null,
      renderCell: (row) => formatNumber(row.target1R),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'rrr',
      dataCol: 'rrr',
      label: 'RRR',
      sortType: 'number',
      getSortValue: (row) => row.rrrComputed ?? null,
      renderCell: (row) => formatRrr(row.rrrComputed),
      cellClassName: 'text-center whitespace-nowrap',
    },
    {
      key: 'signalScore',
      dataCol: 'signal_score',
      label: 'SIGNAL_SCORE',
      sortType: 'number',
      getSortValue: (row) => row.signalScore ?? null,
      renderCell: (row) => formatNumber(row.signalScore, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'signalGrade',
      dataCol: 'signal_grade',
      label: 'SIGNAL_GRADE',
      sortType: 'string',
      getSortValue: (row) => row.signalGrade || '',
      renderCell: (row) => row.signalGrade || '-',
      cellClassName: 'text-center whitespace-nowrap',
    },
    {
      key: 'rsi14',
      dataCol: 'rsi14',
      label: 'RSI14',
      sortType: 'number',
      getSortValue: (row) => row.rsi14 ?? null,
      renderCell: (row) => formatNumber(row.rsi14, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'rsiPrev1d',
      dataCol: 'rsi_prev_1d',
      label: 'RSI_PREV_1D',
      sortType: 'number',
      getSortValue: (row) => row.rsiPrev1d ?? null,
      renderCell: (row) => formatNumber(row.rsiPrev1d, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'rsiPrev5d',
      dataCol: 'rsi_prev_5d',
      label: 'RSI_PREV_5D',
      sortType: 'number',
      getSortValue: (row) => row.rsiPrev5d ?? null,
      renderCell: (row) => formatNumber(row.rsiPrev5d, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'macdHist',
      dataCol: 'macd_hist',
      label: 'MACD_HIST',
      sortType: 'number',
      getSortValue: (row) => row.macdHist ?? null,
      renderCell: (row) => formatNumber(row.macdHist, 4),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'adx14',
      dataCol: 'adx14',
      label: 'ADX14',
      sortType: 'number',
      getSortValue: (row) => row.adx14 ?? null,
      renderCell: (row) => formatNumber(row.adx14, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'atrPercent',
      dataCol: 'atr_percent',
      label: 'ATR_PERCENT',
      sortType: 'number',
      getSortValue: (row) => row.atrPercent ?? null,
      renderCell: (row) => formatPercent(row.atrPercent, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'riskAtr',
      dataCol: 'risk_atr',
      label: 'RISK_ATR',
      sortType: 'number',
      getSortValue: (row) => row.riskAtr ?? null,
      renderCell: (row) => formatNumber(row.riskAtr, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'volumeRatio20',
      dataCol: 'volume_ratio_20',
      label: 'VOLUME_RATIO_20',
      sortType: 'number',
      getSortValue: (row) => row.volumeRatio20 ?? null,
      renderCell: (row) => formatNumber(row.volumeRatio20, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'move1dPct',
      dataCol: 'move_1d_pct',
      label: 'MOVE_1D_PCT',
      sortType: 'number',
      getSortValue: (row) => row.move1dPct ?? null,
      renderCell: (row) => formatPercent(row.move1dPct, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'move1wPct',
      dataCol: 'move_1w_pct',
      label: 'MOVE_1W_PCT',
      sortType: 'number',
      getSortValue: (row) => row.move1wPct ?? null,
      renderCell: (row) => formatPercent(row.move1wPct, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'move1mPct',
      dataCol: 'move_1m_pct',
      label: 'MOVE_1M_PCT',
      sortType: 'number',
      getSortValue: (row) => row.move1mPct ?? null,
      renderCell: (row) => formatPercent(row.move1mPct, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'supportGapPct',
      dataCol: 'support_gap_pct',
      label: 'SUPPORT_GAP_PCT',
      sortType: 'number',
      getSortValue: (row) => row.supportGapPct ?? null,
      renderCell: (row) => formatPercent(row.supportGapPct, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'resistanceGapPct',
      dataCol: 'resistance_gap_pct',
      label: 'RESISTANCE_GAP_PCT',
      sortType: 'number',
      getSortValue: (row) => row.resistanceGapPct ?? null,
      renderCell: (row) => formatPercent(row.resistanceGapPct, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'trendDirection',
      dataCol: 'trend_direction',
      label: 'TREND_DIRECTION',
      sortType: 'string',
      getSortValue: (row) => row.trendDirection || '',
      renderCell: (row) => row.trendDirection || '-',
      cellClassName: 'text-center whitespace-nowrap',
    },
    {
      key: 'emaStack',
      dataCol: 'ema_stack',
      label: 'EMA_STACK',
      sortType: 'string',
      getSortValue: (row) => row.emaStack || '',
      renderCell: (row) => row.emaStack || '-',
      cellClassName: 'text-center whitespace-nowrap',
    },
    {
      key: 'athPrice',
      dataCol: 'ath_price',
      label: 'ATH_PRICE',
      sortType: 'number',
      getSortValue: (row) => row.athPrice ?? null,
      renderCell: (row) => formatNumber(row.athPrice, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
    {
      key: 'athGapPct',
      dataCol: 'ath_gap_pct',
      label: 'ATH_GAP_PCT',
      sortType: 'number',
      getSortValue: (row) => row.athGapPct ?? null,
      renderCell: (row) => formatPercent(row.athGapPct, 2),
      cellClassName: 'text-right whitespace-nowrap',
    },
  ], []);

  const ratingMax = useMemo(
    () => symbolRatingRows.reduce((maxValue, row) => Math.max(maxValue, row.totalSymbols), 0),
    [symbolRatingRows],
  );

  const totalPages = Math.max(1, Math.ceil(Math.max(latestSignals.total, 0) / PAGE_SIZE));

  async function exportCurrentFilterToCsv() {
    setExporting(true);
    try {
      const batchRows: LatestSignalViewRow[] = [];
      let offset = 0;
      let total = 0;
      do {
        const payload = await fetchAsuraV3LatestSignals({
          q: deferredSearch.trim() || undefined,
          rating: ratingFilter === 'ELIGIBLE' ? undefined : ratingFilter,
          grade: gradeFilter === 'ALL' ? undefined : gradeFilter,
          limit: 200,
          offset,
          sortBy: SORT_COLUMN_MAP[sortState.key || 'signalDate'] || 'SIGNAL_DATE',
          sortDir: sortState.direction ?? 'desc',
        });
        total = payload.total;
        payload.items.forEach((row, index) => {
          batchRows.push({
            ...row,
            rrrComputed: computeRrr(row),
            serialNo: offset + index + 1,
          });
        });
        offset += payload.items.length;
      } while (offset < total);

      writeCsv('asura-v3-latest-signals.csv', [
        'S.NO',
        'SYMBOL',
        'SIGNAL_DATE',
        'SYMBOL_RATING',
        'PRICE',
        'ENTRY_PRICE',
        'STOP_LOSS',
        'TARGET_1R',
        'RRR',
        'SIGNAL_SCORE',
        'SIGNAL_GRADE',
        'RSI14',
        'RSI_PREV_1D',
        'RSI_PREV_5D',
        'MACD_HIST',
        'ADX14',
        'ATR_PERCENT',
        'RISK_ATR',
        'VOLUME_RATIO_20',
        'MOVE_1D_PCT',
        'MOVE_1W_PCT',
        'MOVE_1M_PCT',
        'SUPPORT_GAP_PCT',
        'RESISTANCE_GAP_PCT',
        'TREND_DIRECTION',
        'EMA_STACK',
        'ATH_PRICE',
        'ATH_GAP_PCT',
      ], batchRows);
    } catch (error) {
      setTableError(normalizeAsuraV3Error(error, 'Failed to export Asura V3 latest signals CSV.'));
    } finally {
      setExporting(false);
    }
  }

  return (
    <StrategyMigrationLayout activeStrategyPage="/app/strategy/asura-v3" fullWidth>
      <div className="space-y-6">
        <PageHeader
          title="Asura V3.3 High Win Mode"
          actions={(
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                disabled={isBusy}
                leadingIcon={<RefreshIcon className={cn('h-4 w-4', isBusy && 'animate-spin')} />}
                onClick={() => setRefreshVersion((current) => current + 1)}
              >
                {isBusy ? 'Refreshing...' : 'Refresh'}
              </Button>
              <CopyDiagnosticsButton compact={false} extraMessage={diagnosticsMessage} />
            </div>
          )}
        />

        <Card variant="light" padding="lg" className="space-y-5 rounded-2xl bg-[radial-gradient(circle_at_top_right,rgba(14,165,233,0.13),transparent_52%),radial-gradient(circle_at_bottom_left,rgba(16,185,129,0.10),transparent_40%)]">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-2">
              <p className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">{strategyName}</p>
              <h2 className="text-3xl font-black tracking-tight text-slate-950 dark:text-slate-100">28-year Oracle Backtested High-Win Swing Strategy</h2>
              <p className="text-sm text-slate-600 dark:text-slate-300">Final views only. No UI/API-triggered full historical recomputation.</p>
            </div>
            <span className={cn(
              'inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-bold',
              health?.dbReachable
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-700/60 dark:bg-emerald-950/35 dark:text-emerald-200'
                : 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800/60 dark:bg-rose-950/35 dark:text-rose-200',
            )}>
              <span className={cn('h-2.5 w-2.5 rounded-full', health?.dbReachable ? 'bg-emerald-500' : 'bg-rose-500')} />
              {health?.dbReachable ? 'Backend Live' : 'Backend Down'}
            </span>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border border-slate-200/80 bg-white/80 px-4 py-3 dark:border-slate-700/70 dark:bg-slate-900/75">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Latest Signal Date</p>
              <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{formatDate(latestSignalDate)}</p>
            </div>
            <div className="rounded-xl border border-slate-200/80 bg-white/80 px-4 py-3 dark:border-slate-700/70 dark:bg-slate-900/75">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Strategy Code</p>
              <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{strategyCode}</p>
            </div>
            <div className="rounded-xl border border-slate-200/80 bg-white/80 px-4 py-3 dark:border-slate-700/70 dark:bg-slate-900/75">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Run ID</p>
              <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{runId}</p>
            </div>
            <div className="rounded-xl border border-slate-200/80 bg-white/80 px-4 py-3 dark:border-slate-700/70 dark:bg-slate-900/75">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Last API Load Time</p>
              <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{formatLoadTime(lastApiLoadTimeMs)}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-4 text-sm text-slate-600 dark:text-slate-300">
            <span>Dashboard refresh: {formatDateTime(health?.dashboardRefreshTimestamp ?? dashboardSummary?.dashboardRefreshTimestamp ?? null)}</span>
            <span>Last loaded at: {lastApiLoadedAt ? formatDateTime(lastApiLoadedAt.toISOString()) : '-'}</span>
          </div>
        </Card>

        {overviewError ? (
          <ErrorAlertCard context="AsuraV3 overview" message={overviewError} />
        ) : null}

        {overviewLoading && !dashboardSummary ? (
          <div className="space-y-4">
            <SkeletonCards count={10} />
          </div>
        ) : null}

        {!overviewLoading && !overviewError && !dashboardSummary ? (
          <EmptyState
            title="No dashboard summary returned"
            description="The backend did not return Asura V3 dashboard summary rows."
            action={<Button variant="secondary" onClick={() => setRefreshVersion((current) => current + 1)}>Retry</Button>}
          />
        ) : null}

        {dashboardSummary ? (
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            <KpiCard label="Total Trades" value={formatInteger(dashboardSummary.totalTrades)} tone="strong" />
            <KpiCard label="Success Rate" value={formatPercent(dashboardSummary.successRatePct)} tone="good" />
            <KpiCard label="Failure Rate" value={formatPercent(dashboardSummary.failureRatePct)} tone="risk" />
            <KpiCard label="Avg Trading Days" value={formatNumber(dashboardSummary.avgTradingDays)} tone="muted" />
            <KpiCard label="Total P&L %" value={formatPercent(dashboardSummary.totalPnlPercent)} tone="strong" />
            <KpiCard label="Net P&L @0.30%" value={formatPercent(dashboardSummary.netPnlPercent)} tone="good" />
            <KpiCard label="Max Drawdown" value={formatNumber(dashboardSummary.maxDrawdown)} tone="risk" />
            <KpiCard label="Max Consecutive Failures" value={formatInteger(dashboardSummary.maxConsecutiveFailures)} tone="risk" />
            <KpiCard label="Total Symbols" value={formatInteger(dashboardSummary.totalSymbols)} tone="muted" />
            <KpiCard label="Date Range" value={formatDateRange(dashboardSummary.startDate, dashboardSummary.endDate)} tone="muted" />
          </section>
        ) : null}

        <Card variant="light" padding="lg" className="space-y-5 rounded-2xl">
          <SectionTitle title="Latest Signals" subtitle={`Showing page ${page.toLocaleString('en-IN')} of ${totalPages.toLocaleString('en-IN')}`} />

          <div className="grid gap-3 lg:grid-cols-5">
            <label className="grid gap-1 text-sm font-semibold text-slate-700 dark:text-slate-200 lg:col-span-2">
              Search Symbol
              <Input
                variant="light"
                value={search}
                placeholder="Type symbol"
                onChange={(event) => setSearch(event.currentTarget.value.toUpperCase())}
              />
            </label>
            <label className="grid gap-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
              Rating
              <Select variant="light" value={ratingFilter} onChange={(event) => setRatingFilter(event.currentTarget.value)}>
                {RATING_FILTER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </Select>
            </label>
            <label className="grid gap-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
              Grade
              <Select variant="light" value={gradeFilter} onChange={(event) => setGradeFilter(event.currentTarget.value)}>
                <option value="ALL">All Grades</option>
                {gradeOptions.map((grade) => (
                  <option key={grade} value={grade}>{grade}</option>
                ))}
              </Select>
            </label>
            <div className="flex items-end gap-2">
              <Button
                variant="secondary"
                leadingIcon={<DownloadIcon className="h-4 w-4" />}
                disabled={tableLoading || exporting || latestSignals.total === 0}
                onClick={exportCurrentFilterToCsv}
              >
                {exporting ? 'Exporting...' : 'Export CSV'}
              </Button>
              <CopyDiagnosticsButton compact={false} extraMessage={diagnosticsMessage} />
            </div>
          </div>

          {tableError ? (
            <ErrorAlertCard context="AsuraV3 latest signals" message={tableError} />
          ) : null}

          {tableLoading && latestRows.length === 0 ? (
            <SkeletonTable rows={10} cols={12} />
          ) : null}

          {!tableLoading && !latestRows.length && !tableError ? (
            <EmptyState
              title="No latest signals returned"
              description="Try changing search/filter criteria or refresh the page."
              action={<Button variant="secondary" onClick={() => setRefreshVersion((current) => current + 1)}>Retry</Button>}
            />
          ) : null}

          {!tableLoading && latestRows.length > 0 ? (
            <AppDataTable
              className="asura-v3-latest-table"
              columns={latestColumns}
              currentPage={page}
              disableClientSort
              getRowKey={(row) => `${row.symbol}-${row.signalDate || 'na'}-${row.serialNo}`}
              onPageChange={setPage}
              onSortChange={(nextSort) => {
                if (!nextSort.key || !nextSort.direction) return;
                if (!SORT_COLUMN_MAP[nextSort.key]) return;
                setSortState(nextSort);
                setPage(1);
              }}
              pageSize={PAGE_SIZE}
              paginationSummaryLabel="signals"
              rows={latestRows}
              showTopPagination
              sortState={sortState}
              tableClassName="min-w-[3400px] text-sm [&_thead_th]:whitespace-nowrap [&_tbody_td]:whitespace-nowrap"
              tableId="asura-v3-latest-signals"
              totalRows={latestSignals.total}
            />
          ) : null}
        </Card>

        <Card variant="light" padding="lg" className="space-y-4 rounded-2xl">
          <SectionTitle title="Yearly Summary" subtitle={`${yearlyRows.length.toLocaleString('en-IN')} yearly rows`} />
          {yearlyRows.length === 0 ? (
            <EmptyState title="No yearly summary rows" description="The yearly summary view did not return data." />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full table-auto border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-700">
                    <th className="px-3 py-2 text-left">SIGNAL_YEAR</th>
                    <th className="px-3 py-2 text-right">TOTAL_TRADES</th>
                    <th className="px-3 py-2 text-right">SUCCESS_COUNT</th>
                    <th className="px-3 py-2 text-right">FAILURE_COUNT</th>
                    <th className="px-3 py-2 text-right">OPEN_COUNT</th>
                    <th className="px-3 py-2 text-right">SUCCESS_RATE_PCT</th>
                    <th className="px-3 py-2 text-right">FAILURE_RATE_PCT</th>
                    <th className="px-3 py-2 text-right">AVG_TRADING_DAYS</th>
                    <th className="px-3 py-2 text-right">TOTAL_PNL_PERCENT</th>
                    <th className="px-3 py-2 text-right">AVG_R_MULTIPLE</th>
                    <th className="px-3 py-2 text-right">TOTAL_SYMBOLS</th>
                  </tr>
                </thead>
                <tbody>
                  {yearlyRows.map((row, index) => (
                    <tr key={`${row.signalYear || 'year'}-${index}`} className="border-b border-slate-100 dark:border-slate-800">
                      <td className="px-3 py-2">{formatInteger(row.signalYear)}</td>
                      <td className="px-3 py-2 text-right">{formatInteger(row.totalTrades)}</td>
                      <td className="px-3 py-2 text-right">{formatInteger(row.successCount)}</td>
                      <td className="px-3 py-2 text-right">{formatInteger(row.failureCount)}</td>
                      <td className="px-3 py-2 text-right">{formatInteger(row.openCount)}</td>
                      <td className="px-3 py-2 text-right">{formatPercent(row.successRatePct)}</td>
                      <td className="px-3 py-2 text-right">{formatPercent(row.failureRatePct)}</td>
                      <td className="px-3 py-2 text-right">{formatNumber(row.avgTradingDays)}</td>
                      <td className="px-3 py-2 text-right">{formatPercent(row.totalPnlPercent)}</td>
                      <td className="px-3 py-2 text-right">{formatNumber(row.avgRMultiple, 4)}</td>
                      <td className="px-3 py-2 text-right">{formatInteger(row.totalSymbols)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <section className="grid gap-4 xl:grid-cols-2">
          <Card variant="light" padding="lg" className="space-y-4 rounded-2xl">
            <SectionTitle title="Cost Summary" subtitle={`${costRows.length.toLocaleString('en-IN')} scenarios`} />
            {costRows.length === 0 ? (
              <EmptyState title="No cost summary rows" description="The cost summary view did not return data." />
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full table-auto border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 dark:border-slate-700">
                      <th className="px-3 py-2 text-left">COST_SCENARIO</th>
                      <th className="px-3 py-2 text-right">ROUND_TRIP_COST_PCT</th>
                      <th className="px-3 py-2 text-right">CLOSED_TRADES</th>
                      <th className="px-3 py-2 text-right">SUCCESS_RATE</th>
                      <th className="px-3 py-2 text-right">GROSS_P&L%</th>
                      <th className="px-3 py-2 text-right">NET_P&L%</th>
                      <th className="px-3 py-2 text-right">AVG_NET_P&L_PER_TRADE</th>
                      <th className="px-3 py-2 text-right">AVG_TRADING_DAYS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {costRows.map((row, index) => (
                      <tr key={`${row.costScenario || 'cost'}-${index}`} className="border-b border-slate-100 dark:border-slate-800">
                        <td className="px-3 py-2">{row.costScenario || '-'}</td>
                        <td className="px-3 py-2 text-right">{formatPercent(row.roundTripCostPct, 2)}</td>
                        <td className="px-3 py-2 text-right">{formatInteger(row.closedTrades)}</td>
                        <td className="px-3 py-2 text-right">{formatPercent(row.successRatePct, 2)}</td>
                        <td className="px-3 py-2 text-right">{formatPercent(row.grossPnlPercent, 2)}</td>
                        <td className="px-3 py-2 text-right">{formatPercent(row.netPnlPercent, 2)}</td>
                        <td className="px-3 py-2 text-right">{formatPercent(row.avgNetPnlPerTrade, 3)}</td>
                        <td className="px-3 py-2 text-right">{formatNumber(row.avgTradingDays, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card variant="light" padding="lg" className="space-y-4 rounded-2xl">
            <SectionTitle title="Risk Summary" subtitle={`${riskRows.length.toLocaleString('en-IN')} rows`} />
            {riskRows.length === 0 ? (
              <EmptyState title="No risk summary rows" description="The risk summary view did not return data." />
            ) : (
              <div className="space-y-3">
                {riskRows.map((row, index) => (
                  <div key={`risk-${index}`} className="grid gap-3 rounded-xl border border-slate-200/80 bg-white/75 p-4 dark:border-slate-700/70 dark:bg-slate-900/70 sm:grid-cols-2">
                    <div className="text-sm text-slate-500">Closed Trades</div>
                    <div className="text-right text-sm font-semibold text-slate-900 dark:text-slate-100">{formatInteger(row.closedTrades)}</div>
                    <div className="text-sm text-slate-500">Success Count</div>
                    <div className="text-right text-sm font-semibold text-slate-900 dark:text-slate-100">{formatInteger(row.successCount)}</div>
                    <div className="text-sm text-slate-500">Failure Count</div>
                    <div className="text-right text-sm font-semibold text-slate-900 dark:text-slate-100">{formatInteger(row.failureCount)}</div>
                    <div className="text-sm text-slate-500">Success Rate</div>
                    <div className="text-right text-sm font-semibold text-slate-900 dark:text-slate-100">{formatPercent(row.successRatePct)}</div>
                    <div className="text-sm text-slate-500">Max Drawdown</div>
                    <div className="text-right text-sm font-semibold text-rose-700 dark:text-rose-300">{formatNumber(row.maxDrawdown)}</div>
                    <div className="text-sm text-slate-500">Max Consecutive Failures</div>
                    <div className="text-right text-sm font-semibold text-rose-700 dark:text-rose-300">{formatInteger(row.maxConsecutiveFailures)}</div>
                    <div className="text-sm text-slate-500">Avg Trading Days</div>
                    <div className="text-right text-sm font-semibold text-slate-900 dark:text-slate-100">{formatNumber(row.avgTradingDays)}</div>
                    <div className="text-sm text-slate-500">Final Cumulative P&L</div>
                    <div className="text-right text-sm font-semibold text-emerald-700 dark:text-emerald-300">{formatPercent(row.finalCumulativePnl)}</div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </section>

        <Card variant="light" padding="lg" className="space-y-4 rounded-2xl">
          <SectionTitle title="Symbol Rating Distribution" subtitle="Production eligibility defaults to PREMIUM / STRONG / NORMAL." />
          {symbolRatingRows.length === 0 ? (
            <EmptyState title="No symbol rating rows" description="The symbol rating view did not return data." />
          ) : (
            <div className="space-y-3">
              {symbolRatingRows.map((row) => {
                const widthPct = ratingMax > 0 ? Math.max(4, Math.round((row.totalSymbols / ratingMax) * 100)) : 0;
                return (
                  <div key={row.symbolRating} className="grid items-center gap-3 sm:grid-cols-[120px,1fr,90px]">
                    <span className={cn('inline-flex justify-center rounded-full px-3 py-1 text-xs font-bold tracking-wide', ratingTone(row.symbolRating))}>
                      {row.symbolRating || '-'}
                    </span>
                    <div className="h-3 rounded-full bg-slate-200 dark:bg-slate-800">
                      <div
                        className={cn(
                          'h-full rounded-full',
                          row.symbolRating === 'PREMIUM' && 'bg-emerald-500',
                          row.symbolRating === 'STRONG' && 'bg-cyan-500',
                          row.symbolRating === 'NORMAL' && 'bg-amber-500',
                          row.symbolRating === 'WEAK' && 'bg-slate-500',
                          row.symbolRating === 'AVOID' && 'bg-rose-500',
                        )}
                        style={{ width: `${widthPct}%` }}
                      />
                    </div>
                    <span className="text-right text-sm font-semibold text-slate-900 dark:text-slate-100">{row.totalSymbols.toLocaleString('en-IN')}</span>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        <Card variant="light" padding="lg" className="space-y-4 rounded-2xl">
          <SectionTitle title="Strategy Rule Explainability" />
          <div className="grid gap-2 text-sm text-slate-700 dark:text-slate-200">
            <p>Base strict A+ pass conditions: PASS_TREND, PASS_EMA_STACK, PASS_RSI, PASS_RSI_RISING, PASS_MACD, PASS_ADX, PASS_ATR, PASS_VOLUME, PASS_RISK, PASS_SUPPORT_GAP, PASS_MOMENTUM all must be Y.</p>
            <p>Support gap threshold: SUPPORT_GAP_PCT &gt;= 35.</p>
            <p>Momentum threshold: MOVE_1M_PCT &gt;= 20.</p>
            <p>Risk-reward rule: RR ratio = 1R (5% stop loss and 5% target).</p>
            <p>Symbol cooldown: same symbol can re-signal only after previous exit + 3 calendar days.</p>
            <p>Eligible ratings for final production list: PREMIUM / STRONG / NORMAL.</p>
            <p>Conservative execution rule: if SL and target are touched in the same candle, SL is considered first.</p>
          </div>
        </Card>

        {!overviewLoading && !tableLoading && (overviewError || tableError) ? (
          <ErrorState
            surface="light"
            title="Asura V3 data load issues detected"
            description={[overviewError, tableError].filter(Boolean).join(' | ')}
            onRetry={() => setRefreshVersion((current) => current + 1)}
          />
        ) : null}
      </div>
    </StrategyMigrationLayout>
  );
}
