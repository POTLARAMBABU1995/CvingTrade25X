import { legacyApiGet, legacyApiPost, legacyApiPostForm } from '../../api/client';

export type FundamentalIngestionSummary = {
  total_symbols: number;
  symbols_completed: number;
  symbols_pending: number;
  symbols_failed: number;
  download_completed: number;
  download_pending: number;
  download_failed: number;
  download_blocked?: number;
  db_ingestion_completed: number;
  db_ingestion_pending: number;
  db_ingestion_failed: number;
  total_quarters_ingested: number;
  total_years_ingested: number;
  last_scheduler_run_time: string | null;
  last_successful_ingestion_time: string | null;
  generated_at?: string;
};

export type FundamentalSchedulerStatus = {
  running: boolean;
  interval_seconds: number;
  interval_label?: string | null;
  last_run_time: string | null;
  next_run_time: string | null;
  last_success_time: string | null;
  last_failure_time: string | null;
  last_download_time?: string | null;
  last_processed_file: string | null;
  last_processed_symbol: string | null;
  current_run_id?: string | null;
  last_error: string | null;
  login_status?: string | null;
  uploaded_symbols_count?: number;
  download_mode?: string | null;
  scheduler_status?: string | null;
  active_mode?: 'AUTO' | 'MANUAL' | string | null;
  queue_paused?: boolean;
  pause_reason?: string | null;
  workers?: Record<string, FundamentalWorkerMetrics>;
  logs?: FundamentalOperationalLog[];
  pipeline?: FundamentalPipelineState;
  auth?: FundamentalScreenerAuthStatus;
  schema?: FundamentalScreenerSchemaStatus;
  auth_status?: string | null;
  authenticated?: boolean;
};

export type FundamentalScreenerSchemaStatus = {
  status: string;
  missing_objects?: string[];
  missing_columns?: string[];
  missing_constraints?: string[];
  missing_indexes?: string[];
  apply_script?: string | null;
  indexes_script?: string | null;
};

export type FundamentalScreenerAuthStatus = {
  authenticated: boolean;
  auth_status: string;
  symbol?: string | null;
  checked_at?: string | null;
  reason?: string | null;
  session_state_path?: string | null;
  cookie_count?: number;
  session_before_hash?: string | null;
  session_after_hash?: string | null;
  message?: string | null;
  last_error?: string | null;
  schema_status?: string | null;
  missing_schema_objects?: string[];
  missing_schema_columns?: string[];
  missing_schema_constraints?: string[];
  missing_schema_indexes?: string[];
  apply_script?: string | null;
};

export type FundamentalWorkerMetrics = {
  status: string;
  current_symbol?: string | null;
  current_file?: string | null;
  completed_count?: number;
  pending_count?: number;
  failed_count?: number;
  blocked_count?: number;
  retry_count?: number;
  duplicate_count?: number;
  average_duration_ms?: number;
  last_duration_ms?: number;
  cooldown_remaining_seconds?: number;
  last_error?: string | null;
  last_symbol?: string | null;
  last_file?: string | null;
  last_started_at?: string | null;
  last_finished_at?: string | null;
};

export type FundamentalPipelineState = {
  scheduler_status: string;
  active_mode?: 'AUTO' | 'MANUAL' | string | null;
  queue_paused?: boolean;
  pause_reason?: string | null;
  download: FundamentalWorkerMetrics;
  validate: FundamentalWorkerMetrics;
  insert: FundamentalWorkerMetrics;
  success: FundamentalWorkerMetrics;
};

export type FundamentalOperationalLog = {
  timestamp?: string | null;
  category?: string | null;
  status?: string | null;
  job_id?: number | null;
  symbol?: string | null;
  stage?: string | null;
  duration_ms?: number | null;
  message: string;
};

