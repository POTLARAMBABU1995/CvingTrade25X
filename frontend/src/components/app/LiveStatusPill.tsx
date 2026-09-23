import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

export type LiveStatusState = 'live' | 'syncing' | 'synching' | 'stale';

type LiveStatusPillProps = {
  className?: string;
  label?: ReactNode;
  state: LiveStatusState;
  title?: string;
};

const stateClasses: Record<Exclude<LiveStatusState, 'synching'>, string> = {
  live: 'border-emerald-200 bg-emerald-50 text-emerald-700 shadow-emerald-950/5 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300',
  syncing: 'border-sky-200 bg-sky-50 text-sky-700 shadow-sky-950/5 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300',
  stale: 'border-amber-200 bg-amber-50 text-amber-700 shadow-amber-950/5 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300',
};

const stateDots: Record<Exclude<LiveStatusState, 'synching'>, string> = {
  live: 'bg-emerald-500 dark:bg-emerald-400',
  syncing: 'bg-sky-500 dark:bg-sky-400',
  stale: 'bg-amber-500 dark:bg-amber-400',
};

const stateLabels: Record<Exclude<LiveStatusState, 'synching'>, string> = {
  live: 'Live',
  syncing: 'Syncing',
  stale: 'Stale',
};

export function normalizeLiveStatusState(state: LiveStatusState): Exclude<LiveStatusState, 'synching'> {
  return state === 'synching' ? 'syncing' : state;
}

export function LiveStatusPill({ className, label, state, title }: LiveStatusPillProps) {
  const normalizedState = normalizeLiveStatusState(state);
  const resolvedLabel = label ?? stateLabels[normalizedState];

  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold tracking-wide shadow-sm backdrop-blur-sm transition-colors',
        stateClasses[normalizedState],
        className,
      )}
      role="status"
      aria-live="polite"
      aria-label={typeof resolvedLabel === 'string' ? resolvedLabel : title ?? stateLabels[normalizedState]}
      title={title}
    >
      <span aria-hidden="true" className={cn('h-2 w-2 rounded-full', stateDots[normalizedState])} />
      <span>{resolvedLabel}</span>
    </span>
  );
}
