import { legacyApiGet, type RequestOptions } from '../api/client';
import type {
  AsuraV3CostSummaryRow,
  AsuraV3DashboardSummary,
  AsuraV3HealthPayload,
  AsuraV3LatestSignalRow,
  AsuraV3LatestSignalsQuery,
  AsuraV3LatestSignalsResponse,
  AsuraV3RiskSummaryRow,
  AsuraV3SymbolRatingRow,
  AsuraV3YearlySummaryRow,
} from '../types/asuraV3';

const ASURA_V3_API_PREFIX = '/api/strategy/asura-v3';
const ASURA_V3_TIMEOUT_MS = 60000;

type UnknownRecord = Record<string, unknown>;

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' ? value as UnknownRecord : {};
}

function asRows(value: unknown): UnknownRecord[] {
  if (!Array.isArray(value)) return [];
  return value.filter((row): row is UnknownRecord => Boolean(row) && typeof row === 'object');
}

function pick(source: UnknownRecord, keys: readonly string[]): unknown {
  for (const key of keys) {
    const value = source[key];
    if (value === null || value === undefined) continue;
    if (typeof value === 'string' && value.trim() === '') continue;
    return value;
  }
  return undefined;
}

function asString(value: unknown, fallback = ''): string {
  const text = String(value ?? '').trim();
  return text || fallback;
}

function asNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function asYearNumber(value: unknown): number | null {
  const numeric = asNumber(value);
  if (numeric !== null) return Math.trunc(numeric);

  const text = asString(value);
  const match = text.match(/^(\d{4})(?:$|[-/T\s])/);
  if (!match) return null;

  const parsed = Number(match[1]);
  return Number.isFinite(parsed) ? parsed : null;
}

function asInteger(value: unknown): number {
  const parsed = asNumber(value);
  return parsed === null ? 0 : Math.trunc(parsed);
}

function toDateText(value: unknown): string | null {
  const text = asString(value);
  if (!text) return null;
  const maybeIso = text.match(/^(\d{4}-\d{2}-\d{2})/);
  if (maybeIso) return maybeIso[1];
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return text;
  return parsed.toISOString().slice(0, 10);
}

function requestOptions(options: RequestOptions = {}, action: string): RequestOptions {
  return {
    ...options,
    diagnostic: {
      action,
      component: 'AsuraV3StrategyPage',
      page: '/app/strategy/asura-v3',
    },
    timeoutMs: options.timeoutMs ?? ASURA_V3_TIMEOUT_MS,
  };
}

function normalizeDashboardSummary(row: UnknownRecord): AsuraV3DashboardSummary {
  return {
    strategyName: asString(pick(row, ['strategyName', 'strategy_name', 'STRATEGY_NAME']), 'ASURA_V3_3_HIGH_WIN_MODE'),
    strategyCode: asString(pick(row, ['strategyCode', 'strategy_code', 'STRATEGY_CODE']), 'ASURA_V3_TECH'),
    runId: asString(pick(row, ['runId', 'run_id', 'RUN_ID']), 'BT_ASURA_V3_TEST_28Y'),
    latestSignalDate: toDateText(pick(row, ['latestSignalDate', 'latest_signal_date', 'LATEST_SIGNAL_DATE'])),
    totalTrades: asNumber(pick(row, ['totalTrades', 'total_trades', 'TOTAL_TRADES'])),
    successCount: asNumber(pick(row, ['successCount', 'success_count', 'SUCCESS_COUNT'])),
    failureCount: asNumber(pick(row, ['failureCount', 'failure_count', 'FAILURE_COUNT'])),
    openCount: asNumber(pick(row, ['openCount', 'open_count', 'OPEN_COUNT'])),
    successRatePct: asNumber(pick(row, ['successRatePct', 'success_rate_pct', 'SUCCESS_RATE_PCT'])),
    failureRatePct: asNumber(pick(row, ['failureRatePct', 'failure_rate_pct', 'FAILURE_RATE_PCT'])),
    avgTradingDays: asNumber(pick(row, ['avgTradingDays', 'avg_trading_days', 'AVG_TRADING_DAYS'])),
    totalPnlPercent: asNumber(pick(row, ['totalPnlPercent', 'total_pnl_percent', 'TOTAL_PNL_PERCENT'])),
    avgRMultiple: asNumber(pick(row, ['avgRMultiple', 'avg_r_multiple', 'AVG_R_MULTIPLE'])),
    startDate: toDateText(pick(row, ['startDate', 'start_date', 'START_DATE'])),
    endDate: toDateText(pick(row, ['endDate', 'end_date', 'END_DATE'])),
    totalSymbols: asNumber(pick(row, ['totalSymbols', 'total_symbols', 'TOTAL_SYMBOLS'])),
    maxDrawdown: asNumber(pick(row, ['maxDrawdown', 'max_drawdown', 'MAX_DRAWDOWN'])),
    maxConsecutiveFailures: asNumber(pick(row, ['maxConsecutiveFailures', 'max_consecutive_failures', 'MAX_CONSECUTIVE_FAILURES'])),
    roundTripCostPct: asNumber(pick(row, ['roundTripCostPct', 'round_trip_cost_pct', 'ROUND_TRIP_COST_PCT'])),
    netPnlPercent: asNumber(pick(row, ['netPnlPercent', 'net_pnl_percent', 'NET_PNL_PERCENT'])),
    avgNetPnlPerTrade: asNumber(pick(row, ['avgNetPnlPerTrade', 'avg_net_pnl_per_trade', 'AVG_NET_PNL_PER_TRADE'])),
    dashboardRefreshTimestamp: toDateText(
      pick(row, ['dashboardRefreshTimestamp', 'dashboard_refresh_timestamp', 'lastRefreshTs', 'LAST_REFRESH_TS', 'updatedAt', 'UPDATED_AT']),
    ),
    raw: row,
  };
}

