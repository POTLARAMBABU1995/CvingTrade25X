export type AsuraV3DashboardSummary = {
  strategyName: string;
  strategyCode: string;
  runId: string;
  latestSignalDate: string | null;
  totalTrades: number | null;
  successCount: number | null;
  failureCount: number | null;
  openCount: number | null;
  successRatePct: number | null;
  failureRatePct: number | null;
  avgTradingDays: number | null;
  totalPnlPercent: number | null;
  avgRMultiple: number | null;
  startDate: string | null;
  endDate: string | null;
  totalSymbols: number | null;
  maxDrawdown: number | null;
  maxConsecutiveFailures: number | null;
  roundTripCostPct: number | null;
  netPnlPercent: number | null;
  avgNetPnlPerTrade: number | null;
  dashboardRefreshTimestamp: string | null;
  raw: Record<string, unknown>;
};

export type AsuraV3LatestSignalRow = {
  symbol: string;
  signalDate: string | null;
  symbolRating: string;
  price: number | null;
  entryPrice: number | null;
  stopLoss: number | null;
  target1R: number | null;
  rrrRaw: number | string | null;
  signalScore: number | null;
  signalGrade: string;
  rsi14: number | null;
  rsiPrev1d: number | null;
  rsiPrev5d: number | null;
  macdHist: number | null;
  adx14: number | null;
  atrPercent: number | null;
  riskAtr: number | null;
  volumeRatio20: number | null;
  move1dPct: number | null;
  move1wPct: number | null;
  move1mPct: number | null;
  supportGapPct: number | null;
  resistanceGapPct: number | null;
  trendDirection: string;
  emaStack: string;
  athPrice: number | null;
  athGapPct: number | null;
  raw: Record<string, unknown>;
};

export type AsuraV3YearlySummaryRow = {
  signalYear: number | null;
  totalTrades: number | null;
  successCount: number | null;
  failureCount: number | null;
  openCount: number | null;
  successRatePct: number | null;
  failureRatePct: number | null;
  avgTradingDays: number | null;
  totalPnlPercent: number | null;
  avgRMultiple: number | null;
  totalSymbols: number | null;
  raw: Record<string, unknown>;
};

export type AsuraV3CostSummaryRow = {
  costScenario: string;
  roundTripCostPct: number | null;
  closedTrades: number | null;
  successRatePct: number | null;
  grossPnlPercent: number | null;
  netPnlPercent: number | null;
  avgNetPnlPerTrade: number | null;
  avgTradingDays: number | null;
  raw: Record<string, unknown>;
};

export type AsuraV3RiskSummaryRow = {
  closedTrades: number | null;
  successCount: number | null;
  failureCount: number | null;
  successRatePct: number | null;
  maxDrawdown: number | null;
  maxConsecutiveFailures: number | null;
  avgTradingDays: number | null;
  finalCumulativePnl: number | null;
  raw: Record<string, unknown>;
};

export type AsuraV3SymbolRatingRow = {
  symbolRating: string;
  totalSymbols: number;
  raw: Record<string, unknown>;
};

export type AsuraV3HealthPayload = {
  dbReachable: boolean;
  latestSignalDate: string | null;
  dashboardRefreshTimestamp: string | null;
  checkedAt: string;
};

export type AsuraV3LatestSignalsResponse = {
  items: AsuraV3LatestSignalRow[];
  total: number;
  limit: number;
  offset: number;
};

export type AsuraV3LatestSignalsQuery = {
  q?: string;
  rating?: string;
  grade?: string;
  limit?: number;
  offset?: number;
  sortBy?: string;
  sortDir?: 'asc' | 'desc';
};
