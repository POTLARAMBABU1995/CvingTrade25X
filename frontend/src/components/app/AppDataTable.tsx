import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { cn } from '../../lib/cn';
import { AppPagination } from './AppPagination';

export type AppSortType = 'date' | 'number' | 'string';
export type AppSortDirection = 'asc' | 'desc';

export type AppSortState = {
  direction: AppSortDirection | null;
  key: string | null;
};

export type AppDataTableColumn<Row> = {
  cellClassName?: string | ((row: Row) => string | undefined);
  dataCol: string;
  getSortValue: (row: Row) => number | string | null;
  key: string;
  label: ReactNode;
  renderCell: (row: Row) => ReactNode;
  showArrow?: boolean;
  sortable?: boolean;
  sticky?: boolean | 'left';
  stickyWidthPx?: number;
  sortType: AppSortType;
};

type StickyRole = 'sno' | 'symbol';

type StickyMeta = {
  leftPx: number;
  role: StickyRole;
  widthPx: number;
};

const SNO_TOKENS = new Set(['s.no', 's_no', 'serial', 'serial_no', 'serialno', 'sno']);
const PRIMARY_IDENTIFIER_TOKENS = new Set([
  'stock',
  'symbol',
]);
const FALLBACK_IDENTIFIER_TOKENS = new Set([
  'api_name',
  'code',
  'id',
  'index',
  'job_name',
  'name',
  'security_name',
]);

function normalizeToken(value: string): string {
  return value.trim().toLowerCase().replace(/[\s\-]+/g, '_');
}

function looksLikeSno(column: AppDataTableColumn<unknown>): boolean {
  const key = normalizeToken(column.key);
  const dataCol = normalizeToken(column.dataCol);
  return SNO_TOKENS.has(key) || SNO_TOKENS.has(dataCol);
}

function matchesAnyToken(column: AppDataTableColumn<unknown>, tokens: Set<string>): boolean {
  const key = normalizeToken(column.key);
  const dataCol = normalizeToken(column.dataCol);
  return tokens.has(key) || tokens.has(dataCol);
}

function looksLikePrimaryIdentifier(column: AppDataTableColumn<unknown>): boolean {
  return matchesAnyToken(column, PRIMARY_IDENTIFIER_TOKENS);
}

function looksLikeFallbackIdentifier(column: AppDataTableColumn<unknown>): boolean {
  return matchesAnyToken(column, FALLBACK_IDENTIFIER_TOKENS);
}

export function getDefaultSortDirection(sortType: AppSortType): AppSortDirection {
  return sortType === 'string' ? 'asc' : 'desc';
}

export function getNextSortState(current: AppSortState, key: string, sortType: AppSortType): AppSortState {
  const defaultDirection = getDefaultSortDirection(sortType);
  if (current.key !== key || !current.direction) {
    return { key, direction: defaultDirection };
  }
  if (current.direction === defaultDirection) {
    return { key, direction: defaultDirection === 'asc' ? 'desc' : 'asc' };
  }
  return { key: null, direction: null };
}

function comparableFromValue(value: number | string | null, sortType: AppSortType): number | string | null {
  if (value === null || value === undefined || value === '') return null;
  if (sortType === 'number') {
    const numeric = typeof value === 'number' ? value : Number(String(value).replace(/,/g, '').replace(/%/g, ''));
    return Number.isFinite(numeric) ? numeric : null;
  }
  if (sortType === 'date') {
    if (typeof value === 'number') return Number.isFinite(value) ? value : null;
    const text = String(value).trim();
    const ddmmyyyy = text.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
    if (ddmmyyyy) {
      const [, d, m, y] = ddmmyyyy;
      const ts = new Date(Number(y), Number(m) - 1, Number(d)).getTime();
      return Number.isNaN(ts) ? null : ts;
    }
    const parsed = Date.parse(text);
    return Number.isNaN(parsed) ? null : parsed;
  }
  return String(value);
}

export function sortRowsForTable<Row>(
  rows: Row[],
  columns: Array<Pick<AppDataTableColumn<Row>, 'getSortValue' | 'key' | 'sortType'>>,
  sort: AppSortState,
): Row[] {
  if (!sort.key || !sort.direction) return rows;
  const column = columns.find((candidate) => candidate.key === sort.key);
  if (!column) return rows;
  const multiplier = sort.direction === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = comparableFromValue(column.getSortValue(a), column.sortType);
    const vb = comparableFromValue(column.getSortValue(b), column.sortType);
    if (va === null && vb === null) return 0;
    if (va === null) return 1 * multiplier;
    if (vb === null) return -1 * multiplier;
    if (column.sortType === 'string') {
      return String(va).localeCompare(String(vb)) * multiplier;
    }
    return (Number(va) - Number(vb)) * multiplier;
  });
}

