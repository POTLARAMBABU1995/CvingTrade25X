import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { AppPagination } from '../../components/app/AppPagination';
import { LiveStatusPill } from '../../components/app/LiveStatusPill';
import { TechnicalSearchInput } from '../../components/app/TechnicalSearchInput';
import { CvingLegacyHeader } from '@/components/navigation/CvingLegacyHeader';
import { Button } from '../../components/ui/Button';
import { TechnicalMarketCapCell } from '../../components/app/TechnicalMarketCapCell';
import {
  firstPresentValue,
  formatMarketCapRankValue,
  formatMarketCapValue,
  getMarketCapCategory,
  MARKET_CAP_INDEX_ALIASES,
  MARKET_CAP_RANK_ALIASES,
  MARKET_CAP_VALUE_ALIASES,
  normalizeMarketCapIndex,
  toNumber,
  type MarketCapCategory,
} from '../../adapters/technicalMarketCap';
import { fetchPriceActionManualPayload, savePriceActionManualPayload } from '../../services/api/technicalApi';
import type { PriceActionManualLevelWire, PriceActionManualPayloadWire, PriceActionManualRowWire } from '../../types/api/technical';
import { useProtectedPageAuth, useTechnicalThemeMode } from './technicalPageGuards';
import { normalizeDisplaySymbol } from '../../utils/symbols';

const PAGE_SIZE = 15;
const DEFAULT_TD = '1D';

type LoadStatus = 'error' | 'loading' | 'online';

type PriceActionLevel = {
  created_at: string;
  level_id: string;
  level_type: string;
  updated_at: string;
  value: string;
};

type PriceActionRow = {
  created_at: string;
  index: string;
  level_count: number;
  levels: PriceActionLevel[];
  marketCapTone: MarketCapCategory;
  mcap: string;
  mcapRank: string;
  symbol: string;
  td: string;
  updated_at: string;
};

type ModalState = {
  error: string;
  levels: PriceActionLevel[];
  mode: 'create' | 'edit' | 'insert';
  selectedLevelId: string;
  selectedLevelValue: string;
  symbol: string;
  value: string;
};

function normalizeSymbol(value: unknown): string {
  return normalizeDisplaySymbol(value);
}

function formatLevelValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  const text = String(value).trim();
  if (!text) return '';
  const numeric = Number(text.replace(/,/g, ''));
  if (!Number.isFinite(numeric)) return text;
  const fixed = numeric.toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
  return fixed || '0';
}

