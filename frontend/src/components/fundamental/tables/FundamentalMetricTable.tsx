import { cn } from '../../../lib/cn';
import type { FundamentalMetricRow } from '../../../services/fundamental/fundamentalTypes';

type FundamentalMetricTableProps = {
  title: string;
  years: string[];
  rows: FundamentalMetricRow[];
  note?: string;
};

export function FundamentalMetricTable({ title, years, rows, note }: FundamentalMetricTableProps) {
  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 px-2 pb-4">
        <div>
          <h2 className="text-xl font-bold tracking-[-0.03em] text-slate-950">{title}</h2>
          {note ? <p className="mt-1 text-sm text-slate-500">{note}</p> : null}
        </div>
      </div>

      <div className="overflow-x-auto rounded-[22px] border border-slate-200">
        <table className="min-w-[860px] w-full border-separate border-spacing-0 text-left text-sm">
          <thead>
            <tr className="bg-slate-50 text-xs uppercase tracking-[0.16em] text-slate-500">
              <th className="sticky left-0 z-10 min-w-[220px] border-b border-slate-200 bg-slate-50 px-4 py-4 font-bold">Metric</th>
              {years.map((year) => (
                <th key={year} className="border-b border-slate-200 px-4 py-4 text-right font-bold">{year}</th>
              ))}
              <th className="border-b border-slate-200 px-4 py-4 text-right font-bold">YoY</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.metric} className={cn(index % 2 === 0 ? 'bg-white' : 'bg-slate-50/55', row.emphasis && 'font-bold text-slate-950')}>
                <td className={cn('sticky left-0 z-10 border-b border-slate-100 px-4 py-4 text-slate-800', index % 2 === 0 ? 'bg-white' : 'bg-slate-50')}>
                  {row.metric}
                </td>
                {years.map((year) => (
                  <td key={year} className="border-b border-slate-100 px-4 py-4 text-right tabular-nums text-slate-700">
                    {row.values[year] ?? '-'}
                  </td>
                ))}
                <td className="border-b border-slate-100 px-4 py-4 text-right">
                  <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700">improving</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
