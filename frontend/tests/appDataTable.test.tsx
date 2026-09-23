import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { AppDataTable, getNextSortState, sortRowsForTable } from '../src/components/app/AppDataTable';
import { buildPaginationPages } from '../src/components/app/AppPagination';

type TestRow = {
  id: string;
  symbol: string;
  value: number | null;
};

const columns = [
  {
    dataCol: 'symbol',
    getSortValue: (row: TestRow) => row.symbol,
    key: 'symbol',
    label: 'SYMBOL',
    renderCell: (row: TestRow) => row.symbol,
    sortType: 'string' as const,
  },
  {
    dataCol: 'value',
    getSortValue: (row: TestRow) => row.value,
    key: 'value',
    label: 'VALUE',
    renderCell: (row: TestRow) => row.value ?? '-',
    sortType: 'number' as const,
  },
];

describe('AppDataTable primitives', () => {
  test('builds EMA-style numbered pagination with ellipses', () => {
    expect(buildPaginationPages(6, 20)).toEqual([1, 'ellipsis', 4, 5, 6, 7, 8, 'ellipsis', 20]);
  });

  test('cycles sort state using legacy default directions', () => {
    const first = getNextSortState({ key: null, direction: null }, 'value', 'number');
    const second = getNextSortState(first, 'value', 'number');
    const third = getNextSortState(second, 'value', 'number');

    expect(first).toEqual({ key: 'value', direction: 'desc' });
    expect(second).toEqual({ key: 'value', direction: 'asc' });
    expect(third).toEqual({ key: null, direction: null });

    expect(getNextSortState({ key: null, direction: null }, 'symbol', 'string')).toEqual({
      key: 'symbol',
      direction: 'asc',
    });
  });

  test('preserves legacy null ordering for numeric desc sort', () => {
    const rows: TestRow[] = [
      { id: 'a', symbol: 'AAA', value: 10 },
      { id: 'b', symbol: 'BBB', value: null },
      { id: 'c', symbol: 'CCC', value: 5 },
    ];

    const sorted = sortRowsForTable(rows, columns, { key: 'value', direction: 'desc' });
    expect(sorted.map((row) => row.id)).toEqual(['b', 'a', 'c']);
  });

  test('renders first 15 rows, data-col attributes, sticky column keys, and pagination', () => {
    const rows = Array.from({ length: 16 }, (_, index) => ({
      id: String(index + 1),
      symbol: `ROW${index + 1}`,
      value: index + 1,
    }));

    const markup = renderToStaticMarkup(
      <AppDataTable
        columns={columns}
        getRowKey={(row) => row.id}
        pageSize={15}
        rows={rows}
        showTopPagination
        tableClassName="data-table--green"
        tableId="test-table"
      />,
    );

    expect(markup).toContain('data-col="symbol"');
    expect(markup).toContain('data-col="value"');
    expect(markup).toContain('ROW15');
    expect(markup).not.toContain('ROW16');
    expect(markup).toContain('page-number--active');
    expect(markup).toContain('Next');
  });

  test('renders controlled server-pagination rows without client slicing', () => {
    const rows = Array.from({ length: 15 }, (_, index) => ({
      id: String(index + 31),
      symbol: `ROW${index + 31}`,
      value: index + 31,
    }));

    const markup = renderToStaticMarkup(
      <AppDataTable
        columns={columns}
        currentPage={3}
        disableClientSort
        getRowKey={(row) => row.id}
        onPageChange={() => undefined}
        pageSize={15}
        paginationSummaryLabel="stocks"
        rows={rows}
        showTopPagination
        tableId="controlled-table"
        totalRows={45}
      />,
    );

    expect(markup).toContain('ROW31');
    expect(markup).toContain('ROW45');
    expect(markup).toContain('Showing 31-45 of 45 stocks');
    expect(markup).toContain('page-number--active');
  });

  test('keeps controlled page active while server-paginated rows are loading', () => {
    const markup = renderToStaticMarkup(
      <AppDataTable
        columns={columns}
        currentPage={3}
        disableClientSort
        emptyMessage="Loading strategy rows..."
        getRowKey={(row) => row.id}
        onPageChange={() => undefined}
        pageSize={15}
        paginationSummaryLabel="stocks"
        rows={[]}
        showTopPagination
        tableId="controlled-loading-table"
        totalRows={45}
      />,
    );

    expect(markup).toContain('Loading strategy rows...');
    expect(markup).toContain('Showing 31-31 of 45 stocks');
    expect(markup).toContain('aria-current="page"');
    expect(markup).toContain('>3</button>');
  });
});
