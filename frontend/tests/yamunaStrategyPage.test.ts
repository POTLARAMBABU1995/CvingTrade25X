import { describe, expect, test } from 'vitest';
import { formatYamunaPercentageCell, formatYamunaPointsCell } from '../src/adapters/yamunaPageAdapter';

describe('Yamuna strategy page formatting', () => {
  test('preserves TradingView decimal precision for points and percentage cells', () => {
    expect(formatYamunaPointsCell(149.5)).toBe('149.50');
    expect(formatYamunaPercentageCell(6.51)).toBe('6.51%');

    expect(formatYamunaPointsCell(98.4)).toBe('98.40');
    expect(formatYamunaPercentageCell(19.99)).toBe('19.99%');

    expect(formatYamunaPointsCell(76.6)).toBe('76.60');
    expect(formatYamunaPercentageCell(17.35)).toBe('17.35%');
  });

  test('keeps empty Yamuna numeric cells blank-safe', () => {
    expect(formatYamunaPointsCell(null)).toBe('-');
    expect(formatYamunaPercentageCell(undefined)).toBe('-');
  });

  test('uses percent precision for negative and string values without volume-ratio suffixes', () => {
    expect(formatYamunaPointsCell('-88.5')).toBe('-88.50');
    expect(formatYamunaPercentageCell('-4.90%')).toBe('-4.90%');
    expect(formatYamunaPercentageCell('5.90')).toBe('5.90%');
  });
});
