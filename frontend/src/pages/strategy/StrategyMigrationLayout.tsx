import type { ReactNode } from 'react';
import { CvingLegacyHeader } from '@/components/navigation/CvingLegacyHeader';
import { strategyNavItems } from '../../data/strategyNav';
import { cn } from '../../lib/cn';
import { handleInternalNavigationClick } from '../../utils/internalNavigation';
import { useTechnicalThemeMode } from '../technical/technicalPageGuards';

type StrategyMigrationLayoutProps = {
  activeStrategyPage: string;
  children: ReactNode;
  fullWidth?: boolean;
};

export function StrategyMigrationLayout({ activeStrategyPage, children, fullWidth = false }: StrategyMigrationLayoutProps) {
  const themeMode = useTechnicalThemeMode();
  return (
    <div className={cn(
      'page-theme--strategy legacy-react-shell strategy-react-shell min-h-screen bg-[linear-gradient(180deg,#f8fbff_0%,#eef4fb_100%)] text-slate-950 dark:bg-slate-950 dark:text-slate-100',
      themeMode === 'dark' && 'dashboard-react-page--dark',
    )}>
      <CvingLegacyHeader activeSection="strategy" activeStrategyPage={activeStrategyPage} />

      <div className="border-b border-slate-200/80 bg-white/82 backdrop-blur-xl dark:border-slate-700/80 dark:bg-slate-950/82">
        <div className="mx-auto flex w-full max-w-[1880px] flex-wrap items-center justify-between gap-3 px-4 py-3 lg:px-8">
          <nav className="flex flex-wrap gap-2" aria-label="Strategy migrated pages">
            {strategyNavItems.map((item) => (
              <a
                key={item.page}
                href={item.href}
                onClick={(event) => handleInternalNavigationClick(event, item.href)}
                className={cn(
                  'rounded-full px-4 py-2 text-sm font-semibold transition',
                  activeStrategyPage === item.page
                    ? 'bg-gradient-to-r from-[rgb(var(--page-accent-rgb))] to-[rgb(var(--page-accent-rgb-2))] text-white shadow-lg shadow-[rgba(244,63,94,0.14)] dark:shadow-[rgba(244,63,94,0.26)]'
                    : 'border border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:text-slate-950 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-200 dark:hover:border-slate-500 dark:hover:text-slate-100',
                )}
              >
                {item.label}
              </a>
            ))}
          </nav>
        </div>
      </div>

      <main className={cn('mx-auto w-full px-4 py-6 lg:px-8', fullWidth ? 'max-w-[1880px]' : 'max-w-[1680px]')}>
        {children}
      </main>

      <footer className="border-t border-slate-200 bg-white/80 dark:border-slate-700 dark:bg-slate-950/90">
        <div className="mx-auto flex w-full max-w-[1880px] flex-col gap-3 px-4 py-6 text-sm leading-6 text-slate-500 dark:text-slate-400 lg:px-8">
          <p>Investments in securities market are subject to market risk, read all the related documents carefully before investing.</p>
          <p>We collect, retain, and use your contact information for legitimate business purposes only, to contact you and provide product and service updates.</p>
          <p>We do not sell or rent your contact information to third parties.</p>
          <p>Please note that by submitting details, you authorize us to call or SMS you even if you are registered under DND for a period of 12 months.</p>
          <p>Copyright@2026-CvingTrade25X - All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
