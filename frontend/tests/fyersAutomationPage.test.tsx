import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import {
  buildSkippedSymbolsCsv,
  buildSkippedSymbolsFilename,
  canStartFyersExtraction,
  fyersAutomationLatestSelectableDate,
  formatFyersLtcDate,
  FyersAutomationPage,
  isFyersAuthRequiredStartError,
  shouldInitializeFyersAutomation,
} from '../src/pages/fyers/FyersAutomationPage';
import * as automationPageModule from '../src/pages/fyers/FyersAutomationPage';

type PollErrorDecision = {
  clearJob: boolean;
  consecutiveFailures: number;
  kind: 'not-found' | 'retry';
  message: string;
  preserveSnapshot: boolean;
  retryDelayMs: number;
  shouldToast: boolean;
  status: 'loading' | 'warn';
};

type AutomationPageTestExports = {
  formatFyersErrorMessage?: (error: unknown, fallback?: string) => string;
  isBackendUnreachableFyersError?: (error: unknown) => boolean;
  isTerminalFyersJobFailure?: (status: unknown) => boolean;
  resolveFyersPollError?: (error: unknown, consecutiveFailures: number) => PollErrorDecision;
  shouldRetryFyersAuthStatusLoad?: (error: unknown) => boolean;
};

const automationPageTestExports = automationPageModule as unknown as AutomationPageTestExports;

