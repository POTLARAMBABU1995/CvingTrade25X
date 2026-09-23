import { useMemo, useState } from 'react';
import { cn } from '../../../lib/cn';
import { PEER_ROWS } from '../../../services/fundamental/fundamentalApi';
import type { FundamentalPeerRow } from '../../../services/fundamental/fundamentalTypes';

type SortKey = keyof Pick<FundamentalPeerRow, 'name' | 'pe' | 'marketCap' | 'qtrProfitVar' | 'qtrSalesVar' | 'roce'>;

const columns: Array<{ key: SortKey | 'rank' | 'cmp' | 'dividendYield' | 'netProfitQtr' | 'salesQtr'; label: string; sortable?: boolean }> = [
  { key: 'rank', label: 'S.No' },
  { key: 'name', label: 'Name', sortable: true },
  { key: 'cmp', label: 'CMP' },
  { key: 'pe', label: 'P/E', sortable: true },
  { key: 'marketCap', label: 'Market Cap', sortable: true },
  { key: 'dividendYield', label: 'Div Yld' },
  { key: 'netProfitQtr', label: 'Net Profit Qtr' },
  { key: 'qtrProfitVar', label: 'Qtr Profit Var %', sortable: true },
  { key: 'salesQtr', label: 'Sales Qtr' },
  { key: 'qtrSalesVar', label: 'Qtr Sales Var %', sortable: true },
  { key: 'roce', label: 'ROCE %', sortable: true },
];

function numericValue(value: string | number): number {
  if (typeof value === 'number') return value;
  const cleaned = value.replace(/[%,-]/g, '');
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function PeerComparisonTable() {
  const [sortKey, setSortKey] = useState<SortKey>('marketCap');

  const rows = useMemo(() => {
    const medianRows = PEER_ROWS.filter((row) => row.median);
    const companyRows = PEER_ROWS.filter((row) => !row.median).sort((a, b) => {
      if (sortKey === 'name') return a.name.localeCompare(b.name);
      return numericValue(b[sortKey]) - numericValue(a[sortKey]);
    });
    return [...companyRows, ...medianRows];
  }, [sortKey]);

  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 px-2 pb-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Sector breadcrumb</p>
          <h2 className="mt-1 text-xl font-bold tracking-[-0.03em] text-slate-950">Refineries & Marketing Peers</h2>
        </div>
        <button className="rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-white">
          Edit columns
        </button>
      </div>

      <div className="overflow-x-auto rounded-[22px] border border-slate-200">
        <table className="min-w-[1180px] w-full border-separate border-spacing-0 text-sm">
          <thead>
            <tr className="bg-slate-50 text-xs uppercase tracking-[0.14em] text-slate-500">
              {columns.map((column) => (
                <th key={column.key} className="border-b border-slate-200 px-4 py-4 text-right font-bold first:text-left">
                  {column.sortable ? (
                    <button
                      type="button"
                      onClick={() => setSortKey(column.key as SortKey)}
                      className={cn('font-bold transition hover:text-slate-950', sortKey === column.key && 'text-slate-950')}
                    >
                      {column.label}
                    </button>
                  ) : (
                    column.label
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={`${row.rank}-${row.name}`}
                className={cn(
                  'transition',
                  row.selected && 'bg-emerald-50/80',
                  row.median && 'bg-[rgb(var(--page-accent-rgb)/0.10)] text-text',
                  !row.selected && !row.median && 'odd:bg-white even:bg-slate-50/55',
                )}
              >
                <td className="border-b border-slate-100 px-4 py-4 text-left font-bold">{row.rank}</td>
                <td className="border-b border-slate-100 px-4 py-4 text-left font-bold">
                  {row.name}
                  {row.selected ? <span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-emerald-700">selected</span> : null}
                </td>
                <td className="border-b border-slate-100 px-4 py-4 text-right tabular-nums">{row.cmp}</td>
                <td className="border-b border-slate-100 px-4 py-4 text-right tabular-nums">{row.pe}</td>
                <td className="border-b border-slate-100 px-4 py-4 text-right tabular-nums">{row.marketCap}</td>
                <td className="border-b border-slate-100 px-4 py-4 text-right tabular-nums">{row.dividendYield}</td>
                <td className="border-b border-slate-100 px-4 py-4 text-right tabular-nums">{row.netProfitQtr}</td>
                <td className="border-b border-slate-100 px-4 py-4 text-right tabular-nums text-emerald-600">{row.qtrProfitVar}</td>
                <td className="border-b border-slate-100 px-4 py-4 text-right tabular-nums">{row.salesQtr}</td>
                <td className="border-b border-slate-100 px-4 py-4 text-right tabular-nums text-emerald-600">{row.qtrSalesVar}</td>
                <td className="border-b border-slate-100 px-4 py-4 text-right tabular-nums font-bold">{row.roce}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
