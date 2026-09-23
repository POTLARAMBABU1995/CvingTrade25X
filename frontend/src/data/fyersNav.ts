export type FyersNavItem = {
  href: string;
  label: string;
  page: string;
};

export const fyersNavItems = [
  { href: '/app/fyers/automation', label: 'Automation', page: '/app/fyers/automation' },
  { href: '/app/fyers/failed-symbols', label: 'Failed Symbols', page: '/app/fyers/failed-symbols' },
  { href: '/app/fyers/holdings', label: 'Holdings', page: '/app/fyers/holdings' },
  { href: '/app/fyers/nifty500-sync', label: 'NIFTY500 Sync', page: '/app/fyers/nifty500-sync' },
] satisfies ReadonlyArray<FyersNavItem>;

