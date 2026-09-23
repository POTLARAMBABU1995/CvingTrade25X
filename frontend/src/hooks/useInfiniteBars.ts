import { useInfiniteQuery, type InfiniteData } from '@tanstack/react-query';
import { fetchBars } from '../api/bars';
import type { BarsResponse, Timeframe } from '../types';
import { mergeBars } from '../utils/range';
import { useMemo } from 'react';

export type UseInfiniteBarsParams = {
  symbol: string;
  tf: Timeframe;
  from?: string;
  to?: string;
  range?: string;
  limit?: number;
};

type BarsPageParam = {
  cursor?: string;
} | null;

export function useInfiniteBars(params: UseInfiniteBarsParams) {
  const { symbol, tf, from, to, range, limit = 800 } = params;
  const query = useInfiniteQuery<BarsResponse, Error, InfiniteData<BarsResponse>, (string | number | undefined)[], BarsPageParam>({
    queryKey: ['bars', symbol, tf, from, to, range, limit],
    enabled: Boolean(symbol),
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    retry: 1,
    refetchOnWindowFocus: false,
    queryFn: ({ pageParam }) => {
      const isInitial = !pageParam;
      return fetchBars({
        symbol,
        tf,
        from: isInitial ? from : undefined,
        to: isInitial ? to : undefined,
        range: isInitial ? range : undefined,
        cursor: pageParam?.cursor ?? null,
        limit,
      });
    },
    initialPageParam: null as { cursor?: string } | null,
    getNextPageParam: (lastPage) => {
      return lastPage.nextCursor ? { cursor: lastPage.nextCursor } : undefined;
    },
  });

  const bars = useMemo(() => {
    const pages = query.data?.pages.map((page: BarsResponse) => page.bars) ?? [];
    return mergeBars(pages);
  }, [query.data]);

  return {
    ...query,
    bars,
  };
}
