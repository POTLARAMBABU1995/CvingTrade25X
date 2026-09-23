import { useMemo, useState } from 'react';
import type { LocalStrategyRow } from '../../types';
import { cn } from '../../lib/cn';
import { Card } from '../ui/Card';

type SortDirection = 'asc' | 'desc' | null;

type ColumnKey =
  | 'symbol'
  | 'priceChange'
  | 'volumeShock'
  | 'high52'
  | 'low52'
  | 'ath'
  | 'high1y'
  | 'high2y'
  | 'emaDays'
  | 'rsi'
  | 'macd'
  | 'volume'
  | 'atr'
  | 'support'
  | 'resistance';

type ColumnDefinition = {
  key: ColumnKey;
  label: string;
  align?: 'left' | 'right';
  defaultDirection: Exclude<SortDirection, null>;
  sortValue: (row: LocalStrategyRow) => number | string;
  render: (row: LocalStrategyRow) => string;
};

type ColumnPreset = {
  name: string;
  columns: ColumnKey[];
};

const PAGE_SIZE = 25;

const columnPresets: ReadonlyArray<ColumnPreset> = [
  { name: 'Momentum', columns: ['symbol', 'priceChange', 'emaDays', 'rsi', 'macd', 'volume'] },
  { name: 'Breakouts', columns: ['symbol', 'priceChange', 'high52', 'ath', 'support', 'resistance', 'volume'] },
  { name: 'Volume', columns: ['symbol', 'volumeShock', 'volume', 'priceChange'] },
] as const;

const columnDefinitions: ReadonlyArray<ColumnDefinition> = [
  { key: 'symbol', label: 'Stock Name', defaultDirection: 'asc', sortValue: (row) => row.symbol, render: (row) => row.symbol },
  { key: 'priceChange', label: 'Price Movers', align: 'right', defaultDirection: 'desc', sortValue: (row) => row.priceChange, render: (row) => `${row.priceChange > 0 ? '+' : ''}${row.priceChange.toFixed(2)}%` },
  { key: 'volumeShock', label: 'Volume Shockers', align: 'right', defaultDirection: 'desc', sortValue: (row) => row.volumeShock, render: (row) => row.volumeShock.toFixed(2) },
  { key: 'high52', label: '52 Week High', align: 'right', defaultDirection: 'desc', sortValue: (row) => row.high52, render: (row) => row.high52.toLocaleString('en-IN') },
  { key: 'low52', label: '52 Week Low', align: 'right', defaultDirection: 'desc', sortValue: (row) => row.low52, render: (row) => row.low52.toLocaleString('en-IN') },
  { key: 'ath', label: 'ATH', align: 'right', defaultDirection: 'desc', sortValue: (row) => row.ath, render: (row) => row.ath.toLocaleString('en-IN') },
  { key: 'high1y', label: '1 Years High', align: 'right', defaultDirection: 'desc', sortValue: (row) => row.high1y, render: (row) => row.high1y.toLocaleString('en-IN') },
  { key: 'high2y', label: '2 Years High', align: 'right', defaultDirection: 'desc', sortValue: (row) => row.high2y, render: (row) => row.high2y.toLocaleString('en-IN') },
  { key: 'emaDays', label: 'EMA Days (20/50/100/200)', defaultDirection: 'desc', sortValue: (row) => row.emaDaysSort, render: (row) => row.emaDays },
  { key: 'rsi', label: 'RSI', align: 'right', defaultDirection: 'desc', sortValue: (row) => row.rsiValue, render: (row) => row.rsi },
  { key: 'macd', label: 'MACD', align: 'right', defaultDirection: 'desc', sortValue: (row) => row.macdValue, render: (row) => row.macd },
  { key: 'volume', label: 'Volume', align: 'right', defaultDirection: 'desc', sortValue: (row) => row.volume, render: (row) => row.volume.toLocaleString('en-IN') },
  { key: 'atr', label: 'ATR', align: 'right', defaultDirection: 'desc', sortValue: (row) => row.atrValue, render: (row) => row.atr },
  { key: 'support', label: 'Support', align: 'right', defaultDirection: 'desc', sortValue: (row) => row.supportValue ?? Number.NEGATIVE_INFINITY, render: (row) => row.support },
  { key: 'resistance', label: 'Resistance', align: 'right', defaultDirection: 'desc', sortValue: (row) => row.resistanceValue ?? Number.NEGATIVE_INFINITY, render: (row) => row.resistance },
] as const;

