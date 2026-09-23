import type { NseAutomationPageConfig } from '../pages/ops/nseAutomationConfigs';

export type UnknownRecord = Record<string, unknown>;

export type MarketCapIndexRowView = {
  id: string;
  index: string;
  ltcDate: string;
  mcap: string;
  mcapRank: string;
  mcapSeries: string;
  raw: UnknownRecord;
  serialNo: number;
  securityName: string;
  symbol: string;
};

export type MarketCapIndexView = {
  kpis: Array<{ label: string; value: string }>;
  latestDate: string;
  rows: MarketCapIndexRowView[];
};

export type NseAutomationRowView = {
  cells: string[];
  id: string;
  raw: UnknownRecord;
};

export type NseAutomationView = {
  kpis: Array<{ label: string; value: string }>;
  rows: NseAutomationRowView[];
  selectedTradeDate: string;
};

export function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {};
}

export function pickField(record: unknown, aliases: readonly string[], fallback: unknown = null): unknown {
  const source = asRecord(record);
  for (const alias of aliases) {
    if (Object.prototype.hasOwnProperty.call(source, alias)) {
      const value = source[alias];
      if (value !== undefined && value !== null && value !== '') {
        return value;
      }
    }
  }
  return fallback;
}

export function unwrapPayloadData(payload: unknown): unknown {
  const source = asRecord(payload);
  return source.data ?? source.DATA ?? payload;
}

export function extractRows(payload: unknown, aliases: readonly string[] = ['rows', 'ROWS', 'data', 'DATA', 'items', 'latestRows', 'latest_rows']): UnknownRecord[] {
  if (Array.isArray(payload)) {
    return payload.map((row) => asRecord(row));
  }
  const source = asRecord(payload);
  for (const alias of aliases) {
    const value = source[alias];
    if (Array.isArray(value)) {
      return value.map((row) => asRecord(row));
    }
  }
  const data = unwrapPayloadData(payload);
  if (data !== payload) {
    return extractRows(data, aliases);
  }
  return [];
}

export function formatLegacyNumber(value: unknown, fallback = '-'): string {
  if (value === null || value === undefined || value === '') return fallback;
  const numeric = typeof value === 'number' ? value : Number(String(value).replace(/,/g, '').replace(/%/g, ''));
  if (!Number.isFinite(numeric)) return fallback;
  return numeric.toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

export function formatLegacyCount(value: unknown, fallback = '0'): string {
  if (value === null || value === undefined || value === '') return fallback;
  const numeric = typeof value === 'number' ? value : Number(String(value).replace(/,/g, ''));
  if (!Number.isFinite(numeric)) return fallback;
  return Math.max(0, Math.trunc(numeric)).toLocaleString('en-IN');
}

export function safeLegacyText(value: unknown, fallback = '-'): string {
  if (value === null || value === undefined || value === '') return fallback;
  const text = String(value).trim();
  return text || fallback;
}

export function formatLegacyDate(value: unknown, fallback = '-'): string {
  if (value === null || value === undefined || value === '') return fallback;
  const text = String(value).trim();
  if (!text) return fallback;
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2})(?::(\d{2}))?)?/);
  if (iso) {
    const [, year, month, day, hour, minute, second] = iso;
    const dateText = `${day}-${month}-${year}`;
    if (hour && minute) {
      return `${dateText} ${hour}:${minute}:${second ?? '00'}`;
    }
    return dateText;
  }
  const parsed = Date.parse(text);
  if (Number.isNaN(parsed)) return text;
  const d = new Date(parsed);
  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const hours = String(d.getHours()).padStart(2, '0');
  const minutes = String(d.getMinutes()).padStart(2, '0');
  const seconds = String(d.getSeconds()).padStart(2, '0');
  if (/[T\s]\d{2}:\d{2}/.test(text)) {
    return `${day}-${month}-${d.getFullYear()} ${hours}:${minutes}:${seconds}`;
  }
  return `${day}-${month}-${d.getFullYear()}`;
}

export function formatLegacyDateOnly(value: unknown, fallback = '-'): string {
  if (value === null || value === undefined || value === '') return fallback;
  const text = String(value).trim();
  if (!text) return fallback;

  const legacyDateTime = text.match(/^(\d{2})-(\d{2})-(\d{4})(?:\s+\d{2}:\d{2}(?::\d{2})?)?$/);
  if (legacyDateTime) return `${legacyDateTime[1]}-${legacyDateTime[2]}-${legacyDateTime[3]}`;

  const isoDateTime = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s]\d{2}:\d{2}(?::\d{2})?)?/);
  if (isoDateTime) return `${isoDateTime[3]}-${isoDateTime[2]}-${isoDateTime[1]}`;

  const parsed = Date.parse(text.replace(/\.(\d{3})\d+/, '.$1'));
  if (Number.isNaN(parsed)) return text;
  const d = new Date(parsed);
  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  return `${day}-${month}-${d.getFullYear()}`;
}

