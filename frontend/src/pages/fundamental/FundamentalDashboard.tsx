import { FormEvent, ReactNode, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FundamentalScoreCard } from '../../components/fundamental/cards/FundamentalScoreCard';
import { RevenueGrowthChart } from '../../components/fundamental/charts/RevenueGrowthChart';
import { FundamentalRefreshIcon, FundamentalSearchIcon } from '../../components/fundamental/fundamentalIcons';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState as SharedEmptyState } from '../../components/ui/EmptyState';
import { Input } from '../../components/ui/Input';
import { PageHeader } from '../../components/ui/PageHeader';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { cn } from '../../lib/cn';
import { fetchFundamentalCards } from '../../services/fundamental/fundamentalApi';
import { normalizeSymbol } from '../../services/fundamental/fundamentalFormatters';
import { resolveOverallStatus } from '../../services/fundamental/fundamentalScoreRules';
import type { FundamentalCard } from '../../services/fundamental/fundamentalTypes';

const exchanges = ['NSE', 'BSE', 'NSE SME'];
const sectors = ['All Sectors', 'Refineries & Marketing', 'Private Bank', 'IT Services', 'Capital Goods', 'Pharma'];

const recentRuns = [
  { id: 'FA-20260508-001', symbol: 'RELIANCE', status: 'Completed', score: '82/100', time: '08:40 IST' },
  { id: 'FA-20260508-002', symbol: 'TCS', status: 'Queued', score: 'Pending', time: '08:42 IST' },
  { id: 'FA-20260508-003', symbol: 'HDFCBANK', status: 'Completed', score: '76/100', time: '08:45 IST' },
];

const watchlistRows = [
  { symbol: 'RELIANCE', label: 'Good Fundamental', color: 'bg-emerald-100 text-emerald-800' },
  { symbol: 'TCS', label: 'Valuation Watch', color: 'bg-amber-100 text-amber-800' },
  { symbol: 'HDFCBANK', label: 'Balance Sheet Strong', color: 'bg-blue-100 text-blue-800' },
  { symbol: 'ADANIPORTS', label: 'Governance Watch', color: 'bg-rose-100 text-rose-800' },
];

const sectionChipClass: Record<FundamentalCard['section'], string> = {
  overall: 'bg-slate-100 text-slate-800',
  growth: 'bg-emerald-100 text-emerald-800',
  profit_loss: 'bg-violet-100 text-violet-800',
  cash_flow: 'bg-cyan-100 text-cyan-800',
  balance_sheet: 'bg-blue-100 text-blue-800',
  returns: 'bg-teal-100 text-teal-800',
  valuation: 'bg-amber-100 text-amber-800',
  dividend: 'bg-sky-100 text-sky-800',
  governance: 'bg-indigo-100 text-indigo-800',
  peers: 'bg-fuchsia-100 text-fuchsia-800',
  risk: 'bg-rose-100 text-rose-800',
};

function DashboardSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, index) => (
        <Skeleton key={index} variant="light" className="h-[210px] rounded-[26px] border border-slate-200" />
      ))}
    </div>
  );
}

