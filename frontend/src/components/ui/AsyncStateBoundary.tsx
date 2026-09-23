import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { LoadingOverlay } from './LoadingOverlay';

type AsyncStateBoundaryProps = {
  isLoading: boolean;
  isFetching?: boolean;
  isError?: boolean;
  isEmpty?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  skeleton: ReactNode;
  children: ReactNode;
  className?: string;
};

export function AsyncStateBoundary({
  isLoading,
  isFetching = false,
  isError = false,
  isEmpty = false,
  errorMessage,
  onRetry,
  skeleton,
  children,
  className,
}: AsyncStateBoundaryProps) {
  if (isLoading) {
    return <div className={cn('ui-async-state', className)}>{skeleton}</div>;
  }

  if (isError) {
    return (
      <ErrorState
        className={className}
        description={errorMessage || 'The backend request failed. Please retry.'}
        onRetry={onRetry}
      />
    );
  }

  if (isEmpty) {
    return <EmptyState className={className} />;
  }

  return (
    <div className={cn('ui-async-state', className)}>
      {children}
      {isFetching ? <LoadingOverlay /> : null}
    </div>
  );
}

