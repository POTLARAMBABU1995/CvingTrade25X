import { Fragment, type CSSProperties, type SVGProps } from 'react';
import { cn } from '../../lib/cn';
import { SearchIcon } from '../ui/Icons';

type StrategyToolbarProps = {
  apiTimeMs?: number | null;
  className?: string;
  dbTimeMs?: number | null;
  downloadLabel?: string;
  downloading?: boolean;
  insertDisabled?: boolean;
  insertLabel?: string;
  insertLoadingLabel?: string;
  inserting?: boolean;
  isLoading?: boolean;
  lastRefreshed?: Date | string | null;
  liveLoading?: boolean;
  loadTimeMs?: number | null;
  ltcDate?: string | null;
  status?: StrategyToolbarStatus;
  onInsertDb?: () => void;
  onDownload?: () => void;
  onLive?: () => void;
  onLiveRefresh?: () => void;
  onRefresh?: () => void;
  onSearchChange?: (value: string) => void;
  onTimeframeChange?: (value: string) => void;
  refreshing?: boolean;
  searchPlaceholder?: string;
  searchValue?: string;
  showInsertDb?: boolean;
  showTimeframe?: boolean;
  showTotal?: boolean;
  singleSurface?: boolean;
  timeframe?: string;
  timeframeOptions?: readonly string[];
  total?: number | null;
  liveLabel?: string;
  liveLoadingLabel?: string;
};

const DEFAULT_TIMEFRAMES = ['daily', 'weekly', 'monthly', 'yearly'] as const;
export type StrategyToolbarStatus = 'syncing' | 'live' | 'stale' | 'error' | 'idle';

type ToolbarStatusIcon = (props: SVGProps<SVGSVGElement>) => JSX.Element;

function iconProps(props: SVGProps<SVGSVGElement>) {
  return {
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.9,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    ...props,
  };
}

function ActivityIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M3 12h4l2.2-5 3.4 10 2.4-6H21" />
    </svg>
  );
}

function RefreshCwIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M21 12a9 9 0 0 0-15.4-6.4L3.5 7.7" />
      <path d="M3 3v5h5" />
      <path d="M3 12a9 9 0 0 0 15.4 6.4l2.1-2.1" />
      <path d="M21 21v-5h-5" />
    </svg>
  );
}

function DatabaseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <ellipse cx="12" cy="6.2" rx="7.8" ry="3.2" />
      <path d="M4.2 6.2V17.8C4.2 19.6 7.7 21 12 21s7.8-1.4 7.8-3.2V6.2" />
      <path d="M4.2 12.1C4.2 13.9 7.7 15.3 12 15.3s7.8-1.4 7.8-3.2" />
    </svg>
  );
}

function DownloadIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M12 3v11" />
      <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
      <path d="M4 20.5h16" />
    </svg>
  );
}

function WifiOffIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="m2 2 20 20" />
      <path d="M16.7 12.8a6 6 0 0 0-8.7.2" />
      <path d="M12 20h.01" />
      <path d="M5.3 9.2a11 11 0 0 1 13.4 1.6" />
      <path d="M2.6 6.6A16 16 0 0 1 21.4 8" />
    </svg>
  );
}

function Clock3Icon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 8.2v4.2l3.4 1.9" />
    </svg>
  );
}

