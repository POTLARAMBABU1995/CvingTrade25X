import { cn } from '../../lib/cn';
import { Spinner } from './Spinner';

type LoadingOverlayProps = {
  label?: string;
  className?: string;
};

export function LoadingOverlay({ label = 'Refreshing data...', className }: LoadingOverlayProps) {
  return (
    <div className={cn('ui-loading-overlay', className)} role="status" aria-live="polite" aria-label={label}>
      <Spinner size="sm" tone="accent" />
      <span>{label}</span>
    </div>
  );
}
