export type PhaseOneCategory = 'Account' | 'Foundation' | 'Intelligence' | 'Operations';

export type PhaseOnePageId =
  | 'data-freshness'
  | 'data-quality'
  | 'historical-behaviour'
  | 'job-monitor'
  | 'main-dashboard'
  | 'nifty-50-overview'
  | 'opportunity-ranking'
  | 'sector-breadth'
  | 'sector-rotation'
  | 'security-master'
  | 'stock-360'
  | 'stock-search'
  | 'support-resistance'
  | 'system-settings'
  | 'technical-snapshot'
  | 'user-profile'
  | 'volume-delivery';

export type PhaseOneNavItem = {
  category: PhaseOneCategory;
  description: string;
  href: string;
  id: PhaseOnePageId;
  label: string;
  sourceSummary: string;
  symbolAware?: boolean;
  workflowHref?: string;
  workflowLabel?: string;
};

export const PHASE_ONE_ROOT = '/app/phase-1';

export const phaseOneCategoryOrder: ReadonlyArray<PhaseOneCategory> = [
  'Foundation',
  'Intelligence',
  'Operations',
  'Account',
];

export const phaseOneNavItems: ReadonlyArray<PhaseOneNavItem> = [
  {
    category: 'Foundation',
    description: 'A consolidated view of Phase 1 market coverage, data readiness and research entry points.',
    href: `${PHASE_ONE_ROOT}/dashboard`,
    id: 'main-dashboard',
    label: 'Main Dashboard',
    sourceSummary: 'Health, movers and database synchronization',
    workflowHref: '/app/dashboard',
    workflowLabel: 'Open existing dashboard',
  },
  {
    category: 'Foundation',
    description: 'NIFTY 50 market participation and leading price movers from the existing dashboard service.',
    href: `${PHASE_ONE_ROOT}/nifty-50`,
    id: 'nifty-50-overview',
    label: 'NIFTY 50 Overview',
    sourceSummary: 'Top movers and breadth observations',
    workflowHref: '/app/dashboard',
    workflowLabel: 'Open market dashboard',
  },
  {
    category: 'Foundation',
    description: 'Search the approved symbol universe without bypassing the current security-master services.',
    href: `${PHASE_ONE_ROOT}/stock-search`,
    id: 'stock-search',
    label: 'Stock Search',
    sourceSummary: 'Canonical chart and market-data symbol sources',
    symbolAware: true,
    workflowHref: '/app/strategy/stock-chart',
    workflowLabel: 'Open stock chart',
  },
  {
    category: 'Foundation',
    description: 'Inspect the canonical symbol inventory and current NIFTY reference coverage.',
    href: `${PHASE_ONE_ROOT}/security-master`,
    id: 'security-master',
    label: 'Security Master',
    sourceSummary: 'Oracle-backed symbol inventory and NIFTY reference data',
    workflowHref: '/app/fyers/nifty500-sync',
    workflowLabel: 'Open NIFTY500 sync',
  },
  {
    category: 'Intelligence',
    description: 'Sector state and contribution evidence sourced from the current snapshot-first sector APIs.',
    href: `${PHASE_ONE_ROOT}/sector-rotation`,
    id: 'sector-rotation',
    label: 'Sector Rotation',
    sourceSummary: 'Sector discovery and overview snapshots',
    workflowHref: '/app/sector/rotation',
    workflowLabel: 'Open detailed rotation',
  },
  {
    category: 'Intelligence',
    description: 'Participation, advancing and weakening sector evidence from the existing breadth engine.',
    href: `${PHASE_ONE_ROOT}/sector-breadth`,
    id: 'sector-breadth',
    label: 'Sector Breadth',
    sourceSummary: 'Published Sector Rotation V3 breadth',
    workflowHref: '/app/sector/stockedge-rotation',
    workflowLabel: 'Open breadth workflow',
  },
  {
    category: 'Intelligence',
    description: 'A ranked research surface using the explainable strong-technicals score already produced by the backend.',
    href: `${PHASE_ONE_ROOT}/opportunities`,
    id: 'opportunity-ranking',
    label: 'Opportunity Ranking',
    sourceSummary: 'Strong technicals with score breakdown evidence',
    workflowHref: '/app/technical/strong-technicals',
    workflowLabel: 'Open full screener',
  },
  {
    category: 'Intelligence',
    description: 'A single-symbol research summary combining price history, indicators, overlays and levels.',
    href: `${PHASE_ONE_ROOT}/stock-360`,
    id: 'stock-360',
    label: 'Stock 360',
    sourceSummary: 'OHLCV, indicators, overlays and support/resistance',
    symbolAware: true,
    workflowHref: '/app/strategy/stock-chart',
    workflowLabel: 'Open interactive chart',
  },
  {
    category: 'Intelligence',
    description: 'A focused EMA, RSI, MACD, ATR and ADX snapshot for the selected symbol.',
    href: `${PHASE_ONE_ROOT}/technical-snapshot`,
    id: 'technical-snapshot',
    label: 'Technical Snapshot',
    sourceSummary: 'Deterministic indicator services',
    symbolAware: true,
    workflowHref: '/app/technical/ema',
    workflowLabel: 'Open technical lab',
  },
  {
    category: 'Intelligence',
    description: 'Volume participation and delivery evidence presented together without changing either source contract.',
    href: `${PHASE_ONE_ROOT}/volume-delivery`,
    id: 'volume-delivery',
    label: 'Volume & Delivery',
    sourceSummary: 'Volume and delivery technical services',
    symbolAware: true,
    workflowHref: '/app/technical/delivery',
    workflowLabel: 'Open delivery analysis',
  },
  {
    category: 'Intelligence',
    description: 'Automated and manual level evidence for the selected symbol using the current SR pipeline.',
    href: `${PHASE_ONE_ROOT}/support-resistance`,
    id: 'support-resistance',
    label: 'Support & Resistance',
    sourceSummary: 'Calculated SR levels and approved manual levels',
    symbolAware: true,
    workflowHref: '/app/technical/support-resistance',
    workflowLabel: 'Open SR analysis',
  },
  {
    category: 'Intelligence',
    description: 'Available historical candles and breakout evidence for transparent behaviour research.',
    href: `${PHASE_ONE_ROOT}/historical-behaviour`,
    id: 'historical-behaviour',
    label: 'Historical Behaviour',
    sourceSummary: 'Historical rows and long-window price evidence',
    symbolAware: true,
    workflowHref: '/app/database/historical-data',
    workflowLabel: 'Open historical data',
  },
  {
    category: 'Operations',
    description: 'Latest DEV, market-cap, free-float and delivery dates with stale-source visibility.',
    href: `${PHASE_ONE_ROOT}/data-freshness`,
    id: 'data-freshness',
    label: 'Data Freshness',
    sourceSummary: 'Database sync status and technical latest date',
    workflowHref: '/app/database/stock-history',
    workflowLabel: 'Open stock history',
  },
  {
    category: 'Operations',
    description: 'Missing-source counts and stock-history coverage signals derived from existing validation endpoints.',
    href: `${PHASE_ONE_ROOT}/data-quality`,
    id: 'data-quality',
    label: 'Data Quality',
    sourceSummary: 'Stock history statistics and synchronization gaps',
    workflowHref: '/app/database/stock-history',
    workflowLabel: 'Open reconciliation',
  },
  {
    category: 'Operations',
    description: 'Read-only status for NSE market-data automation and the current FYERS background job.',
    href: `${PHASE_ONE_ROOT}/job-monitor`,
    id: 'job-monitor',
    label: 'Job Monitor',
    sourceSummary: 'NSE and FYERS automation status',
    workflowHref: '/app/fyers/automation',
    workflowLabel: 'Open automation',
  },
  {
    category: 'Operations',
    description: 'Read-only runtime health and server status using the existing operational controls.',
    href: `${PHASE_ONE_ROOT}/system-settings`,
    id: 'system-settings',
    label: 'System Settings',
    sourceSummary: 'Flask health and server-control status',
    workflowHref: '/app/database/server',
    workflowLabel: 'Open server control',
  },
  {
    category: 'Account',
    description: 'Current authenticated-session evidence from the centralized application auth context.',
    href: `${PHASE_ONE_ROOT}/profile`,
    id: 'user-profile',
    label: 'User Profile',
    sourceSummary: 'Central authenticated session',
    workflowHref: '/app/auth/login',
    workflowLabel: 'Open account access',
  },
] as const;

const navItemByPath = new Map(phaseOneNavItems.map((item) => [item.href, item]));

export function findPhaseOneNavItem(pathname: string): PhaseOneNavItem | null {
  const normalized = pathname.trim().replace(/\/+$/, '').toLowerCase();
  if (!normalized || normalized === PHASE_ONE_ROOT) {
    return phaseOneNavItems[0];
  }
  return navItemByPath.get(normalized) ?? null;
}

export function isPhaseOnePath(pathname: string): boolean {
  const normalized = pathname.trim().replace(/\/+$/, '').toLowerCase();
  return normalized === PHASE_ONE_ROOT || navItemByPath.has(normalized);
}

export function phaseOneItemsForCategory(category: PhaseOneCategory): ReadonlyArray<PhaseOneNavItem> {
  return phaseOneNavItems.filter((item) => item.category === category);
}
