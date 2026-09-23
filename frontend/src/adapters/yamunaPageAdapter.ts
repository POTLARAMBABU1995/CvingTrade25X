export function toYamunaNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const cleaned = String(value).trim().replace(/,/g, '').replace(/%$/g, '').replace(/x$/gi, '');
  if (!cleaned) return null;
  const num = Number(cleaned);
  return Number.isFinite(num) ? num : null;
}

function formatFixedTwoDecimal(value: unknown): string {
  const numeric = toYamunaNumber(value);
  if (numeric === null) return '-';
  return numeric.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatYamunaPointsCell(value: unknown): string {
  return formatFixedTwoDecimal(value);
}

export function formatYamunaPercentageCell(value: unknown): string {
  const formatted = formatFixedTwoDecimal(value);
  return formatted === '-' ? formatted : `${formatted}%`;
}
