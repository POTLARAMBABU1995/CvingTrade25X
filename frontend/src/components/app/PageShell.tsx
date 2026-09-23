import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

type PageShellProps = {
  children: ReactNode;
  className?: string;
};

export function PageShell({ children, className }: PageShellProps) {
  return <div className={cn('page-shell', className)}>{children}</div>;
}

