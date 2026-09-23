import { FormEvent, useEffect, useState } from 'react';
import { loginWithMpin, loginWithPassword, resetCredentials } from '../../services/auth/authApi';
import { cn } from '../../lib/cn';
import { EyeIcon, EyeOffIcon } from '../../components/ui/Icons';
import { AuthShell } from './AuthShell';
import { persistAuthSession, readQuickMpinProfile, resolvePostLoginRedirect } from './authSession';

type LoginMode = 'mpin' | 'password';
type StatusTone = 'error' | 'info' | 'success';
type AuthToast = {
  description: string;
  title: string;
};

function formText(data: FormData, key: string): string {
  return String(data.get(key) || '').trim();
}

function errorStatus(error: unknown): number | null {
  const candidate = error as { status?: unknown } | null;
  return typeof candidate?.status === 'number' ? candidate.status : null;
}

function sanitizeAuthError(error: unknown, fallback: string, credentialMessage = 'Invalid username or password.'): string {
  const status = errorStatus(error);
  const message = error instanceof Error ? error.message : String(error || '');

  if (
    status === 400 ||
    status === 401 ||
    status === 403 ||
    status === 404 ||
    /invalid|incorrect|not found|unauthori[sz]ed|credential/i.test(message)
  ) {
    return credentialMessage;
  }

  if (status && status >= 500) {
    return 'Server is temporarily unavailable. Please try again later.';
  }

  if (/failed to fetch|network|timeout|aborted|cancelled/i.test(message)) {
    return 'Unable to sign in. Please try again.';
  }

  return fallback;
}

