import { WATCHLIST } from '../../data/dashboard';
import { Surface } from '../ui/Surface';

const BIAS_STYLES = {
  build: 'border-emerald/20 bg-emerald/10 text-emerald',
  hold: 'border-cyan/18 bg-cyan/10 text-cyan',
  trim: 'border-crimson/18 bg-crimson/10 text-crimson',
} as const;

export function WatchlistRail() {
  return (
    <Surface className="p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.32em] text-dim">Watchlist</p>
          <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-text">Shortlist and monitoring rail</h3>
        </div>
        <span className="rounded-full border border-slate-200/70 bg-white/75 px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.24em] text-muted backdrop-blur-xl">
          5 names
        </span>
      </div>
      <div className="mt-5 space-y-3">
        {WATCHLIST.map((item) => (
          <div key={item.symbol} className="rounded-[22px] border border-slate-200/70 bg-white/75 p-4 backdrop-blur-xl">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-text">{item.symbol}</p>
                <p className="mt-1 text-sm leading-6 text-muted">{item.thesis}</p>
              </div>
              <span className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.24em] ${BIAS_STYLES[item.bias]}`}>
                {item.bias}
              </span>
            </div>
            <div className="mt-4 flex items-center justify-between gap-3 text-xs uppercase tracking-[0.24em] text-dim">
              <span>Pivot {item.pivot}</span>
              <span className="font-medium text-text">{item.change}</span>
            </div>
          </div>
        ))}
      </div>
    </Surface>
  );
}
