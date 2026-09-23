export type StrategyNavItem = {
  href: string;
  label: string;
  page: string;
};

export const strategyNavItems = [
  { href: '/app/strategy/stock-chart', label: 'Stock Chart', page: '/app/strategy/stock-chart' },
  { href: '/app/strategy/asura', label: 'Asura', page: '/app/strategy/asura' },
  { href: '/app/strategy/asura-v3', label: 'AsuraV3', page: '/app/strategy/asura-v3' },
  { href: '/app/strategy/bhramhaputra', label: 'Bhramhaputra', page: '/app/strategy/bhramhaputra' },
  { href: '/app/strategy/bhramhastra', label: 'Bhramhastra', page: '/app/strategy/bhramhastra' },
  { href: '/app/strategy/ganga', label: 'Ganga', page: '/app/strategy/ganga' },
  { href: '/app/strategy/kaveri', label: 'Kaveri', page: '/app/strategy/kaveri' },
  { href: '/app/strategy/prudvi', label: 'Prudvi', page: '/app/strategy/prudvi' },
  { href: '/app/strategy/thrinethra', label: 'Thrinethra', page: '/app/strategy/thrinethra' },
  { href: '/app/strategy/thrisul', label: 'Thrisul', page: '/app/strategy/thrisul' },
  { href: '/app/strategy/yamuna', label: 'Yamuna', page: '/app/strategy/yamuna' },
] satisfies ReadonlyArray<StrategyNavItem>;
