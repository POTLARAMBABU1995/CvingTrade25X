import { cn } from '../../lib/cn';
import { Button } from './Button';
import { Card } from './Card';

type ErrorStateProps = {
  title?: string;
  description?: string;
  onRetry?: () => void;
  className?: string;
  retryLabel?: string;
  eyebrow?: string;
  surface?: 'dark' | 'light';
};

export function ErrorState({
  title = 'Failed to load data',
  description = 'The backend request did not complete successfully.',
  onRetry,
  className,
  retryLabel = 'Retry',
  eyebrow,
  surface = 'dark',
}: ErrorStateProps) {
  if (surface === 'light') {
    return (
      <Card variant="light" padding="lg" className={cn('border-rose-200 text-center dark:border-rose-900/50', className)}>
        <div className="mx-auto flex max-w-2xl flex-col items-center gap-3">
          {eyebrow ? <p className="text-xs font-bold uppercase tracking-[0.22em] text-rose-400 dark:text-rose-300">{eyebrow}</p> : null}
          <h3 className="m-0 text-xl font-bold text-slate-950 dark:text-slate-100">{title}</h3>
          <p className="m-0 max-w-xl text-slate-500 dark:text-slate-300">{description}</p>
          {onRetry ? (
            <Button
              variant="secondary"
              className="border-rose-200 bg-rose-50 text-rose-800 hover:bg-rose-100 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-200 dark:hover:bg-rose-950/60"
              onClick={onRetry}
            >
              {retryLabel}
            </Button>
          ) : null}
        </div>
      </Card>
    );
  }

  return (
    <div className={cn('ui-error', className)}>
      {eyebrow ? <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-dim">{eyebrow}</p> : null}
      <h3>{title}</h3>
      <p>{description}</p>
      {onRetry ? (
        <Button type="button" variant="danger" size="sm" className="ui-error__retry rounded-full" onClick={onRetry}>
          {retryLabel}
        </Button>
      ) : null}
    </div>
  );
}
