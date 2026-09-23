import { useEffect, useMemo, useRef, useState } from 'react';
import { TechnicalMarketCapCell } from '../../components/app/TechnicalMarketCapCell';
import { Card } from '../../components/ui/Card';
import { PageHeader } from '../../components/ui/PageHeader';
import {
  extractStrategyMetaNumber,
  extractStrategyRows,
  formatStrategyCell,
  normalizeYamunaRows,
  type StrategyWireRow,
} from '../../adapters/strategyPageAdapter';
import { getMarketCapCategory } from '../../adapters/technicalMarketCap';
import { formatYamunaPercentageCell, formatYamunaPointsCell, toYamunaNumber } from '../../adapters/yamunaPageAdapter';
import { fetchStrategyPayload, postYamunaIngest } from '../../services/api/strategyApi';
import { StrategyMigrationLayout } from './StrategyMigrationLayout';
import { StrategyToolbar, type StrategyToolbarStatus } from '../../components/strategy/StrategyToolbar';

const TOP_LIMIT = 25;

const tableColumns = [
  { key: 'stock', label: 'SYMBOL' },
  { key: 'index', label: 'INDEX' },
  { key: 'mcap', label: 'MCAP' },
  { key: 'mcapRank', label: 'MCAP_RANK' },
  { key: 'price', label: 'PRICE' },
  { key: 'percentage', label: 'Percentage' },
  { key: 'points', label: 'POINTS' },
  { key: 'volume', label: 'VOLUME' },
  { key: 'ltcDate', label: 'LTC_DATE' },
] as const;

const fieldAliases: Record<string, readonly string[]> = {
  index: ['index', 'INDEX', 'index_type', 'indexCategory', 'index_category'],
  ltcDate: ['ltcDate', 'ltc_date', 'LTC_DATE', 'tradingDate', 'TRADING_DATE', 'tradeDate', 'TRADE_DATE'],
  mcap: ['mcap', 'MCAP', 'market_cap', 'marketCapCrores', 'market_cap_crores'],
  mcapRank: ['mcapRank', 'mcap_rank', 'MCAP_RANK', 'marketCapRank', 'market_cap_rank'],
  percentage: ['percentage', 'PERCENTAGE', 'percentChange', 'PERCENT_CHANGE'],
  points: ['points', 'POINTS', 'change', 'CHANGE'],
  price: ['price', 'PRICE', 'close', 'CLOSE'],
  stock: ['stock', 'STOCK', 'symbol', 'SYMBOL', 'stockName', 'STOCK_NAME', 'ticker', 'TICKER'],
  symbol: ['symbol', 'SYMBOL', 'stock', 'STOCK', 'stockName', 'STOCK_NAME', 'ticker', 'TICKER'],
  volume: ['volume', 'VOLUME'],
  volumeRatio: ['volumeRatio', 'volumeRatioSort', 'VOLUME_RATIO', 'VOLUME_RATIO_SORT'],
};

function sumMetaMs(payloads: unknown[], keys: readonly string[]): number | null {
  let total = 0;
  let found = false;
  payloads.forEach((payload) => {
    const value = extractStrategyMetaNumber(payload, keys);
    if (Number.isFinite(value ?? NaN)) {
      total += value as number;
      found = true;
    }
  });
  return found ? total : null;
}

function getField(row: StrategyWireRow, keys: readonly string[]): unknown {
  for (const key of keys) {
    const value = row[key];
    if (value !== null && value !== undefined) {
      if (typeof value === 'string') {
        const token = value.trim();
        if (token === '' || token === '-') continue;
      }
      return value;
    }
  }
  return undefined;
}

