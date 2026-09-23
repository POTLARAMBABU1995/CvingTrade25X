import { recordDiagnostic } from '../lib/diagnostics';
import { createRequestId } from '../lib/requestId';
import { markAuthRejected } from '../services/auth/authSessionStore';

function readBaseUrl(...values: Array<string | undefined>): string {
  for (const value of values) {
    const normalized = String(value ?? '').trim();
    if (normalized) {
      return normalized;
    }
  }
  return '';
}

const CHART_API_BASE = readBaseUrl(import.meta.env.VITE_CHART_API_BASE_URL, import.meta.env.VITE_API_BASE_URL);
const LEGACY_API_BASE = readBaseUrl(import.meta.env.VITE_LEGACY_API_BASE_URL, import.meta.env.VITE_API_BASE_URL);
const CHART_API_KEY = import.meta.env.VITE_CHART_API_KEY ?? import.meta.env.VITE_API_KEY ?? '';
const LEGACY_API_KEY = import.meta.env.VITE_LEGACY_API_KEY ?? import.meta.env.VITE_API_KEY ?? '';
const DEFAULT_TIMEOUT_MS = 45000;

export type QueryParams = Record<string, string | number | boolean | undefined | null>;
export type RequestOptions = {
  signal?: AbortSignal;
  timeoutMs?: number | null;
  headers?: Record<string, string>;
  diagnostic?: {
    action?: string;
    component?: string;
    page?: string;
    suppress?: boolean;
  };
};

type ApiTarget = {
  apiKey: string;
  baseUrl: string;
};

class ApiRequestError extends Error {
  backendCode?: string;
  backendRequestId?: string;
  endpoint: string;
  method: string;
  requestId: string;
  status: number;

  constructor(
    message: string,
    {
      backendRequestId,
      backendCode,
      endpoint,
      method,
      requestId,
      status,
    }: {
      backendRequestId?: string;
      backendCode?: string;
      endpoint: string;
      method: string;
      requestId: string;
      status: number;
    },
  ) {
    super(message);
    this.name = 'ApiRequestError';
    this.backendCode = backendCode;
    this.backendRequestId = backendRequestId;
    this.endpoint = endpoint;
    this.method = method;
    this.requestId = requestId;
    this.status = status;
  }
}

function readSessionToken(): string {
  if (typeof window === 'undefined') return '';
  try {
    return window.localStorage.getItem('ct_session_token') || '';
  } catch {
    return '';
  }
}

function currentRoutePath(): string {
  if (typeof window === 'undefined') return '';
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

function isAuthFailureEndpoint(path: string): boolean {
  const lower = path.toLowerCase();
  return (
    lower.includes('/api/auth/session') ||
    (
      lower.includes('/api/') &&
      !lower.includes('/api/auth/login') &&
      !lower.includes('/api/auth/register') &&
      !lower.includes('/api/auth/reset')
    )
  );
}

function buildRequestHeaders(
  target: ApiTarget,
  options: RequestOptions,
  isForm: boolean,
  requestId: string,
): Record<string, string> {
  const token = readSessionToken();
  const headers: Record<string, string> = {
    ...(isForm ? {} : { 'Content-Type': 'application/json' }),
    ...(target.apiKey ? { 'X-API-Key': target.apiKey } : {}),
    ...options.headers,
  };
  if (token) {
    if (!headers.Authorization && !headers.authorization) {
      headers.Authorization = `Bearer ${token}`;
    }
    if (!headers['X-Session-Token'] && !headers['x-session-token']) {
      headers['X-Session-Token'] = token;
    }
  }
  if (!headers['X-Request-ID'] && !headers['X-Request-Id']) {
    headers['X-Request-ID'] = requestId;
  }
  if (!headers['X-Client-Page']) {
    headers['X-Client-Page'] = options.diagnostic?.page || currentRoutePath();
  }
  if (options.diagnostic?.action && !headers['X-Client-Action']) {
    headers['X-Client-Action'] = options.diagnostic.action;
  }
  if (options.diagnostic?.component && !headers['X-Client-Component']) {
    headers['X-Client-Component'] = options.diagnostic.component;
  }
  return headers;
}

function buildQuery(params?: QueryParams): string {
  if (!params) return '';
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    search.set(key, String(value));
  });
  const query = search.toString();
  return query ? `?${query}` : '';
}

function joinUrl(baseUrl: string, path: string): string {
  if (!baseUrl) return path;
  const normalizedBase = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
}

