import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

type StickyTableHeaderProps = {
  children: ReactNode;
  className?: string;
};

export function StickyTableHeader({ children, className }: StickyTableHeaderProps) {
  return <div className={cn('ui-sticky-table-header', className)}>{children}</div>;
}

