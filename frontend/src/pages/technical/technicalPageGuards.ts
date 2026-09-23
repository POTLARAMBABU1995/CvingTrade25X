import { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import {
  isStoredAuthSessionValid,
  redirectToLogin as redirectToLoginRoute,
} from '../../services/auth/authSessionStore';
import {
  THEME_CHANGE_EVENT,
  resolveThemeMode,
  type ThemeMode,
} from '../../lib/theme';

export type TechnicalThemeMode = 'dark' | 'light';

export function isProtectedSessionValid(): boolean {
  return isStoredAuthSessionValid();
}

export function redirectToLogin(): void {
  redirectToLoginRoute();
}

export function useProtectedPageAuth(): boolean {
  const { isAuthenticated } = useAuth();
  if (typeof window === 'undefined') return true;
  return isAuthenticated;
}

export function useTechnicalThemeMode(): TechnicalThemeMode {
  const [themeMode, setThemeMode] = useState<TechnicalThemeMode>(() => (
    typeof window === 'undefined' ? 'light' : resolveThemeMode()
  ));

  useEffect(() => {
    const apply = () => setThemeMode(resolveThemeMode() as ThemeMode);
    const media = window.matchMedia?.('(prefers-color-scheme: dark)');
    window.addEventListener('storage', apply);
    window.addEventListener(THEME_CHANGE_EVENT, apply);
    media?.addEventListener?.('change', apply);
    apply();
    return () => {
      window.removeEventListener('storage', apply);
      window.removeEventListener(THEME_CHANGE_EVENT, apply);
      media?.removeEventListener?.('change', apply);
    };
  }, []);

  return themeMode;
}
