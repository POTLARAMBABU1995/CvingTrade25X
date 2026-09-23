export type DatabaseNavItem = {
  href: string;
  label: string;
  page: string;
};

export const databaseNavItems = [
  { href: '/app/database/stock-history', label: 'Stock History', page: '/app/database/stock-history' },
  { href: '/app/database/historical-data', label: 'Historical Data', page: '/app/database/historical-data' },
  { href: '/app/database/corporate-actions', label: 'Corporate Actions', page: '/app/database/corporate-actions' },
  { href: '/app/database/nse-market-cap', label: 'NSE Market Cap', page: '/app/database/nse-market-cap' },
  { href: '/app/database/nse-market-cap-index', label: 'NSE Market Cap Index', page: '/app/database/nse-market-cap-index' },
  { href: '/app/database/nse-ffmc', label: 'NSE FFMC', page: '/app/database/nse-ffmc' },
  { href: '/app/database/nse-delivery-data', label: 'NSE Delivery Data', page: '/app/database/nse-delivery-data' },
  { href: '/app/database/server', label: 'Server', page: '/app/database/server' },
] satisfies ReadonlyArray<DatabaseNavItem>;