function normalizeAbortReason(reason: unknown, fallbackTimeoutMs?: number | null): string {
  if (typeof reason === 'string' && reason.trim()) return reason.trim();
  if (reason instanceof Error && reason.message.trim()) return reason.message.trim();
  if (fallbackTimeoutMs && fallbackTimeoutMs > 0) return `Request timeout after ${fallbackTimeoutMs}ms`;
  return 'Request cancelled';
}

function isAbortError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  return error.name === 'AbortError' || /aborted|abort/i.test(error.message);
}

function mergeSignals(signal?: AbortSignal, timeoutMs?: number | null): AbortSignal | undefined {
  if (timeoutMs === null || timeoutMs === 0) return signal;
  const resolvedTimeout = typeof timeoutMs === 'number' && timeoutMs > 0 ? timeoutMs : DEFAULT_TIMEOUT_MS;
  const timeoutController = new AbortController();
  const timerId = globalThis.setTimeout(() => {
    timeoutController.abort(`Request timeout after ${resolvedTimeout}ms`);
  }, resolvedTimeout);
  if (!signal) {
    timeoutController.signal.addEventListener('abort', () => globalThis.clearTimeout(timerId), { once: true });
    return timeoutController.signal;
  }
  if (signal.aborted) {
    globalThis.clearTimeout(timerId);
    timeoutController.abort(signal.reason ?? 'Request cancelled by caller');
    return timeoutController.signal;
  }
  const chained = new AbortController();
  const abortFromCaller = () => chained.abort(signal.reason ?? 'Request cancelled by caller');
  const abortFromTimeout = () => chained.abort(timeoutController.signal.reason ?? `Request timeout after ${resolvedTimeout}ms`);
  signal.addEventListener('abort', abortFromCaller, { once: true });
  timeoutController.signal.addEventListener('abort', abortFromTimeout, { once: true });
  chained.signal.addEventListener('abort', () => {
    globalThis.clearTimeout(timerId);
    signal.removeEventListener('abort', abortFromCaller);
    timeoutController.signal.removeEventListener('abort', abortFromTimeout);
  }, { once: true });
  return chained.signal;
}

async function parseErrorResponse(
  res: Response,
  method: string,
  requestId: string,
  url: string,
): Promise<ApiRequestError> {
  const text = await res.text();
  let baseMessage = text || `Request failed: ${res.status}`;
  let backendCode = '';
  let backendRequestId = res.headers.get('X-Request-ID') || res.headers.get('X-Request-Id') || '';
  if (text) {
    try {
      const parsed = JSON.parse(text) as {
        detail?: unknown;
        code?: unknown;
        error_message?: unknown;
        message?: unknown;
        request_id?: unknown;
        title?: unknown;
      };
      if (typeof parsed?.request_id === 'string' && parsed.request_id) {
        backendRequestId = parsed.request_id;
      }
      if (typeof parsed?.code === 'string' && parsed.code.trim()) {
        backendCode = parsed.code.trim();
      }
      if (typeof parsed?.detail === 'string') {
        baseMessage = parsed.detail;
      } else if (typeof parsed?.message === 'string' && parsed.message.trim()) {
        baseMessage = parsed.message.trim();
      } else if (typeof parsed?.error_message === 'string' && parsed.error_message.trim()) {
        baseMessage = parsed.error_message.trim();
      } else if (typeof parsed?.title === 'string' && parsed.title.trim()) {
        baseMessage = parsed.title.trim();
      } else if (parsed?.detail && typeof parsed.detail === 'object') {
        const detailObj = parsed.detail as Record<string, unknown>;
        const structured = [detailObj.status, detailObj.error_code, detailObj.error_message]
          .filter((value) => typeof value === 'string' && value)
          .join(': ');
        if (structured) {
          baseMessage = structured;
        }
      }
    } catch {
      // Preserve raw response body when JSON parsing is not possible.
    }
  }
  const message = baseMessage.slice(0, 280);
  return new ApiRequestError(message, {
    backendCode: backendCode || undefined,
    backendRequestId: backendRequestId || undefined,
    endpoint: url,
    method,
    requestId,
    status: res.status,
  });
}

function resolveTarget(kind: 'chart' | 'legacy'): ApiTarget {
  return kind === 'chart'
    ? { baseUrl: CHART_API_BASE, apiKey: CHART_API_KEY }
    : { baseUrl: LEGACY_API_BASE, apiKey: LEGACY_API_KEY };
}

