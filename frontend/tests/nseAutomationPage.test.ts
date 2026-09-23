import { describe, expect, test } from 'vitest';
import {
  buildNseAutomationToast,
  buildNseProcessToast,
  buildNseValidateToast,
  isNseAutomationJobActive,
  resolveStageTradeDateLabel,
  shouldAutoContinueAfterDownload,
} from '../src/pages/ops/NseAutomationPage';
import { NSE_AUTOMATION_PAGE_CONFIGS } from '../src/pages/ops/nseAutomationConfigs';

describe('NSE automation download behavior', () => {
  test('continues into full automation when auto insert is enabled and no symbol override is set', () => {
    expect(shouldAutoContinueAfterDownload(true, '')).toBe(true);
    expect(shouldAutoContinueAfterDownload(true, '   ')).toBe(true);
  });

  test('keeps download-only behavior when auto insert is disabled', () => {
    expect(shouldAutoContinueAfterDownload(false, '')).toBe(false);
  });

  test('keeps auto-insert enabled even when a toolbar symbol override is present', () => {
    expect(shouldAutoContinueAfterDownload(true, 'RELIANCE, TCS')).toBe(true);
  });

  test('builds a validate success toast with extracted row counts', () => {
    const toast = buildNseValidateToast('NSE Market Cap', {
      inspection: { matchedRows: 25, parseErrorRows: 1 },
      request: { tradeDate: '2026-05-29' },
    });

    expect(toast.title).toBe('NSE Market Cap Extracted Successfully');
    expect(toast.tone).toBe('success');
    expect(toast.description).toContain('NSE Market Cap extracted successfully for 2026-05-29.');
    expect(toast.description).toContain('Rows 25');
    expect(toast.description).toContain('Valid 25');
    expect(toast.description).toContain('Invalid 1');
  });

  test('builds a manual process success toast for Oracle DB insertions', () => {
    const toast = buildNseProcessToast('NSE Delivery Data', {
      records_inserted: 12,
      records_skipped_existing: 3,
      tradeDate: '2026-05-29',
    });

    expect(toast.title).toBe('NSE Delivery Data Extracted Successfully');
    expect(toast.tone).toBe('success');
    expect(toast.description).toContain('NSE Delivery Data extracted successfully for 2026-05-29.');
    expect(toast.description).toContain('Rows 12');
    expect(toast.description).toContain('Inserted 12');
    expect(toast.description).toContain('Skipped 3');
  });

  test('builds an automation success toast from nested pipeline counts', () => {
    const toast = buildNseAutomationToast('NSE FFMC', {
      result: {
        counts: { insertedRows: 8, skippedRows: 2, failedRows: 0 },
        request: { tradeDate: '2026-05-29' },
      },
    });

    expect(toast.title).toBe('NSE FFMC Extracted Successfully');
    expect(toast.tone).toBe('success');
    expect(toast.description).toContain('NSE FFMC extracted successfully for 2026-05-29.');
    expect(toast.description).toContain('Rows 8');
    expect(toast.description).toContain('Inserted 8');
    expect(toast.description).toContain('Skipped 2');
  });

  test('formats the runtime trade date label from an ISO tradeDate response', () => {
    expect(resolveStageTradeDateLabel({
      tradeDate: '2026-05-29',
    })).toBe('29-05-2026');
  });

  test('prefers an explicit display trade date label from stage payloads', () => {
    expect(resolveStageTradeDateLabel({
      tradeDateLabel: '29-05-2026',
      tradeDate: '2026-05-27',
    })).toBe('29-05-2026');
  });

  test('configures all NSE database pages to use backend persistent jobs', () => {
    expect(NSE_AUTOMATION_PAGE_CONFIGS.marketCap.fullRunEndpoint).toBe('/api/marketdata/nse-mcap/pipeline/start');
    expect(NSE_AUTOMATION_PAGE_CONFIGS.ffmc.fullRunEndpoint).toBe('/api/marketdata/nse-ffmc/pipeline/start');
    expect(NSE_AUTOMATION_PAGE_CONFIGS.delivery.fullRunEndpoint).toBe('/api/marketdata/nse-delivery/pipeline/start');
  });

  test('detects active persisted jobs from refreshed backend snapshots', () => {
    expect(isNseAutomationJobActive({ jobId: 'mcap-job', status: 'RUNNING' })).toBe(true);
    expect(isNseAutomationJobActive({ job_id: 'ffmc-job', status: 'running' })).toBe(true);
    expect(isNseAutomationJobActive({ id: 'delivery-job', status: 'VALIDATING' })).toBe(true);
    expect(isNseAutomationJobActive({ jobId: 'done-job', status: 'SUCCESS' })).toBe(false);
    expect(isNseAutomationJobActive({ status: 'RUNNING' })).toBe(false);
  });
});
