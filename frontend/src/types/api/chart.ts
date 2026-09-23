export type Timeframe = '1D' | '1W' | '1M' | '1Y';

export type Bar = {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
};

export type BarsResponse = {
  version: string;
  symbol: string;
  tf: Timeframe;
  nextCursor?: string | null;
  bars: Bar[];
};

export type IndicatorPoint = {
  t: number;
  v: number;
};

export type IndicatorsResponse = {
  version: string;
  symbol: string;
  tf: Timeframe;
  series: Record<string, IndicatorPoint[]>;
};

export type OverlayAnnotation = {
  type: string;
  id?: string;
  label?: string;
  style?: string;
  zoneType?: string;
  patternType?: string;
  score?: number;
  confidence?: number;
  t1?: number;
  t2?: number;
  p1?: number;
  p2?: number;
  time?: number;
  price?: number;
  shape?: string;
  data?: Record<string, unknown>;
};

export type OverlaysResponse = {
  version: string;
  symbol: string;
  tf: Timeframe;
  annotations: OverlayAnnotation[];
};

export type UserAnnotationsResponse = {
  version: string;
  userId: number;
  symbol: string;
  tf: Timeframe;
  annotations: OverlayAnnotation[];
};

export type SymbolsResponse = {
  version: string;
  q?: string;
  symbols: Array<{ symbol: string; name?: string; exchange?: string; sector?: string }>;
};