function normalizeLatestRow(row: UnknownRecord): AsuraV3LatestSignalRow {
  const price = asNumber(pick(row, ['price', 'PRICE']));
  const entry = asNumber(pick(row, ['entryPrice', 'entry_price', 'ENTRY_PRICE'])) ?? price;
  const rawRrr = pick(row, ['rrrRaw', 'rrr', 'RRR']);
  const normalizedRrr: number | string | null = typeof rawRrr === 'number' || typeof rawRrr === 'string'
    ? rawRrr
    : null;
  return {
    symbol: asString(pick(row, ['symbol', 'SYMBOL'])),
    signalDate: toDateText(pick(row, ['signalDate', 'signal_date', 'SIGNAL_DATE'])),
    symbolRating: asString(pick(row, ['symbolRating', 'symbol_rating', 'SYMBOL_RATING'])),
    price,
    entryPrice: entry,
    stopLoss: asNumber(pick(row, ['stopLoss', 'stop_loss', 'STOP_LOSS'])),
    target1R: asNumber(pick(row, ['target1R', 'target1r', 'target_1r', 'TARGET_1R'])),
    rrrRaw: normalizedRrr,
    signalScore: asNumber(pick(row, ['signalScore', 'signal_score', 'SIGNAL_SCORE'])),
    signalGrade: asString(pick(row, ['signalGrade', 'signal_grade', 'SIGNAL_GRADE'])),
    rsi14: asNumber(pick(row, ['rsi14', 'RSI14'])),
    rsiPrev1d: asNumber(pick(row, ['rsiPrev1d', 'rsi_prev_1d', 'RSI_PREV_1D'])),
    rsiPrev5d: asNumber(pick(row, ['rsiPrev5d', 'rsi_prev_5d', 'RSI_PREV_5D'])),
    macdHist: asNumber(pick(row, ['macdHist', 'macd_hist', 'MACD_HIST'])),
    adx14: asNumber(pick(row, ['adx14', 'ADX14'])),
    atrPercent: asNumber(pick(row, ['atrPercent', 'atr_percent', 'ATR_PERCENT'])),
    riskAtr: asNumber(pick(row, ['riskAtr', 'risk_atr', 'RISK_ATR'])),
    volumeRatio20: asNumber(pick(row, ['volumeRatio20', 'volume_ratio_20', 'VOLUME_RATIO_20'])),
    move1dPct: asNumber(pick(row, ['move1dPct', 'move_1d_pct', 'MOVE_1D_PCT'])),
    move1wPct: asNumber(pick(row, ['move1wPct', 'move_1w_pct', 'MOVE_1W_PCT'])),
    move1mPct: asNumber(pick(row, ['move1mPct', 'move_1m_pct', 'MOVE_1M_PCT'])),
    supportGapPct: asNumber(pick(row, ['supportGapPct', 'support_gap_pct', 'SUPPORT_GAP_PCT'])),
    resistanceGapPct: asNumber(pick(row, ['resistanceGapPct', 'resistance_gap_pct', 'RESISTANCE_GAP_PCT'])),
    trendDirection: asString(pick(row, ['trendDirection', 'trend_direction', 'TREND_DIRECTION'])),
    emaStack: asString(pick(row, ['emaStack', 'ema_stack', 'EMA_STACK'])),
    athPrice: asNumber(pick(row, ['athPrice', 'ath_price', 'ATH_PRICE'])),
    athGapPct: asNumber(pick(row, ['athGapPct', 'ath_gap_pct', 'ATH_GAP_PCT'])),
    raw: row,
  };
}

