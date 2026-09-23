import {
  asRecord,
  extractRows,
  formatLegacyCount,
  formatLegacyDate,
  formatLegacyNumber,
  pickField,
  safeLegacyText,
  type UnknownRecord,
} from './databasePageAdapter';

export function extractFyersRows(payload: unknown, aliases: readonly string[] = ['holdings', 'rows', 'data', 'items']) {
  return extractRows(payload, aliases);
}

export function extractNestedRows(payload: unknown, parentKey: string, rowKey = 'rows'): UnknownRecord[] {
  const parent = asRecord(asRecord(payload)[parentKey]);
  return extractRows(parent, [rowKey, 'rows', 'items', 'data']);
}

export function formatFyersCell(value: unknown, kind: 'count' | 'date' | 'number' | 'percent' | 'text' = 'text') {
  if (kind === 'count') return formatLegacyCount(value, '-');
  if (kind === 'date') return formatLegacyDate(value);
  if (kind === 'number') return formatLegacyNumber(value);
  if (kind === 'percent') {
    if (value === null || value === undefined || value === '') return '-';
    const raw = String(value).trim();
    if (!raw || raw === '-' || raw === '--') return '-';
    const number = Number(raw.replace(/,/g, '').replace(/%/g, ''));
    return Number.isFinite(number) ? `${number.toLocaleString('en-IN', { maximumFractionDigits: 2 })}%` : '-';
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  const token = String(value ?? '').trim().toUpperCase();
  if (['Y', 'YES', 'TRUE'].includes(token)) return 'Yes';
  if (['N', 'NO', 'FALSE'].includes(token)) return 'No';
  return safeLegacyText(value);
}

export function pickFyersField(row: unknown, aliases: readonly string[], fallback: unknown = null): unknown {
  return pickField(row, aliases, fallback);
}

export function normalizeFyersSymbol(value: unknown): string {
  const text = safeLegacyText(value, '').toUpperCase();
  return text.replace(/^(NSE|BSE):/, '').replace(/(\.NS|-EQ)$/, '').trim();
}

export function getFyersStatusMessage(payload: unknown, fallback: string): string {
  const source = asRecord(payload);
  return safeLegacyText(pickField(source, ['message', 'statusMessage', 'detail', 'error']), fallback);
}

export function extractFyersStats(payload: unknown): UnknownRecord {
  const source = asRecord(payload);
  return asRecord(source.stats ?? source.summary ?? source.data);
}

export function readPayloadData(payload: unknown): UnknownRecord {
  const source = asRecord(payload);
  return asRecord(source.data ?? payload);
}

export function buildCsvDownload(rows: UnknownRecord[], columns: Array<{ aliases: readonly string[]; label: string }>) {
  const escapeCsv = (value: unknown) => {
    const text = safeLegacyText(value, '');
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return [
    columns.map((column) => escapeCsv(column.label)).join(','),
    ...rows.map((row) => columns.map((column) => escapeCsv(pickFyersField(row, column.aliases, ''))).join(',')),
  ].join('\r\n');
}
