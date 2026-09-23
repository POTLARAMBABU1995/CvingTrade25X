import { useEffect, useMemo, useState } from 'react';
import { Card } from '../../components/ui/Card';
import { PageHeader } from '../../components/ui/PageHeader';
import {
  extractStrategyRows,
  formatStrategyCell,
  normalizeYamunaRows,
  type StrategyWireRow,
} from '../../adapters/strategyPageAdapter';
import {
  cancelStrategyAgent,
  fetchStrategyAgentBacktests,
  fetchStrategyAgentStatus,
  fetchStrategyPayload,
  runStrategyAgent,
} from '../../services/api/strategyApi';
import { cn } from '../../lib/cn';
import { StrategyMigrationLayout } from './StrategyMigrationLayout';

type LoadStatus = 'error' | 'loading' | 'online' | 'partial';
type UnknownRecord = Record<string, unknown>;
type AgentConfig = {
  canRun: boolean;
  description: string;
  openHref?: string;
  openLabel?: string;
  strategy: string;
  title: string;
};

const ASURA_LIMIT = 100;
const YAMUNA_LIMIT = 25;
const TABLE_PAGE_SIZE = 15;
const ACTIVE_EXECUTION_STATUSES = new Set(['QUEUED', 'RUNNING', 'CANCELLING']);

const trackerColumns = [
  { key: 'stockName', label: 'Stock Name' },
  { key: 'entryPrice', label: 'Entry Price' },
  { key: 'exitPrice', label: 'Exit/Target Price' },
  { key: 'stopLoss', label: 'Stop Loss' },
  { key: 'profitPct', label: 'Profit %' },
  { key: 'entryDate', label: 'Entry Date' },
  { key: 'exitDate', label: 'Exit Date' },
  { key: 'tradingDays', label: 'Trading Days' },
  { key: 'quantity', label: 'Quantity' },
  { key: 'invested', label: 'Invested' },
  { key: 'netProfit', label: 'Net Profit' },
  { key: 'dpCharges', label: 'DP Charges' },
  { key: 'dayGL', label: 'Day G/Expected/L' },
  { key: 'performedPeriod', label: 'Performed Period' },
] as const;

const agentConfigs: readonly AgentConfig[] = [
  {
    canRun: false,
    description: 'Backtesting results from ASURA_BULLISH_TREND_STRATEGY_TESTING.',
    openHref: '/app/strategy/asura',
    openLabel: 'Open Asura',
    strategy: 'asura',
    title: 'Asura Final Results',
  },
  {
    canRun: false,
    description: 'Backtesting results from GAINERS_TOP25, LOOSERS_TOP25, and VOLUME_MOVERS_TOP25.',
    openHref: '/app/strategy/yamuna',
    openLabel: 'Open Yamuna',
    strategy: 'yamuna',
    title: 'Yamuna Final Results',
  },
  {
    canRun: true,
    description: 'Rules-based backtest for NSE_NIFTY50_LARGECAP using NSE_NIFTY500_DAILY_RAW_DATA_DEV from 1998-01-01 onward.',
    strategy: 'backtestnifty50',
    title: 'BackTestNifty50 Final Results',
  },
  {
    canRun: true,
    description: 'Stricter Nifty50 variant with price-action breakout, trendline structure, support/resistance clearance, and ADX > 25.',
    strategy: 'backtestnifty50v2',
    title: 'BackTestNifty50 v2 Final Results',
  },
];

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {};
}

function pick(row: UnknownRecord, keys: readonly string[]): unknown {
  for (const key of keys) {
    const value = row[key];
    if (value !== null && value !== undefined && String(value).trim() !== '') return value;
  }
  return undefined;
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(String(value).trim().replace(/,/g, '').replace(/%$/g, '').replace(/x$/i, ''));
  return Number.isFinite(parsed) ? parsed : null;
}

function average(values: unknown[]): number | null {
  const nums = values.map(toNumber).filter((value): value is number => value !== null);
  return nums.length ? nums.reduce((sum, value) => sum + value, 0) / nums.length : null;
}