const statusStyles: Record<StrategyToolbarStatus, {
  buttonClassName: string;
  dotClassName: string;
  dotStyle?: CSSProperties;
  icon: ToolbarStatusIcon;
  label: string;
  title: string;
}> = {
  error: {
    buttonClassName: 'border-red-300 bg-red-50 text-red-700 shadow-[0_10px_30px_rgba(239,68,68,0.16)] dark:border-red-400/60 dark:bg-red-950/45 dark:text-red-200',
    dotClassName: 'bg-red-500 shadow-[0_0_0_5px_rgba(239,68,68,0.12)] dark:bg-red-400 dark:shadow-[0_0_0_5px_rgba(248,113,113,0.2)]',
    icon: WifiOffIcon,
    label: 'Server Down',
    title: 'Backend/API request failed',
  },
  idle: {
    buttonClassName: 'border-emerald-300 bg-emerald-50 text-emerald-700 shadow-[0_10px_30px_rgba(16,185,129,0.16)] dark:border-emerald-400/60 dark:bg-emerald-950/45 dark:text-emerald-200',
    dotClassName: 'ring-4 ring-emerald-100 dark:ring-emerald-400/20',
    dotStyle: {
      backgroundColor: '#059669',
      boxShadow: '0 0 0 1px rgba(5, 150, 105, 0.45), 0 0 0 5px rgba(16, 185, 129, 0.16)',
    },
    icon: ActivityIcon,
    label: 'Live',
    title: 'Ready to refresh current data',
  },
  live: {
    buttonClassName: 'border-emerald-300 bg-emerald-50 text-emerald-700 shadow-[0_10px_30px_rgba(16,185,129,0.16)] dark:border-emerald-400/60 dark:bg-emerald-950/45 dark:text-emerald-200',
    dotClassName: 'ring-4 ring-emerald-100 dark:ring-emerald-400/20',
    dotStyle: {
      backgroundColor: '#059669',
      boxShadow: '0 0 0 1px rgba(5, 150, 105, 0.45), 0 0 0 5px rgba(16, 185, 129, 0.16)',
    },
    icon: ActivityIcon,
    label: 'Live',
    title: 'Backend/API is reachable and data loaded successfully',
  },
  stale: {
    buttonClassName: 'border-orange-300 bg-orange-50 text-orange-700 shadow-[0_10px_30px_rgba(249,115,22,0.16)] dark:border-orange-400/60 dark:bg-orange-950/45 dark:text-orange-200',
    dotClassName: 'bg-orange-500 shadow-[0_0_0_5px_rgba(249,115,22,0.12)] dark:bg-orange-400 dark:shadow-[0_0_0_5px_rgba(251,146,60,0.2)]',
    icon: Clock3Icon,
    label: 'Stale',
    title: 'Data is stale or backend marked the payload stale',
  },
  syncing: {
    buttonClassName: 'border-emerald-300 bg-emerald-50 text-emerald-700 shadow-[0_10px_30px_rgba(16,185,129,0.16)] dark:border-emerald-400/60 dark:bg-emerald-950/45 dark:text-emerald-200',
    dotClassName: 'bg-emerald-500 shadow-[0_0_0_5px_rgba(16,185,129,0.12)] dark:bg-emerald-400 dark:shadow-[0_0_0_5px_rgba(16,185,129,0.2)]',
    icon: RefreshCwIcon,
    label: 'Syncing',
    title: 'Request is running',
  },
};

export function formatDuration(ms?: number | null): string {
  if (!Number.isFinite(ms ?? NaN) || (ms ?? 0) < 0) return '-';
  if ((ms ?? 0) < 1000) return `${Math.round(ms ?? 0)}ms`;
  return `${((ms ?? 0) / 1000).toFixed(2)}s`;
}

function formatDate(value?: string | null): string {
  const raw = String(value || '').trim();
  if (!raw) return '-';
  const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return `${iso[3]}-${iso[2]}-${iso[1]}`;
  return raw;
}

function formatLastRefreshed(value?: Date | string | null): string {
  if (!value) return '-';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const pad2 = (num: number) => String(num).padStart(2, '0');
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
}

function resolveStatus(
  status: StrategyToolbarStatus | undefined,
  active: boolean,
): StrategyToolbarStatus {
  if (active) return 'syncing';
  return status ?? 'live';
}

function toTimeframeLabel(option: string): string {
  if (!option) return option;
  return option.charAt(0).toUpperCase() + option.slice(1);
}

