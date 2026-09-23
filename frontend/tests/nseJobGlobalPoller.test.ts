import { describe, expect, test } from 'vitest';
import {
  buildNseDatabaseInsertToastDescription,
  buildStockHistoryMergeToastDescription,
  getNseGlobalPollDelay,
  isNseGlobalPollActiveStatus,
  NSE_GLOBAL_POLL_ACTIVE_INTERVAL_MS,
  NSE_GLOBAL_POLL_HIDDEN_INTERVAL_MS,
  NSE_GLOBAL_POLL_IDLE_INTERVAL_MS,
} from '../src/components/app/NseJobGlobalPoller';

describe('NseJobGlobalPoller stock-history merge toast', () => {
  test('formats dev and oracle merged row counts from inserted and updated rows', () => {
    expect(buildStockHistoryMergeToastDescription({
      inserted_dev: 100,
      updated_dev: 23,
      inserted_oracle: 120,
      updated_oracle: 3,
    })).toBe('123 merged both the tables.');
  });

  test('keeps separate dev and oracle merge counts when totals differ', () => {
    expect(buildStockHistoryMergeToastDescription({
      inserted_dev: 100,
      updated_dev: 23,
      inserted_oracle: 120,
      updated_oracle: 4,
    })).toBe('Dev:123 and Oracle:124 merged both the tables.');
  });

  test('formats NSE database insert completion toast details', () => {
    expect(buildNseDatabaseInsertToastDescription('NSE Delivery Data', {
      jobId: 'delivery-run',
      request: { tradeDate: '2026-06-24' },
      counts: { insertedRows: 947 },
    })).toBe('NSE Delivery Data inserted into DB successfully. Rows: 947. Trading Date: 2026-06-24.');
  });
});

describe('NseJobGlobalPoller scheduling', () => {
  test('backs off while idle and pauses longer for hidden tabs', () => {
    expect(getNseGlobalPollDelay(false, true)).toBe(NSE_GLOBAL_POLL_IDLE_INTERVAL_MS);
    expect(getNseGlobalPollDelay(false, false)).toBe(NSE_GLOBAL_POLL_HIDDEN_INTERVAL_MS);
  });

  test('uses the fast interval only while a visible job is active', () => {
    expect(getNseGlobalPollDelay(true, true)).toBe(NSE_GLOBAL_POLL_ACTIVE_INTERVAL_MS);
    expect(getNseGlobalPollDelay(true, false)).toBe(NSE_GLOBAL_POLL_HIDDEN_INTERVAL_MS);
  });

  test('recognizes active job states without treating waiting or terminal states as active', () => {
    expect(isNseGlobalPollActiveStatus('running')).toBe(true);
    expect(isNseGlobalPollActiveStatus('IN_PROGRESS')).toBe(true);
    expect(isNseGlobalPollActiveStatus('WAITING_FOR_5PM_WINDOW')).toBe(false);
    expect(isNseGlobalPollActiveStatus('SUCCESS')).toBe(false);
  });
});