function toIsoDate(value: unknown): string {
  const text = String(value ?? '').trim();
  if (!text) return '';
  const isoDate = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (isoDate) return `${isoDate[1]}-${isoDate[2]}-${isoDate[3]}`;
  const dmyDash = text.match(/^(\d{2})-(\d{2})-(\d{4})$/);
  if (dmyDash) return `${dmyDash[3]}-${dmyDash[2]}-${dmyDash[1]}`;
  return '';
}

function toDateSort(value: unknown): number | null {
  const isoDate = toIsoDate(value);
  if (!isoDate) return null;
  const timestamp = Date.parse(isoDate);
  return Number.isNaN(timestamp) ? null : timestamp;
}

function formatDate(value: unknown): string {
  const isoDate = toIsoDate(value);
  if (!isoDate) return '-';
  const [year, month, day] = isoDate.split('-');
  return `${day}-${month}-${year}`;
}

function formatDateTime(value: unknown): string {
  const text = String(value ?? '').trim();
  return text ? text.slice(0, 19) : '-';
}

function formatNumber(value: unknown, decimals = 2): string {
  const num = toNumber(value);
  return num === null ? '-' : num.toFixed(decimals);
}

function formatPrice(value: unknown): string {
  return formatNumber(value, 2);
}

function formatPct(value: unknown, decimals = 2): string {
  const num = toNumber(value);
  return num === null ? '-' : `${num.toFixed(decimals)}%`;
}

function formatRatio(value: unknown): string {
  const num = toNumber(value);
  return num === null ? '-' : `${num.toFixed(2)}x`;
}

