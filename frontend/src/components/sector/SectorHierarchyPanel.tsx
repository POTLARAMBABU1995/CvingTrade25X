import { useEffect, useMemo, useState } from 'react';
import { adaptSectorWisePayload, formatSectorIndex, type SectorWiseRow } from '../../adapters/sectorPageAdapter';
import { fetchSectorWiseStocks } from '../../services/api/sectorApi';
import { SectorHierarchyFilters } from './SectorHierarchyFilters';
import { SectorHierarchyStocksTable } from './SectorHierarchyStocksTable';
import { SectorHierarchySummaryCards } from './SectorHierarchySummaryCards';
import { normalizeDisplaySymbol } from '../../utils/symbols';
import {
  clearSectorHierarchyCache,
  getIndustries,
  getParents,
  getStocks,
  getSubSectors,
  getSummary,
} from '../../services/api/sectorHierarchyApi';
import type {
  SectorHierarchyIndustry,
  SectorHierarchyParent,
  SectorHierarchyStocksPayload,
  SectorHierarchySubSector,
  SectorHierarchySummary,
} from '../../types/sectorHierarchy';

type LoadStatus = 'error' | 'idle' | 'loading' | 'online';
type SymbolMeta = {
  index?: string | null;
  mcap?: number | null;
  mcapRank?: number | null;
};
type SectorHierarchyPanelProps = {
  symbolMetaBySymbol?: Record<string, SymbolMeta>;
};

function findDefaultParent(parents: SectorHierarchyParent[]): string {
  if (!parents.length) return '';
  const healthcare = parents.find((item) => item.parentSector.toUpperCase() === 'HEALTHCARE');
  return healthcare?.parentSector || parents[0].parentSector;
}

function inferFallbackParentFromRoute(): string {
  if (typeof window === 'undefined') return '';
  const pathname = String(window.location.pathname || '').toLowerCase();
  if (pathname.includes('/app/sector/stocks/healthcare') || pathname.includes('/app/sector/stocks/pharma')) {
    return 'Healthcare';
  }
  return '';
}

function normalizeSymbolToken(value: string | null | undefined): string {
  return normalizeDisplaySymbol(value);
}

function toSortableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(String(value).replace(/,/g, '').replace(/%/g, ''));
  return Number.isFinite(parsed) ? parsed : null;
}

function buildSymbolMetaMap(rows: SectorWiseRow[]): Record<string, SymbolMeta> {
  const out: Record<string, SymbolMeta> = {};
  rows.forEach((row) => {
    const token = normalizeSymbolToken(row.stock);
    if (!token) return;
    out[token] = {
      index: formatSectorIndex(row.index),
      mcap: toSortableNumber(row.totalMcap),
      mcapRank: toSortableNumber(row.mcapRank),
    };
  });
  return out;
}

