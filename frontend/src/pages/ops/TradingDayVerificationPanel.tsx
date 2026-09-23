import { useEffect, useMemo, useState } from 'react';
import { legacyApiGet } from '../../api/client';
import { AppDataTable, type AppDataTableColumn } from '../../components/app/AppDataTable';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import {
  asRecord,
  formatLegacyCount,
  formatLegacyDate,
  formatLegacyDateOnly,
  getNestedDataRecord,
  pickField,
  safeLegacyText,
  type UnknownRecord,
} from '../../adapters/databasePageAdapter';
import { ActionButton, KpiGrid } from './opsPageHelpers';

export type TradingDayVerificationPage = 'DELIVERY' | 'FFMC' | 'MARKET_CAP';

type LoadStatus = 'error' | 'idle' | 'loading' | 'online';

type TradingDayVerificationRow = {
  available: number;
  futurePendingDates: string[];
  futurePendingText: string;
  id: string;
  lastVerifiedAt: string;
  missing: number;
  missingDates: string[];
  missingText: string;
  nonTradingDays: number;
  pageName: string;
  remainingTradingDays: number;
  serialNo: number;
  status: string;
  tradingDaysCy: number;
  year: number;
};

type TradingDayVerificationView = {
  cards: Array<{ className?: string; label: string; value: string }>;
  rows: TradingDayVerificationRow[];
};

type TradingDayVerificationPanelProps = {
  onError?: (message: string) => void;
  page: TradingDayVerificationPage;
  refreshKey: number;
  year: number;
};

function asStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || '').trim()).filter(Boolean);
  }
  const text = safeLegacyText(value, '');
  if (!text || text === '-') return [];
  return text.split(',').map((item) => item.trim()).filter(Boolean);
}