type AppDataTableProps<Row> = {
  className?: string;
  columns: Array<AppDataTableColumn<Row>>;
  currentPage?: number;
  disableClientSort?: boolean;
  emptyMessage?: string;
  getRowKey: (row: Row, index: number) => string;
  onPageChange?: (page: number) => void;
  onSortChange?: (sort: AppSortState) => void;
  pageSize: number;
  paginationSummaryLabel?: string;
  rows: Row[];
  showTopPagination?: boolean;
  sortState?: AppSortState;
  tableClassName?: string;
  tableId: string;
  totalRows?: number;
};

export function AppDataTable<Row>({
  className,
  columns,
  currentPage,
  disableClientSort = false,
  emptyMessage = 'No records returned from backend.',
  getRowKey,
  onPageChange,
  onSortChange,
  pageSize,
  paginationSummaryLabel,
  rows,
  showTopPagination = false,
  sortState,
  tableClassName,
  tableId,
  totalRows,
}: AppDataTableProps<Row>) {
  const [internalSort, setInternalSort] = useState<AppSortState>({ key: null, direction: null });
  const [internalPage, setInternalPage] = useState(1);
  const sort = sortState ?? internalSort;
  const isControlledPagination = currentPage !== undefined && totalRows !== undefined && Boolean(onPageChange);

  const sortedRows = useMemo(
    () => (disableClientSort ? rows : sortRowsForTable(rows, columns, sort)),
    [columns, disableClientSort, rows, sort],
  );
  const stickyMeta = useMemo(() => {
    const normalizedColumns = columns as Array<AppDataTableColumn<unknown>>;
    let leftOffset = 0;
    const result = new Map<string, StickyMeta>();
    const explicitStickyColumns = normalizedColumns.filter((column) => column.sticky === true || column.sticky === 'left');
    const snoColumn = normalizedColumns.find(looksLikeSno);
    const identifierColumn = normalizedColumns.find((column) => column !== snoColumn && looksLikePrimaryIdentifier(column))
      ?? normalizedColumns.find((column) => column !== snoColumn && looksLikeFallbackIdentifier(column));

    const stickySet = new Set<string>();
    if (snoColumn) stickySet.add(snoColumn.key);
    if (identifierColumn) stickySet.add(identifierColumn.key);
    explicitStickyColumns.forEach((column) => stickySet.add(column.key));

    columns.forEach((column) => {
      const sticky = stickySet.has(column.key);
      if (!sticky) return;
      const role: StickyRole = snoColumn && column.key === snoColumn.key ? 'sno' : 'symbol';
      const widthPx = Math.max(
        column.stickyWidthPx ?? (role === 'sno' ? 84 : 190),
        role === 'sno' ? 72 : 140,
      );
      result.set(column.key, { leftPx: leftOffset, role, widthPx });
      leftOffset += widthPx;
    });
    return result;
  }, [columns]);
  const hasStickySno = useMemo(
    () => Array.from(stickyMeta.values()).some((meta) => meta.role === 'sno'),
    [stickyMeta],
  );
  const rowTotal = isControlledPagination ? Math.max(0, totalRows ?? 0) : sortedRows.length;
  const totalPages = Math.max(1, Math.ceil(rowTotal / pageSize));
  const page = Math.min(Math.max(isControlledPagination ? currentPage ?? 1 : internalPage, 1), totalPages);
  const pageRows = isControlledPagination ? sortedRows : sortedRows.slice((page - 1) * pageSize, page * pageSize);
  const pageStart = rowTotal ? ((page - 1) * pageSize) + 1 : 0;
  const pageEnd = isControlledPagination
    ? Math.min(pageStart + Math.max(pageRows.length - 1, 0), rowTotal)
    : Math.min(page * pageSize, rowTotal);
  const paginationSummary = paginationSummaryLabel
    ? `Showing ${pageStart.toLocaleString('en-IN')}-${pageEnd.toLocaleString('en-IN')} of ${rowTotal.toLocaleString('en-IN')} ${paginationSummaryLabel}`
    : '';
  const shouldRenderPaginationRow = Boolean(paginationSummary || totalPages > 1);
  const setPage = onPageChange ?? setInternalPage;
  const setSort = (nextSort: AppSortState) => {
    if (onSortChange) {
      onSortChange(nextSort);
      return;
    }
    setInternalSort(nextSort);
  };

  useEffect(() => {
    if (!isControlledPagination) {
      setInternalPage(1);
    }
  }, [isControlledPagination, rows, sort.key, sort.direction]);

  useEffect(() => {
    if (isControlledPagination) {
      if (rowTotal > 0 && (currentPage ?? 1) > totalPages && onPageChange) {
        onPageChange(totalPages);
      }
      return;
    }
    if (internalPage > totalPages) {
      setInternalPage(totalPages);
    }
  }, [currentPage, internalPage, isControlledPagination, onPageChange, rowTotal, totalPages]);

  return (
    <div className={className}>
      {showTopPagination && shouldRenderPaginationRow ? (
        <div className="app-data-table__pagination-row app-data-table__pagination-row--top">
          {paginationSummary ? <span className="app-data-table__pagination-summary">{paginationSummary}</span> : null}
          <AppPagination currentPage={page} totalPages={totalPages} onPageChange={setPage} />
        </div>
      ) : null}
      <div className="table-wrapper premium-table-wrap">
        <table
          id={tableId}
          className={cn('app-data-table data-table trend-table premium-table table-sticky-safe', tableClassName)}
          data-sticky-has-sno={hasStickySno ? 'true' : 'false'}
        >
          <colgroup data-dt-colgroup="1">
            {columns.map((column) => {
              const sticky = stickyMeta.get(column.key);
              return (
                <col
                  key={column.key}
                  data-col={column.dataCol}
                  data-sticky-role={sticky?.role}
                  style={sticky ? { inlineSize: `${sticky.widthPx}px`, minWidth: `${sticky.widthPx}px` } : undefined}
                />
              );
            })}
          </colgroup>
          <thead>
            <tr>
              {columns.map((column) => {
                const sortState = sort.key === column.key && sort.direction ? sort.direction : 'none';
                const sticky = stickyMeta.get(column.key);
                return (
                  <th
                    key={column.key}
                    data-col={column.dataCol}
                    data-sort-state={sortState}
                    data-sticky-col={sticky ? 'left' : undefined}
                    data-sticky-role={sticky?.role}
                    className={cn(
                      sortState !== 'none' ? 'is-sorted' : undefined,
                      sticky ? 'sticky-header-cell' : undefined,
                      sticky?.role === 'sno' ? 'sticky-sno' : undefined,
                      sticky?.role === 'symbol' ? 'sticky-symbol' : undefined,
                    )}
                    onClick={column.sortable === false ? undefined : () => setSort(getNextSortState(sort, column.key, column.sortType))}
                    style={sticky ? { left: `${sticky.leftPx}px` } : undefined}
                    scope="col"
                  >
                    {column.label}
                    {column.showArrow ? <span className="arrow"> ^</span> : null}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {pageRows.length ? pageRows.map((row, index) => (
              <tr key={getRowKey(row, index)}>
                {columns.map((column) => {
                  const sticky = stickyMeta.get(column.key);
                  const resolvedCellClassName = typeof column.cellClassName === 'function'
                    ? column.cellClassName(row)
                    : column.cellClassName;
                  return (
                    <td
                      key={column.key}
                      data-col={column.dataCol}
                      data-sticky-col={sticky ? 'left' : undefined}
                      data-sticky-role={sticky?.role}
                      className={cn(
                        resolvedCellClassName,
                        sticky ? 'sticky-cell' : undefined,
                        sticky?.role === 'sno' ? 'sticky-sno' : undefined,
                        sticky?.role === 'symbol' ? 'sticky-symbol' : undefined,
                      )}
                      style={sticky ? { left: `${sticky.leftPx}px` } : undefined}
                    >
                      {column.renderCell(row)}
                    </td>
                  );
                })}
              </tr>
            )) : (
              <tr>
                <td colSpan={columns.length} className="empty">
                  {emptyMessage}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {shouldRenderPaginationRow ? (
        <div className="app-data-table__pagination-row app-data-table__pagination-row--bottom">
          {paginationSummary ? <span className="app-data-table__pagination-summary">{paginationSummary}</span> : null}
          <AppPagination currentPage={page} totalPages={totalPages} onPageChange={setPage} />
        </div>
      ) : null}
    </div>
  );
}

