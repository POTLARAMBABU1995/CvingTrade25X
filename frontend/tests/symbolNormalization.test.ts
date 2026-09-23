import { describe, expect, it } from 'vitest';
import { normalizeDisplaySymbol } from '../src/utils/symbols';

describe('normalizeDisplaySymbol', () => {
  it.each([
    ['NSE-ITC-EQ', 'ITC'],
    ['NSE:ABC-BE', 'ABC'],
    ['TEJASCARGO-SM', 'TEJASCARGO'],
    ['PRECISIO-ST', 'PRECISIO'],
    ['VBL', 'VBL'],
    ['HDFCBANK', 'HDFCBANK'],
    ['NSE:BAJAJ-AUTO-EQ', 'BAJAJ-AUTO'],
  ])('normalizes %s to %s', (input, expected) => {
    expect(normalizeDisplaySymbol(input)).toBe(expected);
  });
});
