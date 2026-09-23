import { useCallback, useEffect, useMemo, useState, type MouseEvent } from 'react';
import { CvingLegacyHeader } from '../../components/navigation/CvingLegacyHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { DataBadge } from '../../components/ui/DataBadge';
import { ErrorState } from '../../components/ui/ErrorState';
import { ArrowUpRightIcon, LayersIcon, RadarIcon, SearchIcon } from '../../components/ui/Icons';
import { Input } from '../../components/ui/Input';
import { Skeleton } from '../../components/ui/Skeleton';
import {
  findPhaseOneNavItem,
  phaseOneCategoryOrder,
  phaseOneItemsForCategory,
  phaseOneNavItems,
  type PhaseOneNavItem,
} from '../../data/phaseOneNav';
import { cn } from '../../lib/cn';
import { fetchPhaseOneSources, type PhaseOneSourceResult } from '../../services/api/phaseOneApi';
import { handleInternalNavigationClick } from '../../utils/internalNavigation';
import { normalizeDisplaySymbol } from '../../utils/symbols';

type PhaseOneWorkspacePageProps = {
  currentPath: string;
  disableFetch?: boolean;
  initialSources?: PhaseOneSourceResult[];
};

type DisplayFact = {
  label: string;
  value: string;
};

type PreviewTable = {
  columns: string[];
  rows: Array<Record<string, unknown>>;
};

const SENSITIVE_KEY = /token|password|authorization|cookie|secret|aadhaar|\bpan\b/i;
const FACT_KEYS = [
  'status',
  'message',
  'tradingDate',
  'trading_date',
  'latestTradingDate',
  'latest_trading_date',
  'ltc_date',
  'dev_ltc_date',
  'asOfDate',
  'generated_at',
  'total',
  'totalCount',
  'total_count',
  'rowCount',
  'row_count',
  'total_stocks',
  'total_sectors',
  'is_fully_synced',
  'is_stale',
  'missing_mcap_count',
  'missing_ffmc_count',
  'missing_delivery_count',
] as const;

const PREFERRED_COLUMNS = [
  'symbol',
  'stock',
  'name',
  'sector',
  'index',
  'trading_date',
  'ltc_date',
  'price',
  'close',
  'trend',
  'score',
  'status',
] as const;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function displayLabel(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return Number.isFinite(value) ? value.toLocaleString('en-IN') : '—';
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return `${value.length.toLocaleString('en-IN')} records`;
  return 'Available';
}

function unwrapPayload(value: unknown): unknown {
  const record = asRecord(value);
  if (!record) return value;
  for (const key of ['data', 'payload', 'result'] as const) {
    if (record[key] !== undefined && record[key] !== null) return record[key];
  }
  return value;
}

function findRows(value: unknown, depth = 0): Array<Record<string, unknown>> {
  if (depth > 3) return [];
  const unwrapped = unwrapPayload(value);
  if (Array.isArray(unwrapped)) {
    return unwrapped.flatMap((item) => {
      const record = asRecord(item);
      return record ? [record] : [{ value: item }];
    });
  }
  const record = asRecord(unwrapped);
  if (!record) return [];
  const preferredKeys = ['rows', 'items', 'stocks', 'symbols', 'sectors', 'gainers', 'results', 'bars', 'candles'];
  for (const key of preferredKeys) {
    const rows = findRows(record[key], depth + 1);
    if (rows.length > 0) return rows;
  }
  for (const nested of Object.values(record)) {
    const rows = findRows(nested, depth + 1);
    if (rows.length > 0) return rows;
  }
  return [];
}

function collectFacts(value: unknown): DisplayFact[] {
  const unwrapped = unwrapPayload(value);
  if (Array.isArray(unwrapped)) {
    return [{ label: 'Records', value: unwrapped.length.toLocaleString('en-IN') }];
  }
  const record = asRecord(unwrapped);
  if (!record) return [{ label: 'Response', value: displayValue(unwrapped) }];

  const facts: DisplayFact[] = [];
  for (const key of FACT_KEYS) {
    if (SENSITIVE_KEY.test(key) || record[key] === undefined) continue;
    const valueText = displayValue(record[key]);
    if (valueText === 'Available') continue;
    facts.push({ label: displayLabel(key), value: valueText });
    if (facts.length === 6) break;
  }
  if (facts.length === 0) {
    const rows = findRows(record);
    if (rows.length > 0) facts.push({ label: 'Records', value: rows.length.toLocaleString('en-IN') });
  }
  return facts;
}