export function normalizeInsertionSource(value: unknown): string {
  const token = safeLegacyText(value, '-').toUpperCase();
  return token === '-' ? token : token.replace(/_/g, ' ');
}

export function getNestedDataRecord(payload: unknown): UnknownRecord {
  const data = unwrapPayloadData(payload);
  return asRecord(data);
}

export function adaptMarketCapIndexPayload(payload: unknown): MarketCapIndexView {
  const source = asRecord(payload);
  const data = unwrapPayloadData(payload);
  const rows = Array.isArray(data) ? data.map((row) => asRecord(row)) : extractRows(payload, ['data', 'DATA', 'rows', 'ROWS']);
  const summary = asRecord(source.summary ?? source.SUMMARY);
  const indexWise = Array.isArray(summary.indexWise) ? summary.indexWise.map((row) => asRecord(row)) : [];
  const indexMap = new Map(indexWise.map((row) => [String(row.index ?? '').toUpperCase(), row]));

  const marketCapCards = [
    { label: 'Total Symbols Count', value: formatLegacyCount(pickField(summary, ['totalSymbols', 'TOTAL_SYMBOLS']), '-') },
    { label: 'Total MCap in Crores', value: formatLegacyNumber(pickField(summary, ['totalMarketCapCrores', 'TOTAL_MARKET_CAP_CRORES'])) },
    { label: 'Large Cap Total Symbols Count', value: formatLegacyCount(pickField(summary, ['largeSymbols', 'LARGE_SYMBOLS']), '-') },
    { label: 'Mid Cap Total Symbols Count', value: formatLegacyCount(pickField(summary, ['midSymbols', 'MID_SYMBOLS']), '-') },
    { label: 'Small Cap Total Symbols Count', value: formatLegacyCount(pickField(summary, ['smallSymbols', 'SMALL_SYMBOLS']), '-') },
    {
      label: 'Index Wise Total Symbols Count',
      value: `L:${formatLegacyCount(indexMap.get('LARGE')?.symbolsCount, '-')} | M:${formatLegacyCount(indexMap.get('MID')?.symbolsCount, '-')} | S:${formatLegacyCount(indexMap.get('SMALL')?.symbolsCount, '-')}`,
    },
    {
      label: 'Index Wise Total MCap in Crores',
      value: `L:${formatLegacyNumber(indexMap.get('LARGE')?.marketCapCrores)} | M:${formatLegacyNumber(indexMap.get('MID')?.marketCapCrores)} | S:${formatLegacyNumber(indexMap.get('SMALL')?.marketCapCrores)}`,
    },
    { label: 'Large Cap Total MCap in Crores', value: formatLegacyNumber(pickField(summary, ['largeMarketCapCrores', 'LARGE_MARKET_CAP_CRORES'])) },
    { label: 'Mid Cap Total MCap in Crores', value: formatLegacyNumber(pickField(summary, ['midMarketCapCrores', 'MID_MARKET_CAP_CRORES'])) },
    { label: 'Small Cap Total MCap in Crores', value: formatLegacyNumber(pickField(summary, ['smallMarketCapCrores', 'SMALL_MARKET_CAP_CRORES'])) },
  ];

  return {
    kpis: marketCapCards,
    latestDate: safeLegacyText(pickField(source, ['latestDate', 'LATEST_DATE'])),
    rows: rows.map((row, index) => {
      const symbol = safeLegacyText(pickField(row, ['SYMBOL', 'symbol', 'script', 'SCRIPT']));
      return {
        id: `${symbol}-${index}`,
        index: safeLegacyText(pickField(row, ['INDEX', 'index', 'mcapIndex', 'mcap_index'])),
        ltcDate: formatLegacyDate(pickField(row, ['LTC_DATE', 'ltcDate', 'ltc_date', 'TRADE_DATE', 'tradeDate', 'trade_date'])),
        mcap: formatLegacyNumber(pickField(row, ['MCAP', 'mcap', 'marketCapCrores', 'MARKET_CAP_CRORES', 'market_cap_crores'])),
        mcapRank: formatLegacyCount(pickField(row, ['MCAP_RANK', 'mcapRank', 'mcap_rank']), '-'),
        mcapSeries: safeLegacyText(pickField(row, ['MCAP_SERIES', 'mcapSeries', 'mcap_series'])),
        raw: row,
        serialNo: index + 1,
        securityName: safeLegacyText(pickField(row, ['SECURITY_NAME', 'securityName', 'security_name'])),
        symbol,
      };
    }),
  };
}

