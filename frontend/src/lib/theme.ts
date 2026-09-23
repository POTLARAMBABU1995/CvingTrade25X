export type ThemeMode = 'dark' | 'light';
export type ThemePreference = ThemeMode | 'system';

const THEME_PRIMARY_KEY = 'ct_theme';
const THEME_LEGACY_KEY = 'cving-theme';
export const THEME_CHANGE_EVENT = 'ct:theme-change';

function safeStorageRead(key: string): string {
  if (typeof window === 'undefined') return '';
  try {
    return window.localStorage.getItem(key) || '';
  } catch {
    return '';
  }
}

function safeStorageWrite(key: string, value: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage is best-effort for theme preference.
  }
}

export function readThemePreference(): ThemePreference {
  const values = [safeStorageRead(THEME_PRIMARY_KEY), safeStorageRead(THEME_LEGACY_KEY)]
    .map((value) => value.toLowerCase());
  // Both keys are still used by existing sessions. If they disagree, retain
  // the dark preference so the toggle cannot report light while the UI is dark.
  if (values.includes('dark')) return 'dark';
  if (values.includes('light')) return 'light';
  return 'light';
}

export function resolveThemeMode(preference: ThemePreference = readThemePreference()): ThemeMode {
  if (preference === 'dark') return 'dark';
  return 'light';
}

export function applyThemeMode(mode: ThemeMode): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  const body = document.body;
  root.setAttribute('data-theme', mode);
  root.classList.toggle('dark', mode === 'dark');
  if (body) {
    body.setAttribute('data-theme', mode);
    body.classList.toggle('dark', mode === 'dark');
  }
}

function emitThemeChanged(mode: ThemeMode, preference: ThemePreference): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, {
    detail: { mode, preference },
  }));
}

export function setThemePreference(preference: ThemePreference): ThemeMode {
  safeStorageWrite(THEME_PRIMARY_KEY, preference);
  safeStorageWrite(THEME_LEGACY_KEY, preference);
  const mode = resolveThemeMode(preference);
  applyThemeMode(mode);
  emitThemeChanged(mode, preference);
  return mode;
}

export function toggleThemeMode(): ThemeMode {
  const next = resolveThemeMode() === 'dark' ? 'light' : 'dark';
  return setThemePreference(next);
}

export function bootstrapThemeMode(): ThemeMode {
  const mode = resolveThemeMode();
  applyThemeMode(mode);
  return mode;
}
