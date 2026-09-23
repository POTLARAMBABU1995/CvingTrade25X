import { Surface } from '../ui/Surface';

const METRICS = [
  { label: 'Win rate', value: '64.8%', tone: 'text-emerald' },
  { label: 'Median hold', value: '6.2 days', tone: 'text-text' },
  { label: 'Profit factor', value: '1.82', tone: 'text-cyan' },
  { label: 'Max drawdown', value: '-6.4%', tone: 'text-crimson' },
];

export function BacktestPanel() {
  return (
    <Surface className="p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.32em] text-dim">Backtest lab</p>
          <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-text">Execution regime snapshot</h3>
        </div>
        <span className="rounded-full border border-slate-200/70 bg-white/75 px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.24em] text-muted backdrop-blur-xl">
          Last 180 sessions
        </span>
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {METRICS.map((metric) => (
          <div key={metric.label} className="rounded-[22px] border border-slate-200/70 bg-white/75 p-4 backdrop-blur-xl">
            <p className="text-[11px] uppercase tracking-[0.26em] text-dim">{metric.label}</p>
            <p className={`mt-3 text-2xl font-semibold tracking-[-0.03em] ${metric.tone}`}>{metric.value}</p>
          </div>
        ))}
      </div>
      <div className="mt-5 rounded-[24px] border border-slate-200/70 bg-gradient-to-br from-white/70 to-slate-50/70 p-4 text-sm leading-6 text-muted backdrop-blur-xl">
        Current model quality is strongest when price sits above the 20/50/200 EMA stack, ATR expands from a low-volatility base, and sector leadership remains in the top quartile.
      </div>
    </Surface>
  );
}