export function SectorHierarchyPanel({ symbolMetaBySymbol = {} }: SectorHierarchyPanelProps) {
  const [status, setStatus] = useState<LoadStatus>('idle');
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const [parents, setParents] = useState<SectorHierarchyParent[]>([]);
  const [industries, setIndustries] = useState<SectorHierarchyIndustry[]>([]);
  const [subSectors, setSubSectors] = useState<SectorHierarchySubSector[]>([]);
  const [summary, setSummary] = useState<SectorHierarchySummary | null>(null);
  const [stocks, setStocks] = useState<SectorHierarchyStocksPayload | null>(null);

  const [selectedParent, setSelectedParent] = useState('');
  const [selectedIndustry, setSelectedIndustry] = useState('');
  const [selectedSubSector, setSelectedSubSector] = useState('');
  const [search, setSearch] = useState('');
  const [fallbackSymbolMetaBySymbol, setFallbackSymbolMetaBySymbol] = useState<Record<string, SymbolMeta>>({});

  useEffect(() => {
    let cancelled = false;
    setStatus('loading');
    setError('');
    getParents()
      .then((response) => {
        if (cancelled) return;
        const nextParents = response.data || [];
        if (nextParents.length > 0) {
          setParents(nextParents);
          if (!selectedParent) {
            setSelectedParent(findDefaultParent(nextParents) || inferFallbackParentFromRoute());
          }
          setStatus('online');
          return;
        }
        getParents({ refresh: true })
          .then((refreshResponse) => {
            if (cancelled) return;
            const refreshedParents = refreshResponse.data || [];
            setParents(refreshedParents);
            if (!selectedParent) {
              setSelectedParent(findDefaultParent(refreshedParents) || inferFallbackParentFromRoute());
            }
            setStatus('online');
          })
          .catch((refreshError: unknown) => {
            if (cancelled) return;
            setStatus('error');
            setError(refreshError instanceof Error ? refreshError.message : String(refreshError));
          });
      })
      .catch((loadError: unknown) => {
        if (cancelled) return;
        setStatus('error');
        setError(loadError instanceof Error ? loadError.message : String(loadError));
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedParent) return;
    let cancelled = false;
    setStatus('loading');
    setError('');
    Promise.all([
      getIndustries(selectedParent),
      getSummary(selectedParent),
      getStocks({ parentSector: selectedParent }),
    ])
      .then(async ([industriesResp, summaryResp, stocksResp]) => {
        if (cancelled) return;
        let industryRows = industriesResp.data || [];
        if (!industryRows.length) {
          const refreshResp = await getIndustries(selectedParent, { refresh: true });
          if (cancelled) return;
          industryRows = refreshResp.data || [];
        }
        setIndustries(industryRows);
        setSummary(summaryResp.data || null);
        setStocks(stocksResp.data || null);
        setSelectedIndustry((current) => {
          if (!current) return '';
          const stillExists = industryRows.some((item) => item.industrySector === current);
          return stillExists ? current : '';
        });
        setStatus('online');
      })
      .catch((loadError: unknown) => {
        if (cancelled) return;
        setStatus('error');
        setError(loadError instanceof Error ? loadError.message : String(loadError));
      });

    return () => {
      cancelled = true;
    };
  }, [selectedParent]);

  useEffect(() => {
    if (!selectedParent || !selectedIndustry) {
      setSubSectors([]);
      setSelectedSubSector('');
      return;
    }

    let cancelled = false;
    setError('');
    Promise.all([
      getSubSectors(selectedParent, selectedIndustry),
      getStocks({
        parentSector: selectedParent,
        industrySector: selectedIndustry,
      }),
    ])
      .then(async ([subSectorsResp, stocksResp]) => {
        if (cancelled) return;
        let subSectorRows = subSectorsResp.data || [];
        if (!subSectorRows.length) {
          const refreshResp = await getSubSectors(selectedParent, selectedIndustry, { refresh: true });
          if (cancelled) return;
          subSectorRows = refreshResp.data || [];
        }
        setSubSectors(subSectorRows);
        setStocks(stocksResp.data || null);
        setSelectedSubSector((current) => {
          if (!current) return '';
          const stillExists = subSectorRows.some((item) => item.subSector === current);
          return stillExists ? current : '';
        });
      })
      .catch((loadError: unknown) => {
        if (cancelled) return;
        setError(loadError instanceof Error ? loadError.message : String(loadError));
      });

    return () => {
      cancelled = true;
    };
  }, [selectedIndustry, selectedParent]);

  useEffect(() => {
    if (!selectedParent || !selectedIndustry || !selectedSubSector) return;
    let cancelled = false;
    getStocks({
      parentSector: selectedParent,
      industrySector: selectedIndustry,
      subSector: selectedSubSector,
    })
      .then((response) => {
        if (cancelled) return;
        setStocks(response.data || null);
      })
      .catch((loadError: unknown) => {
        if (cancelled) return;
        setError(loadError instanceof Error ? loadError.message : String(loadError));
      });

    return () => {
      cancelled = true;
    };
  }, [selectedSubSector, selectedIndustry, selectedParent]);

  useEffect(() => {
    const parentToken = String(selectedParent || '').trim().toUpperCase();
    const industryToken = String(selectedIndustry || '').trim().toUpperCase();
    const shouldFetchPharmaMeta = parentToken === 'HEALTHCARE' && (industryToken.includes('PHARMA') || !industryToken);
    if (!shouldFetchPharmaMeta) {
      setFallbackSymbolMetaBySymbol({});
      return;
    }

    let cancelled = false;
    fetchSectorWiseStocks(
      'PHARMA',
      { dir: 'ASC', page: 1, pageSize: 400, sort: 'STOCK' },
      {
        diagnostic: {
          action: 'load-pharma-meta-for-sector-hierarchy',
          component: 'SectorHierarchyPanel',
          page: '/app/sector/stocks/healthcare?tab=hierarchy',
        },
      },
    )
      .then(adaptSectorWisePayload)
      .then((payload) => {
        if (cancelled) return;
        setFallbackSymbolMetaBySymbol(buildSymbolMetaMap(payload.rows));
      })
      .catch(() => {
        if (cancelled) return;
        setFallbackSymbolMetaBySymbol({});
      });

    return () => {
      cancelled = true;
    };
  }, [selectedIndustry, selectedParent]);

  const parentOptions = useMemo(() => {
    if (parents.length) {
      return parents.map((item) => ({ label: `${item.parentSector} (${item.stockCount})`, value: item.parentSector }));
    }
    if (selectedParent) {
      return [{ label: `${selectedParent} (0)`, value: selectedParent }];
    }
    return [];
  }, [parents, selectedParent]);

  const industryOptions = useMemo(
    () => industries.map((item) => ({ label: `${item.industrySector} (${item.stockCount})`, value: item.industrySector })),
    [industries],
  );

  const subSectorOptions = useMemo(
    () => subSectors.map((item) => ({ label: `${item.subSector} (${item.stockCount})`, value: item.subSector })),
    [subSectors],
  );

  const totalSubSectors = useMemo(
    () => (summary?.industries || []).reduce((sum, item) => sum + item.subSectors.length, 0),
    [summary],
  );

  const tableRows = useMemo(() => {
    const mergedMeta = { ...symbolMetaBySymbol, ...fallbackSymbolMetaBySymbol };
    const baseRows = stocks?.stocks || [];
    return baseRows.map((row) => {
      const token = normalizeSymbolToken(row.symbol);
      const meta = mergedMeta[token];
      const rowLevelIndex = formatSectorIndex((row as { INDEX?: unknown; index?: unknown }).index ?? (row as { INDEX?: unknown; index?: unknown }).INDEX);
      const rowLevelMcap = toSortableNumber((row as { MCAP?: unknown; mcap?: unknown }).mcap ?? (row as { MCAP?: unknown; mcap?: unknown }).MCAP);
      const rowLevelMcapRank = toSortableNumber(
        (row as { MCAP_RANK?: unknown; mcapRank?: unknown }).mcapRank ?? (row as { MCAP_RANK?: unknown; mcapRank?: unknown }).MCAP_RANK,
      );
      return {
        index: rowLevelIndex !== '-' ? rowLevelIndex : (meta?.index || null),
        mcap: rowLevelMcap ?? (meta?.mcap ?? null),
        mcapRank: rowLevelMcapRank ?? (meta?.mcapRank ?? null),
        parentSector: row.parentSector || stocks?.parentSector || selectedParent,
        industrySector: row.industrySector || stocks?.industrySector || selectedIndustry,
        subSector: row.subSector || stocks?.subSector || selectedSubSector,
        symbol: row.symbol,
        exchange: row.exchange,
      };
    });
  }, [fallbackSymbolMetaBySymbol, selectedIndustry, selectedParent, selectedSubSector, stocks, symbolMetaBySymbol]);

  const noHierarchyDataLoaded = status === 'online' && parents.length === 0;

  const handleRefresh = () => {
    if (!selectedParent) return;
    setRefreshing(true);
    setError('');
    clearSectorHierarchyCache();

    const stocksRequest = getStocks(
      {
        parentSector: selectedParent,
        ...(selectedIndustry ? { industrySector: selectedIndustry } : {}),
        ...(selectedSubSector ? { subSector: selectedSubSector } : {}),
      },
      { refresh: true },
    );

    Promise.all([
      getParents({ refresh: true }),
      getIndustries(selectedParent, { refresh: true }),
      selectedIndustry ? getSubSectors(selectedParent, selectedIndustry, { refresh: true }) : Promise.resolve({ data: [] }),
      getSummary(selectedParent, { refresh: true }),
      stocksRequest,
    ])
      .then(([parentsResp, industriesResp, subSectorsResp, summaryResp, stocksResp]) => {
        setParents(parentsResp.data || []);
        setIndustries(industriesResp.data || []);
        setSubSectors((subSectorsResp.data as SectorHierarchySubSector[]) || []);
        setSummary(summaryResp.data || null);
        setStocks(stocksResp.data || null);
        setStatus('online');
      })
      .catch((loadError: unknown) => {
        setStatus('error');
        setError(loadError instanceof Error ? loadError.message : String(loadError));
      })
      .finally(() => setRefreshing(false));
  };

  return (
    <div className="sector-hierarchy-panel">
      <SectorHierarchySummaryCards
        totalParents={parents.length}
        totalIndustries={summary?.industries.length || industries.length}
        totalSubSectors={totalSubSectors}
        totalStocks={stocks?.totalStocks || summary?.totalStocks || 0}
        selectedParent={selectedParent}
        selectedIndustry={selectedIndustry}
        selectedSubSector={selectedSubSector}
      />

      <SectorHierarchyFilters
        parentOptions={parentOptions}
        industryOptions={industryOptions}
        subSectorOptions={subSectorOptions}
        selectedParent={selectedParent}
        selectedIndustry={selectedIndustry}
        selectedSubSector={selectedSubSector}
        search={search}
        refreshing={refreshing}
        onParentChange={(value) => {
          setSelectedParent(value);
          setSelectedIndustry('');
          setSelectedSubSector('');
          setSubSectors([]);
        }}
        onIndustryChange={(value) => {
          setSelectedIndustry(value);
          setSelectedSubSector('');
        }}
        onSubSectorChange={setSelectedSubSector}
        onSearchChange={setSearch}
        onRefresh={handleRefresh}
      />

      {error ? <p className="sector-rotation-page-meta is-error">{error}</p> : null}
      {noHierarchyDataLoaded ? (
        <p className="sector-rotation-page-meta">
          Hierarchy master data is not loaded yet. Run the sector hierarchy DDL and CSV loader, then click Refresh.
        </p>
      ) : null}
      {status === 'loading' ? <p className="sector-rotation-page-meta">Loading sector hierarchy...</p> : null}

      <div className="sector-hierarchy-layout">
        <SectorHierarchyStocksTable rows={tableRows} search={search} />
      </div>
    </div>
  );
}