export function LoginPage() {
  const [mode, setMode] = useState<LoginMode>('password');
  const [showPassword, setShowPassword] = useState(false);
  const [showReset, setShowReset] = useState(false);
  const [quickProfile, setQuickProfile] = useState({ name: '', token: '' });
  const [status, setStatus] = useState('');
  const [statusTone, setStatusTone] = useState<StatusTone>('info');
  const [toast, setToast] = useState<AuthToast | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setQuickProfile(readQuickMpinProfile());
  }, []);

  function showErrorToast(description: string, title = 'Unable to sign in. Please try again.'): void {
    setToast({ description, title });
  }

  async function submitPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setStatusTone('info');
    setStatus('Signing in...');
    setToast(null);
    try {
      const data = new FormData(event.currentTarget);
      const response = await loginWithPassword({
        identifier: formText(data, 'identifier'),
        password: formText(data, 'password'),
      });
      persistAuthSession(response);
      setStatusTone('success');
      setStatus('Login successful. Redirecting...');
      window.location.href = resolvePostLoginRedirect();
    } catch (error) {
      const reason = sanitizeAuthError(error, 'Unable to sign in. Please try again.');
      setStatusTone('error');
      setStatus('');
      showErrorToast(reason);
    } finally {
      setBusy(false);
    }
  }

  async function submitMpin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setStatusTone('info');
    setStatus('Verifying MPIN...');
    setToast(null);
    try {
      const data = new FormData(event.currentTarget);
      const identifier = formText(data, 'identifier');
      const response = await loginWithMpin({
        identifier: identifier || undefined,
        mpin: formText(data, 'mpin').replace(/\D/g, '').slice(0, 6),
        quick_token: quickProfile.token || undefined,
      });
      persistAuthSession(response);
      setStatusTone('success');
      setStatus('MPIN verified. Redirecting...');
      window.location.href = resolvePostLoginRedirect();
    } catch (error) {
      const reason = sanitizeAuthError(error, 'Unable to sign in. Please try again.');
      setStatusTone('error');
      setStatus('');
      showErrorToast(reason);
    } finally {
      setBusy(false);
    }
  }

  async function submitReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setStatusTone('info');
    setStatus('Verifying reset details...');
    setToast(null);
    try {
      const data = new FormData(event.currentTarget);
      const newPassword = formText(data, 'new_password');
      const newMpin = formText(data, 'new_mpin').replace(/\D/g, '').slice(0, 6);
      await resetCredentials({
        aadhaar_last4: formText(data, 'aadhaar_last4') || undefined,
        dob: formText(data, 'dob') || undefined,
        identifier: formText(data, 'identifier'),
        new_mpin: newMpin || undefined,
        new_password: newPassword || undefined,
        pan: formText(data, 'pan').toUpperCase() || undefined,
      });
      setStatusTone('success');
      setStatus('Credentials updated. Continue with password or MPIN login.');
      setShowReset(false);
    } catch (error) {
      const reason = sanitizeAuthError(
        error,
        'Unable to update credentials. Please verify the details and try again.',
        'Unable to update credentials. Please verify the details and try again.',
      );
      setStatusTone('error');
      setStatus('');
      showErrorToast(reason, 'Unable to update credentials.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell eyebrow="Secure Access" title="CvingTrade25X">
      <div className="mb-6">
        <h2 className="text-3xl font-black text-slate-950 dark:text-slate-100">Welcome Back</h2>
        <p className="mt-2 text-sm font-semibold leading-6 text-slate-500 dark:text-slate-400">
          Sign in to continue your market analysis.
        </p>
      </div>

      <div className="mb-5 flex rounded-lg border border-slate-200/70 bg-white/80 p-1 shadow-sm backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-900/80">
        <button
          className={cn('flex-1 rounded-lg px-4 py-3 text-sm font-black transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald', mode === 'password' ? 'bg-emerald text-white shadow-lg shadow-black/10 hover:brightness-95' : 'text-slate-600 hover:text-slate-950 dark:text-slate-300 dark:hover:text-white')}
          type="button"
          onClick={() => setMode('password')}
        >
          Password
        </button>
        <button
          className={cn('flex-1 rounded-lg px-4 py-3 text-sm font-black transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald', mode === 'mpin' ? 'bg-emerald text-white shadow-lg shadow-black/10 hover:brightness-95' : 'text-slate-600 hover:text-slate-950 dark:text-slate-300 dark:hover:text-white')}
          type="button"
          onClick={() => setMode('mpin')}
        >
          MPIN
        </button>
      </div>

      {mode === 'password' ? (
        <form className="grid gap-4" onSubmit={(event) => void submitPassword(event)}>
          <label className="grid gap-2 text-sm font-black text-slate-700 dark:text-slate-200" htmlFor="login-identifier">
            Client ID / Mobile / Email
            <input id="login-identifier" className="auth-credential-input rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 font-semibold text-slate-950 outline-none transition focus:border-emerald focus:bg-white focus:ring-2 focus:ring-emerald/15 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-emerald dark:focus:ring-emerald/20" name="identifier" autoComplete="username" required />
          </label>
          <div className="grid gap-2">
            <label className="text-sm font-black text-slate-700 dark:text-slate-200" htmlFor="login-password">
              Password
            </label>
            <div className="relative">
              <input
                id="login-password"
                className="auth-credential-input w-full rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 pr-12 font-semibold text-slate-950 outline-none transition focus:border-emerald focus:bg-white focus:ring-2 focus:ring-emerald/15 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-emerald dark:focus:ring-emerald/20"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                minLength={8}
                required
              />
              <button
                type="button"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                className="absolute right-2 top-1/2 inline-flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-200/70 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
                onClick={() => setShowPassword((current) => !current)}
              >
                {showPassword ? <EyeOffIcon className="h-5 w-5" /> : <EyeIcon className="h-5 w-5" />}
              </button>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm font-bold text-slate-600 dark:text-slate-300">
            <label className="inline-flex items-center gap-2"><input className="h-4 w-4 accent-emerald" type="checkbox" /> Remember me</label>
            <button className="text-emerald hover:text-[#065f46] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald dark:text-emerald dark:hover:text-emerald" type="button" onClick={() => setShowReset(true)}>Reset Password / MPIN</button>
          </div>
          <button className="rounded-lg bg-emerald px-4 py-3 font-black text-white shadow-lg shadow-black/10 transition hover:brightness-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald disabled:opacity-60" type="submit" disabled={busy}>Login</button>
        </form>
      ) : (
        <form className="grid gap-4" onSubmit={(event) => void submitMpin(event)}>
          {quickProfile.token ? (
            <div className="rounded-lg border border-emerald/25 bg-emerald/10 p-4 dark:border-emerald/30 dark:bg-emerald/10">
              <div className="text-lg font-black text-slate-950 dark:text-slate-100">Hey, {quickProfile.name || 'Trader'}!</div>
              <p className="mt-1 text-sm font-semibold text-slate-500 dark:text-slate-400">Enter your 6-digit MPIN to continue.</p>
            </div>
          ) : (
            <label className="grid gap-2 text-sm font-black text-slate-700 dark:text-slate-200" htmlFor="login-mpin-identifier">
              Client ID / Mobile / Email
              <input id="login-mpin-identifier" className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 font-semibold text-slate-950 outline-none transition focus:border-emerald focus:bg-white focus:ring-2 focus:ring-emerald/15 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-emerald dark:focus:ring-emerald/20" name="identifier" autoComplete="username" />
            </label>
          )}
          <label className="grid gap-2 text-sm font-black text-slate-700 dark:text-slate-200" htmlFor="login-mpin">
            MPIN
            <input id="login-mpin" className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-center font-mono text-2xl font-black text-slate-950 outline-none transition focus:border-emerald focus:bg-white focus:ring-2 focus:ring-emerald/15 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-emerald dark:focus:ring-emerald/20" name="mpin" type="password" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required />
          </label>
          <button className="rounded-lg bg-emerald px-4 py-3 font-black text-white shadow-lg shadow-black/10 transition hover:brightness-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald disabled:opacity-60" type="submit" disabled={busy}>Login with MPIN</button>
        </form>
      )}

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm font-bold">
        <a className="text-slate-600 hover:text-slate-950 dark:text-slate-300 dark:hover:text-white" href="/app/home">Back to home</a>
        <a className="text-emerald hover:text-[#065f46] dark:text-emerald dark:hover:text-emerald" href="/register">Create account</a>
      </div>

      {showReset ? (
        <section className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-5 dark:border-slate-700 dark:bg-slate-900/70">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h3 className="text-xl font-black text-slate-950 dark:text-slate-100">Reset Password / MPIN</h3>
              <p className="mt-1 text-sm font-semibold text-slate-500 dark:text-slate-400">Provide any one of DOB, PAN, or Aadhaar last 4 digits for verification.</p>
            </div>
            <button className="text-sm font-black text-emerald dark:text-emerald" type="button" onClick={() => setShowReset(false)}>Back to login</button>
          </div>
          <form className="grid gap-3" onSubmit={(event) => void submitReset(event)}>
            <input className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-950 outline-none focus:border-emerald dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" name="identifier" placeholder="Mobile / Email / Client ID" required />
            <input className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-950 outline-none focus:border-emerald dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" name="dob" placeholder="DOB (YYYY-MM-DD)" />
            <input className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold uppercase text-slate-950 outline-none focus:border-emerald dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" name="pan" placeholder="PAN (optional)" />
            <input className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-950 outline-none focus:border-emerald dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" name="aadhaar_last4" placeholder="Aadhaar last 4 (optional)" inputMode="numeric" maxLength={4} />
            <input className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-950 outline-none focus:border-emerald dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" name="new_password" placeholder="New Password" type="password" minLength={12} />
            <input className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-950 outline-none focus:border-emerald dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" name="new_mpin" placeholder="New MPIN (optional)" type="password" inputMode="numeric" maxLength={6} />
          <button className="rounded-lg bg-emerald px-4 py-3 font-black text-white transition hover:brightness-95 disabled:opacity-60" type="submit" disabled={busy}>Verify</button>
          </form>
        </section>
      ) : null}

      {status ? (
        <p
          className={cn(
            'mt-5 rounded-lg border px-4 py-3 text-sm font-bold',
            statusTone === 'success' && 'border-emerald/25 bg-emerald/10 text-emerald dark:border-emerald/30 dark:bg-emerald/10 dark:text-emerald',
            statusTone === 'error' && 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200',
            statusTone === 'info' && 'border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-200',
          )}
          role={statusTone === 'error' ? 'alert' : 'status'}
          aria-live="polite"
        >
          {status}
        </p>
      ) : null}

      {toast ? (
        <div
          className="fixed bottom-5 right-5 z-[90] w-[min(360px,calc(100vw-2rem))] rounded-lg border border-rose-200 bg-white/95 p-4 text-slate-950 shadow-[0_22px_54px_rgba(15,23,42,0.18)] backdrop-blur-xl dark:border-rose-500/35 dark:bg-slate-950/95 dark:text-slate-100"
          role="alert"
          aria-live="assertive"
        >
          <div className="flex items-start gap-3">
            <span className="mt-0.5 inline-flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-rose-500/12 text-rose-600 dark:text-rose-300">
              !
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-black">{toast.title}</p>
              <p className="mt-1 text-sm font-semibold leading-5 text-slate-600 dark:text-slate-300">{toast.description}</p>
            </div>
            <button
              type="button"
              className="rounded-lg px-2 py-1 text-xs font-black uppercase tracking-[0.12em] text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-500 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
              aria-label="Dismiss sign in message"
              onClick={() => setToast(null)}
            >
              Close
            </button>
          </div>
        </div>
      ) : null}
    </AuthShell>
  );
}
