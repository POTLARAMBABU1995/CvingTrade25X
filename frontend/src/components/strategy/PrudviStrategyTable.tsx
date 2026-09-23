import { useEffect, useMemo, useState } from 'react';
import { AppPagination } from '../app/AppPagination';
import { SearchIcon } from '../ui/Icons';
import { Button } from '../ui/Button';
import { cn } from '../../lib/cn';
import {
  PRUDVI_CONDITION_KPI_FLAGS,
  formatPrudviCell,
  isStrongPrudviUptrendRow,
  PRUDVI_COLUMNS,
  prudviScoreTone,
  type PrudviFlagColumnKey,
  type PrudviKpiCounts,
  type PrudviColumnKey,
} from '../../adapters/prudviStrategyAdapter';
import { getMarketCapCategory, getMarketCapToneClass } from '../../adapters/technicalMarketCap';
import type {
  PrudviCandleDirection,
  PrudviFlag,
  PrudviStrategyFilters,
  PrudviStrategyRow,
  PrudviSupportReaction,
  PrudviTrend,
} from '../../types/strategy/prudvi';

type PrudviStrategyTableProps = {
  errorMessage?: string;
  filters: PrudviStrategyFilters;
  isLoading?: boolean;
  isRefreshing?: boolean;
  kpiCounts?: PrudviKpiCounts;
  onFiltersChange: (filters: PrudviStrategyFilters) => void;
  onRefresh: () => void;
  onStrongUptrendOnlyChange: (value: boolean) => void;
  externalToolbar?: boolean;
  rows: PrudviStrategyRow[];
  strongUptrendOnly: boolean;
  totalRows: number;
};

const PRUDVI_PAGE_SIZE = 25;
const STICKY_SYMBOL_LEFT = 72;
const ZERO_KPI_COUNTS: PrudviKpiCounts = {
  filteredOutStocks: 0,
  flagCounts: PRUDVI_CONDITION_KPI_FLAGS.reduce((counts, item) => {
    counts[item.key] = 0;
    return counts;
  }, {} as Record<PrudviFlagColumnKey, number>),
  totalStocksLoaded: 0,
  trendQualifiedStocks: 0,
};
const FLAG_COLUMNS = new Set<PrudviColumnKey>([
  'SUPPORT_REVERSAL',
  'BULLISH_CANDLE',
  'EMA_GT_20',
  'EMA_GT_50',
  'RSI_GT_50',
  'ADX_GT_25',
  'MACD_GT_0',
  'VOLUME_GT_20',
  'DELIVERY_GT_60',
]);
const BULLISH_CANDLES = new Set([
  'BULLISH_ENGULFING',
  'HAMMER',
  'INVERTED_HAMMER',
  'DRAGONFLY_DOJI',
  'BULLISH_HARAMI',
  'PIERCING_LINE',
  'MORNING_STAR',
  'THREE_WHITE_SOLDIERS',
  'BULLISH_MARUBOZU',
  'THREE_INSIDE_UP',
]);
const BEARISH_CANDLES = new Set([
  'BEARISH_ENGULFING',
  'SHOOTING_STAR',
  'HANGING_MAN',
  'EVENING_STAR',
  'BEARISH_HARAMI',
  'DARK_CLOUD_COVER',
  'THREE_BLACK_CROWS',
  'BEARISH_MARUBOZU',
]);
const CONDITION_TONE_CLASSES: Record<PrudviFlagColumnKey, string> = {
  BULLISH_CANDLE: 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-700/70 dark:bg-emerald-950/35 dark:text-emerald-200',
  EMA_GT_20: 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-700/70 dark:bg-emerald-950/35 dark:text-emerald-200',
  EMA_GT_50: 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-700/70 dark:bg-emerald-950/35 dark:text-emerald-200',
  RSI_GT_50: 'border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-700/70 dark:bg-sky-950/35 dark:text-sky-200',
  ADX_GT_25: 'border-indigo-200 bg-indigo-50 text-indigo-800 dark:border-indigo-700/70 dark:bg-indigo-950/35 dark:text-indigo-200',
  MACD_GT_0: 'border-teal-200 bg-teal-50 text-teal-800 dark:border-teal-700/70 dark:bg-teal-950/35 dark:text-teal-200',
  VOLUME_GT_20: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-700/70 dark:bg-amber-950/35 dark:text-amber-200',
  DELIVERY_GT_60: 'border-orange-200 bg-orange-50 text-orange-800 dark:border-orange-700/70 dark:bg-orange-950/35 dark:text-orange-200',
};

