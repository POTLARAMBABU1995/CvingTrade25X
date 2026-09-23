import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { LoginPage } from '../src/pages/auth/LoginPage';
import { RegisterPage, parseExperienceMonths } from '../src/pages/auth/RegisterPage';

describe('Auth page React migrations', () => {
  test('renders the migrated login page with password, MPIN, and reset flows', () => {
    const markup = renderToStaticMarkup(<LoginPage />);

    expect(markup).toContain('CvingTrade25X');
    expect(markup).toContain('Trading is probability, not gambling.');
    expect(markup).toContain('Pure Equity Trading • NSE Market Intelligence');
    expect(markup).toContain('Client ID / Mobile / Email');
    expect(markup).toContain('Password');
    expect(markup).toMatch(/id="login-identifier"[^>]*class="[^"]*auth-credential-input/);
    expect(markup).toMatch(/id="login-password"[^>]*class="[^"]*auth-credential-input/);
    expect(markup).toContain('aria-label="Show password"');
    expect(markup).toContain('MPIN');
    expect(markup).toContain('Reset Password / MPIN');
    expect(markup).toContain('href="/register"');
  });

  test('renders the migrated register page with legacy identity and security fields', () => {
    const markup = renderToStaticMarkup(<RegisterPage />);

    expect(markup).toContain('CvingTrade25X Register');
    expect(markup).toContain('Registered Mobile Number');
    expect(markup).toContain('Date of Birth');
    expect(markup).toContain('Trading Experience');
    expect(markup).toContain('PAN');
    expect(markup).toContain('Aadhaar');
    expect(markup).toContain('Enable MPIN');
    expect(markup).toContain('href="/login"');
  });

  test('preserves legacy trading-experience parsing into months', () => {
    expect(parseExperienceMonths('2y/3m')).toBe(27);
    expect(parseExperienceMonths('18m')).toBe(18);
    expect(parseExperienceMonths('3y')).toBe(36);
    expect(parseExperienceMonths('')).toBe(0);
  });
});