function parseLevelValue(raw: string): number | null {
  const text = raw.trim().replace(/,/g, '');
  if (!text) return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

function parseLevelValues(raw: string): { error: string; values: string[] } {
  const parts = raw
    .split(/[\n,;|]+/)
    .map((part) => part.trim())
    .filter(Boolean);
  const seen = new Set<string>();
  const values: string[] = [];
  for (const part of parts) {
    const parsed = parseLevelValue(part);
    if (parsed === null) return { error: `Invalid SR level: ${part}`, values: [] };
    const formatted = formatLevelValue(parsed);
    if (seen.has(formatted)) continue;
    seen.add(formatted);
    values.push(formatted);
  }
  return { error: values.length ? '' : 'Enter at least one valid SR level.', values };
}

function sortLevels(a: PriceActionLevel, b: PriceActionLevel): number {
  const aNum = toNumber(a.value);
  const bNum = toNumber(b.value);
  if (aNum !== null && bNum !== null) return aNum - bNum;
  return a.value.localeCompare(b.value);
}

function chunkLevels<T>(items: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
}

function hydrateLevel(level: PriceActionManualLevelWire): PriceActionLevel {
  return {
    created_at: String(level.created_at || ''),
    level_id: String(level.level_id || ''),
    level_type: String(level.level_type || 'SR'),
    updated_at: String(level.updated_at || ''),
    value: formatLevelValue(level.value),
  };
}

function hydrateRows(payload: PriceActionManualPayloadWire | null): { rows: PriceActionRow[]; totalSymbols: number } {
  const wireRows = Array.isArray(payload?.rows) ? payload.rows : [];
  const rows = wireRows.map((row: PriceActionManualRowWire) => {
    const source = row as Record<string, unknown>;
    const levels = (Array.isArray(row.levels) ? row.levels : []).map(hydrateLevel).sort(sortLevels);
    const index = normalizeMarketCapIndex(firstPresentValue(source, MARKET_CAP_INDEX_ALIASES));
    return {
      created_at: String(row.created_at || ''),
      index,
      level_count: levels.length,
      levels,
      marketCapTone: getMarketCapCategory(index),
      mcap: formatMarketCapValue(firstPresentValue(source, MARKET_CAP_VALUE_ALIASES)),
      mcapRank: formatMarketCapRankValue(firstPresentValue(source, MARKET_CAP_RANK_ALIASES)),
      symbol: normalizeSymbol(firstPresentValue(source, ['symbol', 'SYMBOL', 'stock', 'STOCK'])),
      td: String(firstPresentValue(source, ['td', 'TD', 'T_D']) ?? DEFAULT_TD),
      updated_at: String(row.updated_at || ''),
    };
  });
  const totalSymbols = toNumber(payload?.meta?.total_rows) ?? rows.length;
  return { rows, totalSymbols };
}

function sumLevelCount(rows: PriceActionRow[]): number {
  return rows.reduce((total, row) => total + row.levels.length, 0);
}

function emptyModal(mode: ModalState['mode'], row?: PriceActionRow): ModalState {
  return {
    error: '',
    levels: row?.levels ?? [],
    mode,
    selectedLevelId: '',
    selectedLevelValue: '',
    symbol: row?.symbol ?? '',
    value: '',
  };
}

export function PriceActionSR() {
  const authorized = useProtectedPageAuth();
  const [rows, setRows] = useState<PriceActionRow[]>([]);
  const [totalSymbols, setTotalSymbols] = useState(0);
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [statusMessage, setStatusMessage] = useState('Loading price action rows...');
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [modal, setModal] = useState<ModalState | null>(null);
  const themeMode = useTechnicalThemeMode();

  useEffect(() => {
    setPage(1);
  }, [deferredSearch]);

  useEffect(() => {
    if (!authorized) return undefined;
    const controller = new AbortController();
    setStatus('loading');
    setStatusMessage('Loading price action rows...');
    fetchPriceActionManualPayload({ signal: controller.signal })
      .then((payload) => {
        if (payload.ok === false) throw new Error(payload.error || payload.detail || 'Price Action SR API returned an error.');
        const hydrated = hydrateRows(payload);
        setRows(hydrated.rows);
        setTotalSymbols(hydrated.totalSymbols);
        setStatus('online');
        setStatusMessage(`Loaded ${hydrated.rows.length} symbols and ${sumLevelCount(hydrated.rows)} levels.`);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setRows([]);
        setTotalSymbols(0);
        setStatus('error');
        setStatusMessage(error instanceof Error ? error.message : String(error));
      });
    return () => controller.abort();
  }, [authorized, refreshVersion]);

  const filteredRows = useMemo(() => {
    const query = deferredSearch.trim().toUpperCase();
    if (!query) return rows;
    return rows.filter((row) => row.symbol.includes(query));
  }, [deferredSearch, rows]);

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageRows = filteredRows.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const totalLevels = sumLevelCount(rows);

  const saveModal = async () => {
    if (!modal) return;
    const symbol = normalizeSymbol(modal.symbol);
    if (!symbol) {
      setModal({ ...modal, error: 'Symbol is required.' });
      return;
    }

    try {
      if (modal.mode === 'create') {
        const parsed = parseLevelValues(modal.value);
        if (parsed.error) {
          setModal({ ...modal, error: parsed.error });
          return;
        }
        setStatus('loading');
        setStatusMessage(`Saving ${symbol}...`);
        const response = await savePriceActionManualPayload({ mode: 'create_symbol', symbol, sr_levels: parsed.values });
        if (response.ok === false) throw new Error(response.error || response.detail || 'Save failed');
        setModal(null);
        setRefreshVersion((current) => current + 1);
        const insertedCount = Number(response.inserted_count ?? parsed.values.length ?? 0);
        const skippedCount = Number(response.skipped_count ?? 0);
        if (insertedCount > 0 && skippedCount > 0) {
          setStatusMessage(`Inserted ${insertedCount} new SR levels for ${symbol}; skipped ${skippedCount} duplicate levels.`);
        } else if (insertedCount > 0) {
          setStatusMessage(`Inserted ${insertedCount} SR levels for ${symbol}.`);
        } else if (skippedCount > 0) {
          setStatusMessage(`No new SR levels inserted for ${symbol}; all submitted levels already exist.`);
        } else {
          setStatusMessage(`No SR levels inserted for ${symbol}.`);
        }
        return;
      }

      const parsed = parseLevelValue(modal.value);
      if (parsed === null) {
        setModal({ ...modal, error: 'Enter one valid SR level.' });
        return;
      }
      const levelValue = formatLevelValue(parsed);
      if (modal.mode === 'edit') {
        if (!modal.selectedLevelId) {
          setModal({ ...modal, error: 'Select an SR level from the dropdown.' });
          return;
        }
        if (!window.confirm(`Update ${modal.selectedLevelValue || levelValue} to ${levelValue} for ${symbol}?`)) return;
      }

      setStatus('loading');
      setStatusMessage(`${modal.mode === 'edit' ? 'Updating' : 'Saving'} ${symbol}...`);
      const body = modal.mode === 'edit'
        ? { mode: 'update', symbol, sr_level: levelValue, level_id: modal.selectedLevelId }
        : { mode: 'insert', symbol, sr_level: levelValue };
      const response = await savePriceActionManualPayload(body);
      if (response.ok === false) throw new Error(response.error || response.detail || 'Save failed');
      setModal(null);
      setRefreshVersion((current) => current + 1);
      setStatusMessage(`${modal.mode === 'edit' ? 'Updated' : 'Inserted'} ${levelValue} for ${symbol}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setStatus('error');
      setStatusMessage(message);
      setModal((current) => current ? { ...current, error: message.slice(0, 220) } : current);
    }
  };

  const deleteSelectedLevel = async () => {
    if (!modal || modal.mode !== 'edit') return;
    if (!modal.selectedLevelId) {
      setModal({ ...modal, error: 'Select an SR level from the dropdown.' });
      return;
    }
    if (!window.confirm(`Delete ${modal.selectedLevelValue || modal.value} for ${modal.symbol}?`)) return;
    try {
      setStatus('loading');
      setStatusMessage(`Deleting ${modal.symbol} SR level...`);
      const response = await savePriceActionManualPayload({ mode: 'delete', level_id: modal.selectedLevelId });
      if (response.ok === false) throw new Error(response.error || response.detail || 'Delete failed');
      setModal(null);
      setRefreshVersion((current) => current + 1);
      setStatusMessage(`Deleted ${modal.selectedLevelValue || modal.value} for ${modal.symbol}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setStatus('error');
      setStatusMessage(message);
      setModal((current) => current ? { ...current, error: message.slice(0, 220) } : current);
    }
  };

  return (
    <div className={themeMode === 'dark' ? 'page-theme--technicals ema-page ema-page--dark price-action-react' : 'page-theme--technicals ema-page price-action-react'}>
      <CvingLegacyHeader activeSection="technicals" activeTechnicalPage="/app/technical/price-action" />
      <main className="container price-action-react__main">
        <section className="price-action-react__header" aria-label="Price Action SR Levels">
          <h1>Price Action SR Levels</h1>
        </section>

        <section className="card price-action-react__toolbar-card" aria-label="Price action controls">
          <div className="price-action-react__toolbar">
            <LiveStatusPill state={status === 'online' ? 'live' : status === 'loading' ? 'syncing' : 'stale'} title={statusMessage} label={status === 'online' ? 'Live' : status === 'loading' ? 'Syncing' : 'Stale'} />
            <TechnicalSearchInput value={search} onChange={setSearch} />
            <Button className="preset-btn" variant="secondary" disabled={status === 'loading'} onClick={() => setRefreshVersion((current) => current + 1)}>
              Refresh
            </Button>
            <a className="preset-btn price-action-react__link-btn" href="/app/technical/price-action-analysis">
              Analysis
            </a>
            <span className="count-pill">Total Levels <strong>{totalLevels.toLocaleString('en-IN')}</strong></span>
            <span className="count-pill">Total <strong>{totalSymbols.toLocaleString('en-IN')}</strong></span>
            <Button className="preset-btn" variant="primary" onClick={() => setModal(emptyModal('create'))}>
              New SR_LEVEL
            </Button>
          </div>
        </section>

        <section className="card price-action-react__table-card" aria-label="Price action symbols table">
          <div className="table-title">
            <h3>Price Action SR</h3>
            <span className="count-pill">15 rows per page</span>
          </div>
          <AppPagination currentPage={currentPage} totalPages={totalPages} onPageChange={setPage} />
          <div className="table-wrapper">
            <table className="app-data-table table-sticky-safe data-table trend-table price-action-react__table">
              <colgroup>
                <col data-col="sNo" />
                <col data-col="symbol" />
                <col data-col="index" />
                <col data-col="mcap" />
                <col data-col="mcapRank" />
                <col data-col="td" />
                <col data-col="levels" />
                <col data-col="actions" />
              </colgroup>
              <thead>
                <tr>
                  <th data-col="sNo">S.No</th>
                  <th data-col="symbol">SYMBOL</th>
                  <th data-col="index">INDEX</th>
                  <th data-col="mcap">MCAP</th>
                  <th data-col="mcapRank">MCAP_RANK</th>
                  <th data-col="td">TD</th>
                  <th data-col="levels">SR_LEVEL</th>
                  <th data-col="actions">CRUD OPERATIONS</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.length ? pageRows.map((row, index) => {
                  const rowNumber = ((currentPage - 1) * PAGE_SIZE) + index + 1;
                  const marketCapTone = row.marketCapTone;
                  const levelRows = chunkLevels(row.levels, 10);
                  return (
                    <tr key={row.symbol}>
                      <td data-col="sNo">{rowNumber}</td>
                      <td data-col="symbol">
                        <TechnicalMarketCapCell
                          className="price-action-react__symbol"
                          copyText={row.symbol}
                          tone={marketCapTone}
                          onCopy={(value) => {
                            if (!navigator.clipboard) return;
                            navigator.clipboard.writeText(value).catch(() => undefined);
                          }}
                        >
                          <strong>{row.symbol}</strong>
                          <span>{row.levels.length} level{row.levels.length === 1 ? '' : 's'}</span>
                        </TechnicalMarketCapCell>
                      </td>
                      <td data-col="index">
                        <TechnicalMarketCapCell tone={marketCapTone}>{row.index}</TechnicalMarketCapCell>
                      </td>
                      <td data-col="mcap">
                        <TechnicalMarketCapCell tone={marketCapTone}>{row.mcap}</TechnicalMarketCapCell>
                      </td>
                      <td data-col="mcapRank">
                        <TechnicalMarketCapCell tone={marketCapTone}>{row.mcapRank}</TechnicalMarketCapCell>
                      </td>
                      <td data-col="td"><span className="count-pill">{row.td}</span></td>
                      <td data-col="levels">
                        <div className="price-action-react__levels">
                          {levelRows.map((levelRow, levelRowIndex) => (
                            <div className="price-action-react__level-row" key={`${row.symbol}-levels-${levelRowIndex}`}>
                              {levelRow.map((level, levelIndex) => (
                                <span
                                  key={level.level_id || `${level.value}-${levelRowIndex}-${levelIndex}`}
                                  className="price-action-react__level-chip"
                                  title={level.updated_at ? `Updated ${level.updated_at}` : 'SR level'}
                                >
                                  {level.value}
                                </span>
                              ))}
                            </div>
                          ))}
                        </div>
                      </td>
                      <td data-col="actions">
                        <div className="price-action-react__actions">
                          <Button size="sm" variant="ghost" onClick={() => setModal(emptyModal('edit', row))}>Edit</Button>
                          <Button size="sm" variant="secondary" onClick={() => setModal(emptyModal('insert', row))}>Insert</Button>
                        </div>
                      </td>
                    </tr>
                  );
                }) : (
                  <tr>
                    <td colSpan={8} className="empty">
                      {status === 'loading' ? 'Loading price action symbols...' : 'No price action symbols found.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <AppPagination currentPage={currentPage} totalPages={totalPages} onPageChange={setPage} />
        </section>
      </main>

      {modal ? (
        <div className="price-action-react__modal" role="dialog" aria-modal="true" aria-labelledby="priceActionReactModalTitle" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setModal(null);
        }}>
          <form className="price-action-react__modal-dialog" onSubmit={(event) => {
            event.preventDefault();
            saveModal();
          }}>
            <button className="price-action-react__modal-close" type="button" aria-label="Close dialog" onClick={() => setModal(null)}>x</button>
            <h2 id="priceActionReactModalTitle">
              {modal.mode === 'edit' ? `Edit ${modal.symbol}` : modal.mode === 'insert' ? `Insert ${modal.symbol}` : 'New SR_LEVEL'}
            </h2>
            <p>
              {modal.mode === 'edit'
                ? 'Select an existing SR level from the dropdown, then update or delete it.'
                : modal.mode === 'insert'
                  ? 'Enter one new SR level value for this symbol and save it.'
                  : 'Enter a unique symbol and one or more SR levels separated by commas or new lines.'}
            </p>
            <label>
              <span>Symbol</span>
              <input
                type="text"
                value={modal.symbol}
                readOnly={modal.mode !== 'create'}
                placeholder="ADANIPOWER"
                onChange={(event) => setModal({ ...modal, symbol: normalizeSymbol(event.currentTarget.value) })}
              />
            </label>
            {modal.mode === 'edit' ? (
              <label>
                <span>Select SR level</span>
                <select
                  value={modal.selectedLevelId}
                  onChange={(event) => {
                    const selected = modal.levels.find((level) => level.level_id === event.currentTarget.value);
                    setModal({
                      ...modal,
                      selectedLevelId: selected?.level_id ?? '',
                      selectedLevelValue: selected?.value ?? '',
                      value: selected?.value ?? '',
                    });
                  }}
                >
                  <option value="">Select SR level</option>
                  {modal.levels.map((level) => (
                    <option key={level.level_id} value={level.level_id}>{level.value}</option>
                  ))}
                </select>
              </label>
            ) : null}
            <label>
              <span>{modal.mode === 'create' ? 'SR Levels' : 'SR Level'}</span>
              <textarea
                rows={modal.mode === 'create' ? 5 : 2}
                value={modal.value}
                placeholder={modal.mode === 'create' ? '300, 440.25' : '300'}
                onChange={(event) => setModal({ ...modal, value: event.currentTarget.value })}
              />
            </label>
            <div className="price-action-react__modal-meta">
              <span className="count-pill">TD: 1D only</span>
              <span className="count-pill">{modal.mode === 'create' ? 'Create mode' : modal.mode === 'edit' ? 'Edit mode' : 'Insert mode'}</span>
              <span className="count-pill">1D</span>
            </div>
            {modal.error ? <p className="price-action-react__modal-error" role="alert">{modal.error}</p> : null}
            <div className="price-action-react__modal-actions">
              {modal.mode === 'edit' ? (
                <Button variant="danger" type="button" onClick={deleteSelectedLevel}>Delete</Button>
              ) : (
                <Button variant="secondary" type="button" onClick={() => setModal({ ...modal, symbol: modal.mode === 'create' ? '' : modal.symbol, value: '', error: '', selectedLevelId: '', selectedLevelValue: '' })}>Clear</Button>
              )}
              <Button variant="primary" type="submit">{modal.mode === 'edit' ? 'Update' : 'Insert'}</Button>
              <Button variant="secondary" type="button" onClick={() => setModal(null)}>Cancel</Button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
