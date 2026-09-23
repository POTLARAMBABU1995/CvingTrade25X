import { useMemo } from 'react';
import { formatSectorIndex, formatSectorMcap, formatSectorMcapRank } from '../../adapters/sectorPageAdapter';
import type { SectorHierarchyStock } from '../../types/sectorHierarchy';
import { AppDataTable, type AppDataTableColumn } from '../app/AppDataTable';

type SectorHierarchyStocksTableProps = {
  rows: SectorHierarchyStock[];
  search: string;
};

type TableRow = {
  index: string;
  industrySector: string;
  mcap: number | null;
  mcapRank: number | null;
  parentSector: string;
  serial: number;
  subSector: string;
  symbol: string;
};

type RawTableRow = {
  index: string;
  industrySector: string;
  mcap: number | null;
  mcapRank: number | null;
  parentSector: string;
  subSector: string;
  symbol: string;
};

function getIndexCategoryClass(indexValue: unknown): string {
  const value = String(indexValue ?? '').trim().toUpperCase();
  if (value === 'LARGE') return 'sector-index-pill sector-index-pill--large';
  if (value === 'MID') return 'sector-index-pill sector-index-pill--mid';
  if (value === 'SMALL') return 'sector-index-pill sector-index-pill--small';
  return 'sector-index-pill sector-index-pill--unknown';
}

export function SectorHierarchyStocksTable({ rows, search }: SectorHierarchyStocksTableProps) {
  const filteredRows = useMemo(() => {
    const token = String(search || '').trim().toUpperCase();
    if (!token) {
      return rows;
    }
    return rows.filter((row) => {
      const symbol = String(row.symbol || '').toUpperCase();
      const industry = String(row.industrySector || '').toUpperCase();
      const subSector = String(row.subSector || '').toUpperCase();
      const index = String((row as { index?: unknown }).index || '').toUpperCase();
      return symbol.includes(token) || industry.includes(token) || subSector.includes(token) || index.includes(token);
    });
  }, [rows, search]);

  const tableRows = useMemo<RawTableRow[]>(() => {
    return filteredRows.map((row) => ({
      parentSector: String(row.parentSector || '-'),
      industrySector: String(row.industrySector || '-'),
      subSector: String(row.subSector || '-'),
      symbol: String(row.symbol || '-'),
      index: formatSectorIndex((row as { index?: unknown }).index),
      mcap: typeof (row as { mcap?: unknown }).mcap === 'number' ? ((row as { mcap?: number }).mcap ?? null) : null,
      mcapRank: typeof (row as { mcapRank?: unknown }).mcapRank === 'number' ? ((row as { mcapRank?: number }).mcapRank ?? null) : null,
    }));
  }, [filteredRows]);

  const columns: Array<AppDataTableColumn<TableRow>> = [
    {
      dataCol: 'sno',
      getSortValue: (row) => row.symbol,
      key: 'sno',
      label: 'S.NO',
      renderCell: (row) => String(row.serial),
      sortType: 'string',
      sortable: false,
    },
    {
      dataCol: 'symbol',
      getSortValue: (row) => row.symbol,
      key: 'symbol',
      label: 'Symbol',
      renderCell: (row) => <span className={`sector-symbol-copy ${getIndexCategoryClass(row.index)}`}>{row.symbol}</span>,
      sortType: 'string',
    },
    {
      dataCol: 'index',
      getSortValue: (row) => row.index,
      key: 'index',
      label: 'INDEX',
      renderCell: (row) => <span className={getIndexCategoryClass(row.index)}>{row.index || '-'}</span>,
      sortType: 'string',
    },
    {
      dataCol: 'mcap',
      getSortValue: (row) => row.mcap ?? -1,
      key: 'mcap',
      label: 'MCAP',
      renderCell: (row) => <span className={getIndexCategoryClass(row.index)}>{formatSectorMcap(row.mcap)}</span>,
      sortType: 'number',
    },
    {
      dataCol: 'mcap_rank',
      getSortValue: (row) => row.mcapRank ?? Number.MAX_SAFE_INTEGER,
      key: 'mcapRank',
      label: 'MCAP_RANK',
      renderCell: (row) => <span className={getIndexCategoryClass(row.index)}>{formatSectorMcapRank(row.mcapRank)}</span>,
      sortType: 'number',
    },
    {
      dataCol: 'parent_sector',
      getSortValue: (row) => row.parentSector,
      key: 'parentSector',
      label: 'Parent Sector',
      renderCell: (row) => row.parentSector,
      sortType: 'string',
    },
    {
      dataCol: 'industry_sector',
      getSortValue: (row) => row.industrySector,
      key: 'industrySector',
      label: 'Industry / Sector',
      renderCell: (row) => row.industrySector,
      sortType: 'string',
    },
    {
      dataCol: 'sub_sector',
      getSortValue: (row) => row.subSector,
      key: 'subSector',
      label: 'Sub-Sector',
      renderCell: (row) => row.subSector,
      sortType: 'string',
    },
  ];

  const rowsWithSerial: TableRow[] = tableRows.map((row, index) => ({ ...row, serial: index + 1 }));

  return (
    <section className="sector-hierarchy-table-panel">
      <h3 className="sector-hierarchy-table-title">Hierarchy Stocks</h3>
      <AppDataTable
        className="sector-hierarchy-table sector-hierarchy-table--spaced"
        columns={columns}
        emptyMessage="No hierarchy stocks found for selected filters."
        getRowKey={(row) => `${row.parentSector}-${row.industrySector}-${row.subSector}-${row.symbol}-${row.serial}`}
        pageSize={25}
        rows={rowsWithSerial}
        showTopPagination
        tableClassName="sector-hierarchy-stocks-table"
        tableId="sector-hierarchy-stocks-table"
      />
    </section>
  );
}
