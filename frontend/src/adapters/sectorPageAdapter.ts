import {
  asRecord,
  extractRows,
  formatLegacyCount,
  formatLegacyDateOnly,
  formatLegacyNumber,
  pickField,
  safeLegacyText,
  type UnknownRecord,
} from './databasePageAdapter';
import { normalizeDisplaySymbol } from '../utils/symbols';

export type SectorBreadthRow = {
  asOfDate: string;
  countBreadth: number | null;
  effectiveDate: string;
  ffmcBreadth: number | null;
  mcapBreadth: number | null;
  rsi50Pct: number | null;
  rsi55Pct: number | null;
  sectorCode: string;
  sectorName: string;
  sma100Pct: number | null;
  sma20Pct: number | null;
  sma50Pct: number | null;
  stockConfirmationScreening: string;
  totalStocks: number | null;
  tableName: string;
  // Additive V2 Fields
  rotationPhase?: string;
  rotationScore?: number | null;
  momentumScore?: number | null;
  breadthScore?: number | null;
  moneyFlowScore?: number | null;
  riskScore?: number | null;
  trendScore?: number | null;
  confidence?: string;
  reasonCodes?: string[];
  // Additive V3 fields. Optional so V1/V2 payloads keep the same contract.
  bullishStackPercent?: number | null;
  breadthDelta1D?: number | null;
  breadthDelta5D?: number | null;
  breadthDelta21D?: number | null;
  breadthDirection?: string;
  confidenceScore?: number | null;
  configuredWeights?: Record<string, number | null>;
  concentrationHhi?: number | null;
  coveragePercent?: number | null;
  currentRank?: number | null;
  dataQualityScore?: number | null;
  dataQualityStatus?: string;
  divergenceCodes?: string[];
  effectiveWeights?: Record<string, number | null>;
  eligibleStockCount?: number | null;
  finalRotationScore?: number | null;
  historyCoveragePercent?: number | null;
  latestDataDate?: string;
  legacyDisplayScore?: number | null;
  maxDrawdown126?: number | null;
  maxDrawdown252?: number | null;
  moneyFlowCoveragePercent?: number | null;
  moneyFlowDirection?: string;
  momentumAccelerationRaw?: number | null;
  momentumAccelerationScore?: number | null;
  momentumDirection?: string;
  phaseChangedAt?: string;
  phaseDurationDays?: number | null;
  positiveReasons?: string[];
  previousPhase?: string;
  rankChange1D?: number | null;
  rankChange1M?: number | null;
  rankChange1W?: number | null;
  relativeReturn21?: number | null;
  relativeReturn63?: number | null;
  relativeReturn126?: number | null;
  relativeReturn252?: number | null;
  riskRegime?: string;
  riskWarnings?: string[];
  rotationBand?: string;
  scoreChange1D?: number | null;
  scoreChange1W?: number | null;
  sma200Pct?: number | null;
  staleStockCount?: number | null;
  summaryExplanation?: string;
  trendState?: string;
  validIndicatorCount?: number | null;
  validPriceCount?: number | null;
  volatility63?: number | null;
  weightRedistributionApplied?: boolean;
};

export type SectorRotationSnapshotMeta = {
  asOfDate: string;
  cacheStatus: string;
  calculationDurationMs: number | null;
  generatedAt: string;
  isStale: boolean;
  modelVersion: string;
  version: string;
};

export type SectorWiseRow = UnknownRecord & {
  ath: unknown;
  athDate: unknown;
  breakoutStatus: unknown;
  confidence: unknown;
  ema100: unknown;
  ema100Flag: string;
  ema200: unknown;
  ema200Flag: string;
  ema20: unknown;
  ema20Flag: string;
  ema50: unknown;
  ema50Flag: string;
  gap: unknown;
  gapPct: unknown;
  high52w: unknown;
  index: unknown;
  low52w: unknown;
  ltcDate: unknown;
  price: unknown;
  score: unknown;
  sNo: unknown;
  scoreBreakdown: unknown;
  scoreGrade: unknown;
  scoreSort: unknown;
  scoreSource: unknown;
  stock: string;
  totalMcap: unknown;
  mcapRank: unknown;
  riskStatus: unknown;
  rsVsBenchmark: unknown;
  rsVsSector: unknown;
  sectorPhase: unknown;
  sectorScore: unknown;
  trend: unknown;
  trendSort: unknown;
  volumeDeliveryStatus: unknown;
  stockEdgeScore: unknown;
  stockEdgeBand: unknown;
  trendState: unknown;
  coverage: unknown;
  factorScores: unknown;
  return21: unknown;
  return63: unknown;
  return126: unknown;
  relativeMomentumScore: unknown;
  rsi: unknown;
  macd: unknown;
  macdHist: unknown;
  adx14: unknown;
  volumeRatio: unknown;
  deliveryScore: unknown;
  riskLevel: unknown;
  reasonCodes: unknown;
  warnings: unknown;
};

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(String(value).replace(/,/g, '').replace(/%/g, ''));
  return Number.isFinite(parsed) ? parsed : null;
}

