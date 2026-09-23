import { createRequestId } from './requestId';

type DiagnosticKind = 'api' | 'boundary' | 'runtime';
type DiagnosticSeverity = 'error' | 'info' | 'warn';

export type DiagnosticEntry = {
  action?: string;
  backendRequestId?: string;
  component?: string;
  endpoint?: string;
  httpMethod?: string;
  httpStatus?: number;
  id: string;
  kind: DiagnosticKind;
  message: string;
  page?: string;
  requestId?: string;
  route: string;
  severity: DiagnosticSeverity;
  sourceLine?: string;
  stack?: string;
  timestampIso: string;
};

const APP_NAME = 'CvingTrade25X';
const DIAGNOSTIC_LIMIT = 120;
const REDACTED = '[REDACTED]';
const listeners = new Set<() => void>();
const entries: DiagnosticEntry[] = [];
let handlersInitialized = false;

const secretKeyPattern = /(token|authorization|password|passwd|secret|cookie|api[-_]?key|session)/i;

function nowIso(): string {
  return new Date().toISOString();
}

function currentRoute(): string {
  if (typeof window === 'undefined') return '/';
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

function sanitizeText(raw: unknown): string {
  const text = String(raw ?? '').trim();
  if (!text) return '';
  return text
    .replace(/(authorization|token|password|secret|cookie|api[-_]?key|session)(\s*[:=]\s*)([^\s,;]+)/gi, `$1$2${REDACTED}`)
    .replace(/Bearer\s+[A-Za-z0-9\-._~+/]+=*/gi, `Bearer ${REDACTED}`);
}

function sanitizeUrl(raw: string): string {
  const text = String(raw || '').trim();
  if (!text) return '';
  try {
    const base = typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
    const parsed = new URL(text, base);
    parsed.searchParams.forEach((value, key) => {
      if (secretKeyPattern.test(key)) {
        parsed.searchParams.set(key, REDACTED);
      } else if (value.length > 220) {
        parsed.searchParams.set(key, `${value.slice(0, 220)}...`);
      }
    });
    return `${parsed.origin}${parsed.pathname}${parsed.search}`;
  } catch {
    return sanitizeText(text);
  }
}

function push(entry: DiagnosticEntry): DiagnosticEntry {
  entries.unshift(entry);
  if (entries.length > DIAGNOSTIC_LIMIT) {
    entries.length = DIAGNOSTIC_LIMIT;
  }
  listeners.forEach((listener) => listener());
  return entry;
}

function trimmedStack(error: unknown): string | undefined {
  if (!(error instanceof Error)) return undefined;
  const stack = sanitizeText(error.stack || '');
  if (!stack) return undefined;
  return stack.split('\n').slice(0, 10).join('\n');
}

type RecordInput = {
  action?: string;
  backendRequestId?: string;
  component?: string;
  endpoint?: string;
  error?: unknown;
  httpMethod?: string;
  httpStatus?: number;
  kind: DiagnosticKind;
  message: string;
  page?: string;
  requestId?: string;
  severity?: DiagnosticSeverity;
  sourceLine?: string;
};

export function recordDiagnostic(input: RecordInput): DiagnosticEntry {
  const route = currentRoute();
  const endpoint = input.endpoint ? sanitizeUrl(input.endpoint) : undefined;
  return push({
    action: sanitizeText(input.action || '') || undefined,
    backendRequestId: sanitizeText(input.backendRequestId || '') || undefined,
    component: sanitizeText(input.component || '') || undefined,
    endpoint,
    httpMethod: sanitizeText(input.httpMethod || '') || undefined,
    httpStatus: typeof input.httpStatus === 'number' ? input.httpStatus : undefined,
    id: createRequestId(),
    kind: input.kind,
    message: sanitizeText(input.message || 'Unknown error'),
    page: sanitizeText(input.page || '') || undefined,
    requestId: sanitizeText(input.requestId || '') || undefined,
    route,
    severity: input.severity || 'error',
    sourceLine: sanitizeText(input.sourceLine || '') || undefined,
    stack: trimmedStack(input.error),
    timestampIso: nowIso(),
  });
}

export function recordRuntimeError(error: unknown, page?: string, component?: string): DiagnosticEntry {
  const message = error instanceof Error ? error.message : String(error);
  return recordDiagnostic({
    component,
    error,
    kind: 'runtime',
    message,
    page,
    severity: 'error',
  });
}

export function recordBoundaryError(error: unknown, info: string, page?: string): DiagnosticEntry {
  const message = error instanceof Error ? error.message : String(error);
  return recordDiagnostic({
    error,
    kind: 'boundary',
    message,
    page,
    severity: 'error',
    sourceLine: sanitizeText(info),
  });
}

export function getLatestDiagnostic(): DiagnosticEntry | null {
  return entries[0] || null;
}

export function getDiagnosticsSnapshot(): DiagnosticEntry[] {
  return [...entries];
}

export function subscribeDiagnostics(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function browserInfo(): string {
  if (typeof navigator === 'undefined') return 'Unknown';
  const ua = sanitizeText(navigator.userAgent || 'Unknown');
  const lang = sanitizeText(navigator.language || '');
  return lang ? `${ua} | lang=${lang}` : ua;
}

function endpointPath(endpoint?: string): string {
  const text = sanitizeText(endpoint || '');
  if (!text || text === '-') return '';
  try {
    const base = typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
    const parsed = new URL(text, base);
    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return text;
  }
}

function endpointOrigin(endpoint?: string): string {
  const text = sanitizeText(endpoint || '');
  if (!text || text === '-') return '';
  try {
    const base = typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
    const parsed = new URL(text, base);
    return parsed.origin;
  } catch {
    return '';
  }
}

export function formatDiagnosticForCopy(entry: DiagnosticEntry | null, extraMessage = ''): string {
  const now = nowIso();
  if (!entry) {
    return [
      `App: ${APP_NAME}`,
      `Timestamp: ${now}`,
      `Route: ${currentRoute()}`,
      `Message: ${sanitizeText(extraMessage || 'No diagnostics captured in this browser session.')}`,
      `Browser: ${browserInfo()}`,
    ].join('\n');
  }
  const requestPath = endpointPath(entry.endpoint);
  const requestMethod = entry.httpMethod || 'GET';
  const requestLine = requestPath ? `${requestMethod} ${requestPath}` : (entry.action || '-');
  const apiBase = endpointOrigin(entry.endpoint) || (typeof window !== 'undefined' ? window.location.origin : '-');
  const source = entry.kind === 'api' ? 'api-client' : entry.kind;
  const payload = [
    `Page: ${entry.page || `${APP_NAME} - Unknown`}`,
    `Timestamp: ${entry.timestampIso}`,
    `Request URL: ${entry.endpoint || '-'}`,
    `Request Route: ${requestPath || '-'}`,
    `Status: ${entry.httpStatus ?? 0}`,
    `Message: ${entry.message}`,
    `Route: ${entry.route}`,
    `Request: ${requestLine}`,
    `API Base: ${apiBase}`,
    `Source: ${source}`,
    '',
    'Safe Log Tail:',
    entry.endpoint ? `${entry.endpoint}: ${entry.message}` : entry.message,
  ];
  if (extraMessage) {
    payload.push(sanitizeText(extraMessage));
  }
  payload.push('', `Browser: ${browserInfo()}`);
  return payload.join('\n');
}

export function initGlobalDiagnosticsHandlers(): void {
  if (handlersInitialized || typeof window === 'undefined') return;
  handlersInitialized = true;
  window.addEventListener('error', (event) => {
    const source = event.filename && event.lineno
      ? `${event.filename}:${event.lineno}${event.colno ? `:${event.colno}` : ''}`
      : undefined;
    recordDiagnostic({
      error: event.error,
      kind: 'runtime',
      message: event.message || 'Unhandled runtime error',
      page: window.location.pathname,
      severity: 'error',
      sourceLine: source,
    });
  });
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason instanceof Error ? event.reason : new Error(String(event.reason));
    recordDiagnostic({
      error: reason,
      kind: 'runtime',
      message: reason.message || 'Unhandled promise rejection',
      page: window.location.pathname,
      severity: 'error',
    });
  });
}
