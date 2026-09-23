import { cn } from '../../lib/cn';

type SpinnerTone = 'default' | 'accent' | 'success' | 'warn' | 'danger' | 'current';
type SpinnerSize = 'sm' | 'md' | 'lg';

type SpinnerProps = {
  className?: string;
  size?: SpinnerSize;
  tone?: SpinnerTone;
};

const sizeClasses: Record<SpinnerSize, string> = {
  sm: 'h-3.5 w-3.5 border-[2px]',
  md: 'h-4 w-4 border-[2px]',
  lg: 'h-5 w-5 border-[2.5px]',
};

const toneClasses: Record<SpinnerTone, string> = {
  default: 'border-white/18 border-t-white/75',
  accent: 'border-cyan/18 border-t-cyan',
  success: 'border-emerald/18 border-t-emerald',
  warn: 'border-amber/20 border-t-amber',
  danger: 'border-crimson/18 border-t-crimson',
  current: 'border-white/20 border-t-current',
};

export function Spinner({ className, size = 'md', tone = 'accent' }: SpinnerProps) {
  return (
    <span
      aria-hidden="true"
      className={cn('inline-block animate-spin rounded-full', sizeClasses[size], toneClasses[tone], className)}
    />
  );
}
