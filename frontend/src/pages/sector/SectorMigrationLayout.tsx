import type { ReactNode } from 'react';
import { CvingLegacyHeader } from '@/components/navigation/CvingLegacyHeader';
import { cn } from '../../lib/cn';
import { useProtectedPageAuth, useTechnicalThemeMode } from '../technical/technicalPageGuards';

type SectorMigrationLayoutProps = {
  activeSectorPage: string;
  children: ReactNode;
  className?: string;
};

export function SectorMigrationLayout({ activeSectorPage, children, className }: SectorMigrationLayoutProps) {
  const authorized = useProtectedPageAuth();
  const themeMode = useTechnicalThemeMode();

  return (
    <div className={cn('page-theme--sector ema-page sector-react-page', themeMode === 'dark' && 'ema-page--dark', className)}>
      <CvingLegacyHeader activeSection="sector" activeSectorPage={activeSectorPage} />
      <main className="container sector-react-page__main">
        {authorized ? children : (
          <section className="card">
            <div className="empty">Checking secure session...</div>
          </section>
        )}
      </main>
      <section className="disclaimer disclaimer--light">
        <p>Investments in securities market are subject to market risk, read all the related documents carefully before investing.</p>
        <p>Copyright@2026-CvingTrade25X - All rights reserved.</p>
      </section>
    </div>
  );
}
