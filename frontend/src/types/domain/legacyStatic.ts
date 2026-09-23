export type LegacyStaticNavKey = 'portfolio' | 'kaveri' | 'prudvi' | 'technicals' | 'thrinethra' | 'thrisul';

export type PortfolioImage = {
  id: string;
  title: string;
  alt: string;
  src: string;
};

export type LocalMarketMover = {
  s: string;
  chg: number;
};

export type LocalMarketBreadth = {
  advances: number;
  declines: number;
  unchanged: number;
};

export type LocalMarketMovers = {
  gainers: LocalMarketMover[];
  losers: LocalMarketMover[];
  breadth: LocalMarketBreadth;
};

export type LocalScreenerWireRow = {
  symbol: string;
  priceChange: number;
  volumeShock: number;
  high52: number;
  low52: number;
  ath: number;
  high2y: number;
  high5y: number;
  volume: number;
};

export type LocalMarketDataset = {
  movers: LocalMarketMovers;
  screener: LocalScreenerWireRow[];
};

export type LocalStrategyRow = LocalScreenerWireRow & {
  high1y: number;
  emaDays: string;
  emaDaysSort: number;
  rsi: string;
  rsiValue: number;
  macd: string;
  macdValue: number;
  atr: string;
  atrValue: number;
  support: string;
  supportValue: number | null;
  resistance: string;
  resistanceValue: number | null;
};
