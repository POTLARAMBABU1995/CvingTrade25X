import type { ComponentType, SVGProps } from 'react';
import { cn } from '../../../lib/cn';
import { getStatusMeta } from '../../../services/fundamental/fundamentalScoreRules';
import type { FundamentalCard } from '../../../services/fundamental/fundamentalTypes';
import {
  FundamentalAlertIcon,
  FundamentalBuildingIcon,
  FundamentalChartIcon,
  FundamentalScaleIcon,
  FundamentalShieldIcon,
  FundamentalTrendDownIcon,
  FundamentalTrendUpIcon,
  FundamentalWalletIcon,
} from '../fundamentalIcons';

type FundamentalScoreCardProps = {
  card: FundamentalCard;
  compact?: boolean;
};

const sectionIcons: Record<FundamentalCard['section'], ComponentType<SVGProps<SVGSVGElement>>> = {
  overall: FundamentalChartIcon,
  growth: FundamentalTrendUpIcon,
  profit_loss: FundamentalChartIcon,
  cash_flow: FundamentalWalletIcon,
  balance_sheet: FundamentalBuildingIcon,
  returns: FundamentalTrendUpIcon,
  valuation: FundamentalScaleIcon,
  dividend: FundamentalWalletIcon,
  governance: FundamentalShieldIcon,
  peers: FundamentalBuildingIcon,
  risk: FundamentalAlertIcon,
};

const sectionAccent: Record<FundamentalCard['section'], { strip: string; icon: string; wash: string }> = {
  overall: {
    strip: 'from-slate-950 via-sky-500 to-emerald-500',
    icon: 'bg-gradient-to-br from-[rgb(var(--page-accent-rgb))] to-[rgb(var(--page-accent-rgb-2))] text-white ring-slate-200',
    wash: 'bg-sky-100/45',
  },
  growth: {
    strip: 'from-emerald-500 via-lime-400 to-cyan-400',
    icon: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
    wash: 'bg-emerald-100/50',
  },
  profit_loss: {
    strip: 'from-violet-500 via-fuchsia-500 to-rose-400',
    icon: 'bg-violet-50 text-violet-700 ring-violet-100',
    wash: 'bg-violet-100/50',
  },
  cash_flow: {
    strip: 'from-cyan-500 via-sky-500 to-blue-500',
    icon: 'bg-cyan-50 text-cyan-700 ring-cyan-100',
    wash: 'bg-cyan-100/50',
  },
  balance_sheet: {
    strip: 'from-blue-600 via-indigo-500 to-violet-500',
    icon: 'bg-blue-50 text-blue-700 ring-blue-100',
    wash: 'bg-blue-100/45',
  },
  returns: {
    strip: 'from-teal-500 via-emerald-500 to-green-500',
    icon: 'bg-teal-50 text-teal-700 ring-teal-100',
    wash: 'bg-teal-100/45',
  },
  valuation: {
    strip: 'from-amber-500 via-orange-500 to-rose-400',
    icon: 'bg-amber-50 text-amber-700 ring-amber-100',
    wash: 'bg-amber-100/55',
  },
  dividend: {
    strip: 'from-sky-500 via-cyan-500 to-teal-400',
    icon: 'bg-sky-50 text-sky-700 ring-sky-100',
    wash: 'bg-sky-100/50',
  },
  governance: {
    strip: 'from-indigo-500 via-blue-500 to-emerald-500',
    icon: 'bg-indigo-50 text-indigo-700 ring-indigo-100',
    wash: 'bg-indigo-100/45',
  },
  peers: {
    strip: 'from-fuchsia-500 via-purple-500 to-indigo-500',
    icon: 'bg-fuchsia-50 text-fuchsia-700 ring-fuchsia-100',
    wash: 'bg-fuchsia-100/45',
  },
  risk: {
    strip: 'from-rose-500 via-red-500 to-orange-400',
    icon: 'bg-rose-50 text-rose-700 ring-rose-100',
    wash: 'bg-rose-100/45',
  },
};

export function FundamentalScoreCard({ card, compact = false }: FundamentalScoreCardProps) {
  const meta = getStatusMeta(card.status);
  const Icon = sectionIcons[card.section] ?? FundamentalChartIcon;
  const TrendIcon = card.trend === 'down' ? FundamentalTrendDownIcon : FundamentalTrendUpIcon;
  const accent = sectionAccent[card.section] ?? sectionAccent.overall;

  return (
    <article className="group relative min-h-[210px] overflow-hidden rounded-[26px] border border-slate-200 bg-white p-5 shadow-sm transition duration-200 hover:-translate-y-1 hover:border-slate-300 hover:shadow-xl hover:shadow-slate-950/5">
      <div className={cn('absolute inset-x-0 top-0 h-1.5 bg-gradient-to-r', accent.strip)} />
      <div className={cn('pointer-events-none absolute -right-12 -top-14 h-32 w-32 rounded-full blur-2xl', accent.wash)} />
      <div className="flex items-start justify-between gap-4">
        <div className={cn('flex h-12 w-12 shrink-0 items-center justify-center rounded-[18px] ring-1', accent.icon)}>
          <Icon className="h-5 w-5" />
        </div>
        <div className="flex items-center gap-2">
          <span className={cn('rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.14em] ring-1', meta.badgeClass)}>
            {meta.label}
          </span>
          <button
            type="button"
            title={card.tooltip}
            aria-label={`${card.title} scoring logic`}
            className="flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 text-xs font-bold text-slate-500 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900"
          >
            i
          </button>
        </div>
      </div>

      <div className="mt-5">
        <h3 className="text-[13px] font-bold uppercase tracking-[0.18em] text-slate-500">{card.title}</h3>
        <p className={cn('mt-3 font-bold tracking-[-0.04em] text-slate-950', compact ? 'text-3xl' : 'text-4xl')}>
          {card.value}
        </p>
        <p className="mt-3 min-h-[48px] text-sm leading-6 text-slate-600">{card.description}</p>
      </div>

      <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4 text-sm">
        <span className="font-medium text-slate-500">5Y trend</span>
        <span
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold',
            card.trend === 'down' ? 'bg-rose-50 text-rose-700' : card.trend === 'up' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600',
          )}
        >
          <TrendIcon className="h-3.5 w-3.5" />
          {card.trend === 'flat' ? 'stable' : card.trend}
        </span>
      </div>
    </article>
  );
}
