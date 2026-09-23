import type { ReactNode } from 'react';
import { CvingLegacyHeader } from '../../components/navigation/CvingLegacyHeader';
import { fyersNavItems } from '../../data/fyersNav';
import { cn } from '../../lib/cn';
import { handleInternalNavigationClick } from '../../utils/internalNavigation';
import { useProtectedPageAuth, useTechnicalThemeMode } from '../technical/technicalPageGuards';

type FyersMigrationLayoutProps = {
  activeFyersPage: string;
  children: ReactNode;
  className?: string;
};

export function FyersMigrationLayout({ activeFyersPage, children, className }: FyersMigrationLayoutProps) {
  const authorized = useProtectedPageAuth();
  const themeMode = useTechnicalThemeMode();
  const isDarkMode = themeMode === 'dark';

  return (
    <div
      className={cn(
        'page-theme--fyers ema-page fyers-react-page min-h-screen bg-[linear-gradient(180deg,#f4fbff_0%,#e8f1fb_52%,#f8fafc_100%)] text-slate-950',
        isDarkMode && 'ema-page--dark bg-[radial-gradient(circle_at_top,#0f2b3c_0%,#081018_38%,#030712_100%)] text-slate-100',
        className,
      )}
    >
      <CvingLegacyHeader activeSection="fyers" activeFyersPage={activeFyersPage} />

      <main className="container database-page fyers-react-page__main mx-auto w-full max-w-[1680px] px-4 py-6 lg:px-8">
        <nav className="fyers-react-subnav flex flex-wrap gap-2" aria-label="Fyers pages">
          {fyersNavItems.map((item) => (
            <a
              key={item.page}
              className={cn(
                'fyers-react-subnav__link rounded-full border border-slate-200 bg-white/88 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-sky-300 hover:text-slate-950 dark:border-slate-700 dark:bg-slate-900/78 dark:text-slate-200 dark:hover:border-sky-500 dark:hover:text-white',
                item.page === activeFyersPage && 'fyers-react-subnav__link--active border-transparent bg-gradient-to-r from-sky-600 to-cyan-500 text-white shadow-lg shadow-sky-500/20',
              )}
              href={item.href}
              aria-current={item.page === activeFyersPage ? 'page' : undefined}
              onClick={(event) => handleInternalNavigationClick(event, item.href)}
            >
              {item.label}
            </a>
          ))}
        </nav>
        {authorized ? children : (
          <section className="card rounded-[28px] border border-slate-200/80 bg-white/88 p-8 text-center shadow-[0_24px_60px_rgba(15,23,42,0.08)] dark:border-slate-800 dark:bg-slate-950/72">
            <div className="empty text-sm font-medium text-slate-500 dark:text-slate-300">Checking secure session...</div>
          </section>
        )}
      </main>
      <footer className="border-t border-slate-200/80 bg-white/78 dark:border-slate-800 dark:bg-slate-950/88">
        <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-3 px-4 py-6 text-sm leading-6 text-slate-500 dark:text-slate-400 lg:px-8">
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
