import { getMockFundamentalSummary } from '../../services/fundamental/fundamentalApi';
import { FundamentalModulePage } from './FundamentalModulePage';

export function FundamentalInvestmentThesis() {
  const summary = getMockFundamentalSummary('RELIANCE');

  return (
    <FundamentalModulePage title="Investment Thesis" description="A concise thesis surface that turns scorecard evidence into a readable research note.">
      <section className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-[28px] border border-emerald-200 bg-emerald-50 p-6">
          <h2 className="text-xl font-bold text-emerald-950">Why strong</h2>
          <p className="mt-3 text-sm leading-6 text-emerald-800">
            {summary.companyName} shows strong cash conversion, stable margin, clean governance, and peer-relative scale.
          </p>
        </div>
        <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-6">
          <h2 className="text-xl font-bold text-amber-950">What to watch</h2>
          <p className="mt-3 text-sm leading-6 text-amber-800">
            Valuation comfort is fair, not deeply attractive. Watch QoQ profit acceleration and margin stability.
          </p>
        </div>
        <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-xl font-bold text-slate-950">Decision label</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Good Fundamental. Prefer research watchlist inclusion with valuation discipline.
          </p>
        </div>
      </section>
    </FundamentalModulePage>
  );
}
