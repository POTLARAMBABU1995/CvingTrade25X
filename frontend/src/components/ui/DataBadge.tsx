import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

type DataBadgeTone = 'default' | 'accent' | 'success' | 'warn' | 'danger';

type DataBadgeProps = {
  children: ReactNode;
  tone?: DataBadgeTone;
  className?: string;
};

export function DataBadge({ children, tone = 'default', className }: DataBadgeProps) {
  return <span className={cn('ui-data-badge', `ui-data-badge--${tone}`, className)}>{children}</span>;
}