function formatPoints(value: unknown): string {
  const num = toNumber(value);
  if (num === null) return '-';
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}`;
}

function diffDays(startValue: unknown, endValue: unknown): number | null {
  const start = toDateSort(startValue);
  const end = toDateSort(endValue);
  if (start === null || end === null || end < start) return null;
  return Math.round((end - start) / 86400000) + 1;
}

function buildMomentumRows(gainers: StrategyWireRow[]) {
  return gainers.slice(0, TABLE_PAGE_SIZE).map((row) => {
    const movePct = pick(row, ['percentage', 'percentChange']);
    const points = pick(row, ['points', 'change']);
    const entryDate = pick(row, ['tradingDate', 'tradeDate', 'ltcDate']);
    return {
      dayGL: formatPoints(points),
      dpCharges: '',
      entryDate: formatDate(entryDate),
      entryPrice: formatPrice(pick(row, ['price', 'close'])),
      exitDate: '',
      exitPrice: '',
      invested: '',
      netProfit: '',
      performedPeriod: 'Yamuna Gainer',
      profitPct: formatPct(movePct),
      quantity: '',
      stockName: formatStrategyCell(pick(row, ['symbol', 'stockName', 'stock'])),
      stopLoss: '',
      tradingDays: '1',
    };
  });
}

function buildTrendRows(asuraRows: StrategyWireRow[]) {
  return asuraRows.slice(0, TABLE_PAGE_SIZE).map((row) => {
    const entryDate = pick(row, ['buyingDate', 'tradeDate', 'asOfDate']);
    const exitDate = pick(row, ['sellingDate']);
    const target = pick(row, ['target1', 'target2']);
    const tradingDays = diffDays(entryDate, exitDate || pick(row, ['backtestingDate']));
    const dayMove = pick(row, ['move1dPct', 'move_1d_pct']);
    return {
      dayGL: pick(row, ['breakoutFlag'])
        ? `${formatStrategyCell(pick(row, ['breakoutFlag']))}${formatPct(dayMove) === '-' ? '' : ` | ${formatPct(dayMove)}`}`
        : formatPct(dayMove),
      dpCharges: '',
      entryDate: formatDate(entryDate),
      entryPrice: formatPrice(pick(row, ['entryPrice', 'entry_price', 'price'])),
      exitDate: formatDate(exitDate),
      exitPrice: formatPrice(target),
      invested: '',
      netProfit: '',
      performedPeriod: formatStrategyCell(pick(row, ['setupType', 'setup_type', 'trendDirection', 'trend_direction']) || 'Asura'),
      profitPct: formatPct(pick(row, ['target1Pct', 'target1_pct', 'move1mPct', 'move_1m_pct'])),
      quantity: '',
      stockName: formatStrategyCell(pick(row, ['symbol', 'stockName', 'stock'])),
      stopLoss: formatPrice(pick(row, ['stopLoss', 'stop_loss'])),
      tradingDays: tradingDays === null ? '' : String(tradingDays),
    };
  });
}

function buildVolumeRows(volumeRows: StrategyWireRow[]) {
  return [...volumeRows]
    .sort((left, right) => (toNumber(pick(right, ['volumeRatio', 'volumeRatioSort'])) || 0) - (toNumber(pick(left, ['volumeRatio', 'volumeRatioSort'])) || 0))
    .slice(0, TABLE_PAGE_SIZE)
    .map((row) => {
      const volumeRatio = pick(row, ['volumeRatio', 'volumeRatioSort']);
      const points = pick(row, ['points', 'change']);
      const entryDate = pick(row, ['ltcDate', 'tradingDate', 'tradeDate']);
      return {
        dayGL: toNumber(points) === null ? formatRatio(volumeRatio) : `${formatPoints(points)} | ${formatRatio(volumeRatio)}`,
        dpCharges: '',
        entryDate: formatDate(entryDate),
        entryPrice: formatPrice(pick(row, ['price', 'close'])),
        exitDate: '',
        exitPrice: '',
        invested: '',
        netProfit: '',
        performedPeriod: toNumber(volumeRatio) === null ? 'Volume Surge' : `Volume ${formatRatio(volumeRatio)}`,
        profitPct: formatPct(pick(row, ['percentage', 'percentChange'])),
        quantity: '',
        stockName: formatStrategyCell(pick(row, ['symbol', 'stock'])),
        stopLoss: '',
        tradingDays: formatStrategyCell(pick(row, ['td', 'tradingDays'])),
      };
    });
}

function isExecutionActive(execution: unknown): boolean {
  const status = String(asRecord(execution).status ?? '').toUpperCase();
  return ACTIVE_EXECUTION_STATUSES.has(status);
}

function StrategySummaryCard({
  details,
  eyebrow,
  href,
  stats,
  title,
}: {
  details: string;
  eyebrow: string;
  href?: string;
  stats: Array<{ label: string; value: string }>;
  title: string;
}) {
  return (
    <Card variant="light" padding="md" className="border-slate-200 shadow-sm dark:border-slate-700/70">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.22em] text-sky-600">{eyebrow}</p>
          <h3 className="mt-1 text-2xl font-black text-slate-950 dark:text-slate-100">{title}</h3>
        </div>
        {href ? <a className="rounded-full border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-black text-sky-800 dark:border-sky-700/70 dark:bg-slate-900/80 dark:text-sky-200" href={href}>Open page</a> : null}
      </div>
      <p className="mt-4 min-h-12 text-base font-semibold leading-6 text-slate-700 dark:text-slate-300">{details}</p>
      <div className="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded-2xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700/70 dark:bg-slate-900/70">
            <span className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{stat.label}</span>
            <strong className="mt-1 block text-xl font-black text-slate-950 dark:text-slate-100">{stat.value}</strong>
          </div>
        ))}
      </div>
    </Card>
  );
}

function TrackerTable({ rows, stateText, title }: { rows: Array<Record<string, string>>; stateText: string; title: string }) {
  return (
    <Card variant="light" padding="none" className="overflow-hidden border-slate-200 shadow-sm dark:border-slate-700/70">
      <div className="border-b border-slate-200 bg-sky-50 px-5 py-4 dark:border-slate-700/70 dark:bg-slate-900/75">
        <h3 className="text-lg font-black text-slate-950 dark:text-slate-100">{title}</h3>
        <p className="mt-1 text-sm font-semibold text-slate-600 dark:text-slate-300">{stateText}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              {trackerColumns.map((column) => (
                <th key={column.key} className="whitespace-nowrap border-b border-slate-200 bg-sky-50 px-3 py-3 text-left text-xs font-black uppercase text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length ? rows.map((row, index) => (
              <tr key={`${row.stockName}-${index}`} className="odd:bg-white even:bg-slate-50/70 dark:odd:bg-slate-950 dark:even:bg-slate-900/70">
                {trackerColumns.map((column) => (
                  <td key={column.key} className="whitespace-nowrap border-b border-slate-100 px-3 py-3 font-semibold text-slate-800 dark:border-slate-800 dark:text-slate-200">
                    {row[column.key] || '-'}
                  </td>
                ))}
              </tr>
            )) : (
              <tr>
                <td className="px-4 py-6 text-center font-semibold text-slate-500 dark:text-slate-300" colSpan={trackerColumns.length}>No rows available.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function AgentPanel({ config }: { config: typeof agentConfigs[number] }) {
  const [statusPayload, setStatusPayload] = useState<unknown>(null);
  const [backtestsPayload, setBacktestsPayload] = useState<unknown>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [actioning, setActioning] = useState(false);

  async function load(signal?: AbortSignal) {
    setLoading(true);
    setError('');
    try {
      const [status, backtests] = await Promise.all([
        fetchStrategyAgentStatus(config.strategy, { signal }),
        fetchStrategyAgentBacktests(config.strategy, 50, { signal }),
      ]);
      setStatusPayload(status);
      setBacktestsPayload(backtests);
    } catch (loadError) {
      if (!signal?.aborted) setError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [config.strategy]);

  async function run() {
    setActioning(true);
    setError('');
    try {
      await runStrategyAgent(config.strategy);
      await load();
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : String(runError));
    } finally {
      setActioning(false);
    }
  }

  async function cancel() {
    setActioning(true);
    setError('');
    try {
      const execution = asRecord(asRecord(statusPayload).execution);
      const jobId = typeof execution.jobId === 'string' ? execution.jobId : undefined;
      await cancelStrategyAgent(config.strategy, jobId);
      await load();
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : String(cancelError));
    } finally {
      setActioning(false);
    }
  }

  const status = asRecord(statusPayload);
  const backtests = asRecord(backtestsPayload);
  const summary = { ...asRecord(backtests.summary), ...asRecord(status.summary) };
  const lastRun = asRecord(status.lastRun);
  const execution = asRecord(status.execution);
  const rows = extractStrategyRows(backtests).slice(0, 10);
  const active = isExecutionActive(execution);
  const runMeta = active
    ? `${formatStrategyCell(execution.status).toUpperCase()} | Background`
    : lastRun.status
      ? `${formatStrategyCell(lastRun.status)}${lastRun.applied ? ' | Applied' : ' | No change'}`
      : (toNumber(summary.totalTrades) ? 'Preview only' : 'No run yet');

  return (
    <Card variant="light" padding="md" className="border-slate-200 shadow-sm dark:border-slate-700/70">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h3 className="text-xl font-black text-slate-950 dark:text-slate-100">{config.title}</h3>
          <p className="mt-1 text-sm font-semibold leading-6 text-slate-600 dark:text-slate-300">{config.description}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {config.openHref ? <a className="rounded-full border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-black text-sky-800 dark:border-sky-700/70 dark:bg-slate-900/80 dark:text-sky-200" href={config.openHref}>{config.openLabel}</a> : null}
          <button className="rounded-full border border-slate-200 bg-white px-3 py-2 text-sm font-black text-slate-800 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-100" type="button" disabled={loading || actioning} onClick={() => void load()}>
            Refresh
          </button>
          {config.canRun ? (
            <button className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-black text-emerald-800 disabled:opacity-50 dark:border-emerald-700/70 dark:bg-emerald-950/40 dark:text-emerald-200" type="button" disabled={active || actioning} onClick={() => void run()}>
              {active ? 'Running...' : 'Run'}
            </button>
          ) : null}
          {active ? (
            <button className="rounded-full border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-black text-rose-800 disabled:opacity-50 dark:border-rose-700/70 dark:bg-rose-950/40 dark:text-rose-200" type="button" disabled={actioning} onClick={() => void cancel()}>
              Cancel Run
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700/70 dark:bg-slate-900/70"><span className="text-xs font-black uppercase text-slate-500 dark:text-slate-400">Success</span><strong className="block text-lg font-black text-slate-950 dark:text-slate-100">{formatPct(summary.successRate)}</strong></div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700/70 dark:bg-slate-900/70"><span className="text-xs font-black uppercase text-slate-500 dark:text-slate-400">Fail</span><strong className="block text-lg font-black text-slate-950 dark:text-slate-100">{formatPct(summary.failRate)}</strong></div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700/70 dark:bg-slate-900/70"><span className="text-xs font-black uppercase text-slate-500 dark:text-slate-400">Total</span><strong className="block text-lg font-black text-slate-950 dark:text-slate-100">{formatStrategyCell(summary.totalTrades)}</strong></div>
        <div className="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700/70 dark:bg-slate-900/80"><span className="text-xs font-black uppercase text-slate-500 dark:text-slate-400">Avg RR</span><strong className="block text-lg font-black text-slate-950 dark:text-slate-100">{formatNumber(summary.avgReturnRr)}</strong></div>
        <div className="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700/70 dark:bg-slate-900/80"><span className="text-xs font-black uppercase text-slate-500 dark:text-slate-400">Last Run</span><strong className="block text-lg font-black text-slate-950 dark:text-slate-100">{formatDateTime(summary.lastRunAt || lastRun.runAt)}</strong></div>
        <div className="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700/70 dark:bg-slate-900/80"><span className="text-xs font-black uppercase text-slate-500 dark:text-slate-400">Run Status</span><strong className="block text-lg font-black text-slate-950 dark:text-slate-100">{runMeta}</strong></div>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div>
          <div className="text-xs font-black uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Agent Status</div>
          <p className="mt-1 text-sm font-semibold text-slate-700 dark:text-slate-300">{error || (loading ? 'Loading agent status...' : `${config.strategy.toUpperCase()} agent ready`)}</p>
        </div>
        <div>
          <div className="text-xs font-black uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Latest Learning Note</div>
          <p className="mt-1 text-sm font-semibold text-slate-700 dark:text-slate-300">{formatStrategyCell(summary.lastNote || lastRun.notes || 'No learning note yet.')}</p>
        </div>
      </div>

      <div className="mt-5 overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-700/70">
        <table className="min-w-full border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              {['Stock', 'Buying Date', 'Selling Date', 'Selling/SL/Exit', 'Entry', 'T1', 'T2', 'P&L', 'Why trade success/fail', 'Trading Days'].map((label) => (
                <th key={label} className="whitespace-nowrap border-b border-slate-200 bg-sky-50 px-3 py-3 text-left text-xs font-black uppercase text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length ? rows.map((row, index) => (
              <tr key={`${formatStrategyCell(row.symbol)}-${index}`} className="odd:bg-white even:bg-slate-50/70 dark:odd:bg-slate-950 dark:even:bg-slate-900/70">
                <td className="whitespace-nowrap border-b border-slate-100 px-3 py-3 font-semibold text-slate-800 dark:border-slate-800 dark:text-slate-200">{formatStrategyCell(row.symbol)}</td>
                <td className="whitespace-nowrap border-b border-slate-100 px-3 py-3 font-semibold text-slate-800 dark:border-slate-800 dark:text-slate-200">{formatDateTime(row.buyingDate)}</td>
                <td className="whitespace-nowrap border-b border-slate-100 px-3 py-3 font-semibold text-slate-800 dark:border-slate-800 dark:text-slate-200">{formatDateTime(row.sellingDate)}</td>
                <td className="whitespace-nowrap border-b border-slate-100 px-3 py-3 font-semibold text-slate-800 dark:border-slate-800 dark:text-slate-200">{formatStrategyCell(row.sellingOrExit)}</td>
                <td className="whitespace-nowrap border-b border-slate-100 px-3 py-3 font-semibold text-slate-800 dark:border-slate-800 dark:text-slate-200">{formatNumber(row.entryPrice)}</td>
                <td className="whitespace-nowrap border-b border-slate-100 px-3 py-3 font-semibold text-slate-800 dark:border-slate-800 dark:text-slate-200">{formatNumber(row.target1)}</td>
                <td className="whitespace-nowrap border-b border-slate-100 px-3 py-3 font-semibold text-slate-800 dark:border-slate-800 dark:text-slate-200">{formatNumber(row.target2)}</td>
                <td className={cn('whitespace-nowrap border-b border-slate-100 px-3 py-3 font-black dark:border-slate-800', (toNumber(row.returnPct) || 0) > 0 ? 'text-emerald-700 dark:text-emerald-300' : (toNumber(row.returnPct) || 0) < 0 ? 'text-rose-700 dark:text-rose-300' : 'text-slate-700 dark:text-slate-300')}>{formatPct(row.returnPct)}</td>
                <td className="min-w-[260px] border-b border-slate-100 px-3 py-3 font-semibold text-slate-800 dark:border-slate-800 dark:text-slate-200">{formatStrategyCell(row.whyTrade)}</td>
                <td className="whitespace-nowrap border-b border-slate-100 px-3 py-3 font-semibold text-slate-800 dark:border-slate-800 dark:text-slate-200">{formatStrategyCell(row.tradingDays)}</td>
              </tr>
            )) : (
              <tr><td className="px-4 py-6 text-center font-semibold text-slate-500 dark:text-slate-300" colSpan={10}>No backtest rows available yet. Refresh for a live preview or run once to store history.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function StrategyOverviewPage() {
  const [asuraPayload, setAsuraPayload] = useState<unknown>(null);
  const [moversPayload, setMoversPayload] = useState<unknown>(null);
  const [volumePayload, setVolumePayload] = useState<unknown>(null);
  const [, setStatus] = useState<LoadStatus>('loading');
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setStatus('loading');
      setError('');
      const [asuraResult, moversResult, volumeResult] = await Promise.allSettled([
        fetchStrategyPayload('/api/asura', { page: 1, page_size: ASURA_LIMIT, skip_sync: 1, timeframe: 'daily' }, { signal: controller.signal, timeoutMs: 120000 }),
        fetchStrategyPayload('/api/dashboard/movers', { limit: YAMUNA_LIMIT, segment: 'nifty500' }, { signal: controller.signal, timeoutMs: 30000 }),
        fetchStrategyPayload('/api/volume', undefined, { signal: controller.signal, timeoutMs: 30000 }),
      ]);
      if (controller.signal.aborted) return;
      setAsuraPayload(asuraResult.status === 'fulfilled' ? asuraResult.value : null);
      setMoversPayload(moversResult.status === 'fulfilled' ? moversResult.value : null);
      setVolumePayload(volumeResult.status === 'fulfilled' ? volumeResult.value : null);
      const successfulLoads = [asuraResult, moversResult, volumeResult].filter((result) => result.status === 'fulfilled').length;
      setStatus(successfulLoads === 3 ? 'online' : successfulLoads > 0 ? 'partial' : 'error');
      if (successfulLoads === 0) {
        const firstError = [asuraResult, moversResult, volumeResult].find((result) => result.status === 'rejected');
        setError(firstError && firstError.status === 'rejected' ? String(firstError.reason) : 'Live strategy data unavailable.');
      }
    }
    void load();
    return () => controller.abort();
  }, []);

  const asuraRows = useMemo(() => extractStrategyRows(asuraPayload), [asuraPayload]);
  const yamunaState = useMemo(() => normalizeYamunaRows(moversPayload), [moversPayload]);
  const volumeRows = useMemo(() => extractStrategyRows(volumePayload), [volumePayload]);
  const sortedVolumeRows = useMemo(() => [...volumeRows].sort((left, right) => (toNumber(pick(right, ['volumeRatio', 'volumeRatioSort'])) || 0) - (toNumber(pick(left, ['volumeRatio', 'volumeRatioSort'])) || 0)), [volumeRows]);

  const asuraLead = asuraRows[0] ?? {};
  const topGainer = yamunaState.gainers[0] ?? {};
  const topVolume = sortedVolumeRows[0] ?? {};
  const asuraSet = new Set(asuraRows.map((row) => String(pick(row, ['symbol']) ?? '').toUpperCase()).filter(Boolean));
  const overlap = [...yamunaState.gainers.slice(0, 10), ...sortedVolumeRows.slice(0, 10)]
    .map((row) => String(pick(row, ['symbol', 'stockName', 'stock']) ?? '').toUpperCase())
    .filter((symbol, index, symbols) => symbol && symbols.indexOf(symbol) === index && asuraSet.has(symbol));
  const breadth = asRecord(asRecord(moversPayload).breadth);

  return (
    <StrategyMigrationLayout activeStrategyPage="/app/strategy" fullWidth>
      <div className="space-y-6">
        <PageHeader title="Asura + Yamuna + BackTestNifty50 dashboards" />

        {error ? <Card variant="light" padding="md" className="border-rose-200 bg-rose-50 text-sm font-semibold text-rose-800 dark:border-rose-800/70 dark:bg-rose-950/40 dark:text-rose-200">{error}</Card> : null}

        <div className="grid gap-4 xl:grid-cols-3">
          <StrategySummaryCard
            eyebrow="Trend Engine"
            href="/app/strategy/asura"
            title="Asura"
            details={asuraRows.length
              ? `${formatStrategyCell(pick(asuraLead, ['symbol']))} leads the scan with signal ${formatNumber(pick(asuraLead, ['signalScore', 'signal_score']), 1)}.`
              : 'No live Asura setups matched the current trend filters.'}
            stats={[
              { label: 'Signals', value: formatStrategyCell(asRecord(asuraPayload).total ?? asuraRows.length) },
              { label: 'Avg Signal', value: formatNumber(average(asuraRows.map((row) => pick(row, ['signalScore', 'signal_score']))), 1) },
              { label: 'Breakouts', value: String(asuraRows.filter((row) => String(pick(row, ['breakoutFlag']) ?? '').toUpperCase() === 'BREAKOUT').length) },
              { label: 'Avg RR2', value: formatNumber(average(asuraRows.map((row) => pick(row, ['rr2']))), 2) },
            ]}
          />
          <StrategySummaryCard
            eyebrow="Mover Board"
            href="/app/strategy/yamuna"
            title="Yamuna"
            details={yamunaState.gainers.length
              ? `${formatStrategyCell(pick(topGainer, ['symbol', 'stockName']))} is the strongest daily mover at ${formatPct(pick(topGainer, ['percentage', 'percentChange']))}.`
              : 'No live Yamuna mover data is available right now.'}
            stats={[
              { label: 'Gainers', value: String(yamunaState.gainers.length) },
              { label: 'Losers', value: String(yamunaState.losers.length) },
              { label: 'Vol. Movers', value: String(sortedVolumeRows.length) },
              { label: 'Top Volume Ratio', value: formatRatio(pick(topVolume, ['volumeRatio', 'volumeRatioSort'])) },
            ]}
          />
          <StrategySummaryCard
            eyebrow="Confluence"
            title="Shared Focus List"
            details={overlap.length
              ? `Shared focus: ${overlap.slice(0, 6).join(', ')}.`
              : 'No direct overlap in the current snapshot, so keep Asura trends and Yamuna movers separate for now.'}
            stats={[
              { label: 'Overlap', value: String(overlap.length) },
              { label: 'Breadth', value: `${formatStrategyCell(breadth.advances || 0)}/${formatStrategyCell(breadth.declines || 0)}` },
              { label: 'Top Gainer', value: formatStrategyCell(pick(topGainer, ['symbol', 'stockName'])) },
              { label: 'Top Volume', value: formatStrategyCell(pick(topVolume, ['symbol', 'stock'])) },
            ]}
          />
        </div>

        <p className="rounded-3xl border border-slate-200 bg-white px-5 py-4 text-sm font-semibold text-slate-600 shadow-sm dark:border-slate-700/70 dark:bg-slate-900/80 dark:text-slate-300 dark:shadow-[0_12px_32px_rgba(2,6,23,0.22)]">
          Tracker tables below keep the existing column format. When a source does not provide a field directly, that cell stays blank instead of inventing a value.
        </p>

        <section className="space-y-4">
          <h2 className="text-2xl font-black text-slate-950 dark:text-slate-100">4. Final Backtesting Results</h2>
          <div className="grid gap-5">
            {agentConfigs.map((config) => <AgentPanel key={config.strategy} config={config} />)}
          </div>
        </section>

        <section className="space-y-4">
          <h2 className="text-2xl font-black text-slate-950 dark:text-slate-100">1. Momentum Indicators</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <Card variant="light" padding="md"><h3 className="text-lg font-black text-slate-950 dark:text-slate-100">MACD &gt; 0</h3><p className="mt-2 text-sm font-semibold text-slate-600 dark:text-slate-300">Positive MACD histogram supports upside momentum and helps separate genuine continuation from weak bounces.</p></Card>
            <Card variant="light" padding="md"><h3 className="text-lg font-black text-slate-950 dark:text-slate-100">RSI &gt; 50</h3><p className="mt-2 text-sm font-semibold text-slate-600 dark:text-slate-300">RSI above 50 keeps the bias on the strong side of the range and confirms buyers still control the swing.</p></Card>
          </div>
          <TrackerTable rows={buildMomentumRows(yamunaState.gainers)} stateText={yamunaState.gainers.length ? `Loaded ${Math.min(yamunaState.gainers.length, TABLE_PAGE_SIZE)} Yamuna gainers for momentum review.` : 'Yamuna momentum data is currently unavailable.'} title="Strategy Tracker Momentum" />
        </section>

        <section className="space-y-4">
          <h2 className="text-2xl font-black text-slate-950 dark:text-slate-100">2. Trend Indicators</h2>
          <div className="grid gap-4 md:grid-cols-4">
            {['EMA > 20', 'EMA > 50', 'EMA > 100', 'EMA > 200'].map((label) => <Card key={label} variant="light" padding="md"><h3 className="text-lg font-black text-slate-950 dark:text-slate-100">{label}</h3><p className="mt-2 text-sm font-semibold text-slate-600 dark:text-slate-300">Price above this moving average keeps the trend structure aligned with buyers.</p></Card>)}
          </div>
          <Card variant="light" padding="md"><h3 className="text-lg font-black text-slate-950 dark:text-slate-100">About moving averages</h3><p className="mt-2 text-sm font-semibold text-slate-600 dark:text-slate-300">Moving averages smooth price into a readable trend line. The 20/50/100/200-day periods are practical reference levels for short, medium, and long trend context.</p></Card>
          <TrackerTable rows={buildTrendRows(asuraRows)} stateText={asuraRows.length ? `Loaded ${asuraRows.length} Asura setups from the live trend scanner.` : 'Asura trend data is currently unavailable.'} title="Strategy Tracker Trend" />
        </section>

        <section className="space-y-4">
          <h2 className="text-2xl font-black text-slate-950 dark:text-slate-100">3. Volume Indicators</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <Card variant="light" padding="md"><h3 className="text-lg font-black text-slate-950 dark:text-slate-100">Volume &gt; 20-day average</h3><p className="mt-2 text-sm font-semibold text-slate-600 dark:text-slate-300">Volume above the 20-day average validates that participation is expanding with the move.</p></Card>
            <Card variant="light" padding="md"><h3 className="text-lg font-black text-slate-950 dark:text-slate-100">On Balance Volume (OBV)</h3><p className="mt-2 text-sm font-semibold text-slate-600 dark:text-slate-300">OBV helps spot accumulation and divergence. When price breaks out and OBV confirms, the move is usually more trustworthy.</p></Card>
          </div>
          <TrackerTable rows={buildVolumeRows(sortedVolumeRows)} stateText={sortedVolumeRows.length ? `Loaded ${Math.min(sortedVolumeRows.length, TABLE_PAGE_SIZE)} Yamuna volume movers for confirmation.` : 'Yamuna volume data is currently unavailable.'} title="Strategy Tracker Volume" />
        </section>
      </div>
    </StrategyMigrationLayout>
  );
}
