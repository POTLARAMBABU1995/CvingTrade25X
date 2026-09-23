import { LiveStatusPill } from './LiveStatusPill';

export type AppStatusTone = 'error' | 'info' | 'loading' | 'success';

type AppStatusToastProps = {
  children: string;
  className?: string;
  title?: string;
  tone?: AppStatusTone;
};

const toneStates: Record<AppStatusTone, 'live' | 'syncing' | 'stale'> = {
  error: 'stale',
  info: 'live',
  loading: 'syncing',
  success: 'live',
};

export function AppStatusToast({
  children,
  className,
  title,
  tone = 'info',
}: AppStatusToastProps) {
  return (
    <LiveStatusPill state={toneStates[tone]} title={title} label={children} className={className} />
  );
}
