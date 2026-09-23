export type FundamentalStatus = 'EXCELLENT' | 'GOOD' | 'AVERAGE' | 'WATCH' | 'WEAK' | 'RISK' | 'NEUTRAL';

export type FundamentalTrend = 'up' | 'down' | 'flat';

export type FundamentalCardColor = 'green' | 'amber' | 'red' | 'blue' | 'slate';

export type FundamentalCard = {
  key: string;
  title: string;
  value: string;
  numericValue?: number;
  status: FundamentalStatus;
  color: FundamentalCardColor;
  description: string;
  trend: FundamentalTrend;
  tooltip: string;
  section: 'growth' | 'profit_loss' | 'cash_flow' | 'balance_sheet' | 'returns' | 'valuation' | 'dividend' | 'governance' | 'peers' | 'risk' | 'overall';
};

export type FundamentalSummary = {
  symbol: string;
  companyName: string;
  exchange: 'NSE' | 'BSE' | 'NSE SME';
  sector: string;
  marketCap: string;
  currentPrice: string;
  overallScore: number;
  overallStatus: string;
  lastUpdated: string;
  cards: FundamentalCard[];
};

export type FundamentalMetricRow = {
  metric: string;
  values: Record<string, string>;
  emphasis?: boolean;
};

export type FundamentalPeerRow = {
  rank: number | string;
  name: string;
  cmp: string;
  pe: string;
  marketCap: string;
  dividendYield: string;
  netProfitQtr: string;
  qtrProfitVar: string;
  salesQtr: string;
  qtrSalesVar: string;
  roce: string;
  selected?: boolean;
  median?: boolean;
};