function buildPreviewTable(value: unknown): PreviewTable | null {
  const rows = findRows(value).slice(0, 8);
  if (rows.length === 0) return null;
  const availableKeys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))))
    .filter((key) => !SENSITIVE_KEY.test(key) && rows.some((row) => {
      const value = row[key];
      return value === null || ['boolean', 'number', 'string', 'undefined'].includes(typeof value);
    }));
  const preferred = PREFERRED_COLUMNS.filter((key) => availableKeys.includes(key));
  const columns = [...preferred, ...availableKeys.filter((key) => !preferred.includes(key as typeof PREFERRED_COLUMNS[number]))]
    .slice(0, 7);
  return columns.length > 0 ? { columns, rows } : null;
}

function navClick(event: MouseEvent<HTMLAnchorElement>, href: string): void {
  handleInternalNavigationClick(event, href);
}

function PhaseOneSourceCard({ source }: { source: PhaseOneSourceResult }) {
  const facts = source.status === 'online' ? collectFacts(source.payload) : [];
  const preview = source.status === 'online' ? buildPreviewTable(source.payload) : null;

  return (
    <Card variant="light" padding="none" className="overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200/70 px-5 py-4 dark:border-slate-700/70">
        <div>
          <p className="m-0 text-sm font-black text-slate-950 dark:text-slate-100">{source.label}</p>
          <p className="mt-1 font-mono text-[11px] text-slate-500 dark:text-slate-400">GET {source.endpoint}</p>
        </div>
        <DataBadge tone={source.status === 'online' ? 'success' : 'danger'}>
          {source.status === 'online' ? 'Connected' : 'Unavailable'}
        </DataBadge>
      </div>

      {source.status === 'error' ? (
        <div className="p-5">
          <p className="m-0 text-sm leading-6 text-rose-700 dark:text-rose-300">{source.error}</p>
        </div>
      ) : (
        <>
          {facts.length > 0 ? (
            <dl className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-3">
              {facts.map((fact) => (
                <div key={`${source.key}-${fact.label}`} className="rounded-2xl border border-slate-200/70 bg-slate-50/80 px-4 py-3 dark:border-slate-700/70 dark:bg-slate-950/45">
                  <dt className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{fact.label}</dt>
                  <dd className="mt-1 break-words text-sm font-black text-slate-950 dark:text-slate-100">{fact.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}

          {preview ? (
            <div className="overflow-x-auto border-t border-slate-200/70 dark:border-slate-700/70">
              <table className="min-w-full border-collapse text-left text-xs">
                <thead className="bg-slate-100/80 text-slate-600 dark:bg-slate-950/70 dark:text-slate-300">
                  <tr>
                    {preview.columns.map((column) => (
                      <th key={column} className="whitespace-nowrap px-4 py-3 font-black uppercase tracking-[0.12em]">{displayLabel(column)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200/70 dark:divide-slate-700/70">
                  {preview.rows.map((row, index) => (
                    <tr key={`${source.key}-row-${index}`} className="bg-white/50 dark:bg-slate-900/45">
                      {preview.columns.map((column) => (
                        <td key={column} className="max-w-[240px] truncate px-4 py-3 text-slate-700 dark:text-slate-200" title={displayValue(row[column])}>
                          {displayValue(row[column])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      )}
    </Card>
  );
}

function PhaseOneNavigation({ activeItem, variant }: { activeItem: PhaseOneNavItem; variant: 'category' | 'pages' }) {
  return (
    <>
      {variant === 'category' ? <nav aria-label="Phase 1 category navigation" className="overflow-x-auto border-b border-slate-200/70 bg-white/80 px-4 py-3 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-950/80">
        <div className="mx-auto flex min-w-max max-w-[1680px] items-center gap-2">
          <span className="mr-2 inline-flex items-center gap-2 rounded-full bg-emerald-500/10 px-3 py-2 text-xs font-black uppercase tracking-[0.16em] text-emerald-700 dark:text-emerald-300">
            <LayersIcon className="h-4 w-4" /> Phase 1
          </span>
          {phaseOneCategoryOrder.map((category) => {
            const firstItem = phaseOneItemsForCategory(category)[0];
            const active = activeItem.category === category;
            return (
              <a
                key={category}
                href={firstItem.href}
                aria-current={active ? 'page' : undefined}
                onClick={(event) => navClick(event, firstItem.href)}
                className={cn(
                  'rounded-full border px-4 py-2 text-sm font-bold transition',
                  active
                    ? 'border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-300'
                    : 'border-transparent text-slate-600 hover:border-slate-200 hover:bg-slate-100 dark:text-slate-300 dark:hover:border-slate-700 dark:hover:bg-slate-900',
                )}
              >
                {category}
              </a>
            );
          })}
        </div>
      </nav> : null}

      {variant === 'pages' ? <aside className="xl:sticky xl:top-[145px] xl:self-start">
        <nav aria-label="Phase 1 page navigation" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:w-[290px] xl:grid-cols-1">
          {phaseOneCategoryOrder.map((category) => (
            <div key={category} className="rounded-[24px] border border-slate-200/70 bg-white/80 p-3 shadow-sm backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/80">
              <p className="px-2 pb-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">{category}</p>
              <div className="space-y-1">
                {phaseOneItemsForCategory(category).map((item) => {
                  const active = activeItem.id === item.id;
                  return (
                    <a
                      key={item.id}
                      href={item.href}
                      aria-current={active ? 'page' : undefined}
                      onClick={(event) => navClick(event, item.href)}
                      className={cn(
                        'flex items-center justify-between gap-3 rounded-2xl px-3 py-2.5 text-sm font-bold transition',
                        active
                          ? 'bg-gradient-to-r from-blue-600 to-cyan-500 text-white shadow-md'
                          : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white',
                      )}
                    >
                      <span>{item.label}</span>
                      {active ? <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full bg-current" /> : null}
                    </a>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </aside> : null}
    </>
  );
}

export function PhaseOneWorkspacePage({ currentPath, disableFetch = false, initialSources = [] }: PhaseOneWorkspacePageProps) {
  const activeItem = findPhaseOneNavItem(currentPath) ?? phaseOneNavItems[0];
  const initialSymbol = useMemo(() => {
    if (typeof window === 'undefined') return 'RELIANCE';
    return normalizeDisplaySymbol(new URLSearchParams(window.location.search).get('symbol')) || 'RELIANCE';
  }, []);
  const [symbolInput, setSymbolInput] = useState(initialSymbol);
  const [selectedSymbol, setSelectedSymbol] = useState(initialSymbol);
  const [sources, setSources] = useState<PhaseOneSourceResult[]>(initialSources);
  const [loading, setLoading] = useState(!disableFetch && initialSources.length === 0);
  const [pageError, setPageError] = useState('');

  const loadSources = useCallback(async (signal?: AbortSignal) => {
    if (disableFetch) return;
    setLoading(true);
    setPageError('');
    try {
      const nextSources = await fetchPhaseOneSources(activeItem.id, selectedSymbol, signal);
      setSources(nextSources);
      if (nextSources.length > 0 && nextSources.every((source) => source.status === 'error')) {
        setPageError('All connected sources are currently unavailable. Existing workflows remain unchanged.');
      }
    } catch (error) {
      if (signal?.aborted) return;
      setPageError(error instanceof Error ? error.message : 'Phase 1 sources could not be loaded.');
      setSources([]);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [activeItem.id, disableFetch, selectedSymbol]);

  useEffect(() => {
    const controller = new AbortController();
    void loadSources(controller.signal);
    return () => controller.abort('Phase 1 page changed');
  }, [loadSources]);

  function applySymbol() {
    const normalized = normalizeDisplaySymbol(symbolInput);
    if (!normalized) return;
    setSymbolInput(normalized);
    setSelectedSymbol(normalized);
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href);
      url.searchParams.set('symbol', normalized);
      window.history.replaceState(window.history.state ?? {}, '', `${url.pathname}${url.search}${url.hash}`);
    }
  }

  const onlineCount = sources.filter((source) => source.status === 'online').length;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950 dark:bg-slate-950 dark:text-slate-100">
      <CvingLegacyHeader activeSection="phase1" />
      <PhaseOneNavigation activeItem={activeItem} variant="category" />

      <div className="mx-auto grid w-full max-w-[1680px] gap-6 px-4 py-6 md:px-6 xl:grid-cols-[290px_minmax(0,1fr)]">
        <PhaseOneNavigation activeItem={activeItem} variant="pages" />

        <main className="min-w-0 space-y-6" aria-labelledby="phase-one-page-title">
          <Card variant="light" padding="lg" className="overflow-hidden bg-gradient-to-br from-white via-blue-50/70 to-cyan-50/60 dark:from-slate-900 dark:via-blue-950/25 dark:to-cyan-950/20">
            <div className="flex flex-wrap items-start justify-between gap-5">
              <div className="max-w-3xl">
                <div className="flex flex-wrap items-center gap-2">
                  <DataBadge tone="accent">{activeItem.category}</DataBadge>
                  <DataBadge tone={pageError ? 'warn' : 'success'}>
                    {loading ? 'Loading' : `${onlineCount}/${sources.length || 0} sources online`}
                  </DataBadge>
                </div>
                <h1 id="phase-one-page-title" className="mt-4 text-3xl font-black tracking-tight text-slate-950 dark:text-white md:text-4xl">
                  {activeItem.label}
                </h1>
                <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600 dark:text-slate-300 md:text-base">{activeItem.description}</p>
                <p className="mt-3 text-xs font-bold uppercase tracking-[0.14em] text-blue-700 dark:text-blue-300">{activeItem.sourceSummary}</p>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                {activeItem.workflowHref ? (
                  <a
                    href={activeItem.workflowHref}
                    onClick={(event) => navClick(event, activeItem.workflowHref!)}
                    className="focus-ring inline-flex h-10 items-center gap-2 rounded-full border border-slate-300 bg-white px-4 text-sm font-bold text-slate-800 transition hover:border-blue-400 hover:text-blue-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                  >
                    {activeItem.workflowLabel ?? 'Open workflow'}
                    <ArrowUpRightIcon className="h-4 w-4" />
                  </a>
                ) : null}
                <Button variant="primary" onClick={() => void loadSources()} loading={loading}>Refresh</Button>
              </div>
            </div>

            {activeItem.symbolAware ? (
              <div className="mt-6 flex max-w-xl flex-col gap-3 rounded-[24px] border border-blue-200/70 bg-white/75 p-4 sm:flex-row dark:border-blue-900/50 dark:bg-slate-950/45">
                <label className="sr-only" htmlFor="phase-one-symbol">NSE symbol</label>
                <Input
                  id="phase-one-symbol"
                  value={symbolInput}
                  onChange={(event) => setSymbolInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') applySymbol();
                  }}
                  placeholder="Enter NSE symbol"
                  aria-describedby="phase-one-symbol-help"
                  className="min-w-0 flex-1 uppercase"
                />
                <Button leadingIcon={<SearchIcon className="h-4 w-4" />} onClick={applySymbol}>Load {selectedSymbol}</Button>
                <p id="phase-one-symbol-help" className="sr-only">Exchange prefixes and cash-series suffixes are normalized for display only.</p>
              </div>
            ) : null}
          </Card>

          {activeItem.id === 'main-dashboard' ? (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {phaseOneCategoryOrder.map((category) => (
                <Card key={category} variant="light" padding="md">
                  <div className="flex items-center justify-between gap-3">
                    <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-500/10 text-blue-700 dark:text-blue-300">
                      <RadarIcon className="h-5 w-5" />
                    </span>
                    <span className="text-2xl font-black">{phaseOneItemsForCategory(category).length}</span>
                  </div>
                  <p className="mt-4 text-sm font-black">{category}</p>
                  <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">Connected Phase 1 research pages</p>
                </Card>
              ))}
            </div>
          ) : null}

          {pageError ? (
            <ErrorState
              surface="light"
              title="Phase 1 sources are unavailable"
              description={pageError}
              onRetry={() => void loadSources()}
            />
          ) : null}

          {loading ? (
            <div className="grid gap-4 lg:grid-cols-2" aria-label="Loading Phase 1 data">
              <Skeleton className="h-64 rounded-[28px]" />
              <Skeleton className="h-64 rounded-[28px]" />
            </div>
          ) : (
            <div className="grid gap-5 2xl:grid-cols-2">
              {sources.map((source) => <PhaseOneSourceCard key={source.key} source={source} />)}
            </div>
          )}

          <Card variant="subtle" padding="md" className="text-sm leading-6 text-slate-600 dark:text-slate-300">
            This Phase 1 surface is read-only. It reuses approved Flask and Oracle-backed services and does not alter existing pages, calculations, database tables or market-data flow.
          </Card>
        </main>
      </div>
    </div>
  );
}