export type FundamentalIngestionStatusRow = {
  symbol: string;
  company_name: string | null;
  index_name: string;
  status: string;
  download_status?: string | null;
  ingestion_status?: string | null;
  screener_url?: string | null;
  last_download_time?: string | null;
  last_ingestion_time: string | null;
  local_file_name?: string | null;
  local_folder_path?: string | null;
  file_size_bytes?: number | null;
  retry_count?: number;
  last_download_start_time?: string | null;
  last_download_end_time?: string | null;
  quarters_count: number;
  years_count: number;
  first_year: string | null;
  latest_year: string | null;
  first_quarter: string | null;
  latest_quarter: string | null;
  source_file_name: string | null;
  inserted_count: number;
  updated_count: number;
  skipped_count: number;
  failed_count: number;
  error_message: string | null;
  ingestion_error_message?: string | null;
  download_error_message?: string | null;
  rows_inserted_total?: number;
  rows_updated_total?: number;
  run_id?: string | null;
  download_stage?: string | null;
  validation_stage?: string | null;
  extraction_stage?: string | null;
  db_stage?: string | null;
  pipeline_stage?: string | null;
};

export type FundamentalIngestionStatusResponse = {
  summary: FundamentalIngestionSummary;
  items: FundamentalIngestionStatusRow[];
  rows?: FundamentalIngestionStatusRow[];
  scheduler: FundamentalSchedulerStatus;
  auth?: FundamentalScreenerAuthStatus;
  schema?: FundamentalScreenerSchemaStatus;
  pipeline?: FundamentalPipelineState;
  logs?: FundamentalOperationalLog[];
  queue?: {
    status: string;
    items: Array<Record<string, unknown>>;
    count: number;
  };
};

export type LocalXlsxIngestionFileItem = {
  file_id?: number;
  file_name: string;
  file_path: string;
  file_hash: string | null;
  symbol: string | null;
  source?: string | null;
  status: string;
  error_message?: string | null;
  raw_folder_path?: string | null;
  processed_json_path?: string | null;
  file_size_bytes?: number | null;
  section_count?: number;
  warning_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
  processed_at?: string | null;
};

export type LocalXlsxIngestionSummary = {
  inbox_dir?: string;
  output_root_dir?: string;
  auto_ingestion_enabled?: boolean;
  auto_ingestion_interval_seconds?: number;
  inbox_xlsx_count?: number;
  pending_inbox_files?: number;
  total_files_processed?: number;
  processed_count?: number;
  processing_count?: number;
  pending_status_count?: number;
  inserted?: number;
  skipped_duplicate?: number;
  failed?: number;
  failed_validation?: number;
  failed_extraction?: number;
  failed_db_insert?: number;
  discovered_count?: number;
  validating_count?: number;
  validated_count?: number;
  last_file_status?: string | null;
  last_file_name?: string | null;
  status_counts?: Record<string, number>;
  last_ingestion_time?: string | null;
  last_update_time?: string | null;
  latest_symbol_processed?: string | null;
  generated_at?: string;
};

export type LocalXlsxFlowCounts = {
  total: number;
  pending: number;
  processed: number;
  success: number;
  failed: number;
};

export type LocalXlsxFlowLastRun = {
  run_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  status: string | null;
};

export type LocalXlsxFlowStatusResponse = {
  flow: string;
  schema_status: string;
  status: string;
  source_dir: string | null;
  output_dir: string | null;
  counts: LocalXlsxFlowCounts;
  last_run: LocalXlsxFlowLastRun | null;
  message: string;
  summary?: LocalXlsxIngestionSummary;
  items?: LocalXlsxIngestionFileItem[];
};

export type LocalXlsxRunFileResult = {
  file_name: string;
  symbol: string | null;
  status: string;
  stage: string;
  error?: string | null;
  file_hash?: string | null;
  raw_file_path?: string | null;
  processed_json_path?: string | null;
  elapsed_ms?: number | null;
};

export type LocalXlsxRunResponse = {
  run_id: string;
  flow: string;
  schema_status: string;
  status: string;
  stage: string;
  counts: LocalXlsxFlowCounts;
  files: LocalXlsxRunFileResult[];
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number;
  message: string;
};

export type LocalXlsxLogsResponse = {
  flow: string;
  count: number;
  items: Array<{
    timestamp?: string | null;
    file_name?: string | null;
    symbol?: string | null;
    file_hash?: string | null;
    status: string;
    stage: string;
    message: string;
  }>;
};

