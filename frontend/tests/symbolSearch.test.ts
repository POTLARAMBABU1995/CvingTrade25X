import { describe, expect, test } from 'vitest';
import { findExactSymbolMatch, normalizeSearchSymbol, type SymbolSearchOption } from '../src/components/SymbolSearch';

const results: SymbolSearchOption[] = [
  { symbol: 'RELAXO', name: 'RELAXO', exchange: 'NSE' },
  { symbol: 'RELIANCE', name: 'RELIANCE', exchange: 'NSE' },
  { symbol: 'SBIN', name: 'SBIN', exchange: 'NSE' },
];

describe('SymbolSearch exact backend match helpers', () => {
  test('normalizes exchange prefixes and equity suffixes before matching', () => {
    expect(normalizeSearchSymbol('nse:sbin-eq')).toBe('SBIN');
    expect(normalizeSearchSymbol(' bse:reliance:eq ')).toBe('RELIANCE');
  });

  test('returns only exact backend symbol matches', () => {
    expect(findExactSymbolMatch(results, 'reliance')?.symbol).toBe('RELIANCE');
    expect(findExactSymbolMatch(results, 'NSE:SBIN-EQ')?.symbol).toBe('SBIN');
    expect(findExactSymbolMatch(results, 'REL')).toBeNull();
  });
});