function normalizeYearlyRow(row: UnknownRecord): AsuraV3YearlySummaryRow {
  return {
    signalYear: asYearNumber(pick(row, ['signalYear', 'signal_year', 'SIGNAL_YEAR'])),
    totalTrades: asNumber(pick(row, ['totalTrades', 'total_trades', 'TOTAL_TRADES'])),
    successCount: asNumber(pick(row, ['successCount', 'success_count', 'SUCCESS_COUNT'])),
    failureCount: asNumber(pick(row, ['failureCount', 'failure_count', 'FAILURE_COUNT'])),
    openCount: asNumber(pick(row, ['openCount', 'open_count', 'OPEN_COUNT'])),
    successRatePct: asNumber(pick(row, ['successRatePct', 'success_rate_pct', 'SUCCESS_RATE_PCT'])),
    failureRatePct: asNumber(pick(row, ['failureRatePct', 'failure_rate_pct', 'FAILURE_RATE_PCT'])),
    avgTradingDays: asNumber(pick(row, ['avgTradingDays', 'avg_trading_days', 'AVG_TRADING_DAYS'])),
    totalPnlPercent: asNumber(pick(row, ['totalPnlPercent', 'total_pnl_percent', 'TOTAL_PNL_PERCENT'])),
    avgRMultiple: asNumber(pick(row, ['avgRMultiple', 'avg_r_multiple', 'AVG_R_MULTIPLE'])),
    totalSymbols: asNumber(pick(row, ['totalSymbols', 'total_symbols', 'TOTAL_SYMBOLS'])),
    raw: row,
  };
}

function normalizeCostRow(row: UnknownRecord): AsuraV3CostSummaryRow {
  return {
    costScenario: asString(pick(row, ['costScenario', 'cost_scenario', 'COST_SCENARIO'])),
    roundTripCostPct: asNumber(pick(row, ['roundTripCostPct', 'round_trip_cost_pct', 'ROUND_TRIP_COST_PCT'])),
    closedTrades: asNumber(pick(row, ['closedTrades', 'closed_trades', 'CLOSED_TRADES'])),
    successRatePct: asNumber(pick(row, ['successRatePct', 'success_rate_pct', 'SUCCESS_RATE_PCT'])),
    grossPnlPercent: asNumber(pick(row, ['grossPnlPercent', 'gross_pnl_percent', 'GROSS_PNL_PERCENT'])),
    netPnlPercent: asNumber(pick(row, ['netPnlPercent', 'net_pnl_percent', 'NET_PNL_PERCENT'])),
    avgNetPnlPerTrade: asNumber(pick(row, ['avgNetPnlPerTrade', 'avg_net_pnl_per_trade', 'AVG_NET_PNL_PER_TRADE'])),
    avgTradingDays: asNumber(pick(row, ['avgTradingDays', 'avg_trading_days', 'AVG_TRADING_DAYS'])),
    raw: row,
  };
}

function normalizeRiskRow(row: UnknownRecord): AsuraV3RiskSummaryRow {
  return {
    closedTrades: asNumber(pick(row, ['closedTrades', 'closed_trades', 'CLOSED_TRADES'])),
    successCount: asNumber(pick(row, ['successCount', 'success_count', 'SUCCESS_COUNT'])),
    failureCount: asNumber(pick(row, ['failureCount', 'failure_count', 'FAILURE_COUNT'])),
    successRatePct: asNumber(pick(row, ['successRatePct', 'success_rate_pct', 'SUCCESS_RATE_PCT'])),
    maxDrawdown: asNumber(pick(row, ['maxDrawdown', 'max_drawdown', 'MAX_DRAWDOWN'])),
    maxConsecutiveFailures: asNumber(pick(row, ['maxConsecutiveFailures', 'max_consecutive_failures', 'MAX_CONSECUTIVE_FAILURES'])),
    avgTradingDays: asNumber(pick(row, ['avgTradingDays', 'avg_trading_days', 'AVG_TRADING_DAYS'])),
    finalCumulativePnl: asNumber(pick(row, ['finalCumulativePnl', 'final_cumulative_pnl', 'FINAL_CUMULATIVE_PNL'])),
    raw: row,
  };
}