type LocalStrategyScreenerTableProps = {
  rows: LocalStrategyRow[];
};

function sortRows(rows: LocalStrategyRow[], column: ColumnDefinition | undefined, direction: SortDirection): LocalStrategyRow[] {
  if (!column || !direction) {
    return rows;
  }

  const multiplier = direction === 'asc' ? 1 : -1;

  return [...rows].sort((left, right) => {
    const leftValue = column.sortValue(left);
    const rightValue = column.sortValue(right);

    if (typeof leftValue === 'string' && typeof rightValue === 'string') {
      return leftValue.localeCompare(rightValue) * multiplier;
    }

    return ((Number(leftValue) || 0) - (Number(rightValue) || 0)) * multiplier;
  });
}

function paginationWindow(totalPages: number, currentPage: number): Array<number | 'ellipsis'> {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  const pages = new Set<number>([1, totalPages, currentPage - 1, currentPage, currentPage + 1]);
  const values = Array.from(pages)
    .filter((page) => page >= 1 && page <= totalPages)
    .sort((left, right) => left - right);

  const output: Array<number | 'ellipsis'> = [];
  values.forEach((page, index) => {
    if (index > 0 && page - values[index - 1] > 1) {
      output.push('ellipsis');
    }
    output.push(page);
  });

  return output;
}

