import { cn } from '../../../lib/cn';
import { handleInternalNavigationClick } from '../../../utils/internalNavigation';

const NAV_ITEMS = [
  { label: 'Dashboard', href: '/fundamental' },
  { label: 'Company 360', href: '/fundamental/company-360' },
  { label: 'Financials', href: '/fundamental/financials' },
  { label: 'Growth', href: '/fundamental/growth' },
  { label: 'Peers', href: '/fundamental/peers' },
  { label: 'Governance', href: '/fundamental/governance' },
  { label: 'Valuation', href: '/fundamental/valuation' },
  { label: 'Risk', href: '/fundamental/risk-matrix' },
  { label: 'Reports', href: '/fundamental/reports' },
  { label: 'Auto Ingestion', href: '/fundamental/auto-ingestion' },
  { label: 'Admin', href: '/fundamental/reports#admin' },
];

type FundamentalNavbarProps = {
  currentPath: string;
};

export function FundamentalNavbar({ currentPath }: FundamentalNavbarProps) {
  return (
    <nav className="flex min-w-0 items-center gap-2 overflow-x-auto rounded-full border border-slate-200/70 bg-white/80 p-1 shadow-sm backdrop-blur-xl">
      {NAV_ITEMS.map((item) => {
        const active = item.href === '/fundamental'
          ? currentPath === item.href
          : currentPath.startsWith(item.href);
        return (
          <a
            key={item.label}
            href={item.href}
            onClick={(event) => handleInternalNavigationClick(event, item.href)}
            className={cn(
              'whitespace-nowrap rounded-full px-4 py-2 text-sm font-semibold transition',
              active
                ? 'bg-gradient-to-r from-[rgb(var(--page-accent-rgb))] to-[rgb(var(--page-accent-rgb-2))] text-white shadow-sm'
                : 'text-slate-600 hover:bg-[rgb(var(--page-accent-rgb)/0.08)] hover:text-slate-950',
            )}
          >
            {item.label}
          </a>
        );
      })}
    </nav>
  );
}