function FlagBadge({ value }: { value: PrudviFlag }) {
  return (
    <span
      className={cn(
        'inline-flex min-w-8 items-center justify-center rounded-full border px-2 py-1 text-xs font-black leading-none',
        value === 'Y' && 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-700/70 dark:bg-emerald-950/40 dark:text-emerald-200',
        value === 'N' && 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800/70 dark:bg-rose-950/35 dark:text-rose-200',
        value === '-' && 'border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
      )}
    >
      {value}
    </span>
  );
}

function TrendBadge({ value }: { value: PrudviTrend }) {
  return (
    <span
      className={cn(
        'inline-flex min-w-[112px] items-center justify-center rounded-full border px-2.5 py-1 text-xs font-black leading-none',
        value === 'UPTREND' && 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-700/70 dark:bg-emerald-950/40 dark:text-emerald-200',
        value === 'DOWNTREND' && 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800/70 dark:bg-rose-950/35 dark:text-rose-200',
        value === 'CONSOLIDATION' && 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-700/70 dark:bg-amber-950/40 dark:text-amber-200',
        value === '-' && 'border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
      )}
    >
      {value}
    </span>
  );
}

function SupportReactionBadge({ value }: { value: PrudviSupportReaction }) {
  return (
    <span
      className={cn(
        'inline-flex min-w-[112px] items-center justify-center rounded-full border px-2.5 py-1 text-xs font-black leading-none',
        value === 'BOUNCE' && 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-700/70 dark:bg-emerald-950/40 dark:text-emerald-200',
        value === 'BREAKDOWN' && 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800/70 dark:bg-rose-950/35 dark:text-rose-200',
        value === 'HOLDING' && 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-700/70 dark:bg-amber-950/40 dark:text-amber-200',
        value === 'NO_REACTION' && 'border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
        value === '-' && 'border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
      )}
    >
      {value}
    </span>
  );
}

function CandleBadge({ value }: { value: string }) {
  const normalized = value || '-';
  return (
    <span
      className={cn(
        'inline-flex max-w-[154px] items-center justify-center rounded-full border px-2.5 py-1 text-xs font-black leading-none',
        BULLISH_CANDLES.has(normalized) && 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-700/70 dark:bg-emerald-950/40 dark:text-emerald-200',
        BEARISH_CANDLES.has(normalized) && 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800/70 dark:bg-rose-950/35 dark:text-rose-200',
        !BULLISH_CANDLES.has(normalized) && !BEARISH_CANDLES.has(normalized) && normalized !== '-' && normalized !== 'NONE' && 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-700/70 dark:bg-amber-950/40 dark:text-amber-200',
        (normalized === '-' || normalized === 'NONE') && 'border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
      )}
      title={normalized}
    >
      <span className="truncate">{normalized}</span>
    </span>
  );
}

function CandleDirectionBadge({ value }: { value: PrudviCandleDirection }) {
  return (
    <span
      className={cn(
        'inline-flex min-w-[92px] items-center justify-center rounded-full border px-2.5 py-1 text-xs font-black leading-none',
        value === 'BULLISH' && 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-700/70 dark:bg-emerald-950/40 dark:text-emerald-200',
        value === 'BEARISH' && 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800/70 dark:bg-rose-950/35 dark:text-rose-200',
        value === 'NEUTRAL' && 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-700/70 dark:bg-amber-950/40 dark:text-amber-200',
        value === '-' && 'border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
      )}
    >
      {value}
    </span>
  );
}

function ScoreValue({ value }: { value: number }) {
  const tone = prudviScoreTone(value);
  return (
    <span
      className={cn(
        'font-black tabular-nums',
        tone === 'green' && 'text-emerald-700 dark:text-emerald-300',
        tone === 'amber' && 'text-amber-700 dark:text-amber-300',
        tone === 'blue' && 'text-sky-700 dark:text-sky-300',
        tone === 'muted' && 'text-slate-500 dark:text-slate-300',
      )}
    >
      {value}
    </span>
  );
}

function SrLevels({ value }: { value: string }) {
  const levels = value === '-' ? [] : value.split(',').map((item) => item.trim()).filter(Boolean);
  if (!levels.length) {
    return <span className="text-slate-400 dark:text-slate-500">-</span>;
  }
  return (
    <div className="flex max-w-[170px] flex-wrap gap-1.5">
      {levels.map((level) => (
        <span
          key={level}
          className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-bold text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          title={value}
        >
          {level}
        </span>
      ))}
    </div>
  );
}

