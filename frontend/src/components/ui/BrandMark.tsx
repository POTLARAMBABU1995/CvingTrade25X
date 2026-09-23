import { cn } from '../../lib/cn';
import { SparkIcon } from './Icons';

type BrandMarkProps = {
  className?: string;
  size?: 'sm' | 'md';
  textClassName?: string;
  withText?: boolean;
};

export function BrandMark({
  className,
  size = 'md',
  textClassName,
  withText = true,
}: BrandMarkProps) {
  const iconSizeClass = size === 'sm' ? 'h-8 w-8 rounded-lg' : 'h-10 w-10 rounded-xl';
  const sparkSizeClass = size === 'sm' ? 'h-4 w-4' : 'h-5 w-5';
  const textSizeClass = size === 'sm' ? 'text-base' : 'text-lg';

  return (
    <span className={cn('inline-flex items-center gap-3', className)}>
      <span
        aria-hidden="true"
        className={cn(
          'inline-flex items-center justify-center bg-gradient-to-br from-emerald-500 via-sky-500 to-cyan-500 text-white shadow-lg shadow-emerald-500/20',
          iconSizeClass,
        )}
      >
        <SparkIcon className={sparkSizeClass} />
      </span>
      {withText ? (
        <span className={cn('font-black tracking-tight text-slate-950 dark:text-slate-100', textSizeClass, textClassName)}>
          CvingTrade25X
        </span>
      ) : null}
    </span>
  );
}
