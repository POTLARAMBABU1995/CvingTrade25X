import { useMemo, useState } from 'react';
import type { AppDataTableColumn } from '../app/AppDataTable';
import { AppDataTable } from '../app/AppDataTable';
import { TechnicalMarketCapCell } from '../app/TechnicalMarketCapCell';
import { ErrorAlertCard } from '../ui/ErrorAlertCard';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { ErrorState } from '../ui/ErrorState';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { SkeletonCards } from '../ui/SkeletonCards';
import { SkeletonTable } from '../ui/SkeletonTable';
import { StrategyToolbar, type StrategyToolbarStatus } from './StrategyToolbar';
import {
  buildStrongUptrendReversalCsv,
  filterStrongUptrendReversalRows,
  formatStrongUptrendValue,
  getStrongUptrendScoreClass,
  getStrongUptrendSignalClass,
} from '../../adapters/strongUptrendReversalAdapter';
import { formatMarketCapRankValue, formatMarketCapValue, getMarketCapCategory } from '../../adapters/technicalMarketCap';
import { cn } from '../../lib/cn';
import type {
  StrongUptrendReversalFilters,
  StrongUptrendReversalMeta,
  StrongUptrendReversalRow,
  StrongUptrendSignal,
} from '../../types/strategy/strongUptrendReversal';

type StrongUptrendReversalDashboardProps = {
  errorMessage?: string;
  isLoading?: boolean;
  isRefreshing?: boolean;
  meta?: StrongUptrendReversalMeta;
  lastRefreshed?: Date | null;
  liveLoading?: boolean;
  loadTimeMs?: number | null;
  onLiveRefresh?: () => void;
  onRefresh?: () => void;
  rows: StrongUptrendReversalRow[];
};

type ViewRow = StrongUptrendReversalRow & { serialNo: number };

const DEFAULT_FILTERS: StrongUptrendReversalFilters = {
  entryTriggerOnly: false,
  minimumScore: '',
  search: '',
  signal: 'ALL',
  strongBuyOnly: false,
};
const STRONG_UPTREND_PAGE_SIZE = 25;

const SIGNAL_OPTIONS: Array<{ label: string; value: StrongUptrendSignal | 'ALL' }> = [
  { label: 'All Signals', value: 'ALL' },
  { label: 'Strong Buy', value: 'STRONG_BUY_SETUP' },
  { label: 'Watchlist', value: 'WATCHLIST' },
  { label: 'Weak Setup', value: 'WEAK_SETUP' },
  { label: 'Avoid', value: 'AVOID' },
];

function KpiCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: 'amber' | 'emerald' | 'sky' | 'slate';
}) {
  const toneClass = tone === 'emerald'
    ? 'border-emerald-200/80 bg-emerald-50/80 dark:border-emerald-700/60 dark:bg-emerald-950/30'
    : tone === 'amber'
      ? 'border-amber-200/80 bg-amber-50/80 dark:border-amber-700/60 dark:bg-amber-950/30'
      : tone === 'sky'
        ? 'border-sky-200/80 bg-sky-50/80 dark:border-sky-700/60 dark:bg-sky-950/30'
        : 'border-slate-200/80 bg-white/90 dark:border-slate-700/70 dark:bg-slate-900/86';
  return (
    <Card variant="light" padding="md" className={cn('rounded-[24px]', toneClass)}>
      <p className="m-0 text-[11px] font-bold uppercase tracking-[0.26em] text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-3 text-3xl font-black tracking-[-0.04em] text-slate-950 dark:text-slate-100">{value}</p>
    </Card>
  );
}

function FlagPill({ value }: { value: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex min-w-[76px] items-center justify-center rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-[0.18em]',
        value
          ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-700/70 dark:bg-emerald-950/40 dark:text-emerald-200'
          : 'border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-700/70 dark:bg-slate-900 dark:text-slate-300',
      )}
    >
      {value ? 'TRUE' : 'FALSE'}
    </span>
  );
}

