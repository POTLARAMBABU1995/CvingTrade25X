import { describe, expect, test, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  fetchBars: vi.fn(),
  fetchDeliveryPayload: vi.fn(),
  fetchSectorWiseSymbol: vi.fn(),
  fetchSrLevelsPayload: vi.fn(),
  fetchSymbols: vi.fn(),
  fetchTechnicalIndicatorPayload: vi.fn(),
  fetchTechnicalScreenerPayload: vi.fn(),
}));

vi.mock('../src/api/bars', () => ({ fetchBars: apiMocks.fetchBars }));
vi.mock('../src/api/symbols', () => ({ fetchSymbols: apiMocks.fetchSymbols }));
vi.mock('../src/services/api/sectorApi', () => ({ fetchSectorWiseSymbol: apiMocks.fetchSectorWiseSymbol }));
vi.mock('../src/services/api/technicalApi', () => ({
  fetchDeliveryPayload: apiMocks.fetchDeliveryPayload,
  fetchSrLevelsPayload: apiMocks.fetchSrLevelsPayload,
  fetchTechnicalIndicatorPayload: apiMocks.fetchTechnicalIndicatorPayload,
  fetchTechnicalScreenerPayload: apiMocks.fetchTechnicalScreenerPayload,
}));

import { buildWatchlistDataRow, estimateTargetTradingDays, fetchWatchlistDataRow } from '../src/services/api/watchlistData';

function mockWatchlistBaseSources() {
  apiMocks.fetchBars.mockImplementation(({ symbol }: { symbol: string }) => Promise.resolve({
    bars: [{ c: 100, h: 102, l: 98 }],
    symbol,
  }));
  apiMocks.fetchSymbols.mockImplementation((symbol: string) => Promise.resolve({
    symbols: [{ exchange: 'NSE', symbol }],
    version: 'test',
  }));
  apiMocks.fetchSectorWiseSymbol.mockResolvedValue({});
  apiMocks.fetchTechnicalScreenerPayload.mockResolvedValue({ count: 0, rows: [] });
  apiMocks.fetchSrLevelsPayload.mockResolvedValue({ rows: [] });
  apiMocks.fetchTechnicalIndicatorPayload.mockResolvedValue({ count: 0, rows: [] });
  apiMocks.fetchDeliveryPayload.mockResolvedValue({ data: [] });
}

