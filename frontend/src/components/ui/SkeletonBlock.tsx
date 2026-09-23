import { cn } from '../../lib/cn';

type SkeletonBlockProps = {
  className?: string;
};

export function SkeletonBlock({ className }: SkeletonBlockProps) {
  return <div className={cn('animate-pulse rounded-2xl bg-white/6', className)} />;
}