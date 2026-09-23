import type { ReactNode } from 'react';
import { CvingLegacyHeader } from '@/components/navigation/CvingLegacyHeader';
import { cn } from '../../lib/cn';
import { useProtectedPageAuth, useTechnicalThemeMode } from '../technical/technicalPageGuards';

type OpsPageShellProps = {
  activeDatabasePage: string;
  children: ReactNode;
  className?: string;
};

export function OpsPageShell({ activeDatabasePage, children, className = '' }: OpsPageShellProps) {
  const authorized = useProtectedPageAuth();
  const themeMode = useTechnicalThemeMode();
  const isDarkMode = themeMode === 'dark';

  return (
    <div className={cn(
      'page-theme--database ema-page database-react-page',
      isDarkMode && 'ema-page--dark database-react-page--dark',
      className,
    )}>
      <CvingLegacyHeader activeSection="database" activeDatabasePage={activeDatabasePage} />
      <main className="container database-react-page__main">
        {authorized ? children : (
          <section className="card">
            <div className="empty">Checking secure session...</div>
          </section>
        )}
      </main>
      <section className={isDarkMode ? 'disclaimer disclaimer--dark' : 'disclaimer disclaimer--light'}>
        <p>Investments in securities market are subject to market risk, read all the related documents carefully before investing.</p>
        <p>We collect, retain, and use your contact information for legitimate business purposes only, to contact you and provide product and service updates.</p>
        <p>We do not sell or rent your contact information to third parties.</p>
        <p>Please note that by submitting details, you authorize us to call or SMS you even if you are registered under DND for a period of 12 months.</p>
        <p>Copyright@2026-CvingTrade25X - All rights reserved.</p>
      </section>
    </div>
  );
}