describe('Watchlist existing-source adapter', () => {
  test('populates market, setup, levels, targets and confirmation fields', () => {
    const row = buildWatchlistDataRow('NSE:WESTLIFE-EQ', {
      bars: [{ h: 510, l: 495, c: 503.7 }],
      delivery: { symbol: 'WESTLIFE', delivery_pct: 64.5 },
      metadata: { symbol: 'WESTLIFE', sector: 'CONSUMER SERVICES' },
      sr: {
        symbol: 'WESTLIFE',
        supportDisplay: 'S1: 477, S2: 465, S3: 450',
        resistanceDisplay: 'R1: 513.9, R2: 535, R3: 560',
      },
      technical: {
        symbol: 'WESTLIFE', INDEX: 'SMALL', MCAP: 7850.2, price: 503.7,
        trendStructure: 'Strong Uptrend', patternName: 'Ascending Triangle',
        techScore: 88, volumeRatio: 1.7, nearestSupport: 477, nearestResistance: 513.9,
        breakoutStatus: 'Volume Confirmed Breakout',
      },
    });

    expect(row.symbol).toBe('WESTLIFE');
    expect(row.sector).toBe('CONSUMER SERVICES');
    expect(row.ltp).toBe(503.7);
    expect(row.mcap).toBe('7,850.2');
    expect(row.trend).toBe('Strong Uptrend');
    expect(row.pattern).toBe('Ascending Triangle');
    expect(row.setup).toBe('BREAKOUT_CONFIRMED');
    expect(row.support).toEqual([477, 465, 450]);
    expect(row.resistance).toEqual([513.9, 535, 560]);
    expect(row.strongSupport).toBe(477);
    expect(row.strongResistance).toBe(513.9);
    expect(row.targetPrices).toEqual([528.88, 554.07, 579.25]);
    expect(row.targetSources).toEqual(['DYNAMIC', 'DYNAMIC', 'DYNAMIC']);
    expect(row.volumeRatio).toBe(1.7);
    expect(row.delivery).toBe(64.5);
    expect(row.confidence).toBe(88);
  });

  test('keeps partial market data visible when optional technical sources are absent', () => {
    const row = buildWatchlistDataRow('TCS', { bars: [{ h: 4200, l: 4100, c: 4175 }] });
    expect(row.ltp).toBe(4175);
    expect(row.entryLow).toBe(4100);
    expect(row.entryHigh).toBe(4200);
    expect(row.pattern).toBe('Existing data loaded; no active technical pattern');
  });

  test('clones Sector Wise identity and Volume page confirmation values', () => {
    const row = buildWatchlistDataRow('TCS', {
      sectorWise: {
        symbol: 'TCS', sectorCode: 'IT', sectorName: 'IT', INDEX: 'LARGE', MCAP: 850142,
        price: 2349.7, trend: 'Sideways', parent: { phase: 'LEADING' }, stockEdgeScore: 48.47,
      },
      technical: { symbol: 'TCS', INDEX: 'MID', MCAP: 1, price: 2300, trendStructure: 'Downtrend', volumeRatio: 1.1 },
      volume: { symbol: 'TCS', price: 2348, volumeRatio: 2.75 },
    });

    expect(row.sector).toBe('IT');
    expect(row.index).toBe('LARGE');
    expect(row.mcap).toBe('8,50,142');
    expect(row.ltp).toBe(2349.7);
    expect(row.trend).toBe('Sideways');
    expect(row.sectorTrend).toBe('LEADING');
    expect(row.volumeRatio).toBe(2.75);
  });

  test('uses structured combined SR ladders and strongest published levels', () => {
    const row = buildWatchlistDataRow('TCS', {
      sr: {
        symbol: 'TCS', price: 100,
        supportLevels: [
          { price: 98, source: 'manual', touchesTotal: 0 },
          { price: 95, source: 'generated', touchesTotal: 5 },
          { price: 92, source: 'generated', touchesTotal: 2 },
        ],
        resistanceLevels: [
          { price: 105, source: 'manual+generated', touchesTotal: 4 },
          { price: 110, source: 'generated', touchesTotal: 2 },
          { price: 115, source: 'generated', touchesTotal: 1 },
        ],
        strongestSupport: { price: 95 },
        strongestResistance: { price: 105 },
      },
    });

    expect(row.support).toEqual([98, 95, 92]);
    expect(row.resistance).toEqual([105, 110, 115]);
    expect(row.resistanceSources).toEqual(['MANUAL', 'DYNAMIC', 'DYNAMIC']);
    expect(row.strongSupport).toBe(95);
    expect(row.strongSupportSource).toBe('DYNAMIC');
    expect(row.strongResistance).toBe(105);
    expect(row.strongResistanceSource).toBe('MANUAL');
    expect(row.targetPrices).toEqual([105, 110, 115]);
    expect(row.targetSources).toEqual(['MANUAL', 'DYNAMIC', 'DYNAMIC']);
  });

  test('keeps S&R values evidence-backed while using minimum percentage gaps only for missing targets', () => {
    const row = buildWatchlistDataRow('TCS', {
      sr: {
        symbol: 'TCS', price: 100,
        supportLevels: [{ price: 97, source: 'manual' }, { price: 91, source: 'generated' }],
        resistanceLevels: [{ price: 103, source: 'manual' }, { price: 108, source: 'generated' }, { price: 122, source: 'generated' }],
        strongestSupport: { price: 91 },
        strongestResistance: { price: 122 },
      },
    });

    expect(row.support).toEqual([97, 91, 0]);
    expect(row.supportSources).toEqual(['MANUAL', 'DYNAMIC', 'DYNAMIC']);
    expect(row.resistance).toEqual([103, 108, 122]);
    expect(row.targetPrices).toEqual([103, 108, 122]);
    expect(row.targetSources).toEqual(['MANUAL', 'DYNAMIC', 'DYNAMIC']);
    expect(row.strongSupport).toBe(91);
    expect(row.strongSupportSource).toBe('DYNAMIC');
    expect(row.strongResistance).toBe(122);
    expect(row.strongResistanceSource).toBe('DYNAMIC');
  });

  test('fills target slots at 5, 10 and 15 percent when S&R has no resistance levels', () => {
    const row = buildWatchlistDataRow('TCS', { bars: [{ c: 100, h: 101, l: 99 }] });

    expect(row.resistance).toEqual([0, 0, 0]);
    expect(row.targetPrices).toEqual([105, 110, 115]);
    expect(row.targetSources).toEqual(['DYNAMIC', 'DYNAMIC', 'DYNAMIC']);
    expect(row.strongResistance).toBe(0);
  });

  test('estimates target duration from median historical OHLCV time-to-target observations', () => {
    const history = Array.from({ length: 30 }, (_, index) => {
      const close = 100 * (1.02 ** index);
      return { t: index + 1, c: close, h: close, l: close * 0.99 };
    });

    expect(estimateTargetTradingDays(history, 100, [105, 110, 115])).toEqual([3, 5, 8]);
  });

  test('hydrates historical target trading days after the latest candle paints', async () => {
    vi.clearAllMocks();
    mockWatchlistBaseSources();
    const history = Array.from({ length: 30 }, (_, index) => {
      const close = 100 * (1.02 ** index);
      return { t: index + 1, c: close, h: close, l: close * 0.99 };
    });
    apiMocks.fetchBars.mockImplementation(({ symbol, limit }: { symbol: string; limit: number }) => Promise.resolve({
      bars: limit === 1 ? [{ t: 31, c: 100, h: 101, l: 99 }] : history,
      symbol,
    }));
    apiMocks.fetchSrLevelsPayload.mockResolvedValue({
      rows: [{ symbol: 'TCS', price: 100, resistanceLevels: [{ price: 105 }, { price: 110 }, { price: 115 }] }],
    });

    const row = await fetchWatchlistDataRow('TCS');

    expect(row.targetDays).toEqual([3, 5, 8]);
    expect(row.sourceStatus.targetHistory).toBe('LOADED');
    expect(apiMocks.fetchBars).toHaveBeenCalledWith(
      { symbol: 'TCS', tf: '1D', limit: 800 },
      expect.objectContaining({ timeoutMs: 15000 }),
    );
  });

  test('parses legacy SR display text with or without colons', () => {
    const row = buildWatchlistDataRow('TCS', {
      sr: {
        symbol: 'TCS', price: 100,
        supportDisplay: 'S1 98.50 -> S2: 95.25 -> S3 92',
        resistanceDisplay: 'R1 105 -> R2: 110 -> R3 115',
      },
    });

    expect(row.support).toEqual([98.5, 95.25, 92]);
    expect(row.resistance).toEqual([105, 110, 115]);
  });

  test('matches established stock aliases and requests the selected symbol S&R row directly', async () => {
    vi.clearAllMocks();
    mockWatchlistBaseSources();
    apiMocks.fetchTechnicalScreenerPayload.mockResolvedValue({
      count: 1,
      rows: [{ stock: 'WESTLIFE', price: 600, techScore: 77, trendStructure: 'Uptrend' }],
    });
    apiMocks.fetchSrLevelsPayload.mockResolvedValue({
      rows: [{ stock: 'WESTLIFE', price: 600, supportDisplay: 'S1 580', resistanceDisplay: 'R1 620' }],
    });
    apiMocks.fetchDeliveryPayload.mockResolvedValue({
      data: [{ ticker: 'WESTLIFE', delivery_pct: 63.25 }],
    });

    const row = await fetchWatchlistDataRow('NSE:WESTLIFE-EQ');

    expect(row.ltp).toBe(600);
    expect(row.support[0]).toBe(580);
    expect(row.resistance[0]).toBe(620);
    expect(row.delivery).toBe(63.25);
    expect(row.sourceStatus.bars).toBe('LOADED');
    expect(row.sourceStatus.sr).toBe('LOADED');
    expect(row.sourceStatus.volume).toBe('NOT_AVAILABLE');
    expect(apiMocks.fetchSrLevelsPayload).toHaveBeenCalledWith(
      expect.objectContaining({ symbols: 'WESTLIFE' }),
      expect.objectContaining({ timeoutMs: 15000 }),
    );
  });

  test('distinguishes source request failure from a successful response with no symbol data', async () => {
    vi.clearAllMocks();
    mockWatchlistBaseSources();
    apiMocks.fetchSrLevelsPayload.mockRejectedValue(new Error('S&R timeout'));

    const row = await fetchWatchlistDataRow('TCS');

    expect(row.sourceStatus.sr).toBe('LOAD_FAILED');
    expect(row.sourceStatus.technical).toBe('NOT_AVAILABLE');
    expect(row.sourceStatus.delivery).toBe('NOT_AVAILABLE');
    expect(row.ltp).toBe(100);
  });
});