export type FundamentalRunNowResponse = {
  run_id?: string;
  status: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  total_files: number;
  success_count: number;
  failed_count: number;
  skipped_count: number;
  latest_processed_symbol: string | null;
  latest_processed_file: string | null;
  message: string;
  files?: Array<{
    symbol: string | null;
    source_file: string;
    status: string;
    inserted_count: number;
    updated_count: number;
    skipped_count: number;
    failed_count: number;
    error_message: string | null;
  }>;
};

export type FundamentalValidateRunResponse = {
  run_id?: string;
  status: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  total_files: number;
  success_count: number;
  failed_count: number;
  skipped_count: number;
  latest_processed_symbol: string | null;
  latest_processed_file: string | null;
  message: string;
  files?: Array<{
    symbol: string | null;
    source_file: string;
    status: string;
    row_count: number;
    quarters_count: number;
    years_count: number;
    skipped_count: number;
    failed_count: number;
    local_folder_path: string | null;
    file_hash: string | null;
    file_size_bytes: number | null;
    error_message: string | null;
  }>;
};

export type FundamentalSymbolsImportResponse = {
  source_file: string;
  index_name: string;
  inserted_count: number;
  skipped_count: number;
  failed_count: number;
  errors: string[];
  symbols: Array<{ symbol: string }>;
};

export type FundamentalDownloadItem = {
  symbol: string;
  screener_url: string;
  status: string;
  download_status?: string | null;
  local_folder_path: string | null;
  local_file_name: string | null;
  file_hash: string | null;
  file_size_bytes?: number | null;
  error_message: string | null;
  error_code?: string | null;
  abort_reason?: string | null;
  step?: string | null;
  elapsed_ms?: number | null;
  auth_mode?: string | null;
  stack_trace?: string | null;
  cache_used?: boolean;
};

export type FundamentalDownloadRunResponse = {
  run_id?: string;
  status: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  total_symbols: number;
  completed_count: number;
  failed_count: number;
  blocked_count: number;
  skipped_count: number;
  download_completed?: number;
  download_failed?: number;
  download_blocked?: number;
  download_skipped?: number;
  latest_processed_symbol: string | null;
  message: string;
  items: FundamentalDownloadItem[];
  rows?: FundamentalDownloadItem[];
};

export type FundamentalFullAutoResponse = {
  run_id?: string;
  status: string;
  download: FundamentalDownloadRunResponse;
  validation?: FundamentalValidateRunResponse | null;
  ingestion: FundamentalRunNowResponse;
  summary?: Record<string, unknown>;
  symbols?: Array<Record<string, unknown>>;
};

export type FundamentalRetryFailedResponse = {
  run_id?: string;
  status: string;
  download: Pick<FundamentalDownloadRunResponse, 'status' | 'completed_count' | 'failed_count' | 'blocked_count' | 'skipped_count' | 'latest_processed_symbol' | 'message' | 'items'> | null;
  ingestion: Pick<FundamentalRunNowResponse, 'status' | 'total_files' | 'success_count' | 'failed_count' | 'skipped_count' | 'latest_processed_symbol' | 'latest_processed_file' | 'message' | 'files'> | null;
  message: string;
};

export type FundamentalSchedulerActionResponse = FundamentalSchedulerStatus & {
  status?: string;
  message?: string;
  session_ready?: boolean;
  enqueued_count?: number;
  recovered_count?: number;
  reenqueueed_count?: number;
  reenqueued_count?: number;
  login_window_opened?: boolean;
  symbol?: string | null;
  url?: string | null;
  browser_mode?: string | null;
  symbols?: string[];
  max_symbols?: number | null;
};

export type FundamentalUploadedScreenerSymbol = {
  id?: number;
  symbol: string;
  source?: string | null;
  active_flag: string;
  created_ts?: string | null;
  updated_ts?: string | null;
};

export type FundamentalScreenerCsvUploadResponse = {
  status: string;
  run_id: string;
  file_name: string;
  total_rows: number;
  inserted_rows: number;
  duplicate_skipped_rows: number;
  invalid_rows: number;
  uploaded_symbols_count: number;
  errors?: string[];
};

export function fetchFundamentalIngestionStatus(signal?: AbortSignal) {
  return legacyApiGet<FundamentalIngestionStatusResponse>('/api/fundamental/ingestion/status', undefined, {
    signal,
    timeoutMs: 10000,
  });
}

