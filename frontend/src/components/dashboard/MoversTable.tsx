import { MOVERS } from '../../data/dashboard';
import { Surface } from '../ui/Surface';

const STATUS_STYLE = {
  lead: 'border-emerald/20 bg-emerald/10 text-emerald',
  watch: 'border-cyan/18 bg-cyan/10 text-cyan',
  risk: 'border-crimson/18 bg-crimson/10 text-crimson',
} as const;

export function MoversTable() {
  return (
    <Surface className="overflow-hidden p-0">
      <div className="flex items-center justify-between gap-3 border-b border-slate-200/70 px-5 py-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.32em] text-dim">Market pulse</p>
          <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-text">Top movers and signal pressure</h3>
        </div>
        <span className="rounded-full border border-slate-200/70 bg-white/75 px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.24em] text-muted backdrop-blur-xl">
          Intraday shelf
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-slate-200/70 text-[11px] uppercase tracking-[0.28em] text-dim">
              <th className="px-5 py-3 font-medium">Symbol</th>
              <th className="px-5 py-3 font-medium">Setup</th>
              <th className="px-5 py-3 font-medium">Price</th>
              <th className="px-5 py-3 font-medium">Change</th>
              <th className="px-5 py-3 font-medium">Volume</th>
              <th className="px-5 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {MOVERS.map((row) => (
              <tr key={row.symbol} className="border-b border-slate-200/50 text-sm text-muted last:border-b-0 hover:bg-[rgb(var(--page-accent-rgb)/0.06)]">
                <td className="px-5 py-4 font-semibold text-text">{row.symbol}</td>
                <td className="px-5 py-4">{row.setup}</td>
                <td className="px-5 py-4 font-mono text-text">{row.price}</td>
                <td className="px-5 py-4 font-semibold text-text">{row.change}</td>
                <td className="px-5 py-4 font-mono">{row.volume}</td>
                <td className="px-5 py-4">
                  <span className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.24em] ${STATUS_STYLE[row.status]}`}>
                    {row.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Surface>
  );
}
