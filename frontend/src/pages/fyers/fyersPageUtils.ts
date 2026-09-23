import { asRecord, pickField, safeLegacyText } from '../../adapters/databasePageAdapter';

export type FyersToastTone = 'danger' | 'info' | 'success' | 'warn';

export type FyersPageToast = {
  description: string;
  title: string;
  tone: FyersToastTone;
};

export const FYERS_AUTH_EXPIRED_TOAST = 'Authentication Expired Please do the authentication.';

function pad(value: number) {
  return String(value).padStart(2, '0');
}

function parseIsoDateTime(value: unknown): Date | null {
  const text = safeLegacyText(value, '');
  if (!text) return null;
  const parsed = new Date(text);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function parseIsoDate(value: string): Date | null {
  const text = value.trim();
  if (!text) return null;
  const parts = text.split('-').map((token) => Number(token));
  if (parts.length !== 3 || parts.some((token) => !Number.isFinite(token))) return null;
  const [year, month, day] = parts;
  const parsed = new Date(year, month - 1, day);
  if (
    parsed.getFullYear() !== year
    || parsed.getMonth() !== month - 1
    || parsed.getDate() !== day
  ) {
    return null;
  }
  return parsed;
}

export function formatFyersDateTime(value: unknown, fallback = '-') {
  const parsed = parseIsoDateTime(value);
  if (!parsed) return fallback;
  const hours24 = parsed.getHours();
  const hours12 = hours24 % 12 || 12;
  const suffix = hours24 >= 12 ? 'PM' : 'AM';
  return `${pad(parsed.getDate())}-${pad(parsed.getMonth() + 1)}-${parsed.getFullYear()} ${pad(hours12)}:${pad(parsed.getMinutes())} ${suffix}`;
}

export function buildFyersAuthStatusMessage(payload: unknown, fallback = 'Authorization status loaded.') {
  const source = asRecord(payload);
  const message = safeLegacyText(pickField(source, ['message'], ''), '').trim();
  if (pickField(source, ['authenticated'], false) === true) {
    const parts = [message || fallback];
    const statusSource = safeLegacyText(pickField(source, ['source', 'statusSource']), '').trim();
    const verifiedAt = formatFyersDateTime(pickField(source, ['verifiedAt', 'verified_at', 'lastAuthorizedAt']), '');
    const expiresAt = formatFyersDateTime(pickField(source, ['expiresAt', 'expires_at']), '');
    const remainingMinutes = Number(pickField(source, ['remainingValidityMinutes', 'remaining_validity_minutes'], 0));
    if (statusSource) parts.push(`Source: ${statusSource}`);
    if (verifiedAt) parts.push(`Verified: ${verifiedAt}`);
    if (expiresAt) parts.push(`Expires: ${expiresAt}`);
    if (Number.isFinite(remainingMinutes) && remainingMinutes > 0) {
      parts.push(`${remainingMinutes.toLocaleString('en-IN')} mins left`);
    }
    return parts.join(' | ');
  }
  if (message) return message;
  return fallback;
}

export function isFyersAuthExpired(payload: unknown) {
  const source = asRecord(payload);
  const details = asRecord(source.details);
  const errorCode = safeLegacyText(pickField(source, ['errorCode', 'error_code']), '').toUpperCase();
  const uiMessage = safeLegacyText(pickField(source, ['uiMessage', 'ui_message']), '');
  return errorCode === 'FYERS_AUTH_FAILED'
    || errorCode === 'FYERS_AUTH_REQUIRED'
    || errorCode === 'FYERS_AUTH_VALIDATION_FAILED'
    || errorCode === 'FYERS_INVALID_REFRESH_TOKEN'
    || errorCode === 'FYERS_STALE_CALLBACK'
    || pickField(details, ['auth_failed'], false) === true
    || (pickField(source, ['requiresAuthorization'], false) === true && pickField(source, ['canExtract'], true) === false)
    || uiMessage === FYERS_AUTH_EXPIRED_TOAST;
}

export function getFyersAuthExpiredToast(payload: unknown) {
  if (!isFyersAuthExpired(payload)) return '';
  const source = asRecord(payload);
  return safeLegacyText(
    pickField(source, ['uiMessage', 'ui_message', 'message']),
    FYERS_AUTH_EXPIRED_TOAST,
  ) || FYERS_AUTH_EXPIRED_TOAST;
}

export function describeWeekendRange(startIso: string, endIso: string) {
  const start = parseIsoDate(startIso);
  const end = parseIsoDate(endIso);
  if (!start || !end || end < start) {
    return { block: false, warn: false };
  }
  let containsWeekend = false;
  let containsWeekday = false;
  const cursor = new Date(start);
  while (cursor <= end) {
    const day = cursor.getDay();
    if (day === 0 || day === 6) containsWeekend = true;
    else containsWeekday = true;
    cursor.setDate(cursor.getDate() + 1);
  }
  return {
    block: containsWeekend && !containsWeekday,
    warn: containsWeekend && containsWeekday,
  };
}

export function withFyersToast(
  title: string,
  description: string,
  tone: FyersToastTone = 'info',
): FyersPageToast {
  return { title, description, tone };
}
