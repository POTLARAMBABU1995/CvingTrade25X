import { describe, expect, test } from 'vitest';
import { formatFyersCell, normalizeFyersSymbol } from '../src/adapters/fyersPageAdapter';

describe('fyersPageAdapter', () => {
  test('formats missing percent values as dash while preserving valid zero', () => {
    expect(formatFyersCell(null, 'percent')).toBe('-');
    expect(formatFyersCell('', 'percent')).toBe('-');
    expect(formatFyersCell(0, 'percent')).toBe('0%');
  });

  test('normalizes FYERS exchange-prefixed symbols without changing display callers', () => {
    expect(normalizeFyersSymbol('NSE:TANLA-EQ')).toBe('TANLA');
    expect(normalizeFyersSymbol('BSE:CGCL-EQ')).toBe('CGCL');
    expect(normalizeFyersSymbol('IOC.NS')).toBe('IOC');
  });
});
