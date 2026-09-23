export type StockRow = {
  symbol: string;
  companyName: string | null;
  sector: string | null;
  index: string | null;
  tradingDate: string | null;
  price: number | null;
  change: number | null;
  changePct: number | null;
  volume: number | null;
};

export type TechnicalIndicatorRow = StockRow & {
  ema20: number | null;
  ema50: number | null;
  ema100: number | null;
  ema200: number | null;
  rsi50: number | null;
  adx14: number | null;
  atr14: number | null;
  trendDirection: string | null;
  score: number | null;
  signalScore: number | null;
};

export type MarketCapRow = StockRow & {
  totalMcap: number | null;
  freeFloatMcap: number | null;
  mcapRank: number | null;
  sharesOutstanding: number | null;
  ltcDate: string | null;
};

export type DeliveryRow = StockRow & {
  ltcDate: string | null;
  deliveryQty: number | null;
  deliveryPct: number | null;
  deliveryScore: number | null;
};
