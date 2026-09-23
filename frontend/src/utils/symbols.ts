const DISPLAY_SYMBOL_PREFIX = /^(?:NSE|BSE)(?::|-)/i;
const DISPLAY_SYMBOL_SUFFIX = /(?::|-)(?:EQ|BE|SM|ST|BZ)$/i;

/** Normalize an exchange-formatted symbol to the UI/database display token. */
export function normalizeDisplaySymbol(value: unknown): string {
  let token = String(value ?? '')
    .trim()
    .toUpperCase()
    .replace(/\s+/g, '');

  if (!token) return '';
  token = token.replace(DISPLAY_SYMBOL_PREFIX, '');
  token = token.replace(DISPLAY_SYMBOL_SUFFIX, '');
  return token;
}
