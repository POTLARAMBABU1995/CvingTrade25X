export type SectorStrengthKey =
  | 'very-strong-bullish'
  | 'strong-bullish'
  | 'bullish-improving'
  | 'moderate-neutral'
  | 'weak-bearish'
  | 'very-weak-bearish'
  | 'neutral-na';

export type SectorBreadthStrength = {
  avgPct: number;
  scoreClassName: string;
  sectorClassName: string;
  sortRank: number;
  strengthKey: SectorStrengthKey;
  strengthLabel: string;
};

export type SectorBreadthMetricsInput = {
  rsi50Pct?: number | string | null;
  rsi55Pct?: number | string | null;
  sma100Pct?: number | string | null;
  sma20Pct?: number | string | null;
  sma50Pct?: number | string | null;
};

export function parsePercent(value: unknown): number {
  if (value === null || value === undefined) return Number.NaN;
  if (typeof value === 'number') return Number.isFinite(value) ? value : Number.NaN;
  const raw = String(value).trim();
  if (!raw || raw === '-') return Number.NaN;
  const normalized = raw.replace(/%/g, '').replace(/,/g, '');
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function createStrength(
  avgPct: number,
  strengthKey: SectorStrengthKey,
  strengthLabel: string,
  sortRank: number,
  className: string,
): SectorBreadthStrength {
  return {
    avgPct,
    scoreClassName: className,
    sectorClassName: className,
    sortRank,
    strengthKey,
    strengthLabel,
  };
}

export function computeSectorBreadthStrength(row: SectorBreadthMetricsInput): SectorBreadthStrength {
  const values = [row.rsi55Pct, row.rsi50Pct, row.sma20Pct, row.sma50Pct, row.sma100Pct]
    .map((value) => parsePercent(value))
    .filter((value) => Number.isFinite(value));

  if (!values.length) {
    return createStrength(0, 'neutral-na', 'Neutral / NA', 0, 'bg-slate-300 text-slate-900 font-bold');
  }

  const avgPct = values.reduce((sum, value) => sum + value, 0) / values.length;

  if (avgPct >= 90) {
    return createStrength(avgPct, 'very-strong-bullish', 'Very Strong Bullish', 6, 'bg-[#052e16] !text-white font-extrabold');
  }
  if (avgPct >= 75) {
    return createStrength(avgPct, 'strong-bullish', 'Strong Bullish', 5, 'bg-[#15803d] !text-white font-bold');
  }
  if (avgPct >= 60) {
    return createStrength(avgPct, 'bullish-improving', 'Bullish / Improving', 4, 'bg-[#86efac] !text-[#052e16] font-bold');
  }
  if (avgPct >= 45) {
    return createStrength(avgPct, 'moderate-neutral', 'Moderate / Neutral', 3, 'bg-yellow-300 !text-slate-900 font-bold');
  }
  if (avgPct >= 30) {
    return createStrength(avgPct, 'weak-bearish', 'Weak Bearish', 2, 'bg-red-500 !text-white font-bold');
  }
  if (avgPct > 0) {
    return createStrength(avgPct, 'very-weak-bearish', 'Very Weak Bearish', 1, 'bg-red-950 !text-white font-extrabold');
  }
  return createStrength(avgPct, 'neutral-na', 'Neutral / NA', 0, 'bg-slate-300 !text-slate-900 font-bold');
}
