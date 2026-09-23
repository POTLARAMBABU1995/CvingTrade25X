import { useEffect, useState } from 'react';
import { cn } from '../lib/cn';
import {
  THEME_CHANGE_EVENT,
  resolveThemeMode,
  toggleThemeMode,
  type ThemeMode,
} from '../lib/theme';
import { MoonIcon, SunIcon } from './ui/Icons';

type ThemeToggleProps = {
  className?: string;
};

export function ThemeToggle({ className }: ThemeToggleProps) {
  const [mode, setMode] = useState<ThemeMode>(() => resolveThemeMode());

  useEffect(() => {
    const onThemeChange = () => setMode(resolveThemeMode());
    window.addEventListener(THEME_CHANGE_EVENT, onThemeChange);
    window.addEventListener('storage', onThemeChange);
    const media = window.matchMedia?.('(prefers-color-scheme: dark)');
    media?.addEventListener?.('change', onThemeChange);
    return () => {
      window.removeEventListener(THEME_CHANGE_EVENT, onThemeChange);
      window.removeEventListener('storage', onThemeChange);
      media?.removeEventListener?.('change', onThemeChange);
    };
  }, []);

  const isDark = mode === 'dark';
  return (
    <button
      type="button"
      className={cn('cving-header-action cving-header-action--icon', className)}
      aria-label="Toggle theme"
      aria-pressed={isDark}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      onClick={() => setMode(toggleThemeMode())}
    >
      {isDark ? <SunIcon className="h-4 w-4" /> : <MoonIcon className="h-4 w-4" />}
    </button>
  );
}
