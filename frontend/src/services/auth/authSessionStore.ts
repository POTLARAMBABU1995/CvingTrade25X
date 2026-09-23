import type { AuthLoginWireResponse, AuthSessionStatusWireResponse } from '../../types';

export const AUTH_CHANGE_EVENT = 'ct:auth-change';
export const AUTH_INVALID_EVENT = 'ct:auth-invalid';

export const SESSION_TOKEN_KEY = 'ct_session_token';
export const SESSION_EXPIRES_KEY = 'ct_session_expires_at';
const AUTH_VALID_UNTIL_KEY = 'ct_auth_valid_until';
const REDIRECT_KEY = 'ct_post_login_redirect';
const QUICK_MPIN_TOKEN_KEY = 'ct_quick_mpin_token';
const QUICK_MPIN_EXPIRES_KEY = 'ct_quick_mpin_expires_at';
const QUICK_MPIN_NAME_KEY = 'ct_quick_mpin_name';

export type StoredAuthState = {
  expiresAt: string;
  expiresAtMs: number;
  isValid: boolean;
  token: string;
};

function safeLocalStorage(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function parseSessionExpiry(value: string | null): number {
  if (!value) return 0;
  const trimmed = value.trim();
  if (!trimmed) return 0;
  if (/^\d+$/.test(trimmed)) {
    const numeric = Number(trimmed);
    return numeric > 1000000000000 ? numeric : numeric * 1000;
  }
  const parsed = Date.parse(trimmed.replace(/\.(\d{3})\d+/, '.$1'));
  return Number.isNaN(parsed) ? 0 : parsed;
}

function dispatchAuthEvent(name: string, detail?: unknown): void {
  if (typeof window === 'undefined') return;
  try {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  } catch {
    window.dispatchEvent(new Event(name));
  }
}

function isAuthPagePath(path: string): boolean {
  return /(?:^|\/)(login|register)$/i.test(path) || /(?:^|\/)app\/auth\/(?:login|register)$/i.test(path);
}

export function notifyAuthChanged(): void {
  dispatchAuthEvent(AUTH_CHANGE_EVENT);
}

export function notifyAuthRejected(reason?: string): void {
  dispatchAuthEvent(AUTH_INVALID_EVENT, { reason: reason || 'Session invalid.' });
}

export function readStoredAuthState(): StoredAuthState {
  const storage = safeLocalStorage();
  if (!storage) return { expiresAt: '', expiresAtMs: 0, isValid: false, token: '' };

  const token = storage.getItem(SESSION_TOKEN_KEY) || '';
  const expiresAt = storage.getItem(SESSION_EXPIRES_KEY) || storage.getItem(AUTH_VALID_UNTIL_KEY) || '';
  const expiresAtMs = parseSessionExpiry(expiresAt);
  return {
    expiresAt,
    expiresAtMs,
    isValid: Boolean(expiresAtMs && expiresAtMs > Date.now() && (token || storage.getItem(AUTH_VALID_UNTIL_KEY))),
    token,
  };
}

export function isStoredAuthSessionValid(): boolean {
  return readStoredAuthState().isValid;
}

export function persistAuthSession(response: AuthLoginWireResponse): void {
  const storage = safeLocalStorage();
  if (!storage) return;
  try {
    const token = response.session_token || response.session?.token || '';
    const expiresAt = response.session_expires_at || response.session?.expires_at || '';
    if (token) storage.setItem(SESSION_TOKEN_KEY, token);
    if (expiresAt) {
      storage.setItem(SESSION_EXPIRES_KEY, expiresAt);
      storage.setItem(AUTH_VALID_UNTIL_KEY, expiresAt);
    }
    if (response.quick_mpin_token) storage.setItem(QUICK_MPIN_TOKEN_KEY, response.quick_mpin_token);
    if (response.quick_mpin_expires_at) storage.setItem(QUICK_MPIN_EXPIRES_KEY, response.quick_mpin_expires_at);
    const name = response.user?.full_name || response.user?.client_id || '';
    if (name) storage.setItem(QUICK_MPIN_NAME_KEY, name);
  } catch {
    // Cookies still preserve server-side auth if storage is unavailable.
  } finally {
    notifyAuthChanged();
  }
}

export function persistAuthSessionStatus(response: AuthSessionStatusWireResponse): void {
  const storage = safeLocalStorage();
  if (!storage) return;
  try {
    const expiresAt = response.session?.expires_at || '';
    if (expiresAt) {
      storage.setItem(SESSION_EXPIRES_KEY, expiresAt);
      storage.setItem(AUTH_VALID_UNTIL_KEY, expiresAt);
    }
  } catch {
    // Session status persistence is a UI hint; the server session remains authoritative.
  } finally {
    notifyAuthChanged();
  }
}

export function clearAuthSession(options: { keepQuickMpin?: boolean } = {}): void {
  const storage = safeLocalStorage();
  if (!storage) return;
  const keys = [SESSION_TOKEN_KEY, SESSION_EXPIRES_KEY, AUTH_VALID_UNTIL_KEY];
  if (!options.keepQuickMpin) {
    keys.push(QUICK_MPIN_TOKEN_KEY, QUICK_MPIN_EXPIRES_KEY, QUICK_MPIN_NAME_KEY);
  }
  try {
    keys.forEach((key) => storage.removeItem(key));
  } catch {
    // Best effort clear.
  } finally {
    notifyAuthChanged();
  }
}

export function markAuthRejected(reason?: string): void {
  clearAuthSession({ keepQuickMpin: true });
  notifyAuthRejected(reason);
}

export function buildLoginRedirect(): string {
  if (typeof window === 'undefined') return '/login';
  const target = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  try {
    window.localStorage.setItem(REDIRECT_KEY, target);
  } catch {
    // The query string still carries the target when localStorage is unavailable.
  }
  return `/login?redirect=${encodeURIComponent(target)}`;
}

export function redirectToLogin(): void {
  if (typeof window === 'undefined') return;
  window.location.replace(buildLoginRedirect());
}

export function resolvePostLoginRedirect(): string {
  if (typeof window === 'undefined') return '/app/dashboard';
  let target = '';
  try {
    const params = new URLSearchParams(window.location.search);
    target = params.get('redirect') || window.localStorage.getItem(REDIRECT_KEY) || '';
    if (target) window.localStorage.removeItem(REDIRECT_KEY);
  } catch {
    target = '';
  }
  if (!target || isAuthPagePath(target)) return '/app/dashboard';
  return target;
}

export function readQuickMpinProfile(): { name: string; token: string } {
  const storage = safeLocalStorage();
  if (!storage) return { name: '', token: '' };
  try {
    return {
      name: storage.getItem(QUICK_MPIN_NAME_KEY) || '',
      token: storage.getItem(QUICK_MPIN_TOKEN_KEY) || '',
    };
  } catch {
    return { name: '', token: '' };
  }
}

export function markRegistered(): void {
  const storage = safeLocalStorage();
  if (!storage) return;
  try {
    storage.setItem('ct_has_registered', '1');
  } catch {
    // Optional hint only.
  }
}
