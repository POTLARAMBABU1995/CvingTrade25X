import { beforeEach, describe, expect, test, vi } from 'vitest';
import * as apiClient from '../src/api/client';
import {
  clearSectorHierarchyCache,
  getIndustries,
  getParents,
  getStocks,
  getSubSectors,
  getSummary,
  getTree,
} from '../src/services/api/sectorHierarchyApi';

beforeEach(() => {
  clearSectorHierarchyCache();
  vi.restoreAllMocks();
});

describe('sectorHierarchyApi', () => {
  test('caches parent response in-memory for repeat calls', async () => {
    const spy = vi.spyOn(apiClient, 'legacyApiGet').mockResolvedValue({
      success: true,
      data: [{ parentSector: 'Healthcare', stockCount: 56 }],
      metadata: { cacheKey: 'sectorHierarchy:parents:v1', cached: false, generatedAt: 'x' },
    });

    const first = await getParents();
    const second = await getParents();

    expect(first.success).toBe(true);
    expect(second.success).toBe(true);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  test('refresh option bypasses cache', async () => {
    const spy = vi.spyOn(apiClient, 'legacyApiGet').mockResolvedValue({
      success: true,
      data: [{ parentSector: 'Healthcare', stockCount: 56 }],
      metadata: { cacheKey: 'sectorHierarchy:parents:v1', cached: false, generatedAt: 'x' },
    });

    await getParents();
    await getParents({ refresh: true });

    expect(spy).toHaveBeenCalledTimes(2);
  });

  test('sends expected hierarchy params for filtered stocks', async () => {
    const spy = vi.spyOn(apiClient, 'legacyApiGet').mockResolvedValue({
      success: true,
      data: {
        parentSector: 'Healthcare',
        industrySector: 'Pharmaceuticals',
        subSector: 'Formulations & Generics',
        totalStocks: 1,
        stocks: [{ symbol: 'SUNPHARMA', exchange: 'NSE' }],
      },
      metadata: { cacheKey: 'k', cached: false, generatedAt: 'x' },
    });

    await getIndustries('Healthcare');
    await getSubSectors('Healthcare', 'Pharmaceuticals');
    await getSummary('Healthcare');
    await getTree('Healthcare');
    await getStocks({
      parentSector: 'Healthcare',
      industrySector: 'Pharmaceuticals',
      subSector: 'Formulations & Generics',
    });

    const stocksCall = spy.mock.calls.find((call) => call[0] === '/api/sector-hierarchy/stocks');
    expect(stocksCall).toBeTruthy();
    expect(stocksCall?.[1]).toEqual({
      parentSector: 'Healthcare',
      industrySector: 'Pharmaceuticals',
      subSector: 'Formulations & Generics',
    });
  });
});