export function fetchFundamentalSchedulerStatus(signal?: AbortSignal) {
  return legacyApiGet<FundamentalSchedulerStatus>('/api/fundamental/scheduler/status', undefined, {
    signal,
    timeoutMs: 5000,
  });
}

export function runFundamentalIngestionNow(symbols?: string[], failMissingSymbols = false) {
  return legacyApiPost<FundamentalRunNowResponse>(
    '/api/fundamental/ingestion/run-now',
    { symbols, fail_missing_symbols: failMissingSymbols },
    { timeoutMs: 45000 },
  );
}

export function validateScreenerFilesNow(symbols?: string[], failMissingSymbols = false) {
  return legacyApiPost<FundamentalValidateRunResponse>(
    '/api/fundamental/screener/extract-validate/run-now',
    { symbols, fail_missing_symbols: failMissingSymbols },
    { timeoutMs: 45000 },
  );
}

export function importNifty50Symbols() {
  return legacyApiPost<FundamentalSymbolsImportResponse>('/api/fundamental/symbols/import', {}, { timeoutMs: 20000 });
}

export function runScreenerDownloadNow(
  mode: 'pending' | 'all' | 'symbols' | 'selected' = 'all',
  symbols?: string[],
  maxSymbols?: number,
  options?: {
    authMode?: 'anonymous' | 'persistent_session' | 'credentials';
    allowCachedFiles?: boolean;
  },
) {
  return legacyApiPost<FundamentalDownloadRunResponse>(
    '/api/fundamental/screener/download/run-now',
    {
      mode,
      symbols,
      max_symbols: maxSymbols,
      auth_mode: options?.authMode,
      allow_cached_files: options?.allowCachedFiles ?? false,
    },
    { timeoutMs: 300000 },
  );
}

export function runFundamentalFullAutoNow(
  mode: 'pending' | 'all' | 'symbols' | 'selected' = 'pending',
  symbols?: string[],
  options?: {
    authMode?: 'anonymous' | 'persistent_session' | 'credentials';
    allowCachedFiles?: boolean;
  },
) {
  return legacyApiPost<FundamentalFullAutoResponse>(
    '/api/fundamental/full-auto/run-now',
    {
      mode,
      symbols,
      auth_mode: options?.authMode,
      allow_cached_files: options?.allowCachedFiles ?? false,
    },
    { timeoutMs: 360000 },
  );
}

export function retryFailedFundamental() {
  return legacyApiPost<FundamentalRetryFailedResponse>('/api/fundamental/retry-failed', {}, { timeoutMs: 360000 });
}

export function startFundamentalScheduler() {
  return legacyApiPost<FundamentalSchedulerStatus>('/api/fundamental/scheduler/start', {}, { timeoutMs: 5000 });
}

export function stopFundamentalScheduler() {
  return legacyApiPost<FundamentalSchedulerStatus>('/api/fundamental/scheduler/stop', {}, { timeoutMs: 5000 });
}

export function pauseFundamentalScheduler() {
  return legacyApiPost<FundamentalSchedulerActionResponse>('/api/fundamental/screener/scheduler/pause', {}, { timeoutMs: 5000 });
}

export function resumeFundamentalScheduler() {
  return legacyApiPost<FundamentalSchedulerActionResponse>('/api/fundamental/screener/scheduler/resume', {}, { timeoutMs: 5000 });
}

export function retryFailedFundamentalQueue() {
  return legacyApiPost<FundamentalSchedulerActionResponse>('/api/fundamental/screener/scheduler/retry-failed', {}, { timeoutMs: 10000 });
}

export function retryBlockedFundamentalQueue() {
  return legacyApiPost<FundamentalSchedulerActionResponse>('/api/fundamental/screener/scheduler/retry-blocked', {}, { timeoutMs: 10000 });
}

export function clearStuckFundamentalQueue() {
  return legacyApiPost<FundamentalSchedulerActionResponse>('/api/fundamental/screener/scheduler/clear-stuck', {}, { timeoutMs: 10000 });
}

