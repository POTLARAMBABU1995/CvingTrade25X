export const API_ENDPOINTS = {
  auth: {
    login: '/api/auth/login',
    logout: '/api/auth/logout',
    register: '/api/auth/register',
    reset: '/api/auth/reset',
    session: '/api/auth/session',
  },
  technical: {
    adx: '/api/adx',
    atr14: '/api/atr14',
    delivery: '/api/technicals/delivery',
    emaTrend: '/api/trend',
    latestDate: '/api/trend/latestDate',
    macd: '/api/momentum/macd',
    priceActionManual: '/api/price-action-sr-levels-manually',
    rsi50: '/api/rsi50',
    srLevels: '/api/sr-levels',
    volume: '/api/volume',
  },
  fyers: {
    authStatus: '/api/marketdata/fyers/auth-status',
    authorize: '/api/marketdata/fyers/authorize',
    failedSymbols: '/api/marketdata/fyers/failed-symbols',
    holdings: '/api/marketdata/fyers/holdings',
    jobs: '/api/marketdata/fyers/jobs',
    nifty500Sync: '/api/marketdata/fyers/nifty500-sync',
  },
  sector: {
    breadth: '/api/sectors/breadth',
    hierarchySummary: '/api/sector-hierarchy/summary',
    rotationStocks: '/api/sector-rotation/stocks',
    sectorWiseStocks: '/api/sector/{sectorCode}/stocks/sector-wise',
  },
  marketdata: {
    mergeLatest: '/api/marketdata/merge-latest',
    mergeStatusLatest: '/api/merge/status/latest',
    nseSymbols: '/api/nse-symbols',
    tradingDayVerification: '/api/market-calendar/trading-day-verification',
  },
} as const;

export type ApiEndpointGroup = keyof typeof API_ENDPOINTS;
