import type { ReactNode } from 'react';
import { FundamentalAuthShell } from './FundamentalAuthShell';
import { FundamentalFooter } from './FundamentalFooter';
import { FundamentalHeader } from './FundamentalHeader';
import { FundamentalSidebar } from './FundamentalSidebar';

type FundamentalLayoutProps = {
  children: ReactNode;
  currentPath: string;
  lastUpdated?: string;
};

export function FundamentalLayout({ children, currentPath, lastUpdated }: FundamentalLayoutProps) {
  const showSnapshotSidebar = currentPath === '/fundamental' || currentPath === '/fundamental/company-360';

  return (
    <FundamentalAuthShell>
      <div className="page-theme--fundamental fundamental-app min-h-screen bg-[radial-gradient(circle_at_10%_8%,rgba(56,189,248,0.14),transparent_28%),radial-gradient(circle_at_88%_12%,rgba(168,85,247,0.1),transparent_26%),radial-gradient(circle_at_50%_92%,rgba(245,158,11,0.1),transparent_30%),linear-gradient(180deg,#f8fafc_0%,#eef2f7_100%)] text-slate-950">
        <FundamentalHeader currentPath={currentPath} />
        <main className="mx-auto flex w-full max-w-[1680px] gap-6 px-4 py-6 lg:px-8">
          {showSnapshotSidebar ? <FundamentalSidebar /> : null}
          <div className="min-w-0 flex-1">{children}</div>
        </main>
        <FundamentalFooter lastUpdated={lastUpdated} />
      </div>
    </FundamentalAuthShell>
  );
}
