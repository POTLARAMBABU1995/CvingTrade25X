import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';
import { CopyDiagnosticsButton } from '../CopyDiagnosticsButton';
import { ThemeToggle } from '../ThemeToggle';
import { BrandMark } from '../ui/BrandMark';
import { databaseNavItems } from '../../data/databaseNav';
import { fyersNavItems } from '../../data/fyersNav';
import { isSectorDropdownPageActive, sectorDropdownNavItems } from '../../data/sectorNav';
import { strategyNavItems } from '../../data/strategyNav';
import { technicalNavItems } from '../../data/technicalNav';
import { useAuth } from '../../context/AuthContext';
import { cn } from '../../lib/cn';
import { handleInternalNavigationClick } from '../../utils/internalNavigation';
import { PowerIcon } from '../ui/Icons';

export type CvingLegacyHeaderActiveSection =
  | 'dashboard'
  | 'tradesetup'
  | 'sector'
  | 'technicals'
  | 'database'
  | 'fyers'
  | 'portfolio'
  | 'phase1'
  | 'strategy'
  | 'none';

type CvingLegacyHeaderProps = {
  activeSection: CvingLegacyHeaderActiveSection;
  activeDatabasePage?: string;
  activeFyersPage?: string;
  activeSectorPage?: string;
  activeStrategyPage?: string;
  activeTechnicalPage?: string;
  className?: string;
};

type PrimaryNavItem = {
  href: string;
  key: Exclude<CvingLegacyHeaderActiveSection, 'none'>;
  label: string;
};

type DropdownSection = Extract<CvingLegacyHeaderActiveSection, 'tradesetup' | 'sector' | 'technicals' | 'database' | 'fyers' | 'strategy'>;

const primaryNavItems = [
  { href: '/app/dashboard', key: 'dashboard', label: 'Dashboard' },
  { href: '/app/tradesetup', key: 'tradesetup', label: 'Watchlist' },
  { href: '/app/sector/rotation', key: 'sector', label: 'Sector' },
  { href: '/app/technical/ema', key: 'technicals', label: 'Technicals' },
  { href: '/app/database/stock-history', key: 'database', label: 'Database' },
  { href: '/app/fyers/automation', key: 'fyers', label: 'FyersAPI' },
  { href: '/app/portfolio', key: 'portfolio', label: 'Portfolio' },
  { href: '/app/strategy', key: 'strategy', label: 'Strategy' },
  { href: '/app/phase-1', key: 'phase1', label: 'Phase 1' },
] satisfies ReadonlyArray<PrimaryNavItem>;

const sectorHierarchyDropdownItem = {
  href: '/app/sector/stocks/healthcare?tab=hierarchy',
  label: 'Sector Hierarchy',
  page: '/app/sector/stocks/hierarchy',
} as const;

