import { describe, expect, test } from 'vitest';
import { computeSectorBreadthStrength, parsePercent } from '../src/utils/sectorStrength';

describe('sector strength utilities', () => {
  test('parsePercent handles numbers and percent strings', () => {
    expect(parsePercent(95)).toBe(95);
    expect(parsePercent('95')).toBe(95);
    expect(parsePercent('95%')).toBe(95);
  });

  test('parsePercent rejects invalid values', () => {
    expect(Number.isNaN(parsePercent('-'))).toBe(true);
    expect(Number.isNaN(parsePercent(''))).toBe(true);
    expect(Number.isNaN(parsePercent(null))).toBe(true);
    expect(Number.isNaN(parsePercent(undefined))).toBe(true);
  });

  test('Power-like row resolves to Very Strong Bullish', () => {
    const strength = computeSectorBreadthStrength({
      rsi50Pct: 100,
      rsi55Pct: 95,
      sma100Pct: 95,
      sma20Pct: 100,
      sma50Pct: 100,
    });
    expect(Math.round(strength.avgPct)).toBe(98);
    expect(strength.strengthLabel).toBe('Very Strong Bullish');
    expect(strength.sortRank).toBe(6);
  });

  test('Capital Goods-like row resolves to Strong Bullish', () => {
    const strength = computeSectorBreadthStrength({
      rsi50Pct: 88,
      rsi55Pct: 89,
      sma100Pct: 85,
      sma20Pct: 90,
      sma50Pct: 88,
    });
    expect(strength.strengthLabel).toBe('Strong Bullish');
    expect(strength.sortRank).toBe(5);
  });

  test('Power-like 81/86/86/86/81 resolves to Strong Bullish', () => {
    const strength = computeSectorBreadthStrength({
      rsi50Pct: 86,
      rsi55Pct: 81,
      sma100Pct: 81,
      sma20Pct: 86,
      sma50Pct: 86,
    });
    expect(Math.round(strength.avgPct)).toBe(84);
    expect(strength.strengthLabel).toBe('Strong Bullish');
    expect(strength.sortRank).toBe(5);
  });

  test('Pharma-like 100/95/80/70/75 resolves to Strong Bullish', () => {
    const strength = computeSectorBreadthStrength({
      rsi50Pct: 95,
      rsi55Pct: 100,
      sma100Pct: 75,
      sma20Pct: 80,
      sma50Pct: 70,
    });
    expect(Math.round(strength.avgPct)).toBe(84);
    expect(strength.strengthLabel).toBe('Strong Bullish');
    expect(strength.sortRank).toBe(5);
  });

  test('Capital Goods-like 62/67/66/67/62 resolves to Bullish / Improving', () => {
    const strength = computeSectorBreadthStrength({
      rsi50Pct: 67,
      rsi55Pct: 62,
      sma100Pct: 62,
      sma20Pct: 66,
      sma50Pct: 67,
    });
    expect(Math.round(strength.avgPct)).toBe(65);
    expect(strength.strengthLabel).toBe('Bullish / Improving');
    expect(strength.sortRank).toBe(4);
  });

  test('Healthcare-like 42/67/64/58/44 resolves to Moderate / Neutral', () => {
    const strength = computeSectorBreadthStrength({
      rsi50Pct: 67,
      rsi55Pct: 42,
      sma100Pct: 44,
      sma20Pct: 64,
      sma50Pct: 58,
    });
    expect(Math.round(strength.avgPct)).toBe(55);
    expect(strength.strengthLabel).toBe('Moderate / Neutral');
    expect(strength.sortRank).toBe(3);
  });

  test('moderate row resolves to Moderate / Neutral', () => {
    const strength = computeSectorBreadthStrength({
      rsi50Pct: 50,
      rsi55Pct: 55,
      sma100Pct: 45,
      sma20Pct: 52,
      sma50Pct: 48,
    });
    expect(strength.strengthLabel).toBe('Moderate / Neutral');
    expect(strength.sortRank).toBe(3);
  });

  test('weak row resolves to Weak Bearish', () => {
    const strength = computeSectorBreadthStrength({
      rsi50Pct: 40,
      rsi55Pct: 38,
      sma100Pct: 35,
      sma20Pct: 41,
      sma50Pct: 36,
    });
    expect(strength.strengthLabel).toBe('Weak Bearish');
    expect(strength.sortRank).toBe(2);
  });

  test('missing values resolve to Neutral / NA', () => {
    const strength = computeSectorBreadthStrength({
      rsi50Pct: null,
      rsi55Pct: undefined,
      sma100Pct: '-',
      sma20Pct: '',
      sma50Pct: 'NA',
    });
    expect(strength.strengthLabel).toBe('Neutral / NA');
    expect(strength.sortRank).toBe(0);
  });

  test('20/25/30/35/28 resolves to Very Weak Bearish', () => {
    const strength = computeSectorBreadthStrength({
      rsi50Pct: 25,
      rsi55Pct: 20,
      sma100Pct: 28,
      sma20Pct: 30,
      sma50Pct: 35,
    });
    expect(strength.strengthLabel).toBe('Very Weak Bearish');
    expect(strength.sortRank).toBe(1);
  });

  test('sector and score class always align', () => {
    const strength = computeSectorBreadthStrength({
      rsi50Pct: 86,
      rsi55Pct: 81,
      sma100Pct: 81,
      sma20Pct: 86,
      sma50Pct: 86,
    });
    expect(strength.sectorClassName).toBe(strength.scoreClassName);
  });

  test('sorting puts stronger sectors first', () => {
    const rows = [
      { sectorName: 'Weak', rsi55Pct: 30, rsi50Pct: 34, sma20Pct: 32, sma50Pct: 30, sma100Pct: 31 },
      { sectorName: 'Power', rsi55Pct: 95, rsi50Pct: 100, sma20Pct: 100, sma50Pct: 100, sma100Pct: 95 },
      { sectorName: 'Capital Goods', rsi55Pct: 88, rsi50Pct: 88, sma20Pct: 90, sma50Pct: 88, sma100Pct: 85 },
    ];

    const sorted = [...rows].sort((left, right) => {
      const leftStrength = computeSectorBreadthStrength(left);
      const rightStrength = computeSectorBreadthStrength(right);
      return rightStrength.sortRank - leftStrength.sortRank
        || rightStrength.avgPct - leftStrength.avgPct
        || left.sectorName.localeCompare(right.sectorName);
    });

    expect(sorted.map((row) => row.sectorName)).toEqual(['Power', 'Capital Goods', 'Weak']);
  });
});
