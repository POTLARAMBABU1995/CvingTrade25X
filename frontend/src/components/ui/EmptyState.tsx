import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';
import { Card } from './Card';

type EmptyStateProps = {
  title?: string;
  description?: string;
  action?: ReactNode;
  className?: string;
  eyebrow?: string;
  icon?: ReactNode;
  surface?: 'dark' | 'light';
};

export function EmptyState({
  title = 'No records found',
  description = 'Try changing filters or symbol selection.',
  action,
  className,
  eyebrow,
  icon,
  surface = 'dark',
}: EmptyStateProps) {
  if (surface === 'light') {
    return (
      <Card variant="light" padding="lg" className={cn('text-center', className)}>
        <div className="mx-auto flex max-w-2xl flex-col items-center gap-3">
          {icon ? <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500 dark:bg-slate-900 dark:text-slate-400">{icon}</div> : null}
          {eyebrow ? <p className="text-xs font-bold uppercase tracking-[0.22em] text-slate-400 dark:text-slate-500">{eyebrow}</p> : null}
          <h3 className="m-0 text-xl font-bold text-slate-950 dark:text-slate-100">{title}</h3>
          <p className="m-0 max-w-xl text-slate-500 dark:text-slate-300">{description}</p>
          {action ? <div className="pt-2">{action}</div> : null}
        </div>
      </Card>
    );
  }

  return (
    <div className={cn('ui-empty', className)}>
      {icon ? <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/6 text-muted dark:bg-slate-900/72 dark:text-slate-300">{icon}</div> : null}
      {eyebrow ? <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-dim dark:text-slate-400">{eyebrow}</p> : null}
      <h3>{title}</h3>
      <p>{description}</p>
      {action ? <div className="ui-empty__action">{action}</div> : null}
    </div>
  );
}
