import type { HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export type UiCardVariant = 'surface' | 'light' | 'subtle';
export type UiCardPadding = 'none' | 'sm' | 'md' | 'lg';

export type UiCardProps = HTMLAttributes<HTMLDivElement> & {
  padding?: UiCardPadding;
  variant?: UiCardVariant;
};

const variantClasses: Record<UiCardVariant, string> = {
  surface: 'surface-card border border-line/30 text-text shadow-panel backdrop-blur-xl',
  light: 'border border-slate-200/70 bg-white/86 text-slate-950 shadow-[0_12px_32px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-900/86 dark:text-slate-100 dark:shadow-[0_14px_34px_rgba(2,6,23,0.46)]',
  subtle: 'border border-slate-200/60 bg-white/72 text-text shadow-none backdrop-blur-xl dark:border-slate-700/60 dark:bg-slate-900/72 dark:text-slate-100',
};

const paddingClasses: Record<UiCardPadding, string> = {
  none: 'p-0',
  sm: 'p-4',
  md: 'p-5',
  lg: 'p-6 lg:p-8',
};

export function UiCard({ className, padding = 'md', variant = 'surface', ...props }: UiCardProps) {
  return (
    <div
      data-slot="card"
      className={cn(
        'rounded-[28px]',
        variantClasses[variant],
        paddingClasses[padding],
        className,
      )}
      {...props}
    />
  );
}
