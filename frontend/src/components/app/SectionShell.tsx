import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

type SectionShellProps = {
  children: ReactNode;
  className?: string;
};

export function SectionShell({ children, className }: SectionShellProps) {
  return <section className={cn('section-shell', className)}>{children}</section>;
}

