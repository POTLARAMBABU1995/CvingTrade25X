import { cn } from '../../../lib/cn';
import { FundamentalAlertIcon, FundamentalChartIcon, FundamentalScaleIcon, FundamentalShieldIcon, FundamentalWalletIcon } from '../fundamentalIcons';

const SIDEBAR_ITEMS = [
  { label: 'Strengths', value: '7 strong', accent: 'bg-emerald-50 text-emerald-700 ring-emerald-100', icon: FundamentalChartIcon },
  { label: 'Watch Areas', value: '2 watch', accent: 'bg-amber-50 text-amber-700 ring-amber-100', icon: FundamentalAlertIcon },
  { label: 'Cash Flow', value: 'Excellent', accent: 'bg-cyan-50 text-cyan-700 ring-cyan-100', icon: FundamentalWalletIcon },
  { label: 'Governance', value: 'Clean', accent: 'bg-indigo-50 text-indigo-700 ring-indigo-100', icon: FundamentalShieldIcon },
  { label: 'Valuation', value: 'Fair', accent: 'bg-fuchsia-50 text-fuchsia-700 ring-fuchsia-100', icon: FundamentalScaleIcon },
];

export function FundamentalSidebar() {
  return (
    <aside className="hidden w-[280px] shrink-0 xl:block">
      <div className="sticky top-[150px] flex flex-col gap-4">
        <div className="rounded-[28px] border border-slate-200 bg-gradient-to-br from-white via-indigo-50 to-cyan-50 p-5 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Snapshot</p>
          <h2 className="mt-2 text-xl font-bold tracking-[-0.03em] text-slate-950">Decision support, not noise.</h2>
          <p className="mt-3 text-sm leading-6 text-slate-500">
            Cards are grouped by business strength, valuation comfort, and visible risk.
          </p>
        </div>

        <div className="rounded-[28px] border border-slate-200 bg-white p-3 shadow-sm">
          {SIDEBAR_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.label} className="flex items-center gap-3 rounded-[22px] px-3 py-3">
                <span
                  className={cn(
                    'flex h-10 w-10 items-center justify-center rounded-2xl ring-1',
                    item.accent,
                  )}
                >
                  <Icon className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-slate-900">{item.label}</span>
                  <span className="block text-xs font-medium text-slate-500">{item.value}</span>
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
