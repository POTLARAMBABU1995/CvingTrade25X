import type { InputHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export type UiInputVariant = 'surface' | 'light';

export type UiInputProps = InputHTMLAttributes<HTMLInputElement> & {
  invalid?: boolean;
  variant?: UiInputVariant;
};

const variantClasses: Record<UiInputVariant, string> = {
  surface: 'border-line/60 bg-white/80 text-text placeholder:text-dim backdrop-blur-xl focus:border-[rgb(var(--page-accent-rgb)/0.22)] focus:bg-white dark:border-slate-700/70 dark:bg-slate-900/80 dark:text-slate-100 dark:placeholder:text-slate-400 dark:focus:bg-slate-900',
  light: 'border-slate-200 bg-white text-slate-950 placeholder:text-slate-400 focus:border-slate-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-400 dark:focus:border-slate-500',
};

export function UiInput({
  className,
  invalid = false,
  type = 'text',
  variant = 'surface',
  ...props
}: UiInputProps) {
  return (
    <input
      type={type}
      data-slot="input"
      aria-invalid={invalid || props['aria-invalid'] === true}
      className={cn(
        'focus-ring h-12 w-full rounded-[20px] border px-4 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-60',
        variantClasses[variant],
        invalid && (variant === 'light' ? 'border-rose-300' : 'border-crimson/30 text-crimson'),
        className,
      )}
      {...props}
    />
  );
}