describe('Watchlist Volume hydration', () => {
  test('stops stale symbol enrichment before launching the remaining expensive sources', async () => {
    vi.resetModules();
    vi.clearAllMocks();
    mockWatchlistBaseSources();
    apiMocks.fetchSectorWiseSymbol.mockImplementation((_symbol: string, options: { signal?: AbortSignal }) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
    }));

    const controller = new AbortController();
    const { fetchWatchlistDataRow } = await import('../src/services/api/watchlistData');
    await fetchWatchlistDataRow('TCS', undefined, { returnAfterInitial: true, signal: controller.signal });

    expect(apiMocks.fetchSectorWiseSymbol).toHaveBeenCalledTimes(1);
    expect(apiMocks.fetchTechnicalScreenerPayload).not.toHaveBeenCalled();
    expect(apiMocks.fetchSrLevelsPayload).not.toHaveBeenCalled();
    expect(apiMocks.fetchDeliveryPayload).not.toHaveBeenCalled();

    controller.abort('symbol changed');
    await Promise.resolve();
    await Promise.resolve();

    expect(apiMocks.fetchTechnicalScreenerPayload).not.toHaveBeenCalled();
    expect(apiMocks.fetchSrLevelsPayload).not.toHaveBeenCalled();
    expect(apiMocks.fetchDeliveryPayload).not.toHaveBeenCalled();
  });

  test('returns within the initial render budget while optional sources continue progressively', async () => {
    vi.useFakeTimers();
    vi.resetModules();
    vi.clearAllMocks();
    apiMocks.fetchBars.mockReturnValue(new Promise(() => undefined));
    apiMocks.fetchSymbols.mockReturnValue(new Promise(() => undefined));
    apiMocks.fetchSectorWiseSymbol.mockReturnValue(new Promise(() => undefined));
    apiMocks.fetchTechnicalScreenerPayload.mockReturnValue(new Promise(() => undefined));
    apiMocks.fetchSrLevelsPayload.mockReturnValue(new Promise(() => undefined));
    apiMocks.fetchTechnicalIndicatorPayload.mockReturnValue(new Promise(() => undefined));
    apiMocks.fetchDeliveryPayload.mockReturnValue(new Promise(() => undefined));

    try {
      const { fetchWatchlistDataRow } = await import('../src/services/api/watchlistData');
      const rowPromise = fetchWatchlistDataRow('TCS', undefined, { returnAfterInitial: true });
      await vi.advanceTimersByTimeAsync(749);
      let resolved = false;
      void rowPromise.then(() => { resolved = true; });
      await Promise.resolve();
      expect(resolved).toBe(false);
      await vi.advanceTimersByTimeAsync(1);
      const row = await rowPromise;
      expect(row.symbol).toBe('TCS');
      expect(row.ltp).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  test('polls an empty refreshing placeholder and hydrates the populated response without a remount', async () => {
    vi.useFakeTimers();
    vi.resetModules();
    vi.clearAllMocks();
    mockWatchlistBaseSources();
    apiMocks.fetchTechnicalIndicatorPayload
      .mockResolvedValueOnce({ count: 0, refreshing: true, rows: [], stale: true })
      .mockResolvedValueOnce({ count: 1, rows: [{ symbol: 'TCS', volumeRatio: 2.75 }] });

    try {
      const { fetchWatchlistDataRow } = await import('../src/services/api/watchlistData');
      const rowPromise = fetchWatchlistDataRow('TCS');
      await vi.runAllTimersAsync();
      const row = await rowPromise;

      expect(row.volumeRatio).toBe(2.75);
      expect(apiMocks.fetchTechnicalIndicatorPayload).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  test('shares one populated request across concurrent symbols and reuses the normal cache', async () => {
    vi.resetModules();
    vi.clearAllMocks();
    mockWatchlistBaseSources();
    let resolveVolume: ((value: { count: number; rows: Array<{ symbol: string; volumeRatio: number }> }) => void) | undefined;
    apiMocks.fetchTechnicalIndicatorPayload.mockReturnValue(new Promise((resolve) => {
      resolveVolume = resolve;
    }));

    const { fetchWatchlistDataRow } = await import('../src/services/api/watchlistData');
    const tcsPromise = fetchWatchlistDataRow('TCS');
    const infyPromise = fetchWatchlistDataRow('INFY');
    expect(apiMocks.fetchTechnicalIndicatorPayload).toHaveBeenCalledTimes(1);

    resolveVolume?.({
      count: 3,
      rows: [
        { symbol: 'TCS', volumeRatio: 2.1 },
        { symbol: 'INFY', volumeRatio: 1.8 },
        { symbol: 'HDFCBANK', volumeRatio: 1.4 },
      ],
    });
    const [tcs, infy] = await Promise.all([tcsPromise, infyPromise]);
    const hdfc = await fetchWatchlistDataRow('HDFCBANK');

    expect(tcs.volumeRatio).toBe(2.1);
    expect(infy.volumeRatio).toBe(1.8);
    expect(hdfc.volumeRatio).toBe(1.4);
    expect(apiMocks.fetchTechnicalIndicatorPayload).toHaveBeenCalledTimes(1);
  });

  test('stops polling after the bounded placeholder retry budget', async () => {
    vi.useFakeTimers();
    vi.resetModules();
    vi.clearAllMocks();
    mockWatchlistBaseSources();
    apiMocks.fetchTechnicalIndicatorPayload.mockResolvedValue({
      count: 0,
      refreshing: true,
      rows: [],
      stale: true,
    });

    try {
      const { fetchWatchlistDataRow } = await import('../src/services/api/watchlistData');
      const rowPromise = fetchWatchlistDataRow('TCS');
      await vi.runAllTimersAsync();
      const row = await rowPromise;

      expect(row.volumeRatio).toBe(0);
      expect(apiMocks.fetchTechnicalIndicatorPayload).toHaveBeenCalledTimes(4);
    } finally {
      vi.useRealTimers();
    }
  });
});
