import type { KpiCard } from '../../types';
import { cn } from '../../lib/cn';
import { Surface } from './Surface';

type KpiStatCardProps = {
  card: KpiCard;
  className?: string;
};

const toneClasses: Record<NonNullable<KpiCard['tone']>, string> = {
  cyan: 'from-cyan/22 via-cyan/8 to-transparent text-cyan',
  amber: 'from-amber/20 via-amber/8 to-transparent text-amber',
  emerald: 'from-emerald/20 via-emerald/8 to-transparent text-emerald',
  crimson: 'from-crimson/18 via-crimson/8 to-transparent text-crimson',
  slate: 'from-white/12 via-white/6 to-transparent text-text',
};

const trendClasses: Record<NonNullable<KpiCard['trend']>, string> = {
  up: 'text-emerald',
  down: 'text-crimson',
  flat: 'text-muted',
};

export function KpiStatCard({ card, className }: KpiStatCardProps) {
  const helperText = card.change || card.subtext || '--';
  const tone = card.tone || 'cyan';

  return (
    <Surface className={cn('p-5', className)} glow={tone === 'cyan'} title={card.tooltip}>
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[11px] uppercase tracking-[0.34em] text-dim">{card.label}</p>
            {card.status ? (
              <span className="rounded-full border border-slate-200/70 bg-white/75 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-muted backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-950/70 dark:text-slate-300">
                {card.status}
              </span>
            ) : null}
          </div>
          <div>
            <p className="text-2xl font-semibold tracking-[-0.04em] text-text">{card.value}</p>
            <p className={cn('mt-1 text-sm', card.trend ? trendClasses[card.trend] : 'text-muted')}>{helperText}</p>
          </div>
        </div>
        {card.icon ? (
          <div className={cn('flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br', toneClasses[tone])}>
            {card.icon}
          </div>
        ) : null}
      </div>
    </Surface>
  );
}
