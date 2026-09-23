import { describe, expect, test } from 'vitest';
import {
  adaptEmaTrendRow,
  buildEmaSymbolsCsv,
  buildEmaSymbolsTxt,
  filterEmaRowsForDownload,
} from '../src/adapters/technicalEmaAdapter';

const rows = [
  adaptEmaTrendRow({ symbol: 'SIX', tradingDays: 6 }, 0),
  adaptEmaTrendRow({ symbol: 'SEVENTY-SEVEN', tradingDays: 77 }, 1),
  adaptEmaTrendRow({ symbol: 'ONE-FIFTY-SIX', tradingDays: 156 }, 2),
  adaptEmaTrendRow({ symbol: 'TWO-FIFTY', tradingDays: 250 }, 3),
  adaptEmaTrendRow({ symbol: 'EXACT-YEAR', tradingDays: 252 }, 4),
  adaptEmaTrendRow({ symbol: 'THREE-FIFTY', tradingDays: 350 }, 5),
  adaptEmaTrendRow({ symbol: 'OVER-TWO-YEARS', tradingDays: 505 }, 6),
];

describe('EMA symbol downloads', () => {
  test('exports only positive T_D values below the selected year limit', () => {
    expect(filterEmaRowsForDownload(rows, null)).toEqual([]);
    expect(filterEmaRowsForDownload(rows, 1).map((row) => row.symbol)).toEqual([
      'SIX',
      'SEVENTY-SEVEN',
      'ONE-FIFTY-SIX',
      'TWO-FIFTY',
    ]);
    expect(filterEmaRowsForDownload(rows, 2).map((row) => row.symbol)).toEqual([
      'SIX',
      'SEVENTY-SEVEN',
      'ONE-FIFTY-SIX',
      'TWO-FIFTY',
      'EXACT-YEAR',
      'THREE-FIFTY',
    ]);
  });

  test('builds comma-only TXT and exact three-column CSV output', () => {
    const selected = filterEmaRowsForDownload(rows, 1);
    expect(buildEmaSymbolsTxt(selected)).toBe('SIX,SEVENTY-SEVEN,ONE-FIFTY-SIX,TWO-FIFTY');
    expect(buildEmaSymbolsCsv(selected)).toBe([
      's.no,symbol,t_d',
      '1,SIX,6',
      '2,SEVENTY-SEVEN,77',
      '3,ONE-FIFTY-SIX,156',
      '4,TWO-FIFTY,250',
    ].join('\n'));
  });
});