function downloadCsv(filename: string, contents: string) {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const blob = new Blob([contents], { type: 'text/csv;charset=utf-8;' });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

function marketCapToneFromRow(row: StrongUptrendReversalRow) {
  return getMarketCapCategory(row.INDEX);
}

export function StrongUptrendReversalDashboard({
  errorMessage = '',
  isLoading = false,
  isRefreshing = false,
  lastRefreshed = null,
  liveLoading = false,
  loadTimeMs = null,
  meta,
  onLiveRefresh,
  onRefresh,
  rows,
}: StrongUptrendReversalDashboardProps) {
  const [filters, setFilters] = useState<StrongUptrendReversalFilters>(DEFAULT_FILTERS);

  const filteredRows = useMemo(
    () => filterStrongUptrendReversalRows(rows, filters),
    [filters, rows],
  );

  const viewRows = useMemo<ViewRow[]>(
    () => filteredRows.map((row, index) => ({ ...row, serialNo: index + 1 })),
    [filteredRows],
  );

  const kpis = useMemo(() => {
    const total = filteredRows.length;
    const strongBuy = filteredRows.filter((row) => row.SIGNAL === 'STRONG_BUY_SETUP').length;
    const watchlist = filteredRows.filter((row) => row.SIGNAL === 'WATCHLIST').length;
    const entryTrigger = filteredRows.filter((row) => row.ENTRY_TRIGGER).length;
    const averageScore = total ? filteredRows.reduce((sum, row) => sum + row.SCORE, 0) / total : null;
    return {
      total,
      strongBuy,
      watchlist,
      entryTrigger,
      averageScore: averageScore === null ? '-' : averageScore.toFixed(1),
    };
  }, [filteredRows]);

  const csvPayload = useMemo(() => buildStrongUptrendReversalCsv(filteredRows), [filteredRows]);

  const columns = useMemo<Array<AppDataTableColumn<ViewRow>>>(() => [
    {
      key: 'sno',
      dataCol: 'sno',
      label: <span className="block text-center">S.NO</span>,
      sortType: 'number',
      getSortValue: (row) => row.serialNo,
      renderCell: (row) => <span className="block text-center font-semibold">{row.serialNo}</span>,
      sticky: true,
      stickyWidthPx: 88,
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'symbol',
      dataCol: 'symbol',
      label: <span className="block text-left">SYMBOL</span>,
      sortType: 'string',
      getSortValue: (row) => row.SYMBOL,
      renderCell: (row) => (
        <TechnicalMarketCapCell tone={marketCapToneFromRow(row)}>
          {row.SYMBOL || '-'}
        </TechnicalMarketCapCell>
      ),
      sticky: true,
      stickyWidthPx: 180,
      cellClassName: 'text-left align-middle whitespace-nowrap',
    },
    {
      key: 'index',
      dataCol: 'index',
      label: <span className="block text-center">INDEX</span>,
      sortType: 'string',
      getSortValue: (row) => row.INDEX,
      renderCell: (row) => (
        <TechnicalMarketCapCell tone={marketCapToneFromRow(row)}>
          {row.INDEX || '-'}
        </TechnicalMarketCapCell>
      ),
      cellClassName: 'text-center align-middle whitespace-nowrap trend-mcap-cell',
    },
    {
      key: 'mcap',
      dataCol: 'mcap',
      label: <span className="block text-center">MCAP</span>,
      sortType: 'number',
      getSortValue: (row) => row.MCAP,
      renderCell: (row) => (
        <TechnicalMarketCapCell tone={marketCapToneFromRow(row)}>
          {formatMarketCapValue(row.MCAP)}
        </TechnicalMarketCapCell>
      ),
      cellClassName: 'text-center align-middle whitespace-nowrap trend-mcap-cell',
    },
    {
      key: 'mcapRank',
      dataCol: 'mcapRank',
      label: <span className="block text-center">MCAP_RANK</span>,
      sortType: 'number',
      getSortValue: (row) => row.MCAP_RANK,
      renderCell: (row) => (
        <TechnicalMarketCapCell tone={marketCapToneFromRow(row)}>
          {formatMarketCapRankValue(row.MCAP_RANK)}
        </TechnicalMarketCapCell>
      ),
      cellClassName: 'text-center align-middle whitespace-nowrap trend-mcap-cell',
    },
    {
      key: 'tradingDate',
      dataCol: 'trading_date',
      label: <span className="block text-center">TRADING_DATE</span>,
      sortType: 'date',
      getSortValue: (row) => row.TRADING_DATE,
      renderCell: (row) => formatStrongUptrendValue(row.TRADING_DATE),
      cellClassName: 'text-center align-middle whitespace-nowrap',
    },
    {
      key: 'close',
      dataCol: 'close',
      label: <span className="block text-center">CLOSE</span>,
      sortType: 'number',
      getSortValue: (row) => row.CLOSE,
      renderCell: (row) => formatStrongUptrendValue(row.CLOSE),
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'ema20',
      dataCol: 'ema20',
      label: <span className="block text-center">EMA20</span>,
      sortType: 'number',
      getSortValue: (row) => row.EMA20,
      renderCell: (row) => formatStrongUptrendValue(row.EMA20),
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'ema50',
      dataCol: 'ema50',
      label: <span className="block text-center">EMA50</span>,
      sortType: 'number',
      getSortValue: (row) => row.EMA50,
      renderCell: (row) => formatStrongUptrendValue(row.EMA50),
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'rsi14',
      dataCol: 'rsi14',
      label: <span className="block text-center">RSI14</span>,
      sortType: 'number',
      getSortValue: (row) => row.RSI14,
      renderCell: (row) => formatStrongUptrendValue(row.RSI14),
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'adx14',
      dataCol: 'adx14',
      label: <span className="block text-center">ADX14</span>,
      sortType: 'number',
      getSortValue: (row) => row.ADX14,
      renderCell: (row) => formatStrongUptrendValue(row.ADX14),
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'macd',
      dataCol: 'macd',
      label: <span className="block text-center">MACD</span>,
      sortType: 'number',
      getSortValue: (row) => row.MACD,
      renderCell: (row) => formatStrongUptrendValue(row.MACD, { digits: 4 }),
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'deliveryPct',
      dataCol: 'delivery_pct',
      label: <span className="block text-center">DELIVERY_PCT</span>,
      sortType: 'number',
      getSortValue: (row) => row.DELIVERY_PCT,
      renderCell: (row) => formatStrongUptrendValue(row.DELIVERY_PCT, { kind: 'percent' }),
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'volume',
      dataCol: 'volume',
      label: <span className="block text-center">VOLUME</span>,
      sortType: 'number',
      getSortValue: (row) => row.VOLUME,
      renderCell: (row) => formatStrongUptrendValue(row.VOLUME, { kind: 'volume' }),
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'hhHlStructure',
      dataCol: 'hh_hl_structure',
      label: <span className="block text-center">HH_HL_STRUCTURE</span>,
      sortType: 'string',
      getSortValue: (row) => (row.HH_HL_STRUCTURE ? '1' : '0'),
      renderCell: (row) => <FlagPill value={row.HH_HL_STRUCTURE} />,
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'supportConfirmed',
      dataCol: 'support_confirmed',
      label: <span className="block text-center">SUPPORT_CONFIRMED</span>,
      sortType: 'string',
      getSortValue: (row) => (row.SUPPORT_CONFIRMED ? '1' : '0'),
      renderCell: (row) => <FlagPill value={row.SUPPORT_CONFIRMED} />,
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'bullishReversal',
      dataCol: 'bullish_reversal_candle',
      label: <span className="block text-center">BULLISH_REVERSAL_CANDLE</span>,
      sortType: 'string',
      getSortValue: (row) => (row.BULLISH_REVERSAL_CANDLE ? '1' : '0'),
      renderCell: (row) => <FlagPill value={row.BULLISH_REVERSAL_CANDLE} />,
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'breakoutOk',
      dataCol: 'breakout_ok',
      label: <span className="block text-center">BREAKOUT_OK</span>,
      sortType: 'string',
      getSortValue: (row) => (row.BREAKOUT_OK ? '1' : '0'),
      renderCell: (row) => <FlagPill value={row.BREAKOUT_OK} />,
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'score',
      dataCol: 'score',
      label: <span className="block text-center">SCORE</span>,
      sortType: 'number',
      getSortValue: (row) => row.SCORE,
      renderCell: (row) => <span className={cn('font-black', getStrongUptrendScoreClass(row.SCORE))}>{row.SCORE}</span>,
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'signal',
      dataCol: 'signal',
      label: <span className="block text-center">SIGNAL</span>,
      sortType: 'string',
      getSortValue: (row) => row.SIGNAL,
      renderCell: (row) => (
        <span className={cn('inline-flex items-center justify-center rounded-full border px-3 py-1 text-xs font-bold tracking-[0.14em]', getStrongUptrendSignalClass(row.SIGNAL))}>
          {row.SIGNAL}
        </span>
      ),
      cellClassName: 'text-center align-middle whitespace-nowrap',
    },
    {
      key: 'entryPrice',
      dataCol: 'entry_price',
      label: <span className="block text-center">ENTRY_PRICE</span>,
      sortType: 'number',
      getSortValue: (row) => row.ENTRY_PRICE,
      renderCell: (row) => formatStrongUptrendValue(row.ENTRY_PRICE),
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'stopLoss',
      dataCol: 'stop_loss',
      label: <span className="block text-center">STOP_LOSS</span>,
      sortType: 'number',
      getSortValue: (row) => row.STOP_LOSS,
      renderCell: (row) => formatStrongUptrendValue(row.STOP_LOSS),
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'target1',
      dataCol: 'target_1',
      label: <span className="block text-center">TARGET_1</span>,
      sortType: 'number',
      getSortValue: (row) => row.TARGET_1,
      renderCell: (row) => formatStrongUptrendValue(row.TARGET_1),
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'target2',
      dataCol: 'target_2',
      label: <span className="block text-center">TARGET_2</span>,
      sortType: 'number',
      getSortValue: (row) => row.TARGET_2,
      renderCell: (row) => formatStrongUptrendValue(row.TARGET_2),
      cellClassName: 'text-center align-middle',
    },
    {
      key: 'rejectReason',
      dataCol: 'reject_reason',
      label: <span className="block text-center">REJECT_REASON</span>,
      sortType: 'string',
      getSortValue: (row) => row.REJECT_REASON,
      renderCell: (row) => <span className="block min-w-[280px] whitespace-normal text-left text-slate-700 dark:text-slate-300">{row.REJECT_REASON || '-'}</span>,
      cellClassName: 'align-middle',
    },
  ], []);

  const hasInlineError = Boolean(errorMessage) && rows.length > 0;
  const isEmpty = !isLoading && filteredRows.length === 0;
  const canExport = filteredRows.length > 0;
  const toolbarStatus: StrategyToolbarStatus = isLoading || isRefreshing || liveLoading || meta?.refreshing
    ? 'syncing'
    : errorMessage
      ? 'error'
      : meta?.stale
        ? 'stale'
        : lastRefreshed
          ? 'live'
          : 'idle';

  return (
    <div className="space-y-6">
      <StrategyToolbar
        apiTimeMs={meta?.durationMs ?? null}
        dbTimeMs={meta?.oracleLoadMs ?? null}
        isLoading={isLoading || isRefreshing || liveLoading}
        lastRefreshed={lastRefreshed}
        liveLoading={liveLoading}
        loadTimeMs={loadTimeMs}
        ltcDate={meta?.tradingDate ?? null}
        status={toolbarStatus}
        onLiveRefresh={onLiveRefresh}
        onRefresh={onRefresh}
        onSearchChange={(value) => setFilters((current) => ({ ...current, search: value }))}
        refreshing={isRefreshing}
        searchValue={filters.search}
        showTotal
        total={filteredRows.length}
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <KpiCard label="Total Symbols" value={String(kpis.total)} tone="slate" />
        <KpiCard label="Strong Buy" value={String(kpis.strongBuy)} tone="emerald" />
        <KpiCard label="Watchlist" value={String(kpis.watchlist)} tone="amber" />
        <KpiCard label="Entry Trigger" value={String(kpis.entryTrigger)} tone="sky" />
        <KpiCard label="Average Score" value={kpis.averageScore} tone="slate" />
      </section>

      <Card variant="light" padding="lg" className="space-y-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div className="grid flex-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
            <label className="grid gap-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
              Signal
              <Select
                aria-label="Signal filter"
                value={filters.signal}
                onChange={(event) => setFilters((current) => ({ ...current, signal: event.target.value as StrongUptrendSignal | 'ALL' }))}
                variant="light"
              >
                {SIGNAL_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </Select>
            </label>
            <label className="grid gap-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
              Minimum score
              <Input
                aria-label="Minimum score"
                inputMode="numeric"
                placeholder="50"
                value={filters.minimumScore}
                onChange={(event) => setFilters((current) => ({ ...current, minimumScore: event.target.value.replace(/[^\d]/g, '') }))}
                variant="light"
              />
            </label>
            <div className="flex items-end">
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => setFilters(DEFAULT_FILTERS)}
              >
                Reset filters
              </Button>
            </div>
            <div className="flex items-end">
              <Button
                variant={filters.strongBuyOnly ? 'secondary' : 'chip'}
                aria-pressed={filters.strongBuyOnly}
                className={cn(
                  'w-full',
                  filters.strongBuyOnly
                    ? 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-700/70 dark:bg-emerald-950/40 dark:text-emerald-200'
                    : 'text-slate-700 dark:text-slate-300',
                )}
                onClick={() => setFilters((current) => ({ ...current, strongBuyOnly: !current.strongBuyOnly }))}
              >
                {filters.strongBuyOnly ? 'Strong Buy Checked' : 'Strong Buy Unchecked'}
              </Button>
            </div>
            <div className="flex items-end">
              <Button
                variant={filters.entryTriggerOnly ? 'secondary' : 'chip'}
                aria-pressed={filters.entryTriggerOnly}
                className={cn(
                  'w-full',
                  filters.entryTriggerOnly
                    ? 'border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-700/70 dark:bg-sky-950/40 dark:text-sky-200'
                    : 'text-slate-700 dark:text-slate-300',
                )}
                onClick={() => setFilters((current) => ({ ...current, entryTriggerOnly: !current.entryTriggerOnly }))}
              >
                {filters.entryTriggerOnly ? 'Entry Trigger Checked' : 'Entry Trigger Unchecked'}
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              disabled={!canExport}
              onClick={() => downloadCsv('strong-uptrend-reversal.csv', csvPayload)}
            >
              Export CSV
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[22px] border border-slate-200/80 bg-slate-50/90 px-4 py-3 text-sm text-slate-600 dark:border-slate-700/70 dark:bg-slate-900/70 dark:text-slate-300">
          <span>Filtered symbols: {filteredRows.length.toLocaleString('en-IN')} of {rows.length.toLocaleString('en-IN')}</span>
          <span>Trading Date: {meta?.tradingDate || '-'}</span>
          <span>Cache: {meta?.cacheState || '-'}</span>
        </div>

        {hasInlineError ? (
          <ErrorAlertCard
            context="Strong uptrend scanner"
            message={errorMessage}
            className="border border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-800/60 dark:bg-rose-950/30 dark:text-rose-200"
          />
        ) : null}

        {isLoading ? (
          <div className="space-y-4">
            <SkeletonCards count={5} />
            <SkeletonTable rows={8} cols={10} />
          </div>
        ) : null}

        {!isLoading && !rows.length && errorMessage ? (
          <ErrorState
            surface="light"
            title="Strong uptrend scanner unavailable"
            description={errorMessage}
            onRetry={onRefresh}
          />
        ) : null}

        {!isLoading && !rows.length && !errorMessage ? (
          <EmptyState
            surface="light"
            title="No scanner rows returned"
            description="The backend returned an empty result for the latest scan."
            action={onRefresh ? <Button variant="secondary" onClick={onRefresh}>Retry</Button> : undefined}
          />
        ) : null}

        {!isLoading && rows.length > 0 && isEmpty ? (
          <EmptyState
            surface="light"
            title="No rows match the current filters"
            description="Reset filters or lower the minimum score to widen the scan."
            action={<Button variant="secondary" onClick={() => setFilters(DEFAULT_FILTERS)}>Reset filters</Button>}
          />
        ) : null}

        {!isLoading && filteredRows.length > 0 ? (
          <Card variant="light" padding="none" className="overflow-hidden">
            <AppDataTable
              columns={columns}
              getRowKey={(row) => `${row.SYMBOL}-${row.TRADING_DATE}-${row.serialNo}`}
              pageSize={STRONG_UPTREND_PAGE_SIZE}
              paginationSummaryLabel="symbols"
              rows={viewRows}
              showTopPagination
              tableClassName="min-w-[2300px] text-sm [&_tbody_td]:align-middle [&_thead_th]:align-middle"
              tableId="strong-uptrend-reversal-table"
            />
          </Card>
        ) : null}
      </Card>
    </div>
  );
}
