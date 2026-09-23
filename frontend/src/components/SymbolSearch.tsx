import { useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { fetchSymbols } from '../api/symbols';
import { SearchIcon } from './ui/Icons';
import { normalizeDisplaySymbol } from '../utils/symbols';

export type SymbolSearchOption = {
  exchange?: string;
  name?: string;
  sector?: string;
  symbol: string;
};

export type SymbolSearchProps = {
  value: string;
  onSelect: (symbol: string) => void;
};

export function normalizeSearchSymbol(value: string): string {
  return normalizeDisplaySymbol(value);
}

export function findExactSymbolMatch(
  results: SymbolSearchOption[],
  query: string,
): SymbolSearchOption | null {
  const normalizedQuery = normalizeSearchSymbol(query);
  if (!normalizedQuery) return null;
  return results.find((item) => normalizeSearchSymbol(item.symbol) === normalizedQuery) ?? null;
}

export default function SymbolSearch({ value, onSelect }: SymbolSearchProps) {
  const [query, setQuery] = useState(value);
  const [active, setActive] = useState(false);
  const deferredQuery = useDeferredValue(query);

  useEffect(() => {
    setQuery(value);
  }, [value]);

  const { data, isFetching } = useQuery({
    queryKey: ['symbols', deferredQuery],
    queryFn: () => fetchSymbols(deferredQuery),
    enabled: deferredQuery.trim().length > 0,
    staleTime: 1000 * 30,
  });

  const results = useMemo(() => data?.symbols ?? [], [data]);
  const exactMatch = useMemo(() => findExactSymbolMatch(results, deferredQuery), [deferredQuery, results]);
  const commitSymbol = useCallback((symbol: string) => {
    const normalizedSymbol = normalizeSearchSymbol(symbol);
    if (!normalizedSymbol) return;
    onSelect(normalizedSymbol);
    setQuery(normalizedSymbol);
    setActive(false);
  }, [onSelect]);

  useEffect(() => {
    if (!exactMatch) return;
    const typedSymbol = normalizeSearchSymbol(query);
    const deferredSymbol = normalizeSearchSymbol(deferredQuery);
    const currentSymbol = normalizeSearchSymbol(value);
    const nextSymbol = normalizeSearchSymbol(exactMatch.symbol);
    if (!nextSymbol || typedSymbol !== deferredSymbol || nextSymbol === currentSymbol) return;
    commitSymbol(nextSymbol);
  }, [commitSymbol, deferredQuery, exactMatch, query, value]);

  return (
    <div className="relative">
      <div className="flex items-center gap-3 rounded-[22px] border border-slate-200/70 bg-white/80 px-4 py-3 shadow-soft backdrop-blur-xl transition duration-200 focus-within:border-[rgb(var(--page-accent-rgb)/0.22)] focus-within:bg-white">
        <SearchIcon className="h-4 w-4 text-cyan" />
        <input
          className="focus-ring w-full border-none bg-transparent text-sm font-medium text-text placeholder:text-dim"
          value={query}
          placeholder="Search symbol, exchange, or company"
          onChange={(event) => {
            setQuery(event.target.value.toUpperCase());
            setActive(true);
          }}
          onKeyDown={(event) => {
            if (event.key !== 'Enter') return;
            const match = findExactSymbolMatch(results, query);
            if (!match) return;
            event.preventDefault();
            commitSymbol(match.symbol);
          }}
          onFocus={() => setActive(true)}
          onBlur={() => setTimeout(() => setActive(false), 120)}
        />
        <span className="rounded-full border border-slate-200/70 bg-white/70 px-2 py-1 text-[10px] uppercase tracking-[0.24em] text-dim backdrop-blur-xl">
          {isFetching ? 'Sync' : 'Live'}
        </span>
      </div>
      {active && results.length > 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 10 }}
          className="absolute left-0 right-0 top-full z-20 mt-3 max-h-64 overflow-auto rounded-[24px] border border-slate-200/70 bg-white/92 p-2 shadow-float backdrop-blur-2xl"
        >
          {results.slice(0, 8).map((item) => (
            <button
              key={item.symbol}
              type="button"
              className="focus-ring w-full rounded-[18px] border border-transparent px-3 py-3 text-left transition hover:border-[rgb(var(--page-accent-rgb)/0.16)] hover:bg-[rgb(var(--page-accent-rgb)/0.06)]"
              onClick={() => {
                commitSymbol(item.symbol);
              }}
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-text">{item.symbol}</p>
                  <p className="mt-1 text-xs text-muted">{item.name ? `${item.name} - ${item.exchange ?? 'NSE/BSE'}` : item.exchange ?? 'NSE/BSE'}</p>
                </div>
                {item.sector ? (
                  <span className="rounded-full border border-slate-200/70 bg-white/70 px-2 py-1 text-[10px] uppercase tracking-[0.24em] text-dim backdrop-blur-xl">
                    {item.sector}
                  </span>
                ) : null}
              </div>
            </button>
          ))}
        </motion.div>
      ) : null}
    </div>
  );
}