function MarketCapCell({ row, value }: { row: PrudviStrategyRow; value: string }) {
  return (
    <span className={getMarketCapToneClass(getMarketCapCategory(row.INDEX))}>
      {value}
    </span>
  );
}

async function copySymbolToClipboard(symbol: string) {
  const text = String(symbol || '').trim();
  if (!text) return;
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    // Fall through to legacy copy fallback.
  }
  if (typeof document === 'undefined') return;
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
}

function SymbolCopyCell({ row }: { row: PrudviStrategyRow }) {
  const value = formatPrudviCell(row, 'SYMBOL');
  return (
    <button
      aria-label={`Copy symbol ${value}`}
      className="cursor-pointer border-0 bg-transparent p-0 text-left"
      title={`Copy ${value}`}
      type="button"
      onClick={() => {
        void copySymbolToClipboard(value);
      }}
    >
      <MarketCapCell row={row} value={value} />
    </button>
  );
}

function formatKpiNumber(value: number): string {
  return value.toLocaleString('en-IN');
}

function formatKpiPercent(value: number, total: number): string {
  if (!total) return '0.0%';
  return `${((value / total) * 100).toFixed(1)}%`;
}

function SummaryKpiCard({
  label,
  value,
  tone,
}: {
  label: string;
  tone: 'amber' | 'emerald' | 'rose' | 'slate';
  value: number;
}) {
  return (
    <div
      className={cn(
        'rounded-lg border px-4 py-3 shadow-sm',
        tone === 'slate' && 'border-slate-200 bg-white text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100',
        tone === 'emerald' && 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-700/70 dark:bg-emerald-950/35 dark:text-emerald-200',
        tone === 'rose' && 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-800/70 dark:bg-rose-950/30 dark:text-rose-200',
        tone === 'amber' && 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-700/70 dark:bg-amber-950/35 dark:text-amber-200',
      )}
    >
      <p className="m-0 text-[11px] font-black uppercase tracking-wide opacity-80">{label}</p>
      <p className="mt-2 text-2xl font-black tabular-nums">{formatKpiNumber(value)}</p>
    </div>
  );
}

function ConditionKpiCard({
  count,
  label,
  total,
  toneClass,
}: {
  count: number;
  label: string;
  toneClass: string;
  total: number;
}) {
  return (
    <div className={cn('rounded-lg border px-4 py-3 shadow-sm', toneClass)}>
      <p className="m-0 text-[11px] font-black uppercase tracking-wide opacity-80">{label}</p>
      <p className="mt-2 text-xl font-black tabular-nums">
        {formatKpiNumber(count)} / {formatKpiNumber(total)}
      </p>
      <p className="mt-1 text-xs font-black tabular-nums opacity-80">{formatKpiPercent(count, total)}</p>
    </div>
  );
}

function renderCell(row: PrudviStrategyRow, key: PrudviColumnKey) {
  if (FLAG_COLUMNS.has(key)) {
    return <FlagBadge value={row[key] as PrudviFlag} />;
  }
  if (key === 'TREND') {
    return <TrendBadge value={row.TREND} />;
  }
  if (key === 'SUPPORT_REACTION') {
    return <SupportReactionBadge value={row.SUPPORT_REACTION} />;
  }
  if (key === 'SUPPORT_CANDLE') {
    return <CandleBadge value={row.SUPPORT_CANDLE} />;
  }
  if (key === 'CANDLE_DIRECTION') {
    return <CandleDirectionBadge value={row.CANDLE_DIRECTION} />;
  }
  if (key === 'TREND_SCORE') {
    return <ScoreValue value={row.TREND_SCORE} />;
  }
  if (key === 'GAP') {
    return (
      <span className="font-black" style={{ color: '#dc2626' }}>
        {formatPrudviCell(row, key)}
      </span>
    );
  }
  if (key === 'SYMBOL') {
    return <SymbolCopyCell row={row} />;
  }
  if (key === 'INDEX' || key === 'MCAP' || key === 'MCAP_RANK') {
    return <MarketCapCell row={row} value={formatPrudviCell(row, key)} />;
  }
  if (key === 'SUPPORT' || key === 'RESISTANCE') {
    return <SrLevels value={formatPrudviCell(row, key)} />;
  }
  return formatPrudviCell(row, key);
}

