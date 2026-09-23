export type TechnicalNavItem = {
  href: string;
  label: string;
  page: string;
};

export const technicalNavItems = [
  { href: '/app/technical/ema', label: 'EMA-20/50/100/200', page: '/app/technical/ema' },
  { href: '/app/technical/rsi50', label: 'RSI > 50', page: '/app/technical/rsi50' },
  { href: '/app/technical/macd', label: 'MACD > 0', page: '/app/technical/macd' },
  { href: '/app/technical/atr14', label: 'ATR 14', page: '/app/technical/atr14' },
  { href: '/app/technical/adx', label: 'ADX', page: '/app/technical/adx' },
  { href: '/app/technical/price-action', label: 'Price Action SR', page: '/app/technical/price-action' },
  { href: '/app/technical/price-action-analysis', label: 'Price Action Analysis', page: '/app/technical/price-action-analysis' },
  { href: '/app/technical/trendline', label: 'Trendline', page: '/app/technical/trendline' },
  { href: '/app/technical/breakout', label: 'Breakout', page: '/app/technical/breakout' },
  { href: '/app/technical/chart-patterns', label: 'Chart Patterns', page: '/app/technical/chart-patterns' },
  { href: '/app/technical/strong-technicals', label: 'Strong Technicals', page: '/app/technical/strong-technicals' },
  { href: '/app/technical/support-resistance', label: 'Price Action SR', page: '/app/technical/support-resistance' },
  { href: '/app/technical/volume', label: 'Volume MA > 20', page: '/app/technical/volume' },
  { href: '/app/technical/delivery', label: 'Delivery', page: '/app/technical/delivery' },
] satisfies ReadonlyArray<TechnicalNavItem>;
