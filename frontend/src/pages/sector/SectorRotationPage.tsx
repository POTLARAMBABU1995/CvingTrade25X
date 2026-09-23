import { Fragment, useEffect, useMemo, useState } from 'react';
import { StrategyToolbar } from '../../components/strategy/StrategyToolbar';
import { DataBadge } from '../../components/ui/DataBadge';
import {
  adaptSectorBreadthPayload,
  adaptSectorRotationSnapshotMeta,
  formatSectorCount,
  formatSectorPercent,
  sectorHeatClass,
  type SectorBreadthRow,
  type SectorRotationSnapshotMeta,
} from '../../adapters/sectorPageAdapter';
import { findSectorPageByCode } from '../../data/sectorNav';
import { recordDiagnostic } from '../../lib/diagnostics';
import {
  fetchSectorBreadth,
  fetchSectorRotationSectors,
  fetchSectorWiseUnknownSymbols,
  fetchDatabaseSyncStatus,
  refreshSectorData,
  type DatabaseSyncStatus,
} from '../../services/api/sectorApi';
import { computeSectorBreadthStrength } from '../../utils/sectorStrength';
import { SectorMigrationLayout } from './SectorMigrationLayout';

type LoadStatus = 'error' | 'loading' | 'online';
export type SectorRotationVersion = 'v2' | 'v3';
export type SectorRotationExperience = 'classic' | 'stockedge';

export type SectorRotationPageProps = {
  activeSectorPage?: string;
  experience?: SectorRotationExperience;
};