function normalizePage(page?: string): string | undefined {
  return page?.trim().replace(/^\//, '').toLowerCase();
}

export function CvingLegacyHeader({
  activeDatabasePage,
  activeFyersPage,
  activeSectorPage,
  activeSection,
  activeStrategyPage,
  activeTechnicalPage,
  className,
}: CvingLegacyHeaderProps) {
  const headerRef = useRef<HTMLElement | null>(null);
  const [openDropdown, setOpenDropdown] = useState<DropdownSection | null>(null);
  const normalizedDatabasePage = normalizePage(activeDatabasePage);
  const normalizedFyersPage = normalizePage(activeFyersPage);
  const normalizedSectorPage = normalizePage(
    typeof window !== 'undefined' ? window.location.pathname : activeSectorPage,
  );
  const normalizedStrategyPage = normalizePage(activeStrategyPage);
  const normalizedTechnicalPage = normalizePage(activeTechnicalPage);
  const isSectorHierarchyTabActive = (() => {
    if (typeof window === 'undefined') return false;
    try {
      const pathname = window.location.pathname.toLowerCase();
      if (!pathname.startsWith('/app/sector/stocks/')) return false;
      const params = new URLSearchParams(window.location.search || '');
      return String(params.get('tab') || '').trim().toLowerCase() === 'hierarchy';
    } catch {
      return false;
    }
  })();
  const [loggingOut, setLoggingOut] = useState(false);
  const { isAuthenticated, isLoading, logout } = useAuth();

  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && headerRef.current?.contains(target)) {
        return;
      }
      setOpenDropdown(null);
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpenDropdown(null);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  const loginHref = useMemo(() => {
    if (typeof window === 'undefined') return '/login';
    const target = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    return `/login?redirect=${encodeURIComponent(target)}`;
  }, []);

  async function handleLogout() {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      await logout();
    } catch {
      // Preserve previous behavior: local session clear still logs the user out on UI.
    } finally {
      window.location.assign('/login');
    }
  }

  function handleInternalLinkClick(event: MouseEvent<HTMLAnchorElement>, href: string) {
    if (handleInternalNavigationClick(event, href)) {
      setOpenDropdown(null);
    }
  }

  return (
    <header ref={headerRef} className={cn('main-header cving-legacy-header', className)}>
      <div className="container cving-legacy-header__container">
        <div className="cving-legacy-header__left">
          <div className="logo cving-legacy-header__logo">
            <a className="brand cving-legacy-brand" href="/app/home" onClick={(event) => handleInternalLinkClick(event, '/app/home')}>
              <BrandMark size="sm" />
            </a>
          </div>
        </div>

        <div className="cving-legacy-header__middle">
          <nav className="main-nav cving-legacy-nav" id="mainNav" aria-label="Primary" data-active-section={activeSection}>
            <ul className="cving-legacy-nav__list">
              {primaryNavItems.map((item) => {
                const isActive = activeSection === item.key;
                const isDatabase = item.key === 'database';
                const isFyers = item.key === 'fyers';
                const isSector = item.key === 'sector';
                const isStrategy = item.key === 'strategy';
                const isTechnicals = item.key === 'technicals';
                const isTradeSetup = item.key === 'tradesetup';
                const isDropdown = isTradeSetup || isSector || isTechnicals || isDatabase || isFyers || isStrategy;
                const dropdownSection = isDropdown ? (item.key as DropdownSection) : null;
                const isDropdownOpen = dropdownSection !== null && openDropdown === dropdownSection;
                const dropdownId = dropdownSection ? `cving-dropdown-${dropdownSection}` : undefined;

                return (
                  <li
                    key={item.key}
                    className={cn(
                      'cving-legacy-nav__item',
                      isDropdown && 'dropdown cving-legacy-nav__item--dropdown',
                      isSector && 'dropdown--sector',
                      isTechnicals && 'dropdown--technicals',
                      isDatabase && 'dropdown--database',
                      isFyers && 'dropdown--fyers',
                      isStrategy && 'dropdown--strategy',
                      isTradeSetup && 'dropdown--strategy',
                      isDropdownOpen && 'cving-legacy-nav__item--open',
                    )}
                    onBlur={
                      dropdownSection
                        ? (event) => {
                            const nextTarget = event.relatedTarget;
                            if (nextTarget instanceof Node && event.currentTarget.contains(nextTarget)) {
                              return;
                            }
                            setOpenDropdown((current) => (current === dropdownSection ? null : current));
                          }
                        : undefined
                    }
                    onMouseEnter={dropdownSection ? () => setOpenDropdown(dropdownSection) : undefined}
                    onMouseLeave={
                      dropdownSection
                        ? () => setOpenDropdown((current) => (current === dropdownSection ? null : current))
                        : undefined
                    }
                  >
                    {isDropdown && dropdownSection ? (
                      <button
                        type="button"
                        className={cn('cving-legacy-nav__link', isActive && 'active cving-legacy-nav__link--active')}
                        data-active={isActive ? 'true' : undefined}
                        data-section={item.key}
                        aria-controls={dropdownId}
                        aria-expanded={isDropdownOpen ? 'true' : 'false'}
                        aria-haspopup="menu"
                        onClick={() => setOpenDropdown((current) => (current === dropdownSection ? null : dropdownSection))}
                      >
                        {item.label}
                      </button>
                    ) : (
                      <a
                        className={cn('cving-legacy-nav__link', isActive && 'active cving-legacy-nav__link--active')}
                        data-active={isActive ? 'true' : undefined}
                        data-section={item.key}
                        href={item.href}
                        onClick={(event) => handleInternalLinkClick(event, item.href)}
                      >
                        {item.label}
                      </a>
                    )}

                    {isTechnicals ? (
                      <div id={dropdownId} className="cving-technical-dropdown" role="menu" aria-label="Technicals">
                        {technicalNavItems.map((technicalItem) => {
                          const isTechnicalActive = normalizedTechnicalPage === normalizePage(technicalItem.page);

                          return (
                            <a
                              key={technicalItem.page}
                              className={cn(
                                'cving-technical-dropdown__link',
                                isTechnicalActive && 'cving-technical-dropdown__link--active',
                              )}
                              data-active={isTechnicalActive ? 'true' : undefined}
                              data-technical-page={technicalItem.page}
                              href={technicalItem.href}
                              role="menuitem"
                              aria-current={isTechnicalActive ? 'page' : undefined}
                              onClick={(event) => handleInternalLinkClick(event, technicalItem.href)}
                            >
                              {technicalItem.label}
                            </a>
                          );
                        })}
                      </div>
                    ) : null}

                    {isTradeSetup ? (
                      <div id={dropdownId} className="cving-strategy-dropdown" role="menu" aria-label="Watchlist">
                        <a
                          className={cn(
                            'cving-strategy-dropdown__link',
                            isActive && 'cving-strategy-dropdown__link--active',
                          )}
                          data-active={isActive ? 'true' : undefined}
                          data-tradesetup-page="/app/tradesetup"
                          href="/app/tradesetup"
                          role="menuitem"
                          aria-current={isActive ? 'page' : undefined}
                          onClick={(event) => handleInternalLinkClick(event, '/app/tradesetup')}
                        >
                          Trade SetUp
                        </a>
                      </div>
                    ) : null}

                    {isSector ? (
                      <div id={dropdownId} className="cving-sector-dropdown" role="menu" aria-label="Sector">
                        {[...sectorDropdownNavItems, sectorHierarchyDropdownItem].map((sectorItem) => {
                          const isHierarchyItem = sectorItem.page === sectorHierarchyDropdownItem.page;
                          const isSectorActive = isHierarchyItem
                            ? isSectorHierarchyTabActive
                            : isSectorDropdownPageActive(normalizedSectorPage, sectorItem.page);

                          return (
                            <a
                              key={sectorItem.page}
                              className={cn(
                                'cving-sector-dropdown__link',
                                isSectorActive && 'cving-sector-dropdown__link--active',
                              )}
                              data-active={isSectorActive ? 'true' : undefined}
                              data-sector-page={sectorItem.page}
                              href={sectorItem.href}
                              role="menuitem"
                              aria-current={isSectorActive ? 'page' : undefined}
                              onClick={(event) => handleInternalLinkClick(event, sectorItem.href)}
                            >
                              {sectorItem.label}
                            </a>
                          );
                        })}
                      </div>
                    ) : null}

                    {isDatabase ? (
                      <div id={dropdownId} className="cving-database-dropdown" role="menu" aria-label="Database">
                        {databaseNavItems.map((databaseItem) => {
                          const isDatabaseActive = normalizedDatabasePage === normalizePage(databaseItem.page);

                          return (
                            <a
                              key={databaseItem.page}
                              className={cn(
                                'cving-database-dropdown__link',
                                isDatabaseActive && 'cving-database-dropdown__link--active',
                              )}
                              data-active={isDatabaseActive ? 'true' : undefined}
                              data-database-page={databaseItem.page}
                              href={databaseItem.href}
                              role="menuitem"
                              aria-current={isDatabaseActive ? 'page' : undefined}
                              onClick={(event) => handleInternalLinkClick(event, databaseItem.href)}
                            >
                              {databaseItem.label}
                            </a>
                          );
                        })}
                      </div>
                    ) : null}

                    {isFyers ? (
                      <div id={dropdownId} className="cving-fyers-dropdown" role="menu" aria-label="FyersAPI">
                        {fyersNavItems.map((fyersItem) => {
                          const isFyersActive = normalizedFyersPage === normalizePage(fyersItem.page);

                          return (
                            <a
                              key={fyersItem.page}
                              className={cn(
                                'cving-fyers-dropdown__link',
                                isFyersActive && 'cving-fyers-dropdown__link--active',
                              )}
                              data-active={isFyersActive ? 'true' : undefined}
                              data-fyers-page={fyersItem.page}
                              href={fyersItem.href}
                              role="menuitem"
                              aria-current={isFyersActive ? 'page' : undefined}
                              onClick={(event) => handleInternalLinkClick(event, fyersItem.href)}
                            >
                              {fyersItem.label}
                            </a>
                          );
                        })}
                      </div>
                    ) : null}

                    {isStrategy ? (
                      <div id={dropdownId} className="cving-strategy-dropdown" role="menu" aria-label="Strategy">
                        {strategyNavItems.map((strategyItem) => {
                          const isStrategyActive = normalizedStrategyPage === normalizePage(strategyItem.page);

                          return (
                            <a
                              key={strategyItem.page}
                              className={cn(
                                'cving-strategy-dropdown__link',
                                isStrategyActive && 'cving-strategy-dropdown__link--active',
                              )}
                              data-active={isStrategyActive ? 'true' : undefined}
                              data-strategy-page={strategyItem.page}
                              href={strategyItem.href}
                              role="menuitem"
                              aria-current={isStrategyActive ? 'page' : undefined}
                              onClick={(event) => handleInternalLinkClick(event, strategyItem.href)}
                            >
                              {strategyItem.label}
                            </a>
                          );
                        })}
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </nav>
        </div>

        <div className="cving-legacy-header__right">
          <CopyDiagnosticsButton compact />
          <ThemeToggle />
          {!isLoading ? (
            isAuthenticated ? (
              <button
                type="button"
                className={cn(
                  'cving-header-action cving-header-action--icon cving-header-action--logout',
                  loggingOut && 'is-loading',
                )}
                disabled={loggingOut}
                onClick={() => void handleLogout()}
                aria-label={loggingOut ? 'Logging out' : 'Logout'}
                aria-busy={loggingOut ? 'true' : undefined}
                title={loggingOut ? 'Logging out' : 'Logout'}
              >
                <PowerIcon className="h-4 w-4" />
                <span className="sr-only">{loggingOut ? 'Logging out' : 'Logout'}</span>
                <span className="cving-header-action__hint">{loggingOut ? 'Wait' : 'Logout'}</span>
              </button>
            ) : (
              <a className="cving-header-action cving-header-action--auth" href={loginHref} onClick={(event) => handleInternalLinkClick(event, loginHref)}>
                Login
              </a>
            )
          ) : (
            <span className="cving-header-action cving-header-action--auth">Auth...</span>
          )}
        </div>
      </div>
    </header>
  );
}
