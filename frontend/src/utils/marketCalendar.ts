const NSE_HOLIDAYS_2026 = new Set([
  '2026-01-15',
  '2026-01-26',
  '2026-03-03',
  '2026-03-26',
  '2026-03-31',
  '2026-04-03',
  '2026-04-14',
  '2026-05-01',
  '2026-05-28',
  '2026-06-26',
  '2026-09-14',
  '2026-10-02',
  '2026-10-20',
  '2026-11-11',
  '2026-11-24',
  '2026-12-25',
]);
const NSE_SPECIAL_WORKING_DAYS_2026 = new Set([
  '2026-02-01',
]);

function parseIsoDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || '').trim());
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) return null;
  return new Date(Date.UTC(year, month - 1, day));
}

function formatIsoDate(date: Date): string {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`;
}

export function isWeekendDate(value: string): boolean {
  const parsed = parseIsoDate(value);
  if (!parsed) return false;
  const day = parsed.getUTCDay();
  return day === 0 || day === 6;
}

export function isNseHolidayDate(value: string): boolean {
  return NSE_HOLIDAYS_2026.has(String(value || '').trim().slice(0, 10));
}

export function isSpecialMarketWorkingDate(value: string): boolean {
  return NSE_SPECIAL_WORKING_DAYS_2026.has(String(value || '').trim().slice(0, 10));
}

export function marketClosedReason(value: string): string {
  if (!value) return '';
  if (isSpecialMarketWorkingDate(value)) return '';
  if (isWeekendDate(value)) return 'Saturday/Sunday market weekend';
  if (isNseHolidayDate(value)) return 'NSE market holiday';
  return '';
}

export function isMarketWorkingDate(value: string): boolean {
  return Boolean(value) && !marketClosedReason(value);
}

export function previousMarketWorkingDateIso(value = new Date()): string {
  const current = new Date(Date.UTC(value.getFullYear(), value.getMonth(), value.getDate()));
  for (let index = 0; index < 370; index += 1) {
    const isoDate = formatIsoDate(current);
    if (isMarketWorkingDate(isoDate)) return isoDate;
    current.setUTCDate(current.getUTCDate() - 1);
  }
  return formatIsoDate(current);
}
