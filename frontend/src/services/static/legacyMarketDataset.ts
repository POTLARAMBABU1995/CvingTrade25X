import marketDataset from './market.json';
import type { LocalMarketDataset, LocalMarketMovers, LocalScreenerWireRow, LocalStrategyRow } from '../../types';

const SAMPLE_CLOSES = [100, 101, 102, 103, 104, 103, 105, 104, 106, 108, 109, 110, 109, 111, 112, 113, 114, 115];
const SAMPLE_HIGHS = SAMPLE_CLOSES.map((close) => close * 1.01);
const SAMPLE_LOWS = SAMPLE_CLOSES.map((close) => close * 0.99);

function lastValue<T>(values: T[]): T | undefined {
  return values.length ? values[values.length - 1] : undefined;
}

function ema(values: number[], period: number): number[] {
  if (!values.length || period <= 0) {
    return [];
  }

  const multiplier = 2 / (period + 1);
  const output: number[] = [];
  let previous = 0;

  values.forEach((value, index) => {
    previous = index === 0 ? value : value * multiplier + previous * (1 - multiplier);
    output.push(previous);
  });

  return output;
}

function sma(values: number[], period: number): number[] {
  if (values.length < period || period <= 0) {
    return [];
  }

  const output: number[] = [];
  let sum = 0;

  values.forEach((value, index) => {
    sum += value;
    if (index >= period) {
      sum -= values[index - period];
    }

    if (index >= period - 1) {
      output.push(sum / period);
    }
  });

  return output;
}

function rsi(values: number[], period = 14): number[] {
  if (values.length <= period) {
    return [];
  }

  const gains: number[] = [];
  const losses: number[] = [];

  for (let index = 1; index < values.length; index += 1) {
    const difference = values[index] - values[index - 1];
    gains.push(Math.max(0, difference));
    losses.push(Math.max(0, -difference));
  }

  let averageGain = sma(gains, period)[0];
  let averageLoss = sma(losses, period)[0];
  const output = new Array<number>(period).fill(Number.NaN);

  for (let index = period; index < values.length - 1; index += 1) {
    averageGain = (averageGain * (period - 1) + gains[index]) / period;
    averageLoss = (averageLoss * (period - 1) + losses[index]) / period;
    const relativeStrength = averageLoss === 0 ? 100 : averageGain / averageLoss;
    output.push(100 - 100 / (1 + relativeStrength));
  }

  return output;
}

function macd(values: number[], fast = 12, slow = 26, signal = 9) {
  const fastEma = ema(values, fast);
  const slowEma = ema(values, slow);
  const macdLine = fastEma.map((value, index) => value - (slowEma[index] ?? value));
  const signalLine = ema(macdLine, signal);

  return {
    macdLine,
    signalLine,
  };
}

function atr(highs: number[], lows: number[], closes: number[], period = 14): number[] {
  if (!highs.length || !lows.length || !closes.length) {
    return [];
  }

  const trueRanges: number[] = [];

  closes.forEach((close, index) => {
    const previousClose = index > 0 ? closes[index - 1] : close;
    trueRanges.push(
      Math.max(
        highs[index] - lows[index],
        Math.abs(highs[index] - previousClose),
        Math.abs(lows[index] - previousClose),
      ),
    );
  });

  return ema(trueRanges, period);
}

function supportResistance(prices: number[], windowSize = 5) {
  if (prices.length < windowSize) {
    return { support: undefined, resistance: undefined };
  }

  const recent = prices.slice(-windowSize);
  return {
    support: Math.min(...recent),
    resistance: Math.max(...recent),
  };
}

function formatFixed(value: number, digits = 2): string {
  return value.toFixed(digits);
}

export function getLocalMarketDataset(): LocalMarketDataset {
  return marketDataset as LocalMarketDataset;
}

export function getLocalMarketMovers(): LocalMarketMovers {
  return getLocalMarketDataset().movers;
}

export function buildLocalStrategyRows(rows: LocalScreenerWireRow[]): LocalStrategyRow[] {
  const ema20 = lastValue(ema(SAMPLE_CLOSES, 20)) ?? lastValue(SAMPLE_CLOSES) ?? 0;
  const ema50 = lastValue(ema(SAMPLE_CLOSES, 50)) ?? lastValue(SAMPLE_CLOSES) ?? 0;
  const ema100 = lastValue(ema(SAMPLE_CLOSES, 100)) ?? lastValue(SAMPLE_CLOSES) ?? 0;
  const ema200 = lastValue(ema(SAMPLE_CLOSES, 200)) ?? lastValue(SAMPLE_CLOSES) ?? 0;
  const rsi14 = lastValue(rsi(SAMPLE_CLOSES, 14));
  const macdLines = macd(SAMPLE_CLOSES);
  const macdValue = (lastValue(macdLines.macdLine) ?? 0) - (lastValue(macdLines.signalLine) ?? 0);
  const atr14 = lastValue(atr(SAMPLE_HIGHS, SAMPLE_LOWS, SAMPLE_CLOSES, 14)) ?? 0;
  const levels = supportResistance(SAMPLE_CLOSES, 5);
  const emaDays = `20:${formatFixed(ema20)} | 50:${formatFixed(ema50)} | 100:${formatFixed(ema100)} | 200:${formatFixed(ema200)}`;
  const supportValue = levels.support ?? null;
  const resistanceValue = levels.resistance ?? null;

  return rows.map((row) => ({
    ...row,
    high1y: row.high52,
    emaDays,
    emaDaysSort: Number(formatFixed(ema20)),
    rsi: formatFixed(rsi14 ?? 50),
    rsiValue: Number(formatFixed(rsi14 ?? 50)),
    macd: formatFixed(macdValue),
    macdValue: Number(formatFixed(macdValue)),
    atr: formatFixed(atr14),
    atrValue: Number(formatFixed(atr14)),
    support: supportValue === null ? '-' : formatFixed(supportValue),
    supportValue,
    resistance: resistanceValue === null ? '-' : formatFixed(resistanceValue),
    resistanceValue,
  }));
}

export function getLocalStrategyRows(): LocalStrategyRow[] {
  return buildLocalStrategyRows(getLocalMarketDataset().screener);
}
