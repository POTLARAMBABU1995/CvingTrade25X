import type {
  DeliveryRow,
  DeliveryWireRow,
  MarketCapRow,
  MarketCapWireRow,
  TechnicalIndicatorRow,
  TechnicalIndicatorWireRow,
} from '../../types';

function toNullableNumber(value: number | string | null | undefined): number | null {
  if (value === undefined || value === null || value === '') {
    return null;
  }

  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toNullableString(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }

  const normalized = value.trim();
  return normalized ? normalized : null;
}

function buildStockBase<Row extends { SYMBOL: string; COMPANY_NAME?: string | null; SECTOR?: string | null; INDEX?: string | null; TRADING_DATE?: string | null; PRICE?: number | string | null; CHANGE?: number | string | null; CHANGE_PCT?: number | string | null; VOLUME?: number | string | null }>(
  row: Row,
) {
  return {
    symbol: row.SYMBOL,
    companyName: toNullableString(row.COMPANY_NAME),
    sector: toNullableString(row.SECTOR),
    index: toNullableString(row.INDEX),
    tradingDate: toNullableString(row.TRADING_DATE),
    price: toNullableNumber(row.PRICE),
    change: toNullableNumber(row.CHANGE),
    changePct: toNullableNumber(row.CHANGE_PCT),
    volume: toNullableNumber(row.VOLUME),
  };
}

export function adaptMarketCapWireRow(row: MarketCapWireRow): MarketCapRow {
  return {
    ...buildStockBase(row),
    ltcDate: toNullableString(row.LTC_DATE),
    totalMcap: toNullableNumber(row.MCAP),
    freeFloatMcap: toNullableNumber(row.FFMC),
    mcapRank: toNullableNumber(row.MCAP_RANK),
    sharesOutstanding: toNullableNumber(row.SHARES_OUTSTANDING),
  };
}

export function adaptTechnicalIndicatorWireRow(row: TechnicalIndicatorWireRow): TechnicalIndicatorRow {
  return {
    ...buildStockBase(row),
    ema20: toNullableNumber(row.EMA20),
    ema50: toNullableNumber(row.EMA50),
    ema100: toNullableNumber(row.EMA100),
    ema200: toNullableNumber(row.EMA200),
    rsi50: toNullableNumber(row.RSI50),
    adx14: toNullableNumber(row.ADX14),
    atr14: toNullableNumber(row.ATR14),
    trendDirection: toNullableString(row.TREND_DIRECTION),
    score: toNullableNumber(row.SCORE),
    signalScore: toNullableNumber(row.SIGNALSCORE),
  };
}

export function adaptDeliveryWireRow(row: DeliveryWireRow): DeliveryRow {
  return {
    ...buildStockBase(row),
    tradingDate: toNullableString(row.TRADING_DATE),
    ltcDate: toNullableString(row.LTC_DATE),
    deliveryQty: toNullableNumber(row.DELIVERY_QTY),
    deliveryPct: toNullableNumber(row.DELIVERY_PCT),
    deliveryScore: toNullableNumber(row.DELIVERY_SCORE),
  };
}