describe('FyersAutomationPage active job telemetry', () => {
  test('allows only the previous date before 5 PM IST and today from 5 PM IST', () => {
    expect(fyersAutomationLatestSelectableDate(new Date('2026-07-17T11:29:00.000Z'))).toBe('2026-07-16');
    expect(fyersAutomationLatestSelectableDate(new Date('2026-07-17T11:30:00.000Z'))).toBe('2026-07-17');
  });

  test('renders active-job heartbeat and eta labels', () => {
    const markup = renderToStaticMarkup(<FyersAutomationPage />);

    expect(markup).toContain('Authorization URL');
    expect(markup).toContain('Current Symbol');
    expect(markup).toContain('Last Heartbeat');
    expect(markup).toContain('ETA Timestamp');
    expect(markup).toContain('Refresh Status');
  });

  test('renders a local theme toggle next to the copy logs action', () => {
    const markup = renderToStaticMarkup(<FyersAutomationPage />);
    const toggleCount = (markup.match(/aria-label="Toggle theme"/g) || []).length;

    expect(markup).toContain('Copy logs');
    expect(toggleCount).toBeGreaterThanOrEqual(2);
  });

  test('does not render the Uniform_Data rerun summary card', () => {
    const markup = renderToStaticMarkup(<FyersAutomationPage />);

    expect(markup).not.toContain('Uniform_Data Available for Re-Run');
    expect(markup).not.toContain('Open Uniform_Data');
    expect(markup).not.toContain('Copy Failed List');
  });

  test('renders all enterprise automation cards with exact labels', () => {
    const markup = renderToStaticMarkup(<FyersAutomationPage />);

    for (const label of [
      'Total',
      'LTC_DATE',
      'Existing Rows',
      'Missing Ranges',
      'Fetched Rows',
      'Inserted',
      'Updated Rows',
      'Remaining',
      'Failed',
      'Skipped',
      'Skipped Existing',
      'Range Failed',
      'Inserted Skipped',
      'Invalid',
      'Errors',
    ]) {
      expect(markup).toContain(`>${label}<`);
    }
  });

  test('renders skipped-symbol table, columns, and actions', () => {
    const markup = renderToStaticMarkup(<FyersAutomationPage />);

    expect(markup).toContain('Currently Skipped Symbols');
    for (const column of ['Symbol', 'Status', 'Reason', 'Trading Date', 'Retry Count', 'Last Error']) {
      expect(markup).toContain(`>${column}<`);
    }
    expect(markup).toContain('Copy comma-separated symbols');
    expect(markup).toContain('Download TXT');
    expect(markup).toContain('Download detailed CSV');
    expect(markup).not.toContain('Rerun Failed');
    expect(markup).not.toContain('Rerun Remaining');
  });

  test('renders both extraction actions with the shared full-width layout', () => {
    const markup = renderToStaticMarkup(<FyersAutomationPage />);
    const actionRowCount = (markup.match(/fyers-automation-action-row/g) || []).length;
    const fullWidthPrimaryActions = (markup.match(/class="[^"]*w-full[^"]*"[^>]*><span>(Fetch &amp; Insert|Run Batch Insert)<\/span>/g) || []).length;

    expect(actionRowCount).toBe(2);
    expect(fullWidthPrimaryActions).toBe(2);
  });

  test('keeps extraction actions disabled until FYERS auth status allows extraction', () => {
    const markup = renderToStaticMarkup(<FyersAutomationPage />);
    const disabledExtractionActions = (
      markup.match(/disabled=""[^>]*><span>(Fetch &amp; Insert|Run Batch Insert)<\/span>/g) || []
    ).length;

    expect(disabledExtractionActions).toBe(2);
    expect(canStartFyersExtraction({ authenticated: true, canExtract: true })).toBe(true);
    expect(canStartFyersExtraction({ authenticated: true, canExtract: false })).toBe(false);
    expect(canStartFyersExtraction({ authenticated: false })).toBe(false);
  });

  test('classifies backend auth-required start responses separately from unknown job starts', () => {
    expect(isFyersAuthRequiredStartError({
      backendCode: 'FYERS_AUTH_REQUIRED',
      message: 'Authentication Expired. Please authenticate FYERS before extracting symbols.',
      status: 428,
    })).toBe(true);
    expect(isFyersAuthRequiredStartError(new Error('Network unavailable'))).toBe(false);
  });

  test('retries only transient auth-status transport or upstream failures', () => {
    expect(typeof automationPageTestExports.shouldRetryFyersAuthStatusLoad).toBe('function');
    const shouldRetryAuthStatus = automationPageTestExports.shouldRetryFyersAuthStatusLoad;
    if (!shouldRetryAuthStatus) return;

    expect(shouldRetryAuthStatus(new Error('Failed to fetch'))).toBe(true);
    expect(shouldRetryAuthStatus({ message: 'Temporary upstream error', status: 503 })).toBe(true);
    expect(shouldRetryAuthStatus({ message: 'Unauthorized', status: 401 })).toBe(false);
    expect(shouldRetryAuthStatus({ message: 'Validation failed', status: 400 })).toBe(false);
  });

  test('formats backend reachability failures into a clear port-5055 message', () => {
    expect(typeof automationPageTestExports.isBackendUnreachableFyersError).toBe('function');
    expect(typeof automationPageTestExports.formatFyersErrorMessage).toBe('function');
    const isBackendUnreachable = automationPageTestExports.isBackendUnreachableFyersError;
    const formatError = automationPageTestExports.formatFyersErrorMessage;
    if (!isBackendUnreachable || !formatError) return;

    expect(isBackendUnreachable(new TypeError('Failed to fetch'))).toBe(true);
    expect(formatError(new TypeError('Failed to fetch'))).toContain('port 5055');
    expect(isBackendUnreachable({ message: 'Unauthorized', status: 401 })).toBe(false);
  });

  test('reserves the desktop stock-input row in the batch card for horizontal alignment', () => {
    const markup = renderToStaticMarkup(<FyersAutomationPage />);

    expect(markup).toContain('class="fyers-automation-stock-spacer"');
    expect(markup).toContain('aria-hidden="true"');
  });

  test('escapes detailed CSV values safely', () => {
    const csv = buildSkippedSymbolsCsv([
      {
        symbol: 'ABC',
        status: 'FAILED',
        reason: 'Price, unavailable',
        tradingDate: '2026-06-17',
        retryCount: 2,
        lastError: 'Provider said "retry"',
      },
    ]);

    expect(csv).toContain('"Price, unavailable"');
    expect(csv).toContain('"Provider said ""retry"""');
  });

  test('does not substitute the calendar date when trading date is absent', () => {
    expect(buildSkippedSymbolsFilename('txt', '')).toBe('FYERS_SKIPPED_SYMBOLS_--.txt');
    expect(buildSkippedSymbolsFilename('csv', undefined)).toBe('FYERS_SKIPPED_SYMBOLS_--.csv');
  });

  test('waits for centralized session verification before protected job discovery', () => {
    expect(shouldInitializeFyersAutomation(true)).toBe(false);
    expect(shouldInitializeFyersAutomation(false)).toBe(true);
  });

  test('formats the LTC_DATE card as DD-MM-YYYY only', () => {
    expect(formatFyersLtcDate('2026-06-18T00:00:00Z')).toBe('18-06-2026');
    expect(formatFyersLtcDate('2026-06-18')).toBe('18-06-2026');
    expect(formatFyersLtcDate('')).toBe('--');
  });

  test('retries transient polling failures while preserving the last known snapshot', () => {
    expect(typeof automationPageTestExports.resolveFyersPollError).toBe('function');
    const resolvePollError = automationPageTestExports.resolveFyersPollError;
    if (!resolvePollError) return;

    const firstFailure = resolvePollError(new Error('Network unavailable'), 0);
    const thirdFailure = resolvePollError(new Error('Network unavailable'), 2);

    expect(firstFailure).toEqual({
      clearJob: false,
      consecutiveFailures: 1,
      kind: 'retry',
      message: 'Connection delayed. Job may still be running. Retrying...',
      preserveSnapshot: true,
      retryDelayMs: 1500,
      shouldToast: false,
      status: 'loading',
    });
    expect(thirdFailure).toEqual({
      clearJob: false,
      consecutiveFailures: 3,
      kind: 'retry',
      message: 'Unable to refresh status. Last known job may still be running.',
      preserveSnapshot: true,
      retryDelayMs: 1500,
      shouldToast: true,
      status: 'warn',
    });
  });

  test('switches poll recovery to backend-unreachable messaging with backoff', () => {
    expect(typeof automationPageTestExports.resolveFyersPollError).toBe('function');
    const resolvePollError = automationPageTestExports.resolveFyersPollError;
    if (!resolvePollError) return;

    expect(resolvePollError(new TypeError('Failed to fetch'), 0)).toEqual(expect.objectContaining({
      clearJob: false,
      kind: 'retry',
      message: 'Backend server is not reachable. Please check Flask/FastAPI service on port 5055.',
      preserveSnapshot: true,
      retryDelayMs: 1500,
      shouldToast: true,
      status: 'warn',
    }));
    expect(resolvePollError(new TypeError('Failed to fetch'), 2).retryDelayMs).toBeGreaterThan(1500);
  });

  test('clears an active job only for explicit FYERS_JOB_NOT_FOUND responses', () => {
    expect(typeof automationPageTestExports.resolveFyersPollError).toBe('function');
    const resolvePollError = automationPageTestExports.resolveFyersPollError;
    if (!resolvePollError) return;

    expect(resolvePollError(
      { backendCode: 'FYERS_JOB_NOT_FOUND', message: 'FYERS job not found: job-1', status: 404 },
      1,
    )).toEqual(expect.objectContaining({
      clearJob: true,
      kind: 'not-found',
      preserveSnapshot: false,
    }));
    expect(resolvePollError({ message: 'Service unavailable', status: 500 }, 1)).toEqual(expect.objectContaining({
      clearJob: false,
      kind: 'retry',
      preserveSnapshot: true,
    }));
  });

  test('treats only backend FAILED and ERROR statuses as terminal failures', () => {
    expect(typeof automationPageTestExports.isTerminalFyersJobFailure).toBe('function');
    const isTerminalFailure = automationPageTestExports.isTerminalFyersJobFailure;
    if (!isTerminalFailure) return;

    expect(isTerminalFailure('FAILED')).toBe(true);
    expect(isTerminalFailure('ERROR')).toBe(true);
    expect(isTerminalFailure('RUNNING')).toBe(false);
    expect(isTerminalFailure('COMPLETED')).toBe(false);
    expect(isTerminalFailure('SUCCESS')).toBe(false);
  });
});
