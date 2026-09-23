export type MarketCapWireRow = {
  SYMBOL: string;
  COMPANY_NAME?: string | null;
  SECTOR?: string | null;
  INDEX?: string | null;
  TRADING_DATE?: string | null;
  MCAP?: number | string | null;
  FFMC?: number | string | null;
  MCAP_RANK?: number | string | null;
  SHARES_OUTSTANDING?: number | string | null;
  LTC_DATE?: string | null;
  PRICE?: number | string | null;
  CHANGE?: number | string | null;
  CHANGE_PCT?: number | string | null;
  VOLUME?: number | string | null;
  [key: string]: unknown;
};

export type TechnicalIndicatorWireRow = {
  SYMBOL: string;
  COMPANY_NAME?: string | null;
  SECTOR?: string | null;
  INDEX?: string | null;
  TRADING_DATE?: string | null;
  PRICE?: number | string | null;
  CHANGE?: number | string | null;
  CHANGE_PCT?: number | string | null;
  VOLUME?: number | string | null;
  EMA20?: number | string | null;
  EMA50?: number | string | null;
  EMA100?: number | string | null;
  EMA200?: number | string | null;
  RSI50?: number | string | null;
  ADX14?: number | string | null;
  ATR14?: number | string | null;
  TREND_DIRECTION?: string | null;
  SCORE?: number | string | null;
  SIGNALSCORE?: number | string | null;
  [key: string]: unknown;
};

export type DeliveryWireRow = {
  SYMBOL: string;
  COMPANY_NAME?: string | null;
  SECTOR?: string | null;
  INDEX?: string | null;
  TRADING_DATE?: string | null;
  LTC_DATE?: string | null;
  PRICE?: number | string | null;
  CHANGE?: number | string | null;
  CHANGE_PCT?: number | string | null;
  VOLUME?: number | string | null;
  DELIVERY_QTY?: number | string | null;
  DELIVERY_PCT?: number | string | null;
  DELIVERY_SCORE?: number | string | null;
  [key: string]: unknown;
};