function downloadConsolidatedSectorWiseTxt(symbols: string[]) {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const url = window.URL.createObjectURL(new Blob([symbols.join(',')], { type: 'text/plain;charset=utf-8;' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'SectorWiseUnknownInsufficient.txt';
  anchor.click();
  window.URL.revokeObjectURL(url);
}

export type DiscoveredSector = {
  sectorCode: string;
  sectorKey: string;
  sectorName: string;
  stockCount: number;
  tableName: string;
  parentSector?: string | null;
  industry?: string | null;
};

export function resolveSectorRotationVersion(value: unknown): SectorRotationVersion {
  return String(value ?? '').trim().toLowerCase() === 'v3' ? 'v3' : 'v2';
}

function sectorRotationBreadthCacheKey(version: SectorRotationVersion): string {
  return `cv_sector_rotation_breadth_${version}`;
}

function metaText(rows: SectorBreadthRow[], syncStatus?: DatabaseSyncStatus | null) {
  const effectiveDate = syncStatus?.dev_ltc_date || rows.map((row) => row.effectiveDate || row.asOfDate).find(Boolean);
  return effectiveDate ? `Effective data date: ${effectiveDate}` : '';
}

export function resolveSectorLiveToolbarStatus(hasError: boolean): 'error' | 'live' {
  return hasError ? 'error' : 'live';
}

export function shouldForceSectorBreadthRead(
  version: SectorRotationVersion,
  refreshVersion: number,
): boolean {
  return version !== 'v3' && refreshVersion > 0;
}

export function filterSectorRotationRows(rows: SectorBreadthRow[], search: string): SectorBreadthRow[] {
  const token = search.trim().toUpperCase();
  if (!token) return rows;
  return rows.filter((row) => (
    row.sectorName.toUpperCase().includes(token)
    || row.sectorCode.toUpperCase().includes(token)
  ));
}

type StickyColumnRole = 'sno' | 'symbol';

function stickyColumnRole(columnKey: string): StickyColumnRole | null {
  if (columnKey === 'rank') return 'sno';
  if (columnKey === 'sector') return 'symbol';
  return null;
}

function stickyHeaderClass(columnKey: string, baseClass?: string): string | undefined {
  const role = stickyColumnRole(columnKey);
  const className = [baseClass, role ? 'sticky-header-cell' : '', role ? `sticky-${role}` : ''].filter(Boolean).join(' ');
  return className || undefined;
}

function stickyCellClass(columnKey: string, baseClass?: string): string | undefined {
  const role = stickyColumnRole(columnKey);
  const className = [baseClass, role ? 'sticky-cell' : '', role ? `sticky-${role}` : ''].filter(Boolean).join(' ');
  return className || undefined;
}

function finiteNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function formatSectorRotationMetric(
  value: unknown,
  options: { decimals?: number; suffix?: string } = {},
): string {
  const numeric = finiteNumber(value);
  if (numeric === null) return 'N/A';
  const decimals = options.decimals ?? 2;
  return `${numeric.toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}${options.suffix ?? ''}`;
}

export function sortSectorRotationRows(
  rows: SectorBreadthRow[],
  version: SectorRotationVersion,
): SectorBreadthRow[] {
  if (version === 'v3') {
    return [...rows].sort((left, right) => {
      const leftScore = finiteNumber(left.finalRotationScore);
      const rightScore = finiteNumber(right.finalRotationScore);
      if (leftScore === null && rightScore === null) return left.sectorName.localeCompare(right.sectorName);
      if (leftScore === null) return 1;
      if (rightScore === null) return -1;
      return rightScore - leftScore || left.sectorName.localeCompare(right.sectorName);
    });
  }

  return [...rows].sort((left, right) => {
    const leftStrength = computeSectorBreadthStrength(left);
    const rightStrength = computeSectorBreadthStrength(right);
    return rightStrength.sortRank - leftStrength.sortRank
      || rightStrength.avgPct - leftStrength.avgPct
      || left.sectorName.localeCompare(right.sectorName);
  });
}

function phaseTone(phase: string | undefined): 'accent' | 'danger' | 'default' | 'success' | 'warn' {
  const token = String(phase ?? '').trim().toUpperCase();
  if (token === 'LEADING' || token === 'STRONG' || token === 'VERY_STRONG') return 'success';
  if (token === 'IMPROVING') return 'accent';
  if (token === 'WEAKENING') return 'warn';
  if (token === 'LAGGING') return 'danger';
  return 'default';
}

function confidenceTone(confidence: string | undefined): 'danger' | 'default' | 'success' | 'warn' {
  const token = String(confidence ?? '').trim().toUpperCase();
  if (token === 'HIGH') return 'success';
  if (token === 'MEDIUM') return 'warn';
  if (token === 'LOW') return 'danger';
  return 'default';
}

function formatRankChange(value: unknown): string {
  const numeric = finiteNumber(value);
  if (numeric === null) return 'N/A';
  if (numeric > 0) return `+${Math.round(numeric)}`;
  return String(Math.round(numeric));
}

function textOrNa(value: unknown): string {
  const text = String(value ?? '').trim();
  return text || 'N/A';
}

export type SectorEligibilityResult = {
  eligible: boolean;
  failedGates: string[];
};

export function evaluateBestSectorEligibility(
  row: SectorBreadthRow,
  snapshotDate?: string,
): SectorEligibilityResult {
  const warnings = [
    ...(row.riskWarnings ?? []),
    ...(row.divergenceCodes ?? []),
  ].map((value) => String(value).toUpperCase());
  const severeWarning = warnings.some((warning) => (
    warning.includes('DATA_STALE')
    || warning.includes('STALE_DATA')
    || warning.includes('MAPPING_CONFLICT')
    || warning.includes('CORPORATE_ACTION')
    || warning.includes('SEVERE')
  ));
  const effectiveSnapshotDate = String(snapshotDate || row.asOfDate || '').slice(0, 10);
  const gates = {
    score: (finiteNumber(row.finalRotationScore) ?? -1) >= 70,
    band: ['STRONG', 'VERY_STRONG'].includes(String(row.rotationBand ?? '').toUpperCase()),
    phase: ['LEADING', 'IMPROVING'].includes(String(row.rotationPhase ?? '').toUpperCase()),
    confidence: String(row.confidence ?? '').toUpperCase() === 'HIGH',
    coverage: (finiteNumber(row.coveragePercent) ?? -1) >= 85,
    dataQuality: (finiteNumber(row.dataQualityScore) ?? -1) >= 80,
    risk: (finiteNumber(row.riskScore) ?? -1) >= 60,
    currentDate: Boolean(effectiveSnapshotDate)
      && String(row.latestDataDate || '').slice(0, 10) === effectiveSnapshotDate,
    moneyFlow: (finiteNumber(row.moneyFlowScore) ?? -1) >= 50,
    severeWarnings: !severeWarning,
  };
  const failedGates = Object.entries(gates)
    .filter(([, passed]) => !passed)
    .map(([gate]) => gate);
  return { eligible: failedGates.length === 0, failedGates };
}

function WeightDetails({ weights }: { weights?: Record<string, number | null> }) {
  const entries = Object.entries(weights ?? {});
  if (!entries.length) return <span>N/A</span>;
  return (
    <span>{entries.map(([key, value]) => {
      const numeric = finiteNumber(value);
      const display = numeric === null ? 'N/A' : formatSectorRotationMetric(Math.abs(numeric) <= 1 ? numeric * 100 : numeric, { decimals: 1, suffix: '%' });
      return `${key}: ${display}`;
    }).join(' | ')}</span>
  );
}

function DetailMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200/80 bg-white/60 px-3 py-2 dark:border-slate-700 dark:bg-slate-900/50">
      <dt className="text-[11px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="mt-1 font-semibold tabular-nums text-slate-900 dark:text-slate-100">{value}</dd>
    </div>
  );
}

export function SectorRotationV3Details({ row }: { row: SectorBreadthRow }) {
  const reasons = row.positiveReasons?.length ? row.positiveReasons : row.reasonCodes;
  const warnings = [...(row.riskWarnings ?? []), ...(row.divergenceCodes ?? [])];
  return (
    <div className="space-y-4 p-4 text-left" aria-label={`${row.sectorName} V3 factor details`}>
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <DetailMetric label="Momentum Score" value={formatSectorRotationMetric(row.momentumScore)} />
        <DetailMetric label="Breadth Score" value={formatSectorRotationMetric(row.breadthScore)} />
        <DetailMetric label="Trend Score" value={formatSectorRotationMetric(row.trendScore)} />
        <DetailMetric label="Money-Flow Score" value={formatSectorRotationMetric(row.moneyFlowScore)} />
        <DetailMetric label="Risk Score" value={formatSectorRotationMetric(row.riskScore)} />
        <DetailMetric label="Data-Quality Score" value={formatSectorRotationMetric(row.dataQualityScore)} />
        <DetailMetric label="Legacy Breadth Display Score" value={formatSectorRotationMetric(row.legacyDisplayScore, { suffix: '%' })} />
      </dl>
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <DetailMetric label="Relative Return 21D" value={formatSectorRotationMetric(row.relativeReturn21, { suffix: '%' })} />
        <DetailMetric label="Relative Return 63D" value={formatSectorRotationMetric(row.relativeReturn63, { suffix: '%' })} />
        <DetailMetric label="Relative Return 126D" value={formatSectorRotationMetric(row.relativeReturn126, { suffix: '%' })} />
        <DetailMetric label="Relative Return 252D" value={formatSectorRotationMetric(row.relativeReturn252, { suffix: '%' })} />
        <DetailMetric label="Momentum Acceleration" value={formatSectorRotationMetric(row.momentumAccelerationRaw)} />
        <DetailMetric label="Breadth Change 1D / 5D / 21D" value={`${formatSectorRotationMetric(row.breadthDelta1D)} / ${formatSectorRotationMetric(row.breadthDelta5D)} / ${formatSectorRotationMetric(row.breadthDelta21D)}`} />
        <DetailMetric label="Volatility 63D" value={formatSectorRotationMetric(row.volatility63, { suffix: '%' })} />
        <DetailMetric label="Max Drawdown 126D / 252D" value={`${formatSectorRotationMetric(row.maxDrawdown126, { suffix: '%' })} / ${formatSectorRotationMetric(row.maxDrawdown252, { suffix: '%' })}`} />
        <DetailMetric label="Rank History" value={`Now ${formatSectorRotationMetric(row.currentRank, { decimals: 0 })}; 1D ${formatRankChange(row.rankChange1D)}; 1W ${formatRankChange(row.rankChange1W)}; 1M ${formatRankChange(row.rankChange1M)}`} />
        <DetailMetric label="Coverage" value={`${formatSectorRotationMetric(row.coveragePercent, { suffix: '%' })}; history ${formatSectorRotationMetric(row.historyCoveragePercent, { suffix: '%' })}`} />
        <DetailMetric label="Valid Prices / Indicators" value={`${formatSectorRotationMetric(row.validPriceCount, { decimals: 0 })} / ${formatSectorRotationMetric(row.validIndicatorCount, { decimals: 0 })}`} />
        <DetailMetric label="Eligible / Stale Stocks" value={`${formatSectorRotationMetric(row.eligibleStockCount, { decimals: 0 })} / ${formatSectorRotationMetric(row.staleStockCount, { decimals: 0 })}`} />
      </dl>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-200/80 p-3 dark:border-slate-700">
          <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Reason codes</h3>
          <p className="mt-2 text-sm text-slate-700 dark:text-slate-200">{reasons?.length ? reasons.join(' | ') : 'N/A'}</p>
        </div>
        <div className="rounded-lg border border-slate-200/80 p-3 dark:border-slate-700">
          <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Warnings</h3>
          <p className="mt-2 text-sm text-slate-700 dark:text-slate-200">{warnings.length ? warnings.join(' | ') : 'N/A'}</p>
        </div>
        <div className="rounded-lg border border-slate-200/80 p-3 dark:border-slate-700">
          <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Effective factor weights</h3>
          <p className="mt-2 text-sm text-slate-700 dark:text-slate-200"><WeightDetails weights={row.effectiveWeights} /></p>
        </div>
        <div className="rounded-lg border border-slate-200/80 p-3 dark:border-slate-700">
          <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Explanation</h3>
          <p className="mt-2 text-sm text-slate-700 dark:text-slate-200">{textOrNa(row.summaryExplanation)}</p>
        </div>
      </div>
    </div>
  );
}

/** Parse discovered sector API response into typed array, deduplicating by sectorCode. */
function adaptDiscoveredSectors(payload: { sectors?: Array<Record<string, unknown>> }): DiscoveredSector[] {
  const rawSectors = Array.isArray(payload?.sectors) ? payload.sectors : [];
  const seen = new Set<string>();
  const result: DiscoveredSector[] = [];
  for (const s of rawSectors) {
    const code = String(s.sectorCode || '').trim().toUpperCase();
    if (!code || seen.has(code)) continue;
    seen.add(code);
    result.push({
      sectorCode: code,
      sectorKey: String(s.sectorKey || code.toLowerCase().replace(/_/g, '-')),
      sectorName: String(s.sectorName || code).trim(),
      stockCount: Number(s.stockCount || 0),
      tableName: String(s.tableName || '').trim(),
      parentSector: s.parentSector == null ? null : String(s.parentSector).trim(),
      industry: s.industry == null ? null : String(s.industry).trim(),
    });
  }
  return result;
}

/**
 * Merge discovered sectors (master list) with breadth data (metrics).
 * Only discovered sectors appear; breadth-only sectors are excluded.
 */
export function mergeDiscoveredWithBreadth(
  discovered: DiscoveredSector[],
  breadth: SectorBreadthRow[],
  version: SectorRotationVersion = 'v2',
): SectorBreadthRow[] {
  const breadthMap = new Map<string, SectorBreadthRow>();
  for (const row of breadth) {
    breadthMap.set(row.sectorCode, row);
  }

  return discovered.map((sector) => {
    const match = breadthMap.get(sector.sectorCode);
    if (match) {
      const totalStocks = Math.max(Number(match.totalStocks || 0), Number(sector.stockCount || 0));
      return {
        ...match,
        sectorName: match.sectorName || sector.sectorName,
        tableName: match.tableName || sector.tableName,
        totalStocks,
      };
    }
    // Sector exists in DB staging tables but has no breadth data yet — show with neutral metrics
    const missingMetric = version === 'v3' ? null : 0;
    return {
      asOfDate: '',
      countBreadth: null,
      coveragePercent: null,
      effectiveDate: '',
      ffmcBreadth: null,
      finalRotationScore: null,
      historyCoveragePercent: null,
      latestDataDate: '',
      mcapBreadth: null,
      rsi50Pct: missingMetric,
      rsi55Pct: missingMetric,
      sectorCode: sector.sectorCode,
      sectorName: sector.sectorName,
      sma100Pct: missingMetric,
      sma20Pct: missingMetric,
      sma50Pct: missingMetric,
      stockConfirmationScreening: '',
      totalStocks: sector.stockCount,
      tableName: sector.tableName,
    } satisfies SectorBreadthRow;
  });
}

export function SectorRotationPage({
  activeSectorPage = '/app/sector/rotation',
  experience = 'classic',
}: SectorRotationPageProps = {}) {
  const version: SectorRotationVersion = 'v3';
  const isStockEdge = experience === 'stockedge';
  const breadthCacheKey = sectorRotationBreadthCacheKey(version);
  const [error, setError] = useState('');
  const [expandedSectorCode, setExpandedSectorCode] = useState('');
  const [isPreparingDownload, setIsPreparingDownload] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [rows, setRows] = useState<SectorBreadthRow[]>([]);
  const [search, setSearch] = useState('');
  const [discoveredSectors, setDiscoveredSectors] = useState<DiscoveredSector[]>([]);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [syncStatus, setSyncStatus] = useState<DatabaseSyncStatus | null>(null);
  const [snapshotMeta, setSnapshotMeta] = useState<SectorRotationSnapshotMeta | null>(null);
  const [sectorView, setSectorView] = useState<'best' | 'all'>('all');

  const refreshPage = async () => {
    setStatus('loading');
    setError('');
    try {
      await refreshSectorData('v3', {
        diagnostic: {
          action: 'POST /api/sectors/refresh?version=v3',
          component: 'SectorRotationPage',
          page: 'CvingTrade25X - Sector Rotation',
        },
      });
      sessionStorage.removeItem(breadthCacheKey);
      setRefreshVersion((current) => current + 1);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : String(refreshError));
      setStatus('error');
    }
  };

  /* ---- Fetch Database Sync Status ---- */
  useEffect(() => {
    fetchDatabaseSyncStatus({
      diagnostic: {
        action: 'GET /api/database/sync-status',
        component: 'SectorRotationPage',
        page: 'CvingTrade25X - Sector Rotation',
      }
    })
      .then((res) => {
        setSyncStatus(res);
      })
      .catch((err) => {
        console.error('Failed to fetch DB sync status', err);
      });
  }, [refreshVersion]);

  /* ---- Fetch DB-discovered sector list (master list) ---- */
  useEffect(() => {
    const controller = new AbortController();
    const forceBreadthRead = shouldForceSectorBreadthRead(version, refreshVersion);
    fetchSectorRotationSectors(
      forceBreadthRead ? { refresh: 1 } : undefined,
      {
        diagnostic: {
          action: 'GET /api/sector-rotation/sectors',
          component: 'SectorRotationPage',
          page: 'CvingTrade25X - Sector Rotation',
        },
        signal: controller.signal,
      },
    )
      .then((payload) => {
        const sectors = adaptDiscoveredSectors(payload);
        setDiscoveredSectors(sectors);
      })
      .catch((discoveryError: unknown) => {
        if (controller.signal.aborted) return;
        recordDiagnostic({
          action: 'GET /api/sector-rotation/sectors',
          component: 'SectorRotationPage',
          endpoint: '/api/sector-rotation/sectors',
          error: discoveryError,
          httpMethod: 'GET',
          kind: 'api',
          message: `Sector discovery failed: ${discoveryError instanceof Error ? discoveryError.message : String(discoveryError)}`,
          page: 'CvingTrade25X - Sector Rotation',
          severity: 'warn',
        });
        // Discovery failure is non-fatal — breadth-only fallback will be used
      });
    return () => controller.abort();
  }, [refreshVersion]);

  /* ---- Fetch breadth metrics (existing behavior preserved) ---- */
  useEffect(() => {
    const controller = new AbortController();
    const breadthParams = shouldForceSectorBreadthRead(version, refreshVersion)
      ? { refresh: 1, version }
      : { version };
    
    if (refreshVersion === 0) {
      try {
        const cachedStr = sessionStorage.getItem(breadthCacheKey);
        if (cachedStr) {
          const cachedPayload = JSON.parse(cachedStr);
          setRows(adaptSectorBreadthPayload(cachedPayload));
          setSnapshotMeta(adaptSectorRotationSnapshotMeta(cachedPayload));
          setStatus('online');
        } else {
          setStatus('loading');
        }
      } catch {
        setStatus('loading');
      }
    } else {
      setStatus('loading');
    }

    setError('');
    fetchSectorBreadth(
      breadthParams,
      {
        diagnostic: {
          action: 'GET /api/sectors/breadth',
          component: 'SectorRotationPage',
          page: 'CvingTrade25X - Sector Rotation',
        },
        signal: controller.signal,
      },
    )
      .then((payload) => {
        try {
          sessionStorage.setItem(breadthCacheKey, JSON.stringify(payload));
          const nextRows = adaptSectorBreadthPayload(payload);
          setLastRefreshedAt(new Date());
          setRows(nextRows);
          setSnapshotMeta(adaptSectorRotationSnapshotMeta(payload));
          setStatus('online');
          if (!nextRows.length) {
            recordDiagnostic({
              action: 'GET /api/sectors/breadth',
              component: 'SectorRotationPage',
              endpoint: '/api/sectors/breadth',
              httpMethod: 'GET',
              httpStatus: 200,
              kind: 'api',
              message: 'Sector Rotation API returned 0 rows.',
              page: 'CvingTrade25X - Sector Rotation',
              severity: 'info',
            });
          }
        } catch (normalizeError) {
          const message = normalizeError instanceof Error ? normalizeError.message : String(normalizeError);
          recordDiagnostic({
            action: 'normalize-breadth',
            component: 'SectorRotationPage',
            endpoint: '/api/sectors/breadth',
            error: normalizeError,
            httpMethod: 'GET',
            httpStatus: 200,
            kind: 'runtime',
            message: `Sector Rotation payload normalization failed: ${message}`,
            page: 'CvingTrade25X - Sector Rotation',
            severity: 'error',
          });
          throw normalizeError;
        }
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted) return;
        setError(loadError instanceof Error ? loadError.message : String(loadError));
        setRows([]);
        setStatus('error');
      });
    return () => controller.abort();
  }, [breadthCacheKey, refreshVersion, version]);

  /* ---- Merge: discovered sectors as master list, enriched with breadth data ---- */
  const sortedRows = useMemo(() => {
    const masterRows = discoveredSectors.length > 0
      ? mergeDiscoveredWithBreadth(discoveredSectors, rows, version)
      : rows;

    return sortSectorRotationRows(masterRows, isStockEdge ? 'v3' : 'v2');
  }, [rows, discoveredSectors, isStockEdge, version]);

  const bestRows = useMemo(() => (
    sortedRows.filter((row) => evaluateBestSectorEligibility(row, snapshotMeta?.asOfDate).eligible)
  ), [snapshotMeta?.asOfDate, sortedRows]);
  const visibleRows = isStockEdge && sectorView === 'best' ? bestRows : sortedRows;
  const filteredRows = useMemo(() => filterSectorRotationRows(visibleRows, search), [visibleRows, search]);
  const toolbarStatus = resolveSectorLiveToolbarStatus(Boolean(error));
  const emptyMessage = status === 'loading'
    ? 'Loading sector breadth...'
    : search.trim()
      ? 'No sector breadth rows match the current search.'
      : isStockEdge && sectorView === 'best'
        ? 'No sectors currently meet every Best Sector quality gate. Select All Sectors to review the complete 90-sector universe and failed gates.'
        : 'No sector breadth rows available.';
  const toolbarLtcDate = snapshotMeta?.asOfDate
    || syncStatus?.dev_ltc_date
    || sortedRows.map((row) => row.latestDataDate || row.effectiveDate || row.asOfDate).find(Boolean)
    || null;

  const prepareConsolidatedSectorWiseDownload = async () => {
    setIsPreparingDownload(true);
    setError('');
    try {
      const payload = await fetchSectorWiseUnknownSymbols();
      downloadConsolidatedSectorWiseTxt(payload.symbols);
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : 'Unable to prepare the consolidated sector-wise TXT download.');
    } finally {
      setIsPreparingDownload(false);
    }
  };

  return (
    <SectorMigrationLayout activeSectorPage={activeSectorPage} className="sector-rotation-react-page">
      <StrategyToolbar
        className="mb-4"
        isLoading={status === 'loading'}
        lastRefreshed={lastRefreshedAt}
        ltcDate={toolbarLtcDate}
        downloadLabel="Download TXT"
        downloading={isPreparingDownload}
        onDownload={() => void prepareConsolidatedSectorWiseDownload()}
        onLive={() => setRefreshVersion((current) => current + 1)}
        onRefresh={() => void refreshPage()}
        onSearchChange={setSearch}
        refreshing={status === 'loading'}
        searchPlaceholder="Search Card"
        searchValue={search}
        showTotal
        singleSurface
        status={toolbarStatus}
        total={filteredRows.length}
      />

      <div className="sector-compact-page-header">
        <h1 className="sector-compact-page-title">
          {isStockEdge ? 'STOCKEDGE SECTOR ROTATION' : 'SECTOR ROTATION'}
        </h1>
        {isStockEdge && (
          <div className="flex flex-wrap gap-2" aria-label="Sector eligibility view">
            <button
              className={`rounded-full border px-3 py-1 text-xs font-bold ${sectorView === 'best' ? 'border-emerald-500 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300' : 'border-slate-300 dark:border-slate-600'}`}
              onClick={() => setSectorView('best')}
              type="button"
            >
              Best Sectors ({bestRows.length})
            </button>
            <button
              className={`rounded-full border px-3 py-1 text-xs font-bold ${sectorView === 'all' ? 'border-sky-500 bg-sky-500/15 text-sky-700 dark:text-sky-300' : 'border-slate-300 dark:border-slate-600'}`}
              onClick={() => setSectorView('all')}
              type="button"
            >
              All Sectors ({sortedRows.length})
            </button>
          </div>
        )}
      </div>
      <p className={error ? 'sector-rotation-page-meta is-error' : 'sector-rotation-page-meta'} aria-live="polite">
        {error || metaText(sortedRows, syncStatus) || (status === 'loading' ? 'Loading live sector rotation...' : '')}
      </p>
      {snapshotMeta?.isStale && (
        <p className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm font-semibold text-amber-700 dark:text-amber-300" role="status">
          Cached stale V3 snapshot. As of {textOrNa(snapshotMeta.asOfDate)}.
        </p>
      )}

      <section className="card sector-breadth-card">
        <div className="table-wrapper sector-react-table-wrapper">
          <table className="app-data-table table-sticky-safe data-table sector-breadth-table !w-auto">
            <colgroup>
              <col data-col="sno" data-sticky-role={stickyColumnRole('rank') || undefined} />
              <col data-col="sector" data-sticky-role={stickyColumnRole('sector') || undefined} />
            </colgroup>
            <thead>
              <tr>
                <th
                  className={stickyHeaderClass('rank', '!w-auto !px-4')}
                  data-col="sno"
                  data-sticky-col="left"
                  data-sticky-role={stickyColumnRole('rank') || undefined}
                >
                  {isStockEdge ? 'RANK' : 'S.NO'}
                </th>
                <th
                  className={stickyHeaderClass('sector', '!w-auto !px-4 text-left whitespace-nowrap')}
                  data-col="sector"
                  data-sticky-col="left"
                  data-sticky-role={stickyColumnRole('sector') || undefined}
                >
                  SECTOR
                </th>
                <th className="!w-auto !px-4 whitespace-nowrap">TotalStocks</th>
                <th className="!w-auto !px-4 whitespace-nowrap">{isStockEdge ? '% RSI > 55' : 'RSI55 > 0'}</th>
                <th className="!w-auto !px-4 whitespace-nowrap">{isStockEdge ? '% RSI > 50' : 'RSI50 > 0'}</th>
                <th className="!w-auto !px-4 whitespace-nowrap">{isStockEdge ? '% Above SMA20' : 'SMA20'}</th>
                <th className="!w-auto !px-4 whitespace-nowrap">{isStockEdge ? '% Above SMA50' : 'SMA50'}</th>
                <th className="!w-auto !px-4 whitespace-nowrap">{isStockEdge ? '% Above SMA100' : 'SMA100'}</th>
                {isStockEdge ? (
                  <>
                    <th className="!w-auto !px-4 whitespace-nowrap">FINAL SCORE</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">ROTATION BAND</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">PHASE</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">1W Δ</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">CONFIDENCE</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">COVERAGE</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">MONEY FLOW</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">RISK</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">DATA DATE</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">ELIGIBILITY</th>
                  </>
                ) : (
                  <>
                    {/* Existing V2 columns and ordering remain unchanged. */}
                    <th className="!w-auto !px-4 whitespace-nowrap">PHASE</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">ROTATION</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">MOMENTUM</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">BREADTH</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">MONEY_FLOW</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">RISK</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">TREND</th>
                    <th className="!w-auto !px-4 whitespace-nowrap">CONFIDENCE</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {filteredRows.length ? filteredRows.map((row, index) => {
                const sectorPage = findSectorPageByCode(row.sectorCode);
                const strength = computeSectorBreadthStrength(row);
                const isExpanded = isStockEdge && expandedSectorCode === row.sectorCode;
                const eligibility = evaluateBestSectorEligibility(row, snapshotMeta?.asOfDate);
                return (
                  <Fragment key={row.sectorCode}>
                    <tr data-sector-code={row.sectorCode}>
                      <td
                        className={stickyCellClass('rank', '!w-auto !px-4')}
                        data-col="sno"
                        data-sticky-col="left"
                        data-sticky-role={stickyColumnRole('rank') || undefined}
                      >
                        {formatSectorCount(isStockEdge ? row.currentRank ?? index + 1 : index + 1)}
                      </td>
                      <td
                        className={stickyCellClass('sector', '!w-auto !px-4 text-left whitespace-nowrap')}
                        data-col="sector"
                        data-sticky-col="left"
                        data-sticky-role={stickyColumnRole('sector') || undefined}
                      >
                        <a className="sector-react-sector-link" href={sectorPage?.href ?? `/app/sector/stocks/${encodeURIComponent(row.sectorCode.toLowerCase())}`}>
                          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs ${strength.sectorClassName}`}>
                            {row.sectorName}
                          </span>
                        </a>
                        {isStockEdge && (
                          <button
                            aria-controls={`sector-rotation-v3-details-${row.sectorCode}`}
                            aria-expanded={isExpanded}
                            className="ml-2 rounded-full border border-slate-300 px-2 py-0.5 text-[11px] font-bold text-slate-600 transition hover:border-slate-400 hover:text-slate-900 dark:border-slate-600 dark:text-slate-300 dark:hover:text-white"
                            onClick={() => setExpandedSectorCode((current) => current === row.sectorCode ? '' : row.sectorCode)}
                            type="button"
                          >
                            Details
                          </button>
                        )}
                      </td>
                      <td className="font-black tabular-nums text-slate-900 dark:text-slate-100">{formatSectorCount(row.totalStocks)}</td>
                      <td><span className={`heat-pill ${sectorHeatClass(row.rsi55Pct)}`}>{isStockEdge ? formatSectorRotationMetric(row.rsi55Pct, { suffix: '%' }) : formatSectorPercent(row.rsi55Pct)}</span></td>
                      <td><span className={`heat-pill ${sectorHeatClass(row.rsi50Pct)}`}>{isStockEdge ? formatSectorRotationMetric(row.rsi50Pct, { suffix: '%' }) : formatSectorPercent(row.rsi50Pct)}</span></td>
                      <td><span className={`heat-pill ${sectorHeatClass(row.sma20Pct)}`}>{isStockEdge ? formatSectorRotationMetric(row.sma20Pct, { suffix: '%' }) : formatSectorPercent(row.sma20Pct)}</span></td>
                      <td><span className={`heat-pill ${sectorHeatClass(row.sma50Pct)}`}>{isStockEdge ? formatSectorRotationMetric(row.sma50Pct, { suffix: '%' }) : formatSectorPercent(row.sma50Pct)}</span></td>
                      <td><span className={`heat-pill ${sectorHeatClass(row.sma100Pct)}`}>{isStockEdge ? formatSectorRotationMetric(row.sma100Pct, { suffix: '%' }) : formatSectorPercent(row.sma100Pct)}</span></td>
                      {isStockEdge ? (
                        <>
                          <td><span className={`heat-pill ${sectorHeatClass(row.finalRotationScore)}`}>{formatSectorRotationMetric(row.finalRotationScore)}</span></td>
                          <td><DataBadge tone={phaseTone(row.rotationBand)}>{textOrNa(row.rotationBand)}</DataBadge></td>
                          <td><DataBadge tone={phaseTone(row.rotationPhase)}>{textOrNa(row.rotationPhase)}</DataBadge></td>
                          <td className="tabular-nums">{formatRankChange(row.rankChange1W)}</td>
                          <td><DataBadge tone={confidenceTone(row.confidence)}>{textOrNa(row.confidence)}</DataBadge></td>
                          <td><span className={`heat-pill ${sectorHeatClass(row.coveragePercent)}`}>{formatSectorRotationMetric(row.coveragePercent, { suffix: '%' })}</span></td>
                          <td><span className={`heat-pill ${sectorHeatClass(row.moneyFlowScore)}`}>{formatSectorRotationMetric(row.moneyFlowScore)}</span></td>
                          <td><span className={`heat-pill ${sectorHeatClass(row.riskScore)}`}>{formatSectorRotationMetric(row.riskScore)}</span></td>
                          <td className="whitespace-nowrap">{textOrNa(row.latestDataDate || row.asOfDate)}</td>
                          <td title={eligibility.eligible ? 'All Best Sector gates passed.' : `Failed gates: ${eligibility.failedGates.join(', ')}`}>
                            <div className="flex min-w-36 flex-col gap-1">
                              <DataBadge tone={eligibility.eligible ? 'success' : 'warn'}>
                                {eligibility.eligible ? 'BEST' : `INELIGIBLE (${eligibility.failedGates.length})`}
                              </DataBadge>
                              {!eligibility.eligible && (
                                <span className="text-[10px] leading-tight text-amber-700 dark:text-amber-300">
                                  {eligibility.failedGates.join(', ')}
                                </span>
                              )}
                            </div>
                          </td>
                        </>
                      ) : (
                        <>
                          <td>{row.rotationPhase || '-'}</td>
                          <td>{row.rotationScore?.toFixed(2) || '-'}</td>
                          <td>{row.momentumScore?.toFixed(2) || '-'}</td>
                          <td>{row.breadthScore?.toFixed(2) || '-'}</td>
                          <td>{row.moneyFlowScore?.toFixed(2) || '-'}</td>
                          <td>{row.riskScore?.toFixed(2) || '-'}</td>
                          <td>{row.trendScore?.toFixed(2) || '-'}</td>
                          <td>{row.confidence || '-'}</td>
                        </>
                      )}
                    </tr>
                    {isExpanded && (
                      <tr id={`sector-rotation-v3-details-${row.sectorCode}`}>
                        <td className="bg-slate-50/80 p-0 dark:bg-slate-950/50" colSpan={18}>
                          <SectorRotationV3Details row={row} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              }) : (
                <tr>
                  <td className="sector-stock-status" colSpan={isStockEdge ? 18 : 16}>{emptyMessage}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </SectorMigrationLayout>
  );
}
