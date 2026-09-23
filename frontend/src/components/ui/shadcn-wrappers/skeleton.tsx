import type { HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export type UiSkeletonVariant = 'surface' | 'light';

export type UiSkeletonProps = HTMLAttributes<HTMLDivElement> & {
  variant?: UiSkeletonVariant;
};

const variantClasses: Record<UiSkeletonVariant, string> = {
  surface: 'bg-slate-200/60',
  light: 'bg-slate-200/80',
};

export function UiSkeleton({ className, variant = 'surface', ...props }: UiSkeletonProps) {
  return (
    <div
      data-slot="skeleton"
      className={cn('animate-pulse rounded-[24px]', variantClasses[variant], className)}
      aria-hidden="true"
      {...props}
    />
  );
}
