const MARKET_TIME_ZONE = 'Asia/Kolkata';
const DAILY_MARKET_CLOSE_IST_MINUTES = (15 * 60) + 45;

export type DateParts = {
  year: number;
  month: number;
  day: number;
};

export type DailyFreshness = {
  expectedDateKey: string | null;
  isLatest: boolean;
  latestLtcDateKey: string | null;
};

export function toDateParts(value: unknown): DateParts | null {
  if (value === null || value === undefined || value === '') return null;

  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) return null;
    return { year: value.getFullYear(), month: value.getMonth() + 1, day: value.getDate() };
  }

  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return null;
    const millis = value > 1e12 ? value : value * 1000;
    const parsed = new Date(millis);
    if (Number.isNaN(parsed.getTime())) return null;
    return { year: parsed.getFullYear(), month: parsed.getMonth() + 1, day: parsed.getDate() };
  }

  const text = String(value).trim();
  if (!text) return null;
  if (/^\d+(\.\d+)?$/.test(text)) {
    return toDateParts(Number(text));
  }

  const normalized = text.replace(/[\/]/g, '-');
  const isoMatch = normalized.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (isoMatch) {
    return { year: Number(isoMatch[1]), month: Number(isoMatch[2]), day: Number(isoMatch[3]) };
  }

  const dmyMatch = normalized.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (dmyMatch) {
    return { year: Number(dmyMatch[3]), month: Number(dmyMatch[2]), day: Number(dmyMatch[1]) };
  }

  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return null;
  return { year: parsed.getFullYear(), month: parsed.getMonth() + 1, day: parsed.getDate() };
}

export function partsToDateKey(parts: DateParts | null): string | null {
  if (!parts) return null;
  if (![parts.year, parts.month, parts.day].every(Number.isFinite)) return null;
  const month = String(parts.month).padStart(2, '0');
  const day = String(parts.day).padStart(2, '0');
  return `${parts.year}-${month}-${day}`;
}

export function extractLatestDateKey<T>(rows: T[], getRowDate: (row: T) => unknown): string | null {
  let latest: string | null = null;
  rows.forEach((row) => {
    const key = partsToDateKey(toDateParts(getRowDate(row)));
    if (!key) return;
    if (!latest || key > latest) latest = key;
  });
  return latest;
}

function formatUtcDateKey(date: Date): string | null {
  if (Number.isNaN(date.getTime())) return null;
  const year = String(date.getUTCFullYear());
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  const day = String(date.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getIstNowParts(now: Date): { year: number; month: number; day: number; hour: number; minute: number } | null {
  try {
    const formatter = new Intl.DateTimeFormat('en-GB', {
      timeZone: MARKET_TIME_ZONE,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    });
    const parts = formatter.formatToParts(now);
    const pick = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((part) => part.type === type)?.value);
    const year = pick('year');
    const month = pick('month');
    const day = pick('day');
    const hour = pick('hour');
    const minute = pick('minute');
    if (![year, month, day, hour, minute].every(Number.isFinite)) return null;
    return { year, month, day, hour, minute };
  } catch {
    return null;
  }
}

export function getExpectedLatestTradingDateKey(now = new Date()): string | null {
  const nowIst = getIstNowParts(now);
  if (!nowIst) return null;
  const candidate = new Date(Date.UTC(nowIst.year, nowIst.month - 1, nowIst.day));
  const nowMinutes = (nowIst.hour * 60) + nowIst.minute;
  if (nowMinutes < DAILY_MARKET_CLOSE_IST_MINUTES) {
    candidate.setUTCDate(candidate.getUTCDate() - 1);
  }
  while (candidate.getUTCDay() === 0 || candidate.getUTCDay() === 6) {
    candidate.setUTCDate(candidate.getUTCDate() - 1);
  }
  return formatUtcDateKey(candidate);
}

export function assessDailyFreshness<T>(rows: T[], getRowDate: (row: T) => unknown, now = new Date()): DailyFreshness {
  const latestLtcDateKey = extractLatestDateKey(rows, getRowDate);
  const expectedDateKey = getExpectedLatestTradingDateKey(now);
  if (!latestLtcDateKey || !expectedDateKey) {
    return { latestLtcDateKey, expectedDateKey, isLatest: true };
  }
  return {
    latestLtcDateKey,
    expectedDateKey,
    isLatest: latestLtcDateKey >= expectedDateKey,
  };
}
