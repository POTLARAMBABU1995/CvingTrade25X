export type NavItem = {
  id: string;
  label: string;
  hint: string;
};

export type StrategyCard = {
  title: string;
  subtitle: string;
  score: string;
  hitRate: string;
  risk: string;
  tags: string[];
};

export type SectorPulse = {
  name: string;
  weight: string;
  change: string;
  intensity: number;
};

export type MoversRow = {
  symbol: string;
  setup: string;
  price: string;
  change: string;
  volume: string;
  status: 'lead' | 'watch' | 'risk';
};

export type WatchlistRow = {
  symbol: string;
  thesis: string;
  pivot: string;
  change: string;
  bias: 'build' | 'hold' | 'trim';
};

export type InsightItem = {
  title: string;
  summary: string;
  detail: string;
};

export const PRIMARY_NAV: NavItem[] = [
  { id: 'overview', label: 'Overview', hint: 'Desk' },
  { id: 'studio', label: 'Chart Studio', hint: 'Live' },
  { id: 'strategies', label: 'Strategies', hint: 'Models' },
  { id: 'rotation', label: 'Sector Pulse', hint: 'Rotation' },
  { id: 'backtest', label: 'Backtest', hint: 'Lab' },
  { id: 'watchlist', label: 'Watchlists', hint: 'Focus' },
];

export const STRATEGY_CARDS: StrategyCard[] = [
  {
    title: 'Momentum Stack',
    subtitle: 'EMA alignment + RSI confirmation + follow-through volume.',
    score: '92 / 100',
    hitRate: '68%',
    risk: 'Tight',
    tags: ['Trend', 'Breakout', 'High conviction'],
  },
  {
    title: 'Compression Release',
    subtitle: 'ATR contraction into expansion with MACD regime shift.',
    score: '84 / 100',
    hitRate: '61%',
    risk: 'Moderate',
    tags: ['ATR', 'Volatility', 'Early move'],
  },
  {
    title: 'Defensive Rotation',
    subtitle: 'Relative strength shelf for late-cycle sector pivots.',
    score: '79 / 100',
    hitRate: '57%',
    risk: 'Controlled',
    tags: ['Sector', 'Relative strength', 'Swing'],
  },
];

export const SECTOR_PULSE: SectorPulse[] = [
  { name: 'Power', weight: '18%', change: '+2.8%', intensity: 96 },
  { name: 'Private Bank', weight: '15%', change: '+1.9%', intensity: 78 },
  { name: 'IT', weight: '11%', change: '-0.4%', intensity: 36 },
  { name: 'Capital Goods', weight: '13%', change: '+2.2%', intensity: 88 },
  { name: 'Pharma', weight: '9%', change: '+0.8%', intensity: 55 },
  { name: 'Realty Real Estate', weight: '7%', change: '-1.2%', intensity: 20 },
];

export const MOVERS: MoversRow[] = [
  { symbol: 'RELIANCE', setup: 'EMA stack intact', price: '2,948.55', change: '+2.14%', volume: '1.8x', status: 'lead' },
  { symbol: 'TCS', setup: 'Range pressure', price: '4,102.20', change: '+1.08%', volume: '1.2x', status: 'watch' },
  { symbol: 'NTPC', setup: 'Breakout continuation', price: '421.90', change: '+3.64%', volume: '2.4x', status: 'lead' },
  { symbol: 'HDFCBANK', setup: 'Base reclaim', price: '1,678.25', change: '+0.76%', volume: '0.9x', status: 'watch' },
  { symbol: 'ADANIPORTS', setup: 'Volatility spike', price: '1,418.10', change: '-1.82%', volume: '2.1x', status: 'risk' },
];

export const WATCHLIST: WatchlistRow[] = [
  { symbol: 'RELIANCE', thesis: 'Institutional trend shelf', pivot: '2,915', change: '+2.14%', bias: 'build' },
  { symbol: 'NTPC', thesis: 'Power leadership', pivot: '408', change: '+3.64%', bias: 'build' },
  { symbol: 'L&T', thesis: 'Capex continuation', pivot: '3,522', change: '+1.42%', bias: 'hold' },
  { symbol: 'SUNPHARMA', thesis: 'Defensive follow-through', pivot: '1,712', change: '+0.94%', bias: 'hold' },
  { symbol: 'ADANIPORTS', thesis: 'Event risk unwind', pivot: '1,452', change: '-1.82%', bias: 'trim' },
];

export const INSIGHTS: InsightItem[] = [
  {
    title: 'Desk read',
    summary: 'Breadth is improving but leadership remains selective and capital is still clustering around quality beta.',
    detail: 'Use concentrated sizing on names showing EMA stack support plus expanding volume. Avoid low-liquidity laggards even if they print short-term RSI bursts.',
  },
  {
    title: 'Risk framing',
    summary: 'The tape is constructive, but late-day reversals remain the main failure pattern across crowded breakouts.',
    detail: 'Anchor stops below intraday demand zones and favour names with clean ATR compression before expansion. Fade stretched moves that lack secondary participation.',
  },
  {
    title: 'Execution note',
    summary: 'Best fills are coming on controlled retests rather than first-impulse breakouts.',
    detail: 'Let the alert stack surface follow-through names, then stalk entries on reclaim candles with volume staying above one-day average. Preserve dry powder for the second setup, not the first print.',
  },
];