export function forceRunFundamentalQueue(symbols?: string[], maxSymbols?: number) {
  return legacyApiPost<FundamentalSchedulerActionResponse>(
    '/api/fundamental/screener/scheduler/force-run',
    { symbols, max_symbols: maxSymbols },
    { timeoutMs: 10000 },
  );
}

export function fetchUploadedScreenerSymbols(signal?: AbortSignal) {
  return legacyApiGet<FundamentalUploadedScreenerSymbol[]>('/api/screener/symbols', undefined, {
    signal,
    timeoutMs: 10000,
  });
}

export function uploadScreenerSymbolsCsv(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return legacyApiPostForm<FundamentalScreenerCsvUploadResponse>('/api/screener/csv/upload', formData, {
    timeoutMs: 30000,
  });
}

export function manualRunUploadedScreenerSymbols(symbols?: string[], maxSymbols?: number) {
  return legacyApiPost<FundamentalSchedulerActionResponse>(
    '/api/screener/manual/run',
    { symbols, max_symbols: maxSymbols },
    { timeoutMs: 10000 },
  );
}

export function resumeAfterScreenerLogin(symbol?: string) {
  return legacyApiPost<FundamentalSchedulerActionResponse>(
    '/api/fundamental/screener/auth/resume',
    symbol ? { symbol } : {},
    { timeoutMs: 10000 },
  );
}

export function openScreenerLoginBrowser(symbol?: string) {
  return legacyApiPost<FundamentalSchedulerActionResponse>(
    '/api/fundamental/screener/auth/open-login',
    symbol ? { symbol } : {},
    { timeoutMs: 10000 },
  );
}

export function fetchScreenerAuthStatus(signal?: AbortSignal) {
  return legacyApiGet<FundamentalScreenerAuthStatus>('/api/fundamental/screener/auth/status', undefined, {
    signal,
    timeoutMs: 10000,
  });
}

export function verifyScreenerLogin(symbol?: string) {
  return legacyApiPost<FundamentalSchedulerActionResponse>(
    '/api/fundamental/screener/auth/verify',
    symbol ? { symbol } : {},
    { timeoutMs: 10000 },
  );
}

export function fetchScreenerSchemaStatus(signal?: AbortSignal) {
  return legacyApiGet<FundamentalScreenerSchemaStatus>('/api/fundamental/screener/schema/status', undefined, {
    signal,
    timeoutMs: 10000,
  });
}

export function fetchLocalXlsxStatus(signal?: AbortSignal) {
  return legacyApiGet<LocalXlsxFlowStatusResponse>('/api/fundamental/local-xlsx/status', undefined, {
    signal,
    timeoutMs: 10000,
  });
}

export function fetchLocalXlsxSummary(signal?: AbortSignal) {
  return legacyApiGet<LocalXlsxFlowStatusResponse>('/api/fundamental/local-xlsx/summary', undefined, {
    signal,
    timeoutMs: 10000,
  });
}

export function runLocalXlsxIngestion(limit?: number, failOnUnknownSymbol = false) {
  return legacyApiPost<LocalXlsxRunResponse>(
    '/api/fundamental/local-xlsx/run',
    { limit, fail_on_unknown_symbol: failOnUnknownSymbol },
    { timeoutMs: 180000 },
  );
}

export function scanLocalXlsxInbox(limit?: number, failOnUnknownSymbol = false) {
  return legacyApiPost<LocalXlsxRunResponse>(
    '/api/fundamental/local-xlsx/scan',
    { limit, fail_on_unknown_symbol: failOnUnknownSymbol },
    { timeoutMs: 180000 },
  );
}

export function scanLocalXlsxFiles(limit?: number, failOnUnknownSymbol = false) {
  return scanLocalXlsxInbox(limit, failOnUnknownSymbol);
}

export function processLocalXlsxFiles(limit?: number, failOnUnknownSymbol = false) {
  return runLocalXlsxIngestion(limit, failOnUnknownSymbol);
}

export function fetchLocalXlsxLogs(limit = 200, signal?: AbortSignal) {
  return legacyApiGet<LocalXlsxLogsResponse>('/api/fundamental/local-xlsx/logs', { limit }, {
    signal,
    timeoutMs: 10000,
  });
}