export function StrategyToolbar({
  apiTimeMs,
  className,
  dbTimeMs,
  downloadLabel = 'Download TXT',
  downloading = false,
  insertDisabled = false,
  insertLabel = 'Insert DB',
  insertLoadingLabel = 'Inserting...',
  inserting = false,
  isLoading = false,
  lastRefreshed,
  liveLoading = false,
  loadTimeMs,
  ltcDate,
  status,
  onInsertDb,
  onDownload,
  onLive,
  onLiveRefresh,
  onRefresh,
  onSearchChange,
  onTimeframeChange,
  refreshing = false,
  searchPlaceholder = 'Search Symbol',
  searchValue = '',
  showInsertDb = false,
  showTimeframe = false,
  showTotal = false,
  singleSurface = false,
  timeframe = 'daily',
  timeframeOptions = DEFAULT_TIMEFRAMES,
  total,
  liveLabel,
  liveLoadingLabel,
}: StrategyToolbarProps) {
  const showSearch = typeof onSearchChange === 'function';
  const active = isLoading || liveLoading || refreshing || inserting || downloading;
  const disabled = active;
  const liveHandler = onLive ?? onLiveRefresh;
  const resolvedStatus = resolveStatus(status, active);
  const statusStyle = statusStyles[resolvedStatus];
  const StatusIcon = statusStyle.icon;
  const metadata = [
    `LTC_DATE: ${formatDate(ltcDate)}`,
    `Last refreshed: ${formatLastRefreshed(lastRefreshed)}`,
    `Load: ${formatDuration(loadTimeMs)}`,
    `API: ${formatDuration(apiTimeMs)}`,
    `DB: ${formatDuration(dbTimeMs)}`,
  ];

  return (
    <section
      className={cn(
        'strategy-toolbar w-full',
        !singleSurface && 'strategy-toolbar-shell rounded-[32px] border border-sky-200/90 bg-sky-50/95 p-5 shadow-[0_18px_50px_rgba(15,23,42,0.07)] backdrop-blur-xl dark:border-sky-200/90 dark:bg-sky-50/95 dark:shadow-[0_18px_50px_rgba(15,23,42,0.12)]',
        className,
      )}
    >
      <div
        className={cn(
          'strategy-toolbar-scroll w-full overflow-x-auto',
          singleSurface
            ? 'rounded-[32px] border border-sky-200/90 bg-sky-50/95 p-5 shadow-[0_18px_50px_rgba(15,23,42,0.07)] backdrop-blur-xl dark:border-sky-200/90 dark:bg-sky-50/95 dark:shadow-[0_18px_50px_rgba(15,23,42,0.12)]'
            : 'rounded-[28px] border border-sky-200/90 bg-sky-50/95 p-4 shadow-inner dark:border-sky-200/90 dark:bg-sky-50/95',
        )}
      >
        <div className="strategy-toolbar-content flex w-full min-w-[860px] flex-col gap-3 lg:min-w-0">
          <div className="strategy-toolbar-row strategy-toolbar-row-primary flex w-full items-center gap-3">
            {liveHandler ? (
              <button
                type="button"
                className={cn(
                  'group inline-flex h-11 shrink-0 items-center gap-2 rounded-full border px-5 text-sm font-black transition duration-200 hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-75',
                  statusStyle.buttonClassName,
                )}
                disabled={disabled}
                title={statusStyle.title}
                onClick={liveHandler}
              >
                <span
                  aria-hidden="true"
                  className={cn('h-2.5 w-2.5 rounded-full', statusStyle.dotClassName, resolvedStatus === 'syncing' && 'animate-pulse')}
                  style={statusStyle.dotStyle}
                />
                <StatusIcon className={cn('h-4 w-4', resolvedStatus === 'syncing' && 'animate-spin')} />
                {resolvedStatus === 'syncing'
                  ? (liveLoadingLabel || statusStyle.label)
                  : (liveLabel || statusStyle.label)}
              </button>
            ) : null}

            {showSearch ? (
              <label className="relative min-w-[320px] flex-1">
                <span className="sr-only">{searchPlaceholder}</span>
                <SearchIcon className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  className="h-11 w-full rounded-full border border-sky-200 bg-white/95 pl-11 pr-4 text-sm font-bold text-slate-700 outline-none transition placeholder:text-slate-400 focus:border-sky-300 focus:ring-4 focus:ring-sky-100 dark:border-sky-200 dark:bg-white/95 dark:text-slate-700 dark:focus:border-sky-300 dark:focus:ring-sky-100"
                  placeholder={searchPlaceholder}
                  type="search"
                  value={searchValue}
                  onChange={(event) => onSearchChange(event.currentTarget.value)}
                />
              </label>
            ) : null}

            {showTimeframe && onTimeframeChange ? (
              <select
                className="h-11 shrink-0 rounded-full border border-sky-200 bg-white px-5 text-sm font-black text-slate-900 outline-none transition focus:border-sky-300 focus:ring-4 focus:ring-sky-100 dark:border-sky-200 dark:bg-white dark:text-slate-900"
                aria-label="Timeframe"
                value={timeframe}
                onChange={(event) => onTimeframeChange(event.currentTarget.value)}
              >
                {timeframeOptions.map((option) => (
                  <option key={option} value={option}>{toTimeframeLabel(option)}</option>
                ))}
              </select>
            ) : null}

            {showTotal ? (
              <span className="inline-flex h-11 shrink-0 items-center rounded-full border border-sky-200 bg-white px-5 text-sm font-black text-slate-800 dark:border-sky-200 dark:bg-white dark:text-slate-800">
                Total: {(Number(total) || 0).toLocaleString('en-IN')}
              </span>
            ) : null}

            {onDownload ? (
              <button
                type="button"
                className="inline-flex h-11 shrink-0 items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-5 text-sm font-black text-emerald-700 transition hover:-translate-y-0.5 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-emerald-700/80 dark:bg-emerald-900/35 dark:text-emerald-200"
                disabled={disabled}
                onClick={onDownload}
              >
                <DownloadIcon className="h-4 w-4" />
                {downloading ? 'Preparing TXT...' : downloadLabel}
              </button>
            ) : null}

            {onRefresh ? (
              <button
                type="button"
                className="inline-flex h-11 shrink-0 items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-5 text-sm font-black text-sky-700 transition hover:-translate-y-0.5 hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-sky-700/80 dark:bg-sky-900/35 dark:text-sky-200"
                disabled={disabled}
                onClick={onRefresh}
              >
                <RefreshCwIcon className={cn('h-4 w-4', resolvedStatus === 'syncing' && 'animate-spin')} />
                {refreshing ? 'Refreshing...' : 'Refresh'}
              </button>
            ) : null}

            {showInsertDb && onInsertDb ? (
              <button
                type="button"
                className="inline-flex h-11 shrink-0 items-center gap-2 rounded-full border border-slate-200 bg-white px-5 text-sm font-black text-slate-900 transition hover:-translate-y-0.5 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950/85 dark:text-slate-100 dark:hover:bg-slate-900"
                disabled={disabled || inserting || insertDisabled}
                onClick={onInsertDb}
              >
                <DatabaseIcon className="h-4 w-4" />
                {inserting ? insertLoadingLabel : insertLabel}
              </button>
            ) : null}
          </div>

          <div className="strategy-toolbar-row strategy-toolbar-row-meta flex w-full flex-wrap items-center gap-x-2 gap-y-1 px-2 text-xs font-black text-slate-600 dark:text-slate-600">
            {metadata.map((item, index) => (
              <Fragment key={item}>
                <span>{item}</span>
                {index < metadata.length - 1 ? <span className="text-slate-300">|</span> : null}
              </Fragment>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
