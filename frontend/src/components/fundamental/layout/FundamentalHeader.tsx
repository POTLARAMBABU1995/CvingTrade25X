import { FundamentalBuildingIcon, FundamentalShieldIcon } from '../fundamentalIcons';
import { FundamentalNavbar } from './FundamentalNavbar';
import { handleInternalNavigationClick } from '../../../utils/internalNavigation';

type FundamentalHeaderProps = {
  currentPath: string;
};

export function FundamentalHeader({ currentPath }: FundamentalHeaderProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/70 bg-white/82 backdrop-blur-2xl">
      <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-4 px-4 py-4 lg:px-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <a href="/fundamental" className="flex items-center gap-3 text-slate-950" onClick={(event) => handleInternalNavigationClick(event, '/fundamental')}>
            <span className="flex h-12 w-12 items-center justify-center rounded-[20px] bg-gradient-to-br from-[rgb(var(--page-accent-rgb))] to-[rgb(var(--page-accent-rgb-2))] text-white shadow-lg shadow-[rgba(59,130,246,0.18)]">
              <FundamentalBuildingIcon className="h-5 w-5" />
            </span>
            <span>
              <span className="block text-[11px] font-bold uppercase tracking-[0.28em] text-slate-500">CvingTrade25X</span>
              <span className="block text-lg font-bold tracking-[-0.02em]">Fundamental Analysis 360</span>
            </span>
          </a>

          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-800 md:flex">
              <FundamentalShieldIcon className="h-4 w-4" />
              Auth-aware shell
            </div>
            <a
              href="/login"
              className="rounded-full border border-slate-200 bg-white/90 px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-slate-950"
              onClick={(event) => handleInternalNavigationClick(event, '/login')}
            >
              Sign in
            </a>
          </div>
        </div>

        <FundamentalNavbar currentPath={currentPath} />
      </div>
    </header>
  );
}