function StrengthList({ title, cards }: { title: string; cards: FundamentalCard[] }) {
  return (
    <Card variant="light" padding="md">
      <h2 className="text-lg font-bold tracking-[-0.03em] text-slate-950">{title}</h2>
      <div className="mt-4 flex flex-col gap-3">
        {cards.map((card) => (
          <div key={card.key} className="flex items-center justify-between gap-4 rounded-[20px] bg-slate-50 px-4 py-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-bold text-slate-900">{card.title}</p>
              <p className="truncate text-xs text-slate-500">{card.description}</p>
            </div>
            <span className={cn('shrink-0 rounded-full px-2.5 py-1 text-xs font-bold', sectionChipClass[card.section])}>
              {card.value}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function DashboardInfoPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card variant="light" padding="md">
      <h2 className="text-lg font-bold text-slate-950">{title}</h2>
      <div className="mt-4 flex flex-col gap-3">{children}</div>
    </Card>
  );
}

export function FundamentalDashboard() {
  const [symbol, setSymbol] = useState('RELIANCE');
  const [analysisSymbol, setAnalysisSymbol] = useState('RELIANCE');
  const [exchange, setExchange] = useState('NSE');
  const [sector, setSector] = useState('Refineries & Marketing');

  const query = useQuery({
    queryKey: ['fundamental-cards', analysisSymbol],
    queryFn: ({ signal }) => fetchFundamentalCards(analysisSymbol, signal),
  });

  const summary = query.data;
  const overall = resolveOverallStatus(summary?.overallScore ?? 0);

  const topStrengths = useMemo(() => {
    return (summary?.cards ?? [])
      .filter((card) => ['EXCELLENT', 'GOOD'].includes(card.status))
      .sort((a, b) => (b.numericValue ?? 0) - (a.numericValue ?? 0))
      .slice(0, 5);
  }, [summary]);

  const topWeaknesses = useMemo(() => {
    return (summary?.cards ?? [])
      .filter((card) => ['WATCH', 'AVERAGE', 'WEAK', 'RISK'].includes(card.status))
      .slice(0, 5);
  }, [summary]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextSymbol = normalizeSymbol(symbol) || 'RELIANCE';
    setSymbol(nextSymbol);
    setAnalysisSymbol(nextSymbol);
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Fundamental Analysis 360" />

      <form onSubmit={handleSubmit} className="grid gap-3 lg:grid-cols-[1.35fr_0.7fr_0.9fr_auto]">
        <label className="relative block">
          <span className="sr-only">Company symbol</span>
          <FundamentalSearchIcon className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            value={symbol}
            onChange={(event) => setSymbol(event.target.value)}
            variant="light"
            placeholder="Search company or symbol"
            className="pl-11 pr-4 font-semibold"
          />
        </label>

        <Select
          value={exchange}
          onChange={(event) => setExchange(event.target.value)}
          variant="light"
        >
          {exchanges.map((item) => <option key={item}>{item}</option>)}
        </Select>

        <Select
          value={sector}
          onChange={(event) => setSector(event.target.value)}
          variant="light"
        >
          {sectors.map((item) => <option key={item}>{item}</option>)}
        </Select>

        <Button
          type="submit"
          leadingIcon={<FundamentalRefreshIcon className="h-4 w-4" />}
          className="h-12 rounded-[20px] bg-gradient-to-r from-[rgb(var(--page-accent-rgb))] to-[rgb(var(--page-accent-rgb-2))] px-6 text-sm font-bold text-white shadow-lg shadow-[rgba(59,130,246,0.16)] transition hover:-translate-y-0.5"
        >
          Analyze
        </Button>
      </form>

      {summary ? (
        <section className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-[32px] border border-slate-200/70 bg-gradient-to-br from-white/96 via-slate-50/92 to-[rgb(var(--page-accent-rgb)/0.08)] p-6 text-slate-950 shadow-xl shadow-[rgba(15,23,42,0.08)] lg:p-8">
            <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.22em] text-slate-500">{summary.exchange} / {summary.sector}</p>
                <h2 className="mt-3 text-4xl font-bold tracking-[-0.05em] lg:text-6xl">{summary.companyName}</h2>
                <p className="mt-3 text-lg font-semibold text-slate-600">{summary.symbol}</p>
              </div>
              <div className="rounded-[28px] border border-slate-200/70 bg-white/90 p-5 text-slate-950 shadow-sm backdrop-blur-xl">
                <p className="text-sm font-bold uppercase tracking-[0.18em] text-slate-400">Overall score</p>
                <p className="mt-2 text-5xl font-bold tracking-[-0.06em]">{summary.overallScore}</p>
                <p className="mt-2 text-sm font-bold text-emerald-700">{overall.finalLabel}</p>
              </div>
            </div>

            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              <div className="rounded-[24px] border border-slate-200/70 bg-white/82 p-4 backdrop-blur-xl">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Market cap</p>
                <p className="mt-2 text-lg font-bold">{summary.marketCap}</p>
              </div>
              <div className="rounded-[24px] border border-slate-200/70 bg-white/82 p-4 backdrop-blur-xl">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Current price</p>
                <p className="mt-2 text-lg font-bold">{summary.currentPrice}</p>
              </div>
              <div className="rounded-[24px] border border-slate-200/70 bg-white/82 p-4 backdrop-blur-xl">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Last updated</p>
                <p className="mt-2 text-lg font-bold">{summary.lastUpdated}</p>
              </div>
            </div>
          </div>

          <RevenueGrowthChart />
        </section>
      ) : null}

      {query.isLoading ? <DashboardSkeleton /> : null}
      {!query.isLoading && summary && summary.cards.length === 0 ? (
        <SharedEmptyState
          surface="light"
          eyebrow="Fundamental Analysis 360"
          title="No fundamental cards found"
          description="Try another symbol or run analysis after the backend endpoint is connected."
        />
      ) : null}
      {!query.isLoading && summary?.cards?.length ? (
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {summary.cards.map((card) => (
            <FundamentalScoreCard key={card.key} card={card} />
          ))}
        </section>
      ) : null}

      {summary ? (
        <section className="grid gap-4 lg:grid-cols-2">
          <StrengthList title="Top strengths" cards={topStrengths} />
          <StrengthList title="Watch / weakness queue" cards={topWeaknesses} />
        </section>
      ) : null}

      {summary ? (
        <section className="grid gap-4 xl:grid-cols-3">
          <DashboardInfoPanel title="Risk alerts">
            {topWeaknesses.slice(0, 3).map((card) => (
              <div key={card.key} className="rounded-[20px] border border-amber-200 bg-amber-50 px-4 py-3">
                <p className="text-sm font-bold text-amber-950">{card.title}</p>
                <p className="mt-1 text-xs leading-5 text-amber-800">{card.description}</p>
              </div>
            ))}
          </DashboardInfoPanel>

          <DashboardInfoPanel title="Recent analysis runs">
            {recentRuns.map((run) => (
              <div key={run.id} className="grid grid-cols-[1fr_auto] gap-3 rounded-[20px] bg-slate-50 px-4 py-3">
                <div>
                  <p className="text-sm font-bold text-slate-950">{run.symbol}</p>
                  <p className="text-xs text-slate-500">{run.id} / {run.time}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-bold text-slate-800">{run.score}</p>
                  <p className="text-xs text-slate-500">{run.status}</p>
                </div>
              </div>
            ))}
          </DashboardInfoPanel>

          <DashboardInfoPanel title="Watchlist summary">
            {watchlistRows.map((row) => (
              <div key={row.symbol} className="flex items-center justify-between gap-3 rounded-[20px] bg-slate-50 px-4 py-3">
                <span className="font-bold text-slate-950">{row.symbol}</span>
                <span className={cn('rounded-full px-2.5 py-1 text-xs font-bold', row.color)}>{row.label}</span>
              </div>
            ))}
          </DashboardInfoPanel>
        </section>
      ) : null}
    </div>
  );
}
