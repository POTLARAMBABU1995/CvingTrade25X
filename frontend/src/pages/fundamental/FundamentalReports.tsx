import { FundamentalModulePage } from './FundamentalModulePage';

const reportRows = [
  { name: 'Daily Fundamental Snapshot', status: 'Ready', updated: 'Dynamic after backend sync' },
  { name: 'Peer Comparison Export', status: 'Phase 1 UI', updated: 'Mock fallback data' },
  { name: 'Risk Matrix Audit', status: 'Phase 1 UI', updated: 'Mock fallback data' },
  { name: 'Investment Thesis PDF', status: 'Planned', updated: 'Phase 4' },
];

export function FundamentalReports() {
  return (
    <FundamentalModulePage title="Reports" description="Report generation placeholder for Phase 1 with clear future hooks for backend run logs and exports.">
      <section className="rounded-[28px] border border-slate-200 bg-white p-4 shadow-sm">
        <div className="overflow-hidden rounded-[22px] border border-slate-200">
          {reportRows.map((row) => (
            <div key={row.name} className="grid gap-3 border-b border-slate-100 px-4 py-4 last:border-b-0 md:grid-cols-[1fr_180px_240px]">
              <span className="font-bold text-slate-950">{row.name}</span>
              <span className="text-sm font-semibold text-slate-600">{row.status}</span>
              <span className="text-sm text-slate-500">{row.updated}</span>
            </div>
          ))}
        </div>
      </section>
    </FundamentalModulePage>
  );
}