function pick(row: StrategyWireRow, key: string): unknown {
  const aliases = fieldAliases[key] ?? [key, key.toUpperCase(), key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`)];
  return getField(row, aliases);
}

function formatDateDDMMYYYY(value: unknown): string {
  const text = formatStrategyCell(value);
  if (!text || text === '-') return '-';
  const isoMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (isoMatch) return `${isoMatch[3]}-${isoMatch[2]}-${isoMatch[1]}`;
  const displayMatch = text.match(/^(\d{2})-(\d{2})-(\d{4})$/);
  if (displayMatch) return text;
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return text;
  const day = String(parsed.getDate()).padStart(2, '0');
  const month = String(parsed.getMonth() + 1).padStart(2, '0');
  const year = parsed.getFullYear();
  return `${day}-${month}-${year}`;
}

function toIsoDate(value: unknown): string {
  const text = String(value ?? '').trim();
  const match = text.match(/\d{4}-\d{2}-\d{2}/);
  return match?.[0] ?? new Date().toISOString().slice(0, 10);
}

function normalizeIngestRows(rows: StrategyWireRow[], fallbackDate: string, includeVolume: boolean) {
  return rows.map((row, index) => {
    const stock = formatStrategyCell(pick(row, 'stock') || pick(row, 'symbol')).toUpperCase();
    if (!stock || stock === '-') return null;
    const payload: Record<string, unknown> = {
      s_no: index + 1,
      stock,
      ltc_date: toIsoDate(pick(row, 'ltcDate') || fallbackDate),
      price: toYamunaNumber(pick(row, 'price')),
      percentage: toYamunaNumber(pick(row, 'percentage')),
      points: toYamunaNumber(pick(row, 'points')),
    };
    if (includeVolume) payload.volume = toYamunaNumber(pick(row, 'volume'));
    return payload;
  }).filter(Boolean);
}

function buildIngestPayload(gainers: StrategyWireRow[], losers: StrategyWireRow[], volumeMovers: StrategyWireRow[], tradingDate: string) {
  const ltcDate = toIsoDate(tradingDate);
  return {
    ltc_date: ltcDate,
    gainers: normalizeIngestRows(gainers, ltcDate, false),
    loosers: normalizeIngestRows(losers, ltcDate, false),
    volumeMovers: normalizeIngestRows(volumeMovers, ltcDate, true),
  };
}

type RowTone = 'gain' | 'loss' | 'neutral';

function normalizeLabel(value: unknown): string {
  return String(value ?? '').trim().toLowerCase();
}

function isLoserLabel(label: string): boolean {
  return label.includes('looser') || label.includes('loser');
}

function isGainerLabel(label: string): boolean {
  return label.includes('gainer');
}

function getRowTone(row: StrategyWireRow, kind: 'gainers' | 'losers' | 'volume'): RowTone {
  if (kind === 'gainers') return 'gain';
  if (kind === 'losers') return 'loss';
  const label = normalizeLabel(
    `${pick(row, 'category') ?? ''} ${pick(row, 'type') ?? ''} ${pick(row, 'metric') ?? ''} ${pick(row, 'name') ?? ''} ${pick(row, 'label') ?? ''}`,
  );
  if (isGainerLabel(label)) return 'gain';
  if (isLoserLabel(label)) return 'loss';
  const points = toYamunaNumber(pick(row, 'points'));
  if (points !== null) {
    if (points > 0) return 'gain';
    if (points < 0) return 'loss';
  }
  const pct = toYamunaNumber(pick(row, 'percentage'));
  if (pct !== null) {
    if (pct > 0) return 'gain';
    if (pct < 0) return 'loss';
  }
  return 'neutral';
}

function toneClass(tone: RowTone): string {
  if (tone === 'gain') return 'trend-price--up';
  if (tone === 'loss') return 'trend-price--down';
  return 'text-slate-700 dark:text-slate-300';
}

function shouldUseIndexTone(columnKey: string): boolean {
  return columnKey === 'stock' || columnKey === 'index' || columnKey === 'mcap' || columnKey === 'mcapRank';
}

function MiniYamunaTable({
  rows,
  title,
  kind,
}: {
  rows: StrategyWireRow[];
  title: string;
  kind: 'gainers' | 'losers' | 'volume';
}) {
  return (
    <Card variant="light" padding="none" className="overflow-hidden border-slate-200 shadow-sm dark:border-slate-700/70">
      <div className="border-b border-slate-200 bg-sky-50 px-4 py-3 dark:border-slate-700/70 dark:bg-slate-900/75">
        <h3 className="font-black tracking-[-0.02em] text-slate-950 dark:text-slate-100">{title}</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th className="sticky left-0 z-30 border-b border-slate-200 bg-sky-50 px-3 py-3 text-left text-xs font-black uppercase text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">S.NO</th>
              {tableColumns.map((column) => (
                <th key={column.key} className="whitespace-nowrap border-b border-slate-200 bg-sky-50 px-3 py-3 text-left text-xs font-black uppercase text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={tableColumns.length + 1} className="px-4 py-8 text-center text-slate-500 dark:text-slate-300">No rows found.</td></tr>
            ) : rows.map((row, index) => (
              <tr key={`${title}-${index}`} className="odd:bg-white even:bg-slate-50 hover:bg-sky-50/70 dark:odd:bg-slate-950 dark:even:bg-slate-900/70 dark:hover:bg-slate-800/70">
                <td className="sticky left-0 z-20 border-b border-slate-100 bg-inherit px-3 py-3 font-semibold dark:border-slate-800">{index + 1}</td>
                {tableColumns.map((column) => {
                  const baseCellClass = 'whitespace-nowrap border-b border-slate-100 px-3 py-3 dark:border-slate-800';
                  const rawValue = pick(row, column.key);
                  const indexValue = pick(row, 'index');
                  const marketCapTone = getMarketCapCategory(indexValue);
                  const rowTone = getRowTone(row, kind);
                  if (column.key === 'percentage') {
                    const percentageValue = pick(row, 'percentage');
                    return (
                      <td key={`${title}-${column.key}-${index}`} className={baseCellClass}>
                        <span className={toneClass(rowTone)}>
                          {formatYamunaPercentageCell(percentageValue)}
                        </span>
                      </td>
                    );
                  }
                  if (column.key === 'points') {
                    return (
                      <td key={`${title}-${column.key}-${index}`} className={baseCellClass}>
                        <span className={toneClass(rowTone)}>
                          {formatYamunaPointsCell(rawValue)}
                        </span>
                      </td>
                    );
                  }
                  const displayValue = column.key === 'ltcDate'
                    ? formatDateDDMMYYYY(rawValue)
                    : formatStrategyCell(rawValue);
                  return (
                    <td key={`${title}-${column.key}-${index}`} className={`${baseCellClass} text-slate-700 dark:text-slate-200`}>
                      {shouldUseIndexTone(column.key) ? (
                        <TechnicalMarketCapCell tone={marketCapTone}>{displayValue}</TechnicalMarketCapCell>
                      ) : displayValue}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function YamunaStrategyPage() {
  const [payload, setPayload] = useState<unknown>(null);
  const [volumePayload, setVolumePayload] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [liveLoading, setLiveLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  const [ingestStatus, setIngestStatus] = useState('');
  const [ingestFailed, setIngestFailed] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [loadTimeMs, setLoadTimeMs] = useState<number | null>(null);
  const [backendApiMs, setBackendApiMs] = useState<number | null>(null);
  const [backendDbMs, setBackendDbMs] = useState<number | null>(null);
  const [partialError, setPartialError] = useState('');
  const inFlightRef = useRef(false);

  async function load(forceRefresh = false, signal?: AbortSignal, mode: 'initial' | 'live' | 'refresh' = forceRefresh ? 'refresh' : 'initial') {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setError('');
    setPartialError('');
    setIngestFailed(false);
    if (mode === 'live') setLiveLoading(true);
    else if (forceRefresh) setRefreshing(true);
    else setLoading(true);
    const startedAt = performance.now();
    try {
      const [movers, volume] = await Promise.allSettled([
        fetchStrategyPayload('/api/dashboard/movers', { segment: 'nifty500', limit: TOP_LIMIT }, { forceRefresh, signal }),
        fetchStrategyPayload('/api/volume', undefined, { forceRefresh, signal }),
      ]);
      if (signal?.aborted) return;
      if (movers.status === 'fulfilled') setPayload(movers.value);
      if (volume.status === 'fulfilled') setVolumePayload(volume.value);
      if (movers.status === 'rejected' && volume.status === 'rejected') {
        throw movers.reason;
      }
      const fulfilledPayloads = [
        movers.status === 'fulfilled' ? movers.value : null,
        volume.status === 'fulfilled' ? volume.value : null,
      ].filter((item): item is unknown => item !== null);
      setBackendApiMs(sumMetaMs(fulfilledPayloads, ['api_time_ms', 'request_ms', 'duration_ms', 'durationMs', 'load_time_ms']));
      setBackendDbMs(sumMetaMs(fulfilledPayloads, ['db_time_ms', 'oracle_ms', 'oracleLoadMs', 'query_ms']));
      if (movers.status === 'rejected' || volume.status === 'rejected') {
        const failed = movers.status === 'rejected' ? movers.reason : volume.status === 'rejected' ? volume.reason : null;
        setPartialError(failed instanceof Error ? failed.message : String(failed ?? 'Partial strategy data unavailable.'));
      }
      setLoadTimeMs(Math.max(0, Math.round(performance.now() - startedAt)));
      setLastRefreshedAt(new Date());
    } catch (loadError) {
      if (signal?.aborted) return;
      setError(loadError instanceof Error ? loadError.message : String(loadError));
      setLoadTimeMs(Math.max(0, Math.round(performance.now() - startedAt)));
    } finally {
      inFlightRef.current = false;
      if (!signal?.aborted) {
        setLoading(false);
        setRefreshing(false);
        setLiveLoading(false);
      }
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    load(false, controller.signal, 'initial');
    return () => controller.abort();
  }, []);

  const moverRows = useMemo(() => normalizeYamunaRows(payload), [payload]);
  const volumeRows = useMemo(() => {
    const sourceRows = extractStrategyRows(volumePayload);
    const filtered = sourceRows.filter(
      (row) => (toYamunaNumber(pick(row, 'volumeRatio')) ?? 0) >= 3,
    );
    filtered.sort((left, right) => (toYamunaNumber(pick(right, 'volumeRatio')) ?? 0) - (toYamunaNumber(pick(left, 'volumeRatio')) ?? 0));
    return filtered.slice(0, TOP_LIMIT);
  }, [volumePayload]);
  const tables = useMemo(() => {
    const query = search.trim().toUpperCase();
    const filter = (rows: StrategyWireRow[]) => !query
      ? rows
      : rows.filter((row) => formatStrategyCell(pick(row, 'stock')).toUpperCase().includes(query));
    const volumeDate = volumeRows.length ? formatStrategyCell(pick(volumeRows[0], 'ltcDate')) : '-';
    return {
      gainers: filter(moverRows.gainers),
      losers: filter(moverRows.losers),
      volumeMovers: filter(volumeRows.length ? volumeRows : moverRows.volumeMovers),
      tradingDate: moverRows.tradingDate !== '-' ? moverRows.tradingDate : volumeDate,
    };
  }, [moverRows, search, volumeRows]);

  async function ingestVisibleRows() {
    setIngesting(true);
    setIngestStatus('');
    setIngestFailed(false);
    try {
      const result = await postYamunaIngest<Record<string, unknown>>(buildIngestPayload(tables.gainers, tables.losers, tables.volumeMovers, tables.tradingDate));
      setIngestStatus(`Yamuna ingest completed: ${formatStrategyCell(result.message || result.status || 'ok')}`);
    } catch (ingestError) {
      setIngestFailed(true);
      setIngestStatus(ingestError instanceof Error ? ingestError.message : String(ingestError));
    } finally {
      setIngesting(false);
    }
  }

  const toolbarStatus: StrategyToolbarStatus = loading || refreshing || liveLoading || ingesting
    ? 'syncing'
    : error || partialError || ingestFailed
      ? 'error'
      : lastRefreshedAt
        ? 'live'
        : 'idle';

  return (
    <StrategyMigrationLayout activeStrategyPage="/app/strategy/yamuna" fullWidth>
      <div className="space-y-6">
        <PageHeader title="Yamuna Strategy Screener" />

        <Card variant="light" padding="md" className="border-slate-200 shadow-sm dark:border-slate-700/70">
          <StrategyToolbar
            apiTimeMs={backendApiMs}
            dbTimeMs={backendDbMs}
            inserting={ingesting}
            insertDisabled={loading}
            isLoading={loading || refreshing || liveLoading}
            lastRefreshed={lastRefreshedAt}
            liveLoading={liveLoading}
            loadTimeMs={loadTimeMs}
            ltcDate={tables.tradingDate !== '-' ? tables.tradingDate : null}
            status={toolbarStatus}
            onInsertDb={ingestVisibleRows}
            onLiveRefresh={() => undefined}
            onRefresh={() => load(true, undefined, 'refresh')}
            onSearchChange={setSearch}
            refreshing={refreshing}
            searchValue={search}
            showInsertDb
            showTotal
            total={tables.gainers.length + tables.losers.length + tables.volumeMovers.length}
          />
          {error ? <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-800">{error}</p> : null}
          {ingestStatus ? <p className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700 dark:border-slate-700/70 dark:bg-slate-900/80 dark:text-slate-300">{ingestStatus}</p> : null}
        </Card>

        {loading ? (
          <Card variant="light" padding="lg" className="border-slate-200 text-center text-slate-500 dark:border-slate-700/70 dark:text-slate-300">Loading Yamuna tables...</Card>
        ) : (
          <div className="grid gap-5">
            <MiniYamunaTable title="Top Gainers" rows={tables.gainers} kind="gainers" />
            <MiniYamunaTable title="Top Losers" rows={tables.losers} kind="losers" />
            <MiniYamunaTable title="Volume Movers" rows={tables.volumeMovers} kind="volume" />
          </div>
        )}
      </div>
    </StrategyMigrationLayout>
  );
}
