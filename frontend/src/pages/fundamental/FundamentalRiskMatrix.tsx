import { FundamentalCardGrid } from '../../components/fundamental/cards/FundamentalCardGrid';
import { getMockFundamentalSummary } from '../../services/fundamental/fundamentalApi';
import { FundamentalModulePage } from './FundamentalModulePage';

const riskRows = [
  { severity: 'Low', reason: 'No promoter pledge detected', evidence: 'Pledge 0%', mitigation: 'Continue quarterly pledge monitoring', status: 'Controlled' },
  { severity: 'Watch', reason: 'Valuation is not cheap', evidence: 'P/E near sector quality premium', mitigation: 'Prefer staged entry and margin-of-safety checks', status: 'Watch' },
  { severity: 'Low', reason: 'Debt metrics remain inside safe band', evidence: 'Debt/Equity 0.27, Interest Coverage 6.2x', mitigation: 'Track debt trend and coverage', status: 'Controlled' },
];

export function FundamentalRiskMatrix() {
  const summary = getMockFundamentalSummary('RELIANCE');
  const riskCards = summary.cards.filter((card) => card.section === 'risk');

  return (
    <FundamentalModulePage title="Risk Matrix" description="Severity, reason, evidence, mitigation, and current status for fundamental risk factors.">
      <FundamentalCardGrid cards={riskCards} />
      <section className="rounded-[28px] border border-slate-200 bg-white p-4 shadow-sm">
        <div className="overflow-x-auto rounded-[22px] border border-slate-200">
          <table className="min-w-[840px] w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-[0.16em] text-slate-500">
              <tr>
                <th className="px-4 py-4">Severity</th>
                <th className="px-4 py-4">Reason</th>
                <th className="px-4 py-4">Evidence</th>
                <th className="px-4 py-4">Mitigation</th>
                <th className="px-4 py-4">Status</th>
              </tr>
            </thead>
            <tbody>
              {riskRows.map((row) => (
                <tr key={row.reason} className="border-t border-slate-100">
                  <td className="px-4 py-4 font-bold text-slate-950">{row.severity}</td>
                  <td className="px-4 py-4 text-slate-700">{row.reason}</td>
                  <td className="px-4 py-4 text-slate-700">{row.evidence}</td>
                  <td className="px-4 py-4 text-slate-700">{row.mitigation}</td>
                  <td className="px-4 py-4">
                    <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700">{row.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </FundamentalModulePage>
  );
}