function firstValue(row: UnknownRecord, aliases: readonly string[], fallback: unknown = null): unknown {
  return pickField(row, aliases, fallback);
}

function toStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.map((item) => safeLegacyText(item, '').trim()).filter(Boolean);
}

function toNumberRecord(value: unknown): Record<string, number | null> | undefined {
  const source = asRecord(value);
  const entries = Object.entries(source);
  if (!entries.length) return undefined;
  return Object.fromEntries(entries.map(([key, item]) => [key, toNumber(item)]));
}

function toOptionalBoolean(value: unknown): boolean | undefined {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value !== 'string') return undefined;
  const token = value.trim().toLowerCase();
  if (['1', 'true', 'yes', 'y'].includes(token)) return true;
  if (['0', 'false', 'no', 'n'].includes(token)) return false;
  return undefined;
}

export function adaptSectorRotationSnapshotMeta(payload: unknown): SectorRotationSnapshotMeta {
  const source = asRecord(payload);
  const nested = asRecord(source.data);
  const row = Object.keys(nested).length ? { ...source, ...nested } : source;
  return {
    asOfDate: safeLegacyText(firstValue(row, ['asOfDate', 'as_of_date', 'AS_OF_DATE']), ''),
    cacheStatus: safeLegacyText(firstValue(row, ['cacheStatus', 'cache_status', 'CACHE_STATUS']), ''),
    calculationDurationMs: toNumber(firstValue(row, ['calculationDurationMs', 'calculation_duration_ms', 'CALCULATION_DURATION_MS'])),
    generatedAt: safeLegacyText(firstValue(row, ['generatedAt', 'generated_at', 'GENERATED_AT']), ''),
    isStale: toOptionalBoolean(firstValue(row, ['isStale', 'is_stale', 'IS_STALE'], false)) ?? false,
    modelVersion: safeLegacyText(firstValue(row, ['modelVersion', 'model_version', 'MODEL_VERSION']), ''),
    version: safeLegacyText(firstValue(row, ['version', 'VERSION']), ''),
  };
}

function normalizeStockDisplay(value: unknown): string {
  const text = normalizeDisplaySymbol(safeLegacyText(value, ''));
  const upper = text.toUpperCase();
  if (upper === 'BAJAJAUTO') return 'BAJAJ-AUTO';
  if (upper === 'MM') return 'M&M';
  return text;
}

function resolveGapPct(row: Pick<SectorWiseRow, 'ath' | 'gapPct' | 'price'>): number | null {
  const explicitPct = toNumber(row.gapPct);
  if (explicitPct !== null) return explicitPct;
  const price = toNumber(row.price);
  const ath = toNumber(row.ath);
  if (price === null || ath === null || ath === 0) return null;
  return ((price - ath) / ath) * 100;
}

function resolveScore(row: Pick<SectorWiseRow, 'score' | 'scoreSort'>): number | null {
  const value = row.score ?? row.scoreSort;
  const numeric = toNumber(value);
  return numeric === null ? null : Math.max(0, Math.min(100, numeric));
}

export function formatSectorPercent(value: unknown): string {
  const numeric = toNumber(value);
  if (numeric === null) return '-';
  return `${numeric.toLocaleString('en-IN', { maximumFractionDigits: 2 })}%`;
}

export function formatSectorText(value: unknown, fallback = '-'): string {
  return safeLegacyText(value, fallback);
}

export function formatSectorNumber(value: unknown): string {
  return formatLegacyNumber(value);
}

export function formatSectorPrice(value: unknown): string {
  const numeric = toNumber(value);
  return numeric === null ? '-' : numeric.toFixed(2);
}