function numberValue(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const parsed = Number(String(value ?? '').replace(/,/g, '').trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatDateList(values: string[], limit = values.length): string {
  const selected = values.slice(0, limit).map((value) => formatLegacyDateOnly(value));
  return selected.length ? selected.join(', ') : '-';
}

function adaptVerificationPayload(payload: UnknownRecord): TradingDayVerificationView {
  const source = getNestedDataRecord(payload);
  const rowsSource = Array.isArray(source.rows) ? source.rows.map((row) => asRecord(row)) : [];
  const row = rowsSource[0] ?? source;
  const pageName = safeLegacyText(pickField(row, ['pageName', 'PAGE_NAME', 'page']), safeLegacyText(pickField(source, ['pageName', 'page']), '-'));
  const year = numberValue(pickField(row, ['YEAR', 'year'], pickField(source, ['year'])));
  const nonTradingDays = numberValue(pickField(row, ['NON_TD', 'non_trading_days'], pickField(source, ['non_trading_days'])));
  const tradingDaysCy = numberValue(pickField(row, ['TDCY', 'trading_days_cy'], pickField(source, ['trading_days_cy'])));
  const remainingTradingDays = numberValue(pickField(row, ['TDCRY', 'trading_days_remaining_cy'], pickField(source, ['trading_days_remaining_cy'])));
  const available = numberValue(pickField(row, ['TDAPT', 'trading_days_available_in_table'], pickField(source, ['trading_days_available_in_table'])));
  const missing = numberValue(pickField(row, ['TDMD', 'trading_days_missing_count'], pickField(source, ['trading_days_missing_count'])));
  const missingDates = asStringArray(pickField(row, ['TDMD_DATES', 'missing_trading_dates', 'historical_missing_dates'], pickField(source, ['missing_trading_dates'])));
  const futurePendingDates = asStringArray(pickField(row, ['futurePendingDates', 'future_pending_dates'], pickField(source, ['future_pending_dates'])));
  const status = safeLegacyText(pickField(row, ['STATUS', 'verificationStatus', 'verification_status'], pickField(source, ['verification_status'])), 'MISSING').toUpperCase();
  const lastVerifiedAt = formatLegacyDate(pickField(row, ['LAST_VERIFIED_AT', 'lastVerifiedAt', 'last_verified_at'], pickField(source, ['last_verified_at'])));
  const verificationRow: TradingDayVerificationRow = {
    available,
    futurePendingDates,
    futurePendingText: formatDateList(futurePendingDates, 10),
    id: `${pageName}-${year}`,
    lastVerifiedAt,
    missing,
    missingDates,
    missingText: formatDateList(missingDates, 10),
    nonTradingDays,
    pageName,
    remainingTradingDays,
    serialNo: numberValue(pickField(row, ['S_NO', 'sNo'], 1)) || 1,
    status,
    tradingDaysCy,
    year,
  };
  return {
    cards: [
      { label: 'Non Trading Days', value: formatLegacyCount(nonTradingDays) },
      { label: 'Trading Days CY', value: formatLegacyCount(tradingDaysCy) },
      { label: 'Trading Days Remaining CY', value: formatLegacyCount(remainingTradingDays) },
      { label: 'Available In Table', value: formatLegacyCount(available) },
      {
        className: missing > 0 ? 'trading-day-verification__kpi--missing' : 'trading-day-verification__kpi--complete',
        label: 'Missing Trading Days',
        value: formatLegacyCount(missing),
      },
    ],
    rows: [verificationRow],
  };
}

function statusClassName(status: string): string {
  return `trading-day-verification__status trading-day-verification__status--${status.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
}

export function shouldFetchTradingDayVerification(requestVersion: number): boolean {
  return requestVersion > 0;
}

export function TradingDayVerificationPanel({ onError, page, refreshKey, year }: TradingDayVerificationPanelProps) {
  const [error, setError] = useState('');
  const [payload, setPayload] = useState<UnknownRecord>({});
  const [requestVersion, setRequestVersion] = useState(0);
  const [status, setStatus] = useState<LoadStatus>('idle');

  useEffect(() => {
    if (!shouldFetchTradingDayVerification(requestVersion)) return undefined;
    const controller = new AbortController();
    setStatus('loading');
    setError('');
    legacyApiGet<UnknownRecord>('/api/market-calendar/trading-day-verification', {
      page,
      refresh: `${refreshKey}-${requestVersion}`,
      year,
    }, {
      signal: controller.signal,
      timeoutMs: 60000,
    }).then((data) => {
      setPayload(getNestedDataRecord(data));
      setStatus('online');
    }).catch((loadError) => {
      if (controller.signal.aborted) return;
      const message = loadError instanceof Error ? loadError.message : String(loadError);
      setError(message);
      setStatus('error');
      onError?.(message);
    });
    return () => controller.abort();
  }, [onError, page, refreshKey, requestVersion, year]);

  const view = useMemo(() => adaptVerificationPayload(payload), [payload]);
  const activeRow = view.rows[0];
  const hasPayload = Object.keys(payload).length > 0;

  const columns = useMemo<Array<AppDataTableColumn<TradingDayVerificationRow>>>(() => [
    { dataCol: 'sno', getSortValue: (row) => row.serialNo, key: 'sno', label: 'S.No', renderCell: (row) => row.serialNo, sortType: 'number' },
    { dataCol: 'page', getSortValue: (row) => row.pageName, key: 'page', label: 'Page Name', renderCell: (row) => row.pageName, sortType: 'string' },
    { dataCol: 'year', getSortValue: (row) => row.year, key: 'year', label: 'Year', renderCell: (row) => row.year, sortType: 'number' },
    { dataCol: 'non_trading_days', getSortValue: (row) => row.nonTradingDays, key: 'nonTradingDays', label: 'Non Trading Days', renderCell: (row) => formatLegacyCount(row.nonTradingDays), sortType: 'number' },
    { dataCol: 'trading_days_cy', getSortValue: (row) => row.tradingDaysCy, key: 'tradingDaysCy', label: 'Trading Days CY', renderCell: (row) => formatLegacyCount(row.tradingDaysCy), sortType: 'number' },
    { dataCol: 'trading_days_remaining_cy', getSortValue: (row) => row.remainingTradingDays, key: 'remainingTradingDays', label: 'Trading Days Remaining CY', renderCell: (row) => formatLegacyCount(row.remainingTradingDays), sortType: 'number' },
    { dataCol: 'trading_days_available_in_table', getSortValue: (row) => row.available, key: 'available', label: 'Trading Days Available In Table', renderCell: (row) => formatLegacyCount(row.available), sortType: 'number' },
    { dataCol: 'trading_days_missing', getSortValue: (row) => row.missing, key: 'missing', label: 'Trading Days Missing', renderCell: (row) => formatLegacyCount(row.missing), sortType: 'number' },
    {
      cellClassName: (row) => row.missing > 0 ? 'trading-day-verification__dates-cell is-missing' : 'trading-day-verification__dates-cell',
      dataCol: 'missing_trading_dates',
      getSortValue: (row) => row.missing,
      key: 'missingDates',
      label: 'Missing Trading Dates',
      renderCell: (row) => row.missingText,
      sortType: 'number',
    },
    {
      dataCol: 'status',
      getSortValue: (row) => row.status,
      key: 'status',
      label: 'Status',
      renderCell: (row) => <span className={statusClassName(row.status)}>{row.status}</span>,
      sortType: 'string',
    },
    { dataCol: 'last_verified_at', getSortValue: (row) => row.lastVerifiedAt, key: 'lastVerifiedAt', label: 'Last Verified At', renderCell: (row) => row.lastVerifiedAt, sortType: 'date' },
  ], []);

  return (
    <section className="trading-day-verification">
      <div className="trading-day-verification__header">
        <div>
          <h3>Trading Day Verification</h3>
          <span>Year {year}</span>
        </div>
        <ActionButton disabled={status === 'loading'} onClick={() => setRequestVersion((current) => current + 1)}>Refresh Verification</ActionButton>
      </div>

      {status === 'loading' && !hasPayload ? (
        <section className="card trading-day-verification__state"><span className="count-pill">Loading trading day verification...</span></section>
      ) : null}
      {error ? <ErrorAlertCard message={error} /> : null}

      {hasPayload ? (
        <>
          <KpiGrid items={view.cards} />
          <section className="card">
            <AppDataTable
              columns={columns}
              emptyMessage="No trading day verification returned."
              getRowKey={(row) => row.id}
              pageSize={1}
              rows={view.rows}
              tableClassName="data-table--blue trading-day-verification__table"
              tableId={`${page}TradingDayVerificationTable`}
            />
          </section>
          {activeRow?.missingDates.length > 10 ? (
            <details className="trading-day-verification__details trading-day-verification__details--missing">
              <summary>View all {formatLegacyCount(activeRow.missingDates.length)} missing trading dates</summary>
              <div>{formatDateList(activeRow.missingDates)}</div>
              <button type="button" onClick={() => navigator.clipboard?.writeText(activeRow.missingDates.join(', '))}>Copy missing dates</button>
            </details>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
