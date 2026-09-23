import { cn } from '../../lib/cn';

type SkeletonCardsProps = {
  count?: number;
  className?: string;
};

export function SkeletonCards({ count = 4, className }: SkeletonCardsProps) {
  return (
    <div className={cn('ui-skeleton-cards', className)} aria-hidden="true">
      {Array.from({ length: Math.max(1, count) }).map((_, idx) => (
        <div key={idx} className="ui-skeleton-card" />
      ))}
    </div>
  );
}

