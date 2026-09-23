export function readUrlSymbolSearch(): string {
  if (typeof window === 'undefined') return '';
  try {
    return String(new URLSearchParams(window.location.search).get('symbol') || '').trim().toUpperCase();
  } catch {
    return '';
  }
}