async function requestJson<T>(
  target: ApiTarget,
  method: 'DELETE' | 'GET' | 'POST' | 'PUT',
  path: string,
  options: RequestOptions,
  body?: BodyInit,
  params?: QueryParams,
  isForm = false,
  responseType: 'blob' | 'json' = 'json',
): Promise<T> {
  const signal = mergeSignals(options.signal, options.timeoutMs);
  const requestId = createRequestId();
  const url = `${joinUrl(target.baseUrl, path)}${buildQuery(params)}`;
  const route = currentRoutePath();
  try {
    const res = await fetch(url, {
      method,
      headers: buildRequestHeaders(target, options, isForm, requestId),
      body,
      credentials: 'include',
      signal,
    });
    if (!res.ok) {
      throw await parseErrorResponse(res, method, requestId, url);
    }
    if (responseType === 'blob') {
      return await res.blob() as T;
    }
    return res.json();
  } catch (error) {
    if (isAbortError(error)) {
      const reason = normalizeAbortReason(signal?.reason, options.timeoutMs);
      const message = `Request aborted: ${reason}`;
      if (!options.diagnostic?.suppress) {
        recordDiagnostic({
          action: options.diagnostic?.action || method,
          component: options.diagnostic?.component,
          endpoint: url,
          kind: 'api',
          message,
          page: options.diagnostic?.page || route,
          requestId,
          severity: 'error',
        });
      }
      throw new Error(message);
    }

    if (error instanceof ApiRequestError) {
      if (error.status === 401 && isAuthFailureEndpoint(path)) {
        markAuthRejected(error.message);
      }
      if (!options.diagnostic?.suppress) {
        recordDiagnostic({
          action: options.diagnostic?.action || method,
          backendRequestId: error.backendRequestId,
          component: options.diagnostic?.component,
          endpoint: error.endpoint,
          error,
          httpMethod: method,
          httpStatus: error.status,
          kind: 'api',
          message: error.message,
          page: options.diagnostic?.page || route,
          requestId: error.requestId,
        });
      }
      throw error;
    }

    const fallback = error instanceof Error ? error : new Error(String(error));
    if (!options.diagnostic?.suppress) {
      recordDiagnostic({
        action: options.diagnostic?.action || method,
        component: options.diagnostic?.component,
        endpoint: url,
        error: fallback,
        httpMethod: method,
        kind: 'api',
        message: fallback.message,
        page: options.diagnostic?.page || route,
        requestId,
      });
    }
    throw fallback;
  }
}

export function chartApiGet<T>(path: string, params?: QueryParams, options: RequestOptions = {}): Promise<T> {
  return requestJson<T>(resolveTarget('chart'), 'GET', path, options, undefined, params);
}

export function chartApiPost<T>(path: string, body: unknown, options: RequestOptions = {}): Promise<T> {
  return requestJson<T>(resolveTarget('chart'), 'POST', path, options, JSON.stringify(body));
}

export function chartApiPostForm<T>(path: string, body: FormData, options: RequestOptions = {}): Promise<T> {
  return requestJson<T>(resolveTarget('chart'), 'POST', path, options, body, undefined, true);
}

export function legacyApiGet<T>(path: string, params?: QueryParams, options: RequestOptions = {}): Promise<T> {
  return requestJson<T>(resolveTarget('legacy'), 'GET', path, options, undefined, params);
}

export function legacyApiGetBlob(path: string, params?: QueryParams, options: RequestOptions = {}): Promise<Blob> {
  return requestJson<Blob>(resolveTarget('legacy'), 'GET', path, options, undefined, params, false, 'blob');
}

export function legacyApiPost<T>(path: string, body: unknown, options: RequestOptions = {}): Promise<T> {
  return requestJson<T>(resolveTarget('legacy'), 'POST', path, options, JSON.stringify(body));
}

export function legacyApiPostForm<T>(path: string, body: FormData, options: RequestOptions = {}): Promise<T> {
  return requestJson<T>(resolveTarget('legacy'), 'POST', path, options, body, undefined, true);
}

export function legacyApiPut<T>(path: string, body: unknown, options: RequestOptions = {}): Promise<T> {
  return requestJson<T>(resolveTarget('legacy'), 'PUT', path, options, JSON.stringify(body));
}

export function legacyApiDelete<T>(path: string, body?: unknown, options: RequestOptions = {}): Promise<T> {
  return requestJson<T>(
    resolveTarget('legacy'),
    'DELETE',
    path,
    options,
    body === undefined ? undefined : JSON.stringify(body),
  );
}

// Legacy-first default preserves the current migration assumption:
// new page-by-page React migrations will target Flask-backed APIs
// unless a feature is explicitly chart-service-only.
export const apiGet = legacyApiGet;
export const apiPost = legacyApiPost;
export const apiPostForm = legacyApiPostForm;
