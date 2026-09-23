import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

type FilterBarProps = {
  children: ReactNode;
  className?: string;
};

export function FilterBar({ children, className }: FilterBarProps) {
  return <div className={cn('ui-filter-bar', className)}>{children}</div>;
}

