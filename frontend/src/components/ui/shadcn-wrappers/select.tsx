import type { SelectHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export type UiSelectVariant = 'surface' | 'light';

export type UiSelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  invalid?: boolean;
  variant?: UiSelectVariant;
};

const variantClasses: Record<UiSelectVariant, string> = {
  surface: 'border-line/60 bg-white/80 text-text backdrop-blur-xl focus:border-[rgb(var(--page-accent-rgb)/0.22)] focus:bg-white dark:border-slate-700/70 dark:bg-slate-900/80 dark:text-slate-100 dark:focus:bg-slate-900',
  light: 'border-slate-200 bg-white text-slate-800 focus:border-slate-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-slate-500',
};

export function UiSelect({
  className,
  invalid = false,
  variant = 'surface',
  ...props
}: UiSelectProps) {
  return (
    <select
      data-slot="select"
      aria-invalid={invalid || props['aria-invalid'] === true}
      className={cn(
        'focus-ring h-12 w-full rounded-[20px] border px-4 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60',
        variantClasses[variant],
        invalid && (variant === 'light' ? 'border-rose-300' : 'border-crimson/30 text-crimson'),
        className,
      )}
      {...props}
    />
  );
}
