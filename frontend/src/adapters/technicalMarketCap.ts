export type MarketCapCategory = 'large' | 'mid' | 'small' | 'unknown';

export const MARKET_CAP_INDEX_ALIASES = [
  'INDEX',
  'index',
  'marketCapIndex',
  'market_cap_index',
  'marketCapCategory',
  'market_cap_category',
  'indexValue',
  'INDEX_VALUE',
];

export const MARKET_CAP_VALUE_ALIASES = [
  'MCAP',
  'mcap',
  'marketCapCrores',
  'MARKET_CAP_CRORES',
  'market_cap_crores',
  'marketCap',
  'MARKET_CAP',
  'totalMcap',
  'TOTAL_MCAP',
  'total_mcap_cr',
  'TOTAL_MCAP_CR',
];

export const MARKET_CAP_RANK_ALIASES = [
  'MCAP_RANK',
  'mcapRank',
  'mcap_rank',
  'market_cap_rank',
  'MARKET_CAP_RANK',
  'marketCapRank',
  'MCAPRank',
  'rank',
  'RANK',
  'MCAP_RANKING',
  'mcapRanking',
  'mcap_ranking',
  'MARKETCAPRANK',
];

function isPresentValue(value: unknown): boolean {
  if (value === undefined || value === null) return false;
  if (typeof value === 'string' && value.trim() === '') return false;
  return true;
}

export function firstPresentValue(row: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(row, key)) continue;
    const value = row[key];
    if (!isPresentValue(value)) continue;
    return value;
  }
  return null;
}

export function toNumber(value: unknown): number | null {
  if (value === undefined || value === null || value === '') return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const cleaned = String(value).replace(/,/g, '').replace(/%/g, '').trim();
  if (!cleaned || cleaned === '-') return null;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

export function normalizeMarketCapIndex(value: unknown): string {
  const text = String(value ?? '').trim().toUpperCase();
  if (!text || text === '-' || text === 'NULL' || text === 'UNDEFINED') return '-';
  if (text.includes('LARGE')) return 'LARGE';
  if (text.includes('MID')) return 'MID';
  if (text.includes('SMALL')) return 'SMALL';
  return text;
}

export function getMarketCapCategory(value: unknown): MarketCapCategory {
  const text = String(value ?? '').trim().toUpperCase();
  if (text.includes('LARGE')) return 'large';
  if (text.includes('MID')) return 'mid';
  if (text.includes('SMALL')) return 'small';
  return 'unknown';
}

export function getMarketCapToneClass(category: MarketCapCategory | undefined): string | undefined {
  switch (category) {
    case 'large':
      return 'trend-mcap-index-value trend-mcap-index-value--large';
    case 'mid':
      return 'trend-mcap-index-value trend-mcap-index-value--mid';
    case 'small':
      return 'trend-mcap-index-value trend-mcap-index-value--small';
    case 'unknown':
      return 'trend-mcap-index-value trend-mcap-index-value--unknown';
    default:
      return undefined;
  }
}

export function formatMarketCapValue(value: unknown): string {
  const numeric = toNumber(value);
  if (numeric === null) return '-';
  return numeric.toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

export function formatMarketCapRankValue(value: unknown): string {
  const numeric = toNumber(value);
  if (numeric === null) return '-';
  return Math.round(numeric).toLocaleString('en-IN');
}

export function resolveMarketCapCategory(row: Record<string, unknown>): MarketCapCategory {
  return getMarketCapCategory(firstPresentValue(row, MARKET_CAP_INDEX_ALIASES));
}

