import { motion, useReducedMotion } from 'framer-motion';
import { PRIMARY_NAV, WATCHLIST } from '../../data/dashboard';
import { cn } from '../../lib/cn';
import {
  BookmarkIcon,
  ChartIcon,
  ChevronRightIcon,
  LabIcon,
  LayersIcon,
  PanelLeftIcon,
  RadarIcon,
  StrategyIcon,
} from '../ui/Icons';

type SidebarProps = {
  collapsed: boolean;
  onToggle: () => void;
};

const ICONS = [ChartIcon, RadarIcon, StrategyIcon, LayersIcon, LabIcon, BookmarkIcon] as const;

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.aside
      layout
      transition={{ duration: reduceMotion ? 0 : 0.28, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        'sticky top-4 hidden h-[calc(100vh-2rem)] flex-col rounded-[30px] border border-slate-200/70 bg-white/80 px-4 py-5 shadow-float backdrop-blur-xl xl:flex dark:border-slate-700/70 dark:bg-slate-900/80',
        collapsed ? 'w-[98px]' : 'w-[288px]',
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-[rgb(var(--page-accent-rgb)/0.22)] via-[rgb(var(--page-accent-rgb)/0.12)] to-transparent text-[rgb(var(--page-accent-rgb))] shadow-glow">
            <RadarIcon className="h-5 w-5" />
          </div>
          {!collapsed ? (
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.36em] text-dim">CvingTrade25X</p>
              <p className="truncate text-sm font-medium text-text">Command Deck</p>
            </div>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onToggle}
          className="focus-ring flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-200/70 bg-white/78 text-muted backdrop-blur-xl hover:border-[rgb(var(--page-accent-rgb)/0.18)] hover:text-text dark:border-slate-700/70 dark:bg-slate-900/78 dark:text-slate-300"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <PanelLeftIcon className={cn('h-4 w-4 transition', collapsed && 'rotate-180')} />
        </button>
      </div>

      <div className="mt-8 space-y-2">
        {PRIMARY_NAV.map((item, index) => {
          const Icon = ICONS[index];
          const active = index === 0;
          return (
            <a
              key={item.id}
              href={`#${item.id}`}
              className={cn(
                'group flex items-center gap-3 rounded-2xl border px-3 py-3 transition duration-200',
                active
                  ? 'border-[rgb(var(--page-accent-rgb)/0.22)] bg-[rgb(var(--page-accent-rgb)/0.09)] text-text shadow-glow'
                  : 'border-transparent bg-transparent text-muted hover:border-slate-200/70 hover:bg-white/70 hover:text-text dark:hover:border-slate-700/70 dark:hover:bg-slate-900/72 dark:hover:text-slate-100',
              )}
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-200/70 bg-white/75 text-current backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-950/70">
                <Icon className="h-4 w-4" />
              </span>
              {!collapsed ? (
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{item.label}</span>
                  <span className="block truncate text-[11px] uppercase tracking-[0.28em] text-dim dark:text-slate-400">{item.hint}</span>
                </span>
              ) : null}
              {!collapsed ? <ChevronRightIcon className="h-4 w-4 text-dim dark:text-slate-400" /> : null}
            </a>
          );
        })}
      </div>

      <div className="mt-auto rounded-[28px] border border-slate-200/70 bg-white/78 p-4 backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-900/78">
        <div className="flex items-center justify-between">
          {!collapsed ? (
            <div>
              <p className="text-[11px] uppercase tracking-[0.34em] text-dim dark:text-slate-400">Focus list</p>
              <p className="mt-1 text-sm font-medium text-text">High priority names</p>
            </div>
          ) : null}
          <span className="rounded-full border border-emerald/20 bg-emerald/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.28em] text-emerald dark:border-emerald-500/30 dark:bg-emerald-500/12 dark:text-emerald-300">
            5
          </span>
        </div>
        {!collapsed ? (
          <div className="mt-4 space-y-3">
            {WATCHLIST.slice(0, 3).map((item) => (
              <div key={item.symbol} className="rounded-2xl border border-slate-200/70 bg-white/76 px-3 py-3 backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-950/70">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-text">{item.symbol}</p>
                  <span className="text-xs font-medium text-emerald">{item.change}</span>
                </div>
                <p className="mt-1 text-xs leading-5 text-muted dark:text-slate-400">{item.thesis}</p>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </motion.aside>
  );
}