export function formatSectorMcap(value: unknown): string {
  const numeric = toNumber(value);
  return numeric === null ? '-' : numeric.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatSectorMcapRank(value: unknown): string {
  const numeric = toNumber(value);
  return numeric === null ? '-' : Math.round(numeric).toLocaleString('en-IN');
}

export function formatSectorIndex(value: unknown): string {
  const token = safeLegacyText(value, '').trim().toUpperCase();
  return token === 'LARGE' || token === 'MID' || token === 'SMALL' ? token : '-';
}

export function formatSectorGap(row: Pick<SectorWiseRow, 'ath' | 'gapPct' | 'price'>): string {
  const pct = resolveGapPct(row);
  if (pct === null) return '-';
  return `${pct > 0 ? '+' : ''}${pct.toFixed(2)}%`;
}

export function formatSectorDate(value: unknown): string {
  return formatLegacyDateOnly(value);
}

export function formatSectorCount(value: unknown): string {
  return formatLegacyCount(value, '-');
}

export function normalizeSectorFlag(value: unknown, fallback = 'N'): string {
  const token = safeLegacyText(value, '').toUpperCase();
  if (['Y', 'YES', 'TRUE', '1', 'ABOVE', 'UP'].includes(token)) return 'Y';
  if (['N', 'NO', 'FALSE', '0', 'BELOW', 'DOWN'].includes(token)) return 'N';
  return fallback;
}

export function sectorHeatClass(value: unknown): string {
  const numeric = toNumber(value);
  if (numeric === null) return 'heat-neutral';
  if (numeric >= 70) return 'heat-strong';
  if (numeric >= 55) return 'heat-positive';
  if (numeric <= 35) return 'heat-negative';
  return 'heat-neutral';
}

export function sectorFlagClass(value: string): string {
  return value === 'Y' ? 'sector-flag sector-flag--yes' : 'sector-flag sector-flag--no';
}

export function sectorGapClass(row: Pick<SectorWiseRow, 'ath' | 'gapPct' | 'price'>): string {
  const pct = resolveGapPct(row);
  if (pct === null) return '';
  if (pct > 0) return 'data-table__cell--up';
  if (pct < 0) return 'data-table__cell--down';
  return '';
}

export function sectorTrendLabel(row: Pick<SectorWiseRow, 'trend' | 'trendSort'>): string {
  const raw = safeLegacyText(row.trend, '').trim();
  const token = raw.toUpperCase();
  if (token.includes('STRONG') && token.includes('UP')) return 'Strong Uptrend';
  if (token.includes('PULLBACK') && token.includes('UP')) return 'Pullback in Uptrend';
  if (token.includes('POSSIBLE') && token.includes('REVERSAL')) return 'Possible Reversal';
  if (token.includes('UP')) return 'Uptrend';
  if (token.includes('DOWN')) return 'Downtrend';
  if (token.includes('SIDEWAYS')) return 'Sideways';
  if (token.includes('CONSOLIDATION') || token.includes('RANGE')) return 'Consolidation';
  return raw || safeLegacyText(row.trendSort, 'Unknown');
}

export function sectorTrendClass(row: Pick<SectorWiseRow, 'trend' | 'trendSort'>): string {
  const token = sectorTrendLabel(row).toUpperCase();
  if (token.includes('STRONG') && token.includes('UP')) return 'trend-direction trend-direction--strong-up';
  if (token.includes('PULLBACK') && token.includes('UP')) return 'trend-direction trend-direction--pullback-up';
  if (token.includes('UP')) return 'trend-direction trend-direction--up';
  if (token.includes('DOWN')) return 'trend-direction trend-direction--down';
  if (token.includes('POSSIBLE') && token.includes('REVERSAL')) return 'trend-direction trend-direction--possible-reversal';
  if (token.includes('SIDEWAYS')) return 'trend-direction trend-direction--sideways';
  if (token.includes('CONSOLIDATION') || token.includes('RANGE')) return 'trend-direction trend-direction--consolidation';
  return 'trend-direction trend-direction--unknown';
}

export function formatSectorScore(row: Pick<SectorWiseRow, 'score' | 'scoreSort'>): string {
  const score = resolveScore(row);
  return score === null ? '-' : String(Math.round(score));
}

export function sectorScoreClass(row: Pick<SectorWiseRow, 'score' | 'scoreSort'>): string {
  const score = resolveScore(row);
  if (score === null) return 'sector-score sector-score--unknown';
  if (score >= 80) return 'sector-score sector-score--strong';
  if (score >= 60) return 'sector-score sector-score--medium';
  if (score >= 40) return 'sector-score sector-score--watch';
  return 'sector-score sector-score--weak';
}

export function sectorScoreTitle(row: Pick<SectorWiseRow, 'scoreBreakdown' | 'scoreGrade' | 'scoreSource'>): string {
  const parts: string[] = [];
  const grade = safeLegacyText(row.scoreGrade, '').trim();
  const source = safeLegacyText(row.scoreSource, '').trim();
  if (grade) parts.push(`Grade: ${grade}`);
  if (source) parts.push(`Source: ${source}`);
  const breakdown = asRecord(row.scoreBreakdown);
  for (const key of ['trend', 'ema', 'momentum', 'adx', 'volume', 'delivery', 'structure', 'riskPenalty']) {
    const value = breakdown[key];
    if (value !== null && value !== undefined && value !== '') {
      parts.push(`${key}: ${String(value)}`);
    }
  }
  return parts.join(' | ');
}

function resolveEmaFlag(row: UnknownRecord, period: 20 | 50 | 100 | 200): string {
  const key = `ema${period}`;
  const price = toNumber(firstValue(row, ['price', 'close_price', 'closePrice', 'CLOSE_PRICE', 'PRICE']));
  const emaValue = toNumber(firstValue(row, [key, key.toUpperCase()]));
  if (price !== null && emaValue !== null) return price > emaValue ? 'Y' : 'N';
  return normalizeSectorFlag(firstValue(row, [`${key}Flag`, `${key}_flag`, `${key.toUpperCase()}_FLAG`, key, key.toUpperCase()]));
}

export function adaptSectorBreadthPayload(payload: unknown): SectorBreadthRow[] {
  const breadthRows = Array.isArray(payload)
    ? payload.map((row) => asRecord(row))
    : extractRows(payload, ['rows', 'items', 'data']);

  return breadthRows.map((raw) => {
    const row = asRecord(raw);
    const sectorToken = safeLegacyText(
      firstValue(row, ['sectorCode', 'sector_code', 'SECTOR_CODE', 'sector', 'SECTOR', 'sector_name', 'SECTOR_NAME']),
      '',
    );
    const values = [
      toNumber(firstValue(row, ['rsi55Percent', 'rsi55_percent', 'RSI55_PERCENT', 'rsi55Pct', 'rsi55_pct', 'RSI55_PCT', 'rsi55_gt_0', 'rsi55_gt0', 'RSI55_GT_0', 'RSI55_GT0', 'RSI55', 'RSI55 > 0'])),
      toNumber(firstValue(row, ['rsi50Percent', 'rsi50_percent', 'RSI50_PERCENT', 'rsi50Pct', 'rsi50_pct', 'RSI50_PCT', 'rsi50_gt_0', 'rsi50_gt0', 'RSI50_GT_0', 'RSI50_GT0', 'RSI50', 'RSI50 > 0'])),
      toNumber(firstValue(row, ['sma20Percent', 'sma20_percent', 'SMA20_PERCENT', 'sma20Pct', 'sma20_pct', 'SMA20_PCT', 'sma20', 'SMA20', 'SMA_20'])),
      toNumber(firstValue(row, ['sma50Percent', 'sma50_percent', 'SMA50_PERCENT', 'sma50Pct', 'sma50_pct', 'SMA50_PCT', 'sma50', 'SMA50', 'SMA_50'])),
      toNumber(firstValue(row, ['sma100Percent', 'sma100_percent', 'SMA100_PERCENT', 'sma100Pct', 'sma100_pct', 'SMA100_PCT', 'sma100', 'SMA100', 'SMA_100'])),
    ].filter((value): value is number => value !== null);
    const average = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
    const label = average === null
      ? 'Neutral / NA'
      : average >= 70
        ? 'Strong'
        : average >= 55
          ? 'Positive'
          : average <= 35
            ? 'Weak'
            : 'Neutral';
    const confidence = safeLegacyText(firstValue(row, ['confidence', 'CONFIDENCE']), '').trim() || undefined;
    const rotationPhase = safeLegacyText(firstValue(row, ['rotationPhase', 'rotation_phase', 'ROTATION_PHASE', 'phase', 'PHASE']), '').trim() || undefined;
    const breadthScore = toNumber(firstValue(row, ['breadthScore', 'breadth_score', 'BREADTH_SCORE', 'breadth', 'BREADTH']));
    const moneyFlowScore = toNumber(firstValue(row, ['moneyFlowScore', 'money_flow_score', 'MONEY_FLOW_SCORE', 'moneyFlow', 'money_flow', 'MONEY_FLOW']));
    const momentumScore = toNumber(firstValue(row, ['momentumScore', 'momentum_score', 'MOMENTUM_SCORE', 'momentum', 'MOMENTUM']));
    const riskScore = toNumber(firstValue(row, ['riskScore', 'risk_score', 'RISK_SCORE', 'risk', 'RISK']));
    const rotationScore = toNumber(firstValue(row, ['rotationScore', 'rotation_score', 'ROTATION_SCORE', 'finalRotation', 'final_rotation', 'FINAL_ROTATION', 'rotation', 'ROTATION']));
    const trendScore = toNumber(firstValue(row, ['trendScore', 'trend_score', 'TREND_SCORE', 'trend', 'TREND']));
    const reasonCodes = toStringArray(firstValue(row, ['reasonCodes', 'reason_codes', 'REASON_CODES']));
    const positiveReasons = toStringArray(firstValue(row, ['positiveReasons', 'positive_reasons', 'POSITIVE_REASONS']));
    const riskWarnings = toStringArray(firstValue(row, ['riskWarnings', 'risk_warnings', 'RISK_WARNINGS']));
    const divergenceCodes = toStringArray(firstValue(row, ['divergenceCodes', 'divergence_codes', 'DIVERGENCE_CODES']));
    return {
      asOfDate: safeLegacyText(firstValue(row, ['asOfDate', 'as_of_date', 'AS_OF_DATE']), ''),
      breadthDelta1D: toNumber(firstValue(row, ['breadthDelta1D', 'breadth_delta_1d', 'BREADTH_DELTA_1D'])),
      breadthDelta5D: toNumber(firstValue(row, ['breadthDelta5D', 'breadth_delta_5d', 'BREADTH_DELTA_5D'])),
      breadthDelta21D: toNumber(firstValue(row, ['breadthDelta21D', 'breadth_delta_21d', 'BREADTH_DELTA_21D'])),
      breadthDirection: safeLegacyText(firstValue(row, ['breadthDirection', 'breadth_direction', 'BREADTH_DIRECTION']), '').trim() || undefined,
      countBreadth: toNumber(firstValue(row, ['countBreadth', 'count_breadth', 'COUNT_BREADTH'])),
      confidence,
      confidenceScore: toNumber(firstValue(row, ['confidenceScore', 'confidence_score', 'CONFIDENCE_SCORE'])),
      configuredWeights: toNumberRecord(firstValue(row, ['configuredWeights', 'configured_weights', 'CONFIGURED_WEIGHTS'])),
      concentrationHhi: toNumber(firstValue(row, ['concentrationHhi', 'concentration_hhi', 'CONCENTRATION_HHI'])),
      coveragePercent: toNumber(firstValue(row, ['coveragePercent', 'coverage_percent', 'COVERAGE_PERCENT'])),
      currentRank: toNumber(firstValue(row, ['currentRank', 'current_rank', 'CURRENT_RANK'])),
      dataQualityScore: toNumber(firstValue(row, ['dataQualityScore', 'data_quality_score', 'DATA_QUALITY_SCORE'])),
      dataQualityStatus: safeLegacyText(firstValue(row, ['dataQualityStatus', 'data_quality_status', 'DATA_QUALITY_STATUS']), '').trim() || undefined,
      divergenceCodes,
      effectiveWeights: toNumberRecord(firstValue(row, ['effectiveWeights', 'effective_weights', 'EFFECTIVE_WEIGHTS'])),
      eligibleStockCount: toNumber(firstValue(row, ['eligibleStockCount', 'eligible_stock_count', 'ELIGIBLE_STOCK_COUNT'])),
      breadthScore,
      effectiveDate: safeLegacyText(firstValue(row, ['effectiveDate', 'effective_date', 'EFFECTIVE_DATE']), ''),
      ffmcBreadth: toNumber(firstValue(row, ['ffmcBreadth', 'ffmc_breadth', 'FFMC_BREADTH'])),
      finalRotationScore: toNumber(firstValue(row, ['finalRotationScore', 'final_rotation_score', 'FINAL_ROTATION_SCORE'])),
      historyCoveragePercent: toNumber(firstValue(row, ['historyCoveragePercent', 'history_coverage_percent', 'HISTORY_COVERAGE_PERCENT'])),
      latestDataDate: safeLegacyText(firstValue(row, ['latestDataDate', 'latest_data_date', 'LATEST_DATA_DATE']), ''),
      legacyDisplayScore: toNumber(firstValue(row, ['legacyDisplayScore', 'legacy_display_score', 'LEGACY_DISPLAY_SCORE'])),
      mcapBreadth: toNumber(firstValue(row, ['mcapBreadth', 'mcap_breadth', 'MCAP_BREADTH'])),
      maxDrawdown126: toNumber(firstValue(row, ['maxDrawdown126', 'max_drawdown_126', 'MAX_DRAWDOWN_126'])),
      maxDrawdown252: toNumber(firstValue(row, ['maxDrawdown252', 'max_drawdown_252', 'MAX_DRAWDOWN_252'])),
      moneyFlowCoveragePercent: toNumber(firstValue(row, ['moneyFlowCoveragePercent', 'money_flow_coverage_percent', 'MONEY_FLOW_COVERAGE_PERCENT'])),
      moneyFlowDirection: safeLegacyText(firstValue(row, ['moneyFlowDirection', 'money_flow_direction', 'MONEY_FLOW_DIRECTION']), '').trim() || undefined,
      moneyFlowScore,
      momentumAccelerationRaw: toNumber(firstValue(row, ['momentumAccelerationRaw', 'momentum_acceleration_raw', 'MOMENTUM_ACCELERATION_RAW'])),
      momentumAccelerationScore: toNumber(firstValue(row, ['momentumAccelerationScore', 'momentum_acceleration_score', 'MOMENTUM_ACCELERATION_SCORE'])),
      momentumDirection: safeLegacyText(firstValue(row, ['momentumDirection', 'momentum_direction', 'MOMENTUM_DIRECTION']), '').trim() || undefined,
      momentumScore,
      phaseChangedAt: safeLegacyText(firstValue(row, ['phaseChangedAt', 'phase_changed_at', 'PHASE_CHANGED_AT']), '').trim() || undefined,
      phaseDurationDays: toNumber(firstValue(row, ['phaseDurationDays', 'phase_duration_days', 'PHASE_DURATION_DAYS'])),
      positiveReasons,
      previousPhase: safeLegacyText(firstValue(row, ['previousPhase', 'previous_phase', 'PREVIOUS_PHASE']), '').trim() || undefined,
      rankChange1D: toNumber(firstValue(row, ['rankChange1D', 'rank_change_1d', 'RANK_CHANGE_1D'])),
      rankChange1M: toNumber(firstValue(row, ['rankChange1M', 'rank_change_1m', 'RANK_CHANGE_1M'])),
      rankChange1W: toNumber(firstValue(row, ['rankChange1W', 'rank_change_1w', 'RANK_CHANGE_1W'])),
      reasonCodes,
      relativeReturn21: toNumber(firstValue(row, ['relativeReturn21', 'relative_return_21', 'RELATIVE_RETURN_21'])),
      relativeReturn63: toNumber(firstValue(row, ['relativeReturn63', 'relative_return_63', 'RELATIVE_RETURN_63'])),
      relativeReturn126: toNumber(firstValue(row, ['relativeReturn126', 'relative_return_126', 'RELATIVE_RETURN_126'])),
      relativeReturn252: toNumber(firstValue(row, ['relativeReturn252', 'relative_return_252', 'RELATIVE_RETURN_252'])),
      riskRegime: safeLegacyText(firstValue(row, ['riskRegime', 'risk_regime', 'RISK_REGIME']), '').trim() || undefined,
      riskScore,
      riskWarnings,
      rotationBand: safeLegacyText(firstValue(row, ['rotationBand', 'rotation_band', 'ROTATION_BAND']), '').trim() || undefined,
      rsi50Pct: toNumber(firstValue(row, ['rsi50Percent', 'rsi50_percent', 'RSI50_PERCENT', 'rsi50Pct', 'rsi50_pct', 'RSI50_PCT', 'rsi50_gt_0', 'rsi50_gt0', 'RSI50_GT_0', 'RSI50_GT0', 'RSI50', 'RSI50 > 0'])),
      rsi55Pct: toNumber(firstValue(row, ['rsi55Percent', 'rsi55_percent', 'RSI55_PERCENT', 'rsi55Pct', 'rsi55_pct', 'RSI55_PCT', 'rsi55_gt_0', 'rsi55_gt0', 'RSI55_GT_0', 'RSI55_GT0', 'RSI55', 'RSI55 > 0'])),
      rotationPhase,
      rotationScore,
      scoreChange1D: toNumber(firstValue(row, ['scoreChange1D', 'score_change_1d', 'SCORE_CHANGE_1D'])),
      scoreChange1W: toNumber(firstValue(row, ['scoreChange1W', 'score_change_1w', 'SCORE_CHANGE_1W'])),
      sectorCode: sectorToken.toUpperCase(),
      sectorName: safeLegacyText(firstValue(row, ['sectorName', 'sector_name', 'SECTOR_NAME', 'sector', 'SECTOR']), sectorToken || 'Unknown'),
      sma100Pct: toNumber(firstValue(row, ['sma100Percent', 'sma100_percent', 'SMA100_PERCENT', 'sma100Pct', 'sma100_pct', 'SMA100_PCT', 'sma100', 'SMA100', 'SMA_100'])),
      sma200Pct: toNumber(firstValue(row, ['sma200Percent', 'sma200_percent', 'SMA200_PERCENT', 'sma200Pct', 'sma200_pct', 'SMA200_PCT', 'sma200', 'SMA200', 'SMA_200'])),
      sma20Pct: toNumber(firstValue(row, ['sma20Percent', 'sma20_percent', 'SMA20_PERCENT', 'sma20Pct', 'sma20_pct', 'SMA20_PCT', 'sma20', 'SMA20', 'SMA_20'])),
      sma50Pct: toNumber(firstValue(row, ['sma50Percent', 'sma50_percent', 'SMA50_PERCENT', 'sma50Pct', 'sma50_pct', 'SMA50_PCT', 'sma50', 'SMA50', 'SMA_50'])),
      bullishStackPercent: toNumber(firstValue(row, ['bullishStackPercent', 'bullish_stack_percent', 'BULLISH_STACK_PERCENT'])),
      staleStockCount: toNumber(firstValue(row, ['staleStockCount', 'stale_stock_count', 'STALE_STOCK_COUNT'])),
      stockConfirmationScreening: safeLegacyText(firstValue(row, ['stockConfirmationScreening', 'stock_confirmation_screening', 'strengthLabel', 'score', 'SCORE']), label),
      summaryExplanation: safeLegacyText(firstValue(row, ['summaryExplanation', 'summary_explanation', 'SUMMARY_EXPLANATION']), '').trim() || undefined,
      totalStocks: toNumber(firstValue(row, ['totalStocks', 'total_stocks', 'totalSymbols', 'total_symbols', 'stockCount', 'stock_count', 'TOTAL_STOCKS', 'TOTAL_SYMBOLS', 'STOCK_COUNT'])),
      tableName: safeLegacyText(firstValue(row, ['tableName', 'table_name', 'TABLE_NAME']), ''),
      trendScore,
      trendState: safeLegacyText(firstValue(row, ['trendState', 'trend_state', 'TREND_STATE']), '').trim() || undefined,
      validIndicatorCount: toNumber(firstValue(row, ['validIndicatorCount', 'valid_indicator_count', 'VALID_INDICATOR_COUNT'])),
      validPriceCount: toNumber(firstValue(row, ['validPriceCount', 'valid_price_count', 'VALID_PRICE_COUNT'])),
      volatility63: toNumber(firstValue(row, ['volatility63', 'volatility_63', 'VOLATILITY_63'])),
      weightRedistributionApplied: toOptionalBoolean(firstValue(row, ['weightRedistributionApplied', 'weight_redistribution_applied', 'WEIGHT_REDISTRIBUTION_APPLIED'])),
    };
  }).filter((row) => row.sectorCode && row.sectorCode !== 'BANK');
}

export function adaptSectorWisePayload(payload: unknown): {
  asOfDate: string;
  generatedAt: string;
  isStale: boolean;
  loadedAt: string;
  modelVersion: string;
  page: number;
  parent: UnknownRecord;
  rows: SectorWiseRow[];
  runId: string;
  source: string;
  staleReason: string;
  technicalSourceDate: string;
  totalCount: number;
  totalPages: number;
  version: string;
} {
  const source = asRecord(payload);
  const sourceText = safeLegacyText(source.source, '');
  const staleReason = safeLegacyText(source.staleReason ?? source.stale_reason, '');
  const rows = extractRows(payload, ['rows', 'stocks', 'data']).map((raw) => {
    const row = asRecord(raw);
    return {
      ...row,
      ath: firstValue(row, ['ath', 'ath_price', 'ATH']),
      athDate: firstValue(row, ['athDate', 'ath_date', 'ATH_DATE']),
      breakoutStatus: firstValue(row, ['breakoutStatus', 'breakout_status', 'BREAKOUT_STATUS']),
      confidence: firstValue(row, ['confidence', 'CONFIDENCE']),
      ema100: firstValue(row, ['ema100', 'EMA100']),
      ema100Flag: resolveEmaFlag(row, 100),
      ema200: firstValue(row, ['ema200', 'EMA200']),
      ema200Flag: resolveEmaFlag(row, 200),
      ema20: firstValue(row, ['ema20', 'EMA20']),
      ema20Flag: resolveEmaFlag(row, 20),
      ema50: firstValue(row, ['ema50', 'EMA50']),
      ema50Flag: resolveEmaFlag(row, 50),
      gap: firstValue(row, ['gap', 'gap_percent', 'GAP']),
      gapPct: firstValue(row, ['gapPct', 'gap_pct', 'gapPercent', 'GAP_PCT']),
      high52w: firstValue(row, ['high52w', 'high_52w', 'week_52_high', 'week52HighLevel', 'WEEK52HIGHLEVEL', '52wh', '52WH', 'HIGH52W', 'HIGH_52W']),
      index: firstValue(row, ['index', 'INDEX', 'index_value', 'INDEX_VALUE', 'market_cap_index', 'MARKET_CAP_INDEX', 'indexCategory', 'index_category']),
      low52w: firstValue(row, ['low52w', 'low_52w', 'week_52_low', 'week52LowLevel', 'WEEK52LOWLEVEL', '52wl', '52WL', 'LOW52W', 'LOW_52W']),
      ltcDate: firstValue(row, ['ltcDate', 'ltc_date', 'trading_date', 'LTC_DATE', 'TRADING_DATE']),
      price: firstValue(row, ['price', 'close_price', 'closePrice', 'CLOSE_PRICE', 'PRICE']),
      score: firstValue(row, ['score', 'signalScore', 'signal_score', 'SCORE', 'masterScore', 'master_score']),
      scoreBreakdown: firstValue(row, ['scoreBreakdown', 'score_breakdown', 'scoreBreakdownJson', 'score_breakdown_json', 'masterScoreBreakdown', 'master_score_breakdown']),
      scoreGrade: firstValue(row, ['scoreGrade', 'score_grade', 'SCORE_GRADE', 'masterScoreGrade', 'master_score_grade']),
      scoreSort: firstValue(row, ['scoreSort', 'score_sort', 'SCORE_SORT', 'masterScoreSort', 'master_score_sort']),
      scoreSource: firstValue(row, ['scoreSource', 'score_source', 'SCORE_SOURCE', 'masterScoreSource', 'master_score_source', 'trendSource', 'masterTrendSource']),
      sNo: firstValue(row, ['sNo', 's_no', 'S_NO']),
      stock: normalizeStockDisplay(firstValue(row, ['stock', 'symbol', 'SYMBOL'])),
      totalMcap: firstValue(row, ['totalMcap', 'total_mcap', 'TOTAL_MCAP', 'TOTAL_MCAP_CR', 'mcap', 'MCAP']),
      mcapRank: firstValue(row, ['mcapRank', 'mcap_rank', 'MCAP_RANK', 'MCAPRank', 'market_cap_rank', 'MARKET_CAP_RANK', 'marketCapRank', 'MCAPRANK', 'MCAP_RANKING', 'mcapRanking', 'mcap_ranking', 'MARKET_CAP_RANKING', 'rank', 'RANK']),
      riskStatus: firstValue(row, ['riskStatus', 'risk_status', 'RISK_STATUS']),
      rsVsBenchmark: firstValue(row, ['rsVsBenchmark', 'rs_vs_benchmark', 'RS_VS_BENCHMARK', 'rs_vs_bmark', 'RS_VS_BMARK']),
      rsVsSector: firstValue(row, ['rsVsSector', 'rs_vs_sector', 'RS_VS_SECTOR']),
      sectorPhase: firstValue(row, ['sectorPhase', 'sector_phase', 'SECTOR_PHASE']),
      sectorScore: firstValue(row, ['sectorScore', 'sector_score', 'SECTOR_SCORE']),
      trend: firstValue(row, ['trend', 'trendDirection', 'trend_direction', 'TREND']),
      trendSort: firstValue(row, ['trendSort', 'trend_sort', 'trendDirectionSort', 'trend_direction_sort']),
      volumeDeliveryStatus: firstValue(row, ['volumeDeliveryStatus', 'volume_delivery_status', 'VOL_DELIVERY', 'VOLUME_DELIVERY_STATUS']),
      stockEdgeScore: firstValue(row, ['stockEdgeScore', 'stock_edge_score', 'STOCK_EDGE_SCORE']),
      stockEdgeBand: firstValue(row, ['stockEdgeBand', 'stock_edge_band', 'STOCK_EDGE_BAND']),
      trendState: firstValue(row, ['trendState', 'trend_state', 'TREND_STATE']),
      coverage: firstValue(row, ['coverage', 'factorCoverage', 'factor_coverage', 'COVERAGE']),
      factorScores: firstValue(row, ['factorScores', 'factor_scores', 'FACTOR_SCORES']),
      return21: firstValue(row, ['return21', 'return_21', 'RETURN21']),
      return63: firstValue(row, ['return63', 'return_63', 'RETURN63']),
      return126: firstValue(row, ['return126', 'return_126', 'RETURN126']),
      relativeMomentumScore: firstValue(row, ['relativeMomentumScore', 'relative_momentum_score', 'RELATIVE_MOMENTUM_SCORE']),
      rsi: firstValue(row, ['rsi', 'RSI']),
      macd: firstValue(row, ['macd', 'MACD']),
      macdHist: firstValue(row, ['macdHist', 'macd_hist', 'MACD_HIST']),
      adx14: firstValue(row, ['adx14', 'adx', 'ADX14', 'ADX']),
      volumeRatio: firstValue(row, ['volumeRatio', 'volume_ratio', 'VOLUME_RATIO']),
      deliveryScore: firstValue(row, ['deliveryScore', 'delivery_score', 'DELIVERY_SCORE']),
      riskLevel: firstValue(row, ['riskLevel', 'risk_level', 'RISK_LEVEL']),
      reasonCodes: firstValue(row, ['reasonCodes', 'reason_codes', 'REASON_CODES']),
      warnings: firstValue(row, ['warnings', 'WARNINGS']),
    };
  });
  const totalCount = Math.max(0, Number(source.totalCount ?? source.totalRows ?? rows.length));
  const pageSize = Math.max(1, Number(source.pageSize ?? 25));
  return {
    asOfDate: safeLegacyText(source.asOfDate ?? source.as_of_date, ''),
    generatedAt: safeLegacyText(source.generatedAt ?? source.generated_at, ''),
    isStale: Boolean(source.isStale || source.is_stale || source.stale || sourceText === 'stale_snapshot' || staleReason),
    loadedAt: safeLegacyText(source.loadedAt ?? source.generatedAt ?? source.generated_at, ''),
    modelVersion: safeLegacyText(source.modelVersion ?? source.model_version, ''),
    page: Math.max(1, Number(source.page ?? 1)),
    parent: asRecord(source.parent),
    rows,
    runId: safeLegacyText(source.runId ?? source.run_id, ''),
    source: sourceText,
    staleReason,
    technicalSourceDate: safeLegacyText(source.technicalSourceDate ?? source.technical_source_date, ''),
    totalCount,
    totalPages: Math.max(1, Number(source.totalPages ?? (Math.ceil(totalCount / pageSize) || 1))),
    version: safeLegacyText(source.version, ''),
  };
}
