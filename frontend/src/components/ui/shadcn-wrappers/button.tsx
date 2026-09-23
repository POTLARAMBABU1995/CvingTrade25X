import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { Spinner } from '../Spinner';

export type UiButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'chip';
export type UiButtonSize = 'sm' | 'md' | 'lg';

export type UiButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  size?: UiButtonSize;
  variant?: UiButtonVariant;
  loading?: boolean;
  leadingIcon?: ReactNode;
  trailingIcon?: ReactNode;
  fullWidth?: boolean;
};

const sizeClasses: Record<UiButtonSize, string> = {
  sm: 'h-9 px-3 text-sm',
  md: 'h-10 px-4 text-sm',
  lg: 'h-11 px-5 text-base',
};

const variantClasses: Record<UiButtonVariant, string> = {
  primary: 'border border-transparent bg-gradient-to-r from-[rgb(var(--page-accent-rgb))] to-[rgb(var(--page-accent-rgb-2))] text-white shadow-[0_16px_34px_rgba(59,130,246,0.22)] hover:brightness-105',
  secondary: 'border border-line/70 bg-white/85 text-text backdrop-blur-xl hover:bg-white dark:border-slate-700/70 dark:bg-slate-900/85 dark:text-slate-100 dark:hover:bg-slate-900',
  ghost: 'bg-transparent text-text hover:bg-[rgb(var(--page-accent-rgb)/0.08)]',
  danger: 'border border-crimson/22 bg-crimson/10 text-crimson hover:bg-crimson/16',
  chip: 'border border-line/70 bg-white/70 text-muted backdrop-blur-xl hover:border-[rgb(var(--page-accent-rgb)/0.18)] hover:text-text dark:border-slate-700/70 dark:bg-slate-900/72 dark:text-slate-300',
};

export function UiButton({
  className,
  children,
  disabled,
  fullWidth = false,
  leadingIcon,
  loading = false,
  size = 'md',
  trailingIcon,
  type = 'button',
  variant = 'primary',
  ...props
}: UiButtonProps) {
  return (
    <button
      type={type}
      data-slot="button"
      className={cn(
        'focus-ring inline-flex items-center justify-center gap-2 rounded-full font-semibold transition duration-200 disabled:cursor-not-allowed disabled:opacity-60',
        fullWidth && 'w-full',
        sizeClasses[size],
        variantClasses[variant],
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Spinner size={size === 'sm' ? 'sm' : 'md'} tone={variant === 'danger' ? 'danger' : 'current'} /> : null}
      {!loading && leadingIcon ? <span className="shrink-0">{leadingIcon}</span> : null}
      <span>{children}</span>
      {trailingIcon ? <span className="shrink-0">{trailingIcon}</span> : null}
    </button>
  );
}
