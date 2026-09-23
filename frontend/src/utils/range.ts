import type { Bar, Timeframe } from '../types';

export function toDateString(date: Date): string {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  const day = String(date.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function getInitialRange(_tf: Timeframe): { from: string; to: string } {
  const now = new Date();
  const from = new Date(Date.UTC(1900, 0, 1));
  return { from: toDateString(from), to: toDateString(now) };
}

export function epochToDateString(epochSeconds: number): string {
  const date = new Date(epochSeconds * 1000);
  return toDateString(date);
}

export function mergeBars(pages: Bar[][]): Bar[] {
  const map = new Map<number, Bar>();
  pages.flat().forEach((bar) => {
    map.set(bar.t, bar);
  });
  return Array.from(map.values()).sort((a, b) => a.t - b.t);
}
