import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

type AppToolbarProps = {
  'aria-label': string;
  children: ReactNode;
  className?: string;
};

export function AppToolbar({ children, className, 'aria-label': ariaLabel }: AppToolbarProps) {
  return (
    <section className={cn('sr-toolbar trend-toolbar', className)} aria-label={ariaLabel}>
      {children}
    </section>
  );
}
