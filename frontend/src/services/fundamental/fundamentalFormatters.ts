import { normalizeDisplaySymbol } from '../../utils/symbols';

export function formatPercent(value: number, digits = 1): string {
  return `${value.toFixed(digits)}%`;
}

export function formatScore(value: number): string {
  return `${Math.round(value)}/100`;
}

export function formatCurrencyCrore(value: number): string {
  return `Rs. ${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cr`;
}

export function formatNumber(value: number, digits = 1): string {
  return value.toLocaleString('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function normalizeSymbol(symbol: string): string {
  return normalizeDisplaySymbol(symbol);
}