function normalizeRatingRow(row: UnknownRecord): AsuraV3SymbolRatingRow {
  return {
    symbolRating: asString(pick(row, ['symbolRating', 'symbol_rating', 'SYMBOL_RATING'])),
    totalSymbols: asInteger(pick(row, ['totalSymbols', 'total_symbols', 'TOTAL_SYMBOLS', 'count', 'COUNT'])),
    raw: row,
  };
}

export async function fetchAsuraV3DashboardSummary(options: RequestOptions = {}): Promise<AsuraV3DashboardSummary> {
  const payload = await legacyApiGet<unknown>(
    `${ASURA_V3_API_PREFIX}/dashboard-summary`,
    undefined,
    requestOptions(options, 'asura_v3_dashboard_summary'),
  );
  const source = asRecord(payload);
  return normalizeDashboardSummary(asRecord(source.item));
}

export async function fetchAsuraV3LatestSignals(
  query: AsuraV3LatestSignalsQuery = {},
  options: RequestOptions = {},
): Promise<AsuraV3LatestSignalsResponse> {
  const payload = await legacyApiGet<unknown>(
    `${ASURA_V3_API_PREFIX}/latest-signals`,
    {
      q: query.q || undefined,
      rating: query.rating || undefined,
      grade: query.grade || undefined,
      limit: query.limit ?? 25,
      offset: query.offset ?? 0,
      sort_by: query.sortBy || undefined,
      sort_dir: query.sortDir || undefined,
    },
    requestOptions(options, 'asura_v3_latest_signals'),
  );

  const source = asRecord(payload);
  const items = asRows(source.items).map(normalizeLatestRow);
  return {
    items,
    total: asInteger(source.total),
    limit: asInteger(source.limit) || Number(query.limit ?? 25),
    offset: asInteger(source.offset),
  };
}

export async function fetchAsuraV3YearlySummary(options: RequestOptions = {}): Promise<AsuraV3YearlySummaryRow[]> {
  const payload = await legacyApiGet<unknown>(
    `${ASURA_V3_API_PREFIX}/yearly-summary`,
    undefined,
    requestOptions(options, 'asura_v3_yearly_summary'),
  );
  return asRows(asRecord(payload).items).map(normalizeYearlyRow);
}

export async function fetchAsuraV3CostSummary(options: RequestOptions = {}): Promise<AsuraV3CostSummaryRow[]> {
  const payload = await legacyApiGet<unknown>(
    `${ASURA_V3_API_PREFIX}/cost-summary`,
    undefined,
    requestOptions(options, 'asura_v3_cost_summary'),
  );
  return asRows(asRecord(payload).items).map(normalizeCostRow);
}

export async function fetchAsuraV3RiskSummary(options: RequestOptions = {}): Promise<AsuraV3RiskSummaryRow[]> {
  const payload = await legacyApiGet<unknown>(
    `${ASURA_V3_API_PREFIX}/risk-summary`,
    undefined,
    requestOptions(options, 'asura_v3_risk_summary'),
  );
  return asRows(asRecord(payload).items).map(normalizeRiskRow);
}

export async function fetchAsuraV3SymbolRatings(options: RequestOptions = {}): Promise<AsuraV3SymbolRatingRow[]> {
  const payload = await legacyApiGet<unknown>(
    `${ASURA_V3_API_PREFIX}/symbol-ratings`,
    undefined,
    requestOptions(options, 'asura_v3_symbol_ratings'),
  );
  return asRows(asRecord(payload).items).map(normalizeRatingRow);
}

export async function fetchAsuraV3Health(options: RequestOptions = {}): Promise<AsuraV3HealthPayload> {
  const payload = await legacyApiGet<unknown>(
    `${ASURA_V3_API_PREFIX}/health`,
    undefined,
    requestOptions(options, 'asura_v3_health'),
  );
  const source = asRecord(payload);
  return {
    dbReachable: source.dbReachable === true,
    latestSignalDate: toDateText(pick(source, ['latestSignalDate', 'latest_signal_date', 'LATEST_SIGNAL_DATE'])),
    dashboardRefreshTimestamp: toDateText(
      pick(source, ['dashboardRefreshTimestamp', 'dashboard_refresh_timestamp', 'DASHBOARD_REFRESH_TIMESTAMP']),
    ),
    checkedAt: asString(pick(source, ['checkedAt', 'checked_at', 'CHECKED_AT']), new Date().toISOString()),
  };
}

export function normalizeAsuraV3Error(error: unknown, fallback: string): string {
  const text = error instanceof Error ? error.message : String(error ?? '').trim();
  if (!text) return fallback;
  if (/unexpected token|json|html|failed to fetch|networkerror|aborted/i.test(text)) return fallback;
  return text;
}