export function PrudviStrategyTable({
  errorMessage = '',
  filters,
  isLoading = false,
  isRefreshing = false,
  kpiCounts = ZERO_KPI_COUNTS,
  onFiltersChange,
  onRefresh,
  onStrongUptrendOnlyChange,
  externalToolbar = false,
  rows,
  strongUptrendOnly,
  totalRows,
}: PrudviStrategyTableProps) {
  const [page, setPage] = useState(1);
  const updateFilter = (patch: Partial<PrudviStrategyFilters>) => onFiltersChange({ ...filters, ...patch });
  const tableMinWidth = PRUDVI_COLUMNS.reduce((sum, column) => sum + column.width, 0);
  const totalPages = Math.max(1, Math.ceil(rows.length / PRUDVI_PAGE_SIZE));
  const currentPage = Math.min(Math.max(1, page), totalPages);
  const pageStartIndex = (currentPage - 1) * PRUDVI_PAGE_SIZE;
  const pageRows = useMemo(() => rows.slice(pageStartIndex, pageStartIndex + PRUDVI_PAGE_SIZE).map((row, index) => ({
    ...row,
    S_NO: pageStartIndex + index + 1,
  })), [pageStartIndex, rows]);
  const strongUptrendRows = useMemo(() => rows.filter(isStrongPrudviUptrendRow).length, [rows]);
  const pageStart = rows.length ? pageStartIndex + 1 : 0;
  const pageEnd = Math.min(pageStartIndex + PRUDVI_PAGE_SIZE, rows.length);
  const currentPageRows = isLoading ? 0 : pageRows.length;

  useEffect(() => {
    setPage(1);
  }, [rows]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  return (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white text-slate-950 shadow-sm dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100">
      <div className="space-y-3 border-b border-slate-200 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-900/50">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <SummaryKpiCard label="TOTAL STOCKS LOADED" value={kpiCounts.totalStocksLoaded} tone="slate" />
          <SummaryKpiCard label="TREND QUALIFIED STOCKS" value={kpiCounts.trendQualifiedStocks} tone="emerald" />
          <SummaryKpiCard label="FILTERED OUT STOCKS" value={kpiCounts.filteredOutStocks} tone="rose" />
          <SummaryKpiCard label="CURRENT PAGE ROWS" value={currentPageRows} tone="amber" />
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Prudvi condition KPI cards">
          {PRUDVI_CONDITION_KPI_FLAGS.map((item) => (
            <ConditionKpiCard
              key={item.key}
              count={kpiCounts.flagCounts[item.key] ?? 0}
              label={item.label}
              toneClass={CONDITION_TONE_CLASSES[item.key]}
              total={kpiCounts.totalStocksLoaded}
            />
          ))}
        </div>
      </div>
      <div className="flex flex-col gap-3 border-b border-slate-200 bg-slate-50/80 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/72 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-1 flex-col gap-3 md:flex-row md:items-center">
          {!externalToolbar ? (
            <label className="relative min-w-[240px] flex-1 md:max-w-sm">
              <span className="sr-only">Search by symbol</span>
              <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                className="h-10 w-full rounded-full border border-slate-200 bg-white pl-9 pr-3 text-sm font-semibold text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-sky-300 focus:ring-2 focus:ring-sky-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-sky-600 dark:focus:ring-sky-950"
                type="search"
                value={filters.search}
                placeholder="Search symbol"
                onChange={(event) => updateFilter({ search: event.currentTarget.value })}
              />
            </label>
          ) : null}
          <select
            className="h-10 rounded-full border border-slate-200 bg-white px-3 text-sm font-bold text-slate-700 outline-none focus:border-sky-300 focus:ring-2 focus:ring-sky-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            aria-label="Trend filter"
            value={filters.trend}
            onChange={(event) => updateFilter({ trend: event.currentTarget.value as PrudviStrategyFilters['trend'] })}
          >
            <option value="ALL">All trends</option>
            <option value="UPTREND">UPTREND</option>
            <option value="DOWNTREND">DOWNTREND</option>
            <option value="CONSOLIDATION">CONSOLIDATION</option>
            <option value="-">-</option>
          </select>
          <input
            className="h-10 w-32 rounded-full border border-slate-200 bg-white px-3 text-sm font-bold text-slate-700 outline-none focus:border-sky-300 focus:ring-2 focus:ring-sky-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            type="number"
            min="0"
            max="100"
            aria-label="Minimum trend score"
            placeholder="Min score"
            value={filters.minimumScore}
            onChange={(event) => updateFilter({ minimumScore: event.currentTarget.value })}
          />
        </div>
        <div className="flex items-center justify-between gap-3 lg:justify-end">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-black text-emerald-700 dark:border-emerald-700/70 dark:bg-emerald-950/40 dark:text-emerald-200">
            <input
              aria-label="Show only strong uptrend rows"
              checked={strongUptrendOnly}
              className="h-4 w-4 accent-emerald-600"
              type="checkbox"
              onChange={(event) => onStrongUptrendOnlyChange(event.currentTarget.checked)}
            />
            <span>Strong uptrend: {strongUptrendRows}</span>
          </label>
          <span className="rounded-full border border-slate-200 bg-white px-3 py-2 text-sm font-black text-slate-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200">
            Displayed: {rows.length} / {totalRows}
          </span>
          {!externalToolbar ? (
            <Button size="sm" variant="secondary" loading={isRefreshing} onClick={onRefresh}>
              Refresh
            </Button>
          ) : null}
        </div>
      </div>

      {errorMessage ? (
        <div className="border-b border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-700 dark:border-rose-900/70 dark:bg-rose-950/30 dark:text-rose-200">
          {errorMessage}
        </div>
      ) : null}

      {rows.length ? (
        <div className="flex flex-col gap-3 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-950 md:flex-row md:items-center md:justify-between">
          <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">
            Showing {pageStart.toLocaleString('en-IN')}-{pageEnd.toLocaleString('en-IN')} of {rows.length.toLocaleString('en-IN')} symbols
          </span>
          <AppPagination currentPage={currentPage} totalPages={totalPages} onPageChange={setPage} />
        </div>
      ) : null}

      <div className="overflow-x-auto overflow-y-visible lg:min-h-[780px]">
        <table className="border-separate border-spacing-0 text-sm" style={{ minWidth: tableMinWidth }}>
          <colgroup>
            {PRUDVI_COLUMNS.map((column) => (
              <col key={column.key} style={{ width: column.width }} />
            ))}
          </colgroup>
          <thead>
            <tr>
              {PRUDVI_COLUMNS.map((column) => {
                const isSerial = column.key === 'S_NO';
                const isSymbol = column.key === 'SYMBOL';
                return (
                  <th
                    key={column.key}
                    className={cn(
                      'sticky top-0 z-20 border-b border-r border-slate-300 bg-slate-100 px-3 py-3 text-left align-middle text-[11px] font-black uppercase text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200',
                      isSerial && 'left-0 z-30 text-center',
                      isSymbol && 'z-30',
                    )}
                    style={isSymbol ? { left: STICKY_SYMBOL_LEFT } : undefined}
                  >
                    {column.label}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={PRUDVI_COLUMNS.length} className="px-4 py-8 text-center text-sm font-semibold text-slate-500 dark:text-slate-300">
                  Loading Prudvi strategy rows...
                </td>
              </tr>
            ) : rows.length ? pageRows.map((row) => (
              <tr key={`${row.SYMBOL}-${row.S_NO}`} className="group">
                {PRUDVI_COLUMNS.map((column) => {
                  const isSerial = column.key === 'S_NO';
                  const isSymbol = column.key === 'SYMBOL';
                  return (
                    <td
                      key={`${row.SYMBOL}-${column.key}`}
                      className={cn(
                        'border-b border-r border-slate-300 bg-white px-3 py-2.5 align-middle text-slate-700 group-hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:group-hover:bg-slate-900/75',
                        isSerial && 'sticky left-0 z-10 text-center font-black tabular-nums',
                        isSymbol && 'sticky z-10 font-black text-slate-950 dark:text-white',
                        !isSerial && !isSymbol && 'whitespace-nowrap',
                      )}
                      style={isSymbol ? { left: STICKY_SYMBOL_LEFT } : undefined}
                    >
                      {renderCell(row, column.key)}
                    </td>
                  );
                })}
              </tr>
            )) : (
              <tr>
                <td colSpan={PRUDVI_COLUMNS.length} className="px-4 py-8 text-center text-sm font-semibold text-slate-500 dark:text-slate-300">
                  No Prudvi strategy rows matched the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {rows.length ? (
        <div className="flex flex-col gap-3 border-t border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-950 md:flex-row md:items-center md:justify-between">
          <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">
            Showing {pageStart.toLocaleString('en-IN')}-{pageEnd.toLocaleString('en-IN')} of {rows.length.toLocaleString('en-IN')} symbols
          </span>
          <AppPagination currentPage={currentPage} totalPages={totalPages} onPageChange={setPage} />
        </div>
      ) : null}
    </section>
  );
}
