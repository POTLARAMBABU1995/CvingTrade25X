import type { FundamentalCardColor, FundamentalStatus, FundamentalTrend } from './fundamentalTypes';

export type StatusMeta = {
  label: string;
  status: FundamentalStatus;
  color: FundamentalCardColor;
  toneClass: string;
  badgeClass: string;
};

export const STATUS_META: Record<FundamentalStatus, StatusMeta> = {
  EXCELLENT: {
    label: 'Excellent',
    status: 'EXCELLENT',
    color: 'green',
    toneClass: 'border-emerald-200 bg-emerald-50 text-emerald-950',
    badgeClass: 'bg-emerald-100 text-emerald-800 ring-emerald-200',
  },
  GOOD: {
    label: 'Good',
    status: 'GOOD',
    color: 'green',
    toneClass: 'border-emerald-200 bg-emerald-50 text-emerald-950',
    badgeClass: 'bg-emerald-100 text-emerald-800 ring-emerald-200',
  },
  AVERAGE: {
    label: 'Average',
    status: 'AVERAGE',
    color: 'amber',
    toneClass: 'border-amber-200 bg-amber-50 text-amber-950',
    badgeClass: 'bg-amber-100 text-amber-800 ring-amber-200',
  },
  WATCH: {
    label: 'Watch',
    status: 'WATCH',
    color: 'amber',
    toneClass: 'border-amber-200 bg-amber-50 text-amber-950',
    badgeClass: 'bg-amber-100 text-amber-800 ring-amber-200',
  },
  WEAK: {
    label: 'Weak',
    status: 'WEAK',
    color: 'red',
    toneClass: 'border-rose-200 bg-rose-50 text-rose-950',
    badgeClass: 'bg-rose-100 text-rose-800 ring-rose-200',
  },
  RISK: {
    label: 'Risk',
    status: 'RISK',
    color: 'red',
    toneClass: 'border-rose-200 bg-rose-50 text-rose-950',
    badgeClass: 'bg-rose-100 text-rose-800 ring-rose-200',
  },
  NEUTRAL: {
    label: 'Neutral',
    status: 'NEUTRAL',
    color: 'slate',
    toneClass: 'border-slate-200 bg-slate-50 text-slate-950',
    badgeClass: 'bg-slate-100 text-slate-700 ring-slate-200',
  },
};

export function resolveOverallStatus(score: number): StatusMeta & { finalLabel: string } {
  if (score >= 85) return { ...STATUS_META.EXCELLENT, finalLabel: 'Strong Fundamental' };
  if (score >= 70) return { ...STATUS_META.GOOD, finalLabel: 'Good Fundamental' };
  if (score >= 55) return { ...STATUS_META.AVERAGE, finalLabel: 'Average Fundamental' };
  if (score >= 40) return { ...STATUS_META.WEAK, finalLabel: 'Weak Fundamental' };
  return { ...STATUS_META.RISK, finalLabel: 'Avoid / High Risk' };
}

export function resolveGrowthStrength(salesCagr5Y: number, profitCagr5Y: number): StatusMeta & { value: string } {
  if (salesCagr5Y >= 12 && profitCagr5Y >= 12) return { ...STATUS_META.EXCELLENT, value: 'Strong Growth' };
  if (salesCagr5Y >= 8 && profitCagr5Y >= 8) return { ...STATUS_META.GOOD, value: 'Good Growth' };
  if (salesCagr5Y >= 4) return { ...STATUS_META.AVERAGE, value: 'Average Growth' };
  return { ...STATUS_META.WEAK, value: 'Weak Growth' };
}

export function resolveCashFlow(cfo: number, cfoToPat: number, fcf: number): StatusMeta & { value: string } {
  if (cfo > 0 && cfoToPat >= 0.8 && fcf > 0) return { ...STATUS_META.EXCELLENT, value: 'Strong Cash Flow' };
  if (cfo < 0 || cfoToPat < 0.5) return { ...STATUS_META.WEAK, value: 'Weak Cash Flow' };
  return { ...STATUS_META.WATCH, value: 'Watch Cash Flow' };
}

export function resolveBalanceSheet(debtEquity: number, interestCoverage: number, currentRatio: number): StatusMeta & { value: string } {
  if (debtEquity <= 0.5 && interestCoverage >= 5 && currentRatio >= 1.2) return { ...STATUS_META.EXCELLENT, value: 'Strong Balance Sheet' };
  if (debtEquity > 1.5 || interestCoverage < 2) return { ...STATUS_META.WEAK, value: 'Weak Balance Sheet' };
  return { ...STATUS_META.WATCH, value: 'Watch Leverage' };
}

export function resolveQoQStrength(salesGrowth: number, profitGrowth: number): StatusMeta & { value: string } {
  if (salesGrowth > 0 && profitGrowth > 0) return { ...STATUS_META.GOOD, value: 'Strong QoQ' };
  if (salesGrowth < 0 && profitGrowth < 0) return { ...STATUS_META.WEAK, value: 'Weak QoQ' };
  return { ...STATUS_META.WATCH, value: 'Mixed QoQ' };
}

export function resolveYoYStrength(salesGrowth: number, profitGrowth: number): StatusMeta & { value: string } {
  if (salesGrowth > 8 && profitGrowth > 8) return { ...STATUS_META.GOOD, value: 'Strong YoY' };
  if (salesGrowth > 0 && profitGrowth > 0) return { ...STATUS_META.AVERAGE, value: 'Average YoY' };
  return { ...STATUS_META.WEAK, value: 'Weak YoY' };
}

export function resolvePromoterPledge(pledgePercent: number): StatusMeta & { value: string } {
  if (pledgePercent === 0) return { ...STATUS_META.EXCELLENT, value: 'Excellent' };
  if (pledgePercent <= 5) return { ...STATUS_META.WATCH, value: 'Watch' };
  if (pledgePercent <= 20) return { ...STATUS_META.RISK, value: 'Risk' };
  return { ...STATUS_META.WEAK, value: 'High Risk / Weak' };
}

export function resolveDividendPayout(payoutPercent: number, positiveFcf: boolean, growthCompany: boolean): StatusMeta & { value: string } {
  if (payoutPercent >= 10 && payoutPercent <= 60 && positiveFcf) return { ...STATUS_META.GOOD, value: 'Healthy' };
  if (payoutPercent > 80 && !positiveFcf) return { ...STATUS_META.RISK, value: 'Risk' };
  if (payoutPercent === 0 && growthCompany) return { ...STATUS_META.NEUTRAL, value: 'Neutral' };
  if (payoutPercent === 0) return { ...STATUS_META.WEAK, value: 'Weak' };
  return { ...STATUS_META.WATCH, value: 'Watch' };
}

export function resolveTrendDirection(value: number): FundamentalTrend {
  if (value > 0) return 'up';
  if (value < 0) return 'down';
  return 'flat';
}

export function getStatusMeta(status: FundamentalStatus): StatusMeta {
  return STATUS_META[status] ?? STATUS_META.NEUTRAL;
}