export function formatLegacyFlag(value: unknown, fallback = 'N'): string {
  if (value === null || value === undefined || value === '') return fallback;
  if (typeof value === 'boolean') return value ? 'Y' : 'N';
  const text = String(value).trim();
  if (!text) return fallback;
  const normalized = text.toLowerCase();
  if (['y', 'yes', 'true', 'manual', 'automation'].includes(normalized)) return 'Y';
  if (['n', 'no', 'false', 'none', 'unknown'].includes(normalized)) return 'N';
  const numeric = Number(text.replace(/,/g, ''));
  if (Number.isFinite(numeric)) return numeric > 0 ? 'Y' : 'N';
  return text.toUpperCase();
}

export function formatCellByKind(value: unknown, kind: 'count' | 'date' | 'dateOnly' | 'flag' | 'number' | 'source' | 'text'): string {
  if (kind === 'count') return formatLegacyCount(value, '-');
  if (kind === 'date') return formatLegacyDate(value);
  if (kind === 'dateOnly') return formatLegacyDateOnly(value);
  if (kind === 'flag') return formatLegacyFlag(value);
  if (kind === 'number') return formatLegacyNumber(value);
  if (kind === 'source') return normalizeInsertionSource(value);
  return safeLegacyText(value);
}

function numericValue(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(String(value).replace(/,/g, '').trim());
  return Number.isFinite(parsed) ? parsed : null;
}

function formatNseRowStatus(row: UnknownRecord, aliases: readonly string[]): string {
  const raw = safeLegacyText(pickField(row, aliases), '').toUpperCase();
  const insertedRows = numericValue(pickField(row, ['inserted_rows', 'insertedRows', 'inserted_count', 'insertedCount', 'success_rows', 'successRows']));
  if (insertedRows !== null && insertedRows > 0) return 'SUCCESS';
  if (raw === 'PARSE_ERROR') return 'FAILED';
  return formatCellByKind(raw, 'text');
}

export function buildNseAutomationView(config: NseAutomationPageConfig, payload: unknown): NseAutomationView {
  const data = getNestedDataRecord(payload);
  const summary = asRecord(data.summary ?? data.SUMMARY);
  const rows = extractRows(data, ['rows', 'ROWS', 'latestRows', 'latest_rows']);
  const latestRowTradeDate = rows
    .map((row) => pickField(row, ['trade_date', 'TRADE_DATE', 'tradeDate']))
    .find((value) => value !== null && value !== undefined && value !== '');
  const selectedTradeDate = safeLegacyText(
    latestRowTradeDate
      ?? pickField(data, ['latest_trade_date', 'latestTradeDate', 'tradeDate', 'trade_date', 'tradeDateLabel', 'trade_date_display'])
      ?? pickField(summary, ['latest_trade_date', 'latestTradeDate', 'tradeDate', 'trade_date', 'tradeDateLabel', 'trade_date_display']),
  );
  const mode = safeLegacyText(pickField(data, ['mode', 'sourceMode', 'source_mode', 'runMode', 'run_mode']), '').toUpperCase();

  const kpis = config.kpis.map((kpi) => {
    const source = kpi.source === 'data' ? data : summary;
    let rawValue = kpi.aliases === 'tradeDate'
      ? selectedTradeDate
      : pickField(source, kpi.aliases);
    if (kpi.format === 'flag' && kpi.label === 'Manual Rows' && mode === 'MANUAL') rawValue = true;
    if (kpi.format === 'flag' && kpi.label === 'Automation Rows' && mode === 'AUTOMATION') rawValue = true;
    return {
      label: kpi.label,
      value: formatCellByKind(rawValue, kpi.format),
    };
  });

  return {
    kpis,
    rows: rows.map((row, index) => {
      const symbol = safeLegacyText(pickField(row, ['symbol', 'SYMBOL', 'script', 'SCRIPT']), String(index + 1));
      return {
        cells: config.rowColumns.map((column) => (
          column.key === 'status'
            ? formatNseRowStatus(row, column.aliases)
            : formatCellByKind(pickField(row, column.aliases), column.format)
        )),
        id: `${symbol}-${index}`,
        raw: row,
      };
    }),
    selectedTradeDate,
  };
}