export function LocalStrategyScreenerTable({ rows }: LocalStrategyScreenerTableProps) {
  const [visibleColumns, setVisibleColumns] = useState<ColumnKey[]>(columnDefinitions.map((column) => column.key));
  const [sortKey, setSortKey] = useState<ColumnKey | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);
  const [currentPage, setCurrentPage] = useState(1);

  const activeColumns = useMemo(
    () => columnDefinitions.filter((column) => visibleColumns.includes(column.key)),
    [visibleColumns],
  );
  const sortColumn = useMemo(
    () => columnDefinitions.find((column) => column.key === sortKey),
    [sortKey],
  );
  const sortedRows = useMemo(
    () => sortRows(rows, sortColumn, sortDirection),
    [rows, sortColumn, sortDirection],
  );
  const totalPages = Math.max(1, Math.ceil(sortedRows.length / PAGE_SIZE));
  const safeCurrentPage = Math.min(currentPage, totalPages);
  const pagedRows = useMemo(() => {
    const startIndex = (safeCurrentPage - 1) * PAGE_SIZE;
    return sortedRows.slice(startIndex, startIndex + PAGE_SIZE);
  }, [safeCurrentPage, sortedRows]);

  function applyPreset(preset: ColumnPreset) {
    setVisibleColumns(preset.columns);
    setCurrentPage(1);
  }

  function toggleColumn(columnKey: ColumnKey) {
    setVisibleColumns((current) => {
      if (current.includes(columnKey)) {
        const next = current.filter((value) => value !== columnKey);
        return next.length ? next : current;
      }

      const next = [...current, columnKey];
      return columnDefinitions
        .map((column) => column.key)
        .filter((key) => next.includes(key));
    });
    setCurrentPage(1);
  }

  function toggleSort(column: ColumnDefinition) {
    if (sortKey !== column.key) {
      setSortKey(column.key);
      setSortDirection(column.defaultDirection);
      setCurrentPage(1);
      return;
    }

    if (sortDirection === column.defaultDirection) {
      setSortDirection(column.defaultDirection === 'asc' ? 'desc' : 'asc');
      setCurrentPage(1);
      return;
    }

    if (sortDirection) {
      setSortKey(null);
      setSortDirection(null);
      setCurrentPage(1);
    }
  }

  const paginationItems = paginationWindow(totalPages, safeCurrentPage);

  return (
    <Card variant="light" padding="md" className="overflow-hidden border-slate-200 shadow-sm dark:border-slate-700/70">
      <div className="flex flex-col gap-4 border-b border-slate-200 pb-4 lg:flex-row lg:items-start lg:justify-between dark:border-slate-700/70">
        <div>
          <h2 className="text-lg font-bold tracking-[-0.03em] text-slate-950 dark:text-slate-100">Strategy Screener</h2>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-300">Local JSON parity migration with the same derived EMA, RSI, MACD, ATR, support, and resistance columns.</p>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-sm">
          {columnPresets.map((preset) => (
            <button
              key={preset.name}
              type="button"
              className="rounded-full border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200 dark:hover:border-slate-500 dark:hover:text-slate-100"
              onClick={() => applyPreset(preset)}
            >
              {preset.name}
            </button>
          ))}
          <details className="group relative">
            <summary className="list-none cursor-pointer rounded-full border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-700 transition hover:border-slate-300 hover:text-slate-950 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200 dark:hover:border-slate-500 dark:hover:text-slate-100">
              Toggle columns
            </summary>
            <div className="absolute right-0 z-20 mt-2 grid min-w-[220px] gap-2 rounded-[20px] border border-slate-200 bg-white p-4 shadow-lg dark:border-slate-700 dark:bg-slate-950">
              {columnDefinitions.map((column) => (
                <label key={column.key} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={visibleColumns.includes(column.key)}
                    onChange={() => toggleColumn(column.key)}
                  />
                  <span>{column.label}</span>
                </label>
              ))}
            </div>
          </details>
        </div>
      </div>

      <div className="overflow-x-auto pt-4">
        <table className="min-w-full border-separate border-spacing-y-2 text-sm">
          <thead>
            <tr>
              {activeColumns.map((column) => {
                const isSorted = sortKey === column.key && sortDirection;
                const sortLabel = !isSorted ? 'sort' : sortDirection === 'asc' ? 'asc' : 'desc';

                return (
                  <th
                    key={column.key}
                    className={cn(
                      'whitespace-nowrap px-3 py-2 text-left text-xs font-bold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400',
                      column.align === 'right' && 'text-right',
                    )}
                  >
                    <button
                      type="button"
                      className="inline-flex items-center gap-2 font-inherit text-inherit"
                      onClick={() => toggleSort(column)}
                    >
                      <span>{column.label}</span>
                      <span className="text-slate-400 dark:text-slate-500">{sortLabel}</span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {pagedRows.map((row) => (
              <tr key={row.symbol} className="overflow-hidden rounded-[18px] bg-slate-50 dark:bg-slate-900/70">
                {activeColumns.map((column) => {
                  const value = column.render(row);
                  const isPositive = column.key === 'priceChange' && row.priceChange > 0;
                  const isNegative = (column.key === 'priceChange' && row.priceChange < 0) || (column.key === 'macd' && row.macdValue < 0);

                  return (
                    <td
                      key={`${row.symbol}-${column.key}`}
                      className={cn(
                        'whitespace-nowrap px-3 py-3 text-slate-700 first:rounded-l-[18px] last:rounded-r-[18px] dark:text-slate-200',
                        column.align === 'right' ? 'text-right' : 'text-left',
                        column.key === 'symbol' && 'font-semibold text-slate-950 dark:text-slate-100',
                        isPositive && 'text-emerald-700 dark:text-emerald-300',
                        isNegative && 'text-rose-700 dark:text-rose-300',
                        column.key === 'emaDays' && 'min-w-[300px] text-slate-600 dark:text-slate-300',
                      )}
                    >
                      {value}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-5 flex flex-col gap-4 border-t border-slate-200 pt-4 lg:flex-row lg:items-center lg:justify-between dark:border-slate-700/70">
        <p className="text-sm text-slate-500 dark:text-slate-300">
          Showing {pagedRows.length} of {rows.length} rows - Page {safeCurrentPage} of {totalPages}
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="rounded-full border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200"
            disabled={safeCurrentPage <= 1}
            onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
          >
            Prev
          </button>

          {paginationItems.map((item, index) =>
            item === 'ellipsis' ? (
              <span key={`ellipsis-${index}`} className="px-2 text-slate-500 dark:text-slate-400">...</span>
            ) : (
              <button
                key={item}
                type="button"
                className={cn(
                  'rounded-full px-3 py-2 text-sm font-semibold transition',
                  safeCurrentPage === item
                    ? 'border border-[rgb(var(--page-accent-rgb)/0.18)] bg-[rgb(var(--page-accent-rgb)/0.12)] text-text shadow-sm'
                    : 'border border-slate-200 bg-white text-slate-700 hover:border-[rgb(var(--page-accent-rgb)/0.18)] hover:text-slate-950 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200 dark:hover:border-slate-500 dark:hover:text-slate-100',
                )}
                onClick={() => setCurrentPage(item)}
              >
                {item}
              </button>
            ),
          )}

          <button
            type="button"
            className="rounded-full border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200"
            disabled={safeCurrentPage >= totalPages}
            onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
          >
            Next
          </button>
        </div>
      </div>
    </Card>
  );
}
