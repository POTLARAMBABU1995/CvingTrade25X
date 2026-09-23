import { FormEvent, useEffect, useMemo, useState } from 'react';
import { cn } from '../../lib/cn';
import { registerUser } from '../../services/auth/authApi';
import type { RegisterUserPayload } from '../../services/auth/authApi';
import { AuthShell } from './AuthShell';
import { markRegistered } from './authSession';

type Gender = 'M' | 'F' | 'O';
type StatusTone = 'error' | 'info' | 'success';

function onlyDigits(value: string): string {
  return value.replace(/\D+/g, '');
}

function formText(data: FormData, key: string): string {
  return String(data.get(key) || '').trim();
}

function isAdultIso(value: string): boolean {
  if (!value) return false;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return false;
  const today = new Date();
  let age = today.getFullYear() - parsed.getFullYear();
  const monthDiff = today.getMonth() - parsed.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < parsed.getDate())) {
    age -= 1;
  }
  return age >= 18;
}

function normalizeMobile(value: string): string {
  return onlyDigits(value).slice(-10);
}

function normalizeClientId(value: string): string {
  return value.trim();
}

function readRegisterPrefill(): { clientId: string; mobile: string } {
  if (typeof window === 'undefined') return { clientId: '', mobile: '' };
  try {
    const params = new URLSearchParams(window.location.search || '');
    return {
      clientId: normalizeClientId(params.get('client') || ''),
      mobile: normalizeMobile(params.get('mobile') || ''),
    };
  } catch {
    return { clientId: '', mobile: '' };
  }
}

function redirectToLogin(identifier: string): void {
  if (typeof window === 'undefined') return;
  try {
    if (identifier) {
      window.sessionStorage.setItem('ct_login_identifier', identifier);
    }
  } catch {
    // Optional login prefill only.
  }

  let target = '';
  try {
    const params = new URLSearchParams(window.location.search || '');
    target = params.get('redirect') || '';
  } catch {
    target = '';
  }

  if (target && (/(?:^|\/)(login|register)$/i.test(target) || /(?:^|\/)app\/auth\/(?:login|register)$/i.test(target))) {
    target = '';
  }

  const suffix = target ? `?redirect=${encodeURIComponent(target)}` : '';
  window.setTimeout(() => {
    window.location.href = `/login${suffix}`;
  }, 900);
}

export function parseExperienceMonths(value: string): number {
  const normalized = value.toLowerCase().trim();
  if (!normalized) return 0;

  let total = 0;
  const years = /([0-9]{1,3})\s*y/.exec(normalized);
  const months = /([0-9]{1,3})\s*m/.exec(normalized);
  if (years) total += Number.parseInt(years[1], 10) * 12;
  if (months) total += Number.parseInt(months[1], 10);
  if (!years && !months && /^\d{1,3}$/.test(normalized)) {
    total = Number.parseInt(normalized, 10);
  }
  return Number.isFinite(total) ? Math.max(0, total) : 0;
}

function passwordScore(value: string): number {
  return [
    value.length >= 12,
    /[A-Z]/.test(value),
    /[a-z]/.test(value),
    /\d/.test(value),
    /[!@#$%&*]/.test(value),
  ].filter(Boolean).length;
}

export function RegisterPage() {
  const [status, setStatus] = useState('');
  const [statusTone, setStatusTone] = useState<StatusTone>('info');
  const [busy, setBusy] = useState(false);
  const [mobile, setMobile] = useState('');
  const [clientId, setClientId] = useState('');
  const [enableMpin, setEnableMpin] = useState(false);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  useEffect(() => {
    const prefill = readRegisterPrefill();
    setMobile(prefill.mobile);
    setClientId(prefill.clientId);
  }, []);

  const score = useMemo(() => passwordScore(password), [password]);
  const passwordsMatch = !confirmPassword || password === confirmPassword;
  const meterWidth = `${score * 20}%`;
  const meterColor = score >= 5 ? 'bg-sky-500' : score >= 3 ? 'bg-emerald-500' : score >= 2 ? 'bg-amber-500' : 'bg-rose-500';

  async function submitRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatusTone('info');
    setStatus('Creating account...');

    const form = new FormData(event.currentTarget);
    const fullName = formText(form, 'full_name');
    const email = formText(form, 'email').toLowerCase();
    const mobileDigits = normalizeMobile(mobile);
    const dob = formText(form, 'dob');
    const genderValue = formText(form, 'gender').toUpperCase();
    const gender = genderValue === 'M' || genderValue === 'F' || genderValue === 'O' ? genderValue as Gender : undefined;
    const pan = formText(form, 'pan').toUpperCase();
    const aadhaarLast4 = onlyDigits(formText(form, 'aadhaar_last4')).slice(-4);
    const expMonths = parseExperienceMonths(formText(form, 'experience'));
    const passwordValue = formText(form, 'password');
    const confirmValue = formText(form, 'confirm_password');
    const mpin = onlyDigits(formText(form, 'mpin')).slice(0, 6);
    const normalizedClientId = normalizeClientId(clientId);

    setMobile(mobileDigits);
    setClientId(normalizedClientId);

    if (!fullName) {
      setStatusTone('error');
      setStatus('Full name is required.');
      return;
    }
    if (!email) {
      setStatusTone('error');
      setStatus('Email is required.');
      return;
    }
    if (mobileDigits.length !== 10) {
      setStatusTone('error');
      setStatus('Enter a valid 10-digit mobile number.');
      return;
    }
    if (!isAdultIso(dob)) {
      setStatusTone('error');
      setStatus('You must be at least 18 years old to register.');
      return;
    }
    if (passwordValue !== confirmValue) {
      setStatusTone('error');
      setStatus('Passwords do not match.');
      return;
    }
    if (enableMpin && !/^\d{6}$/.test(mpin)) {
      setStatusTone('error');
      setStatus('MPIN must be exactly 6 digits.');
      return;
    }

    const payload: RegisterUserPayload = {
      aadhaar_last4: aadhaarLast4 || undefined,
      client_id: normalizedClientId || undefined,
      dob,
      email,
      exp_months: expMonths,
      full_name: fullName,
      gender,
      mobile_e164: `+91${mobileDigits}`,
      mobileNumber: mobileDigits,
      mpin: enableMpin ? mpin : undefined,
      pan: pan || undefined,
      password: passwordValue,
    };

    setBusy(true);
    try {
      const response = await registerUser(payload);
      markRegistered();
      const preferredId = response.client_id || normalizedClientId || mobileDigits || email;
      setStatusTone('success');
      setStatus('Registration successful. Redirecting to login...');
      redirectToLogin(preferredId);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (/already|exists/i.test(message)) {
        markRegistered();
        setStatusTone('error');
        setStatus(`${message} Redirecting to login...`);
        redirectToLogin(normalizedClientId || mobileDigits || email);
        return;
      }
      setStatusTone('error');
      setStatus(message || 'Registration failed. Please review your inputs.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell eyebrow="Create account" title="CvingTrade25X Register">
      <div className="mb-6">
        <h2 className="text-3xl font-black tracking-[-0.03em] text-slate-950">Open secure access</h2>
        <p className="mt-2 text-sm font-semibold leading-6 text-slate-500">
          Create secure access for equity research and market analysis.
        </p>
      </div>

      <form className="grid gap-5" onSubmit={(event) => void submitRegister(event)}>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="grid gap-2 text-sm font-black text-slate-700">
            Full Name
            <input className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-semibold text-slate-950 outline-none focus:border-sky-400 focus:bg-white" name="full_name" autoComplete="name" maxLength={100} required />
          </label>
          <label className="grid gap-2 text-sm font-black text-slate-700">
            Email
            <input className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-semibold text-slate-950 outline-none focus:border-sky-400 focus:bg-white" name="email" type="email" autoComplete="email" maxLength={100} required />
          </label>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="grid gap-2 text-sm font-black text-slate-700">
            Registered Mobile Number
            <div className="flex overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 focus-within:border-sky-400 focus-within:bg-white">
              <span className="grid place-items-center border-r border-slate-200 px-4 font-black text-slate-500">+91</span>
              <input className="min-w-0 flex-1 bg-transparent px-4 py-3 font-semibold text-slate-950 outline-none" name="mobile" inputMode="numeric" maxLength={10} value={mobile} onChange={(event) => setMobile(onlyDigits(event.currentTarget.value).slice(0, 10))} placeholder="9123456789" required />
            </div>
          </label>
          <label className="grid gap-2 text-sm font-black text-slate-700">
            Date of Birth
            <input className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-semibold text-slate-950 outline-none focus:border-sky-400 focus:bg-white" name="dob" type="date" required />
          </label>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="grid gap-2 text-sm font-black text-slate-700">
            Gender
            <select className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-semibold text-slate-950 outline-none focus:border-sky-400 focus:bg-white" name="gender" defaultValue="" required>
              <option value="" disabled>Select gender</option>
              <option value="M">Male</option>
              <option value="F">Female</option>
              <option value="O">Other</option>
            </select>
          </label>
          <label className="grid gap-2 text-sm font-black text-slate-700">
            Trading Experience
            <input className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-semibold text-slate-950 outline-none focus:border-sky-400 focus:bg-white" name="experience" placeholder="e.g., 2y/2m" />
          </label>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="grid gap-2 text-sm font-black text-slate-700">
            PAN
            <input className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-semibold uppercase text-slate-950 outline-none focus:border-sky-400 focus:bg-white" name="pan" maxLength={10} required />
          </label>
          <label className="grid gap-2 text-sm font-black text-slate-700">
            Aadhaar
            <input className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-semibold text-slate-950 outline-none focus:border-sky-400 focus:bg-white" name="aadhaar_last4" inputMode="numeric" maxLength={4} placeholder="Last 4 digits only" required />
          </label>
        </div>

        <label className="grid gap-2 text-sm font-black text-slate-700">
          Client ID
          <input className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-semibold text-slate-950 outline-none focus:border-sky-400 focus:bg-white" name="client_id" value={clientId} onChange={(event) => setClientId(event.currentTarget.value)} placeholder="Optional client ID" />
        </label>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="grid gap-2 text-sm font-black text-slate-700">
            Password
            <input className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-semibold text-slate-950 outline-none focus:border-sky-400 focus:bg-white" name="password" type="password" minLength={12} value={password} onChange={(event) => setPassword(event.currentTarget.value)} required />
            <span className="h-2 overflow-hidden rounded-full bg-slate-100" aria-hidden="true"><span className={cn('block h-full rounded-full transition-all', meterColor)} style={{ width: meterWidth }} /></span>
          </label>
          <label className="grid gap-2 text-sm font-black text-slate-700">
            Confirm Password
            <input className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-semibold text-slate-950 outline-none focus:border-sky-400 focus:bg-white" name="confirm_password" type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.currentTarget.value)} required />
            {!passwordsMatch ? <span className="text-xs font-black text-rose-700">Passwords do not match.</span> : null}
          </label>
        </div>

        <label className="inline-flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-black text-slate-700">
          <input type="checkbox" checked={enableMpin} onChange={(event) => setEnableMpin(event.currentTarget.checked)} />
          <span>Enable MPIN</span>
        </label>

        {enableMpin ? (
          <label className="grid gap-2 text-sm font-black text-slate-700">
            MPIN
            <input className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-center font-mono text-2xl font-black tracking-[0.3em] text-slate-950 outline-none focus:border-sky-400 focus:bg-white" name="mpin" type="password" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} placeholder="6 digits" required />
          </label>
        ) : null}

        <button className="rounded-2xl bg-gradient-to-r from-[rgb(var(--page-accent-rgb))] to-[rgb(var(--page-accent-rgb-2))] px-4 py-3 font-black text-white shadow-lg shadow-[rgba(59,130,246,0.2)] disabled:opacity-60" type="submit" disabled={busy}>Submit</button>
      </form>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm font-bold">
        <a className="text-slate-600 hover:text-slate-950" href="/app/home">Back to home</a>
        <a className="text-sky-700 hover:text-sky-900" href="/login">Already registered? Login</a>
      </div>

      {status ? (
        <p className={cn(
          'mt-5 rounded-2xl border px-4 py-3 text-sm font-bold',
          statusTone === 'success' && 'border-emerald-200 bg-emerald-50 text-emerald-800',
          statusTone === 'error' && 'border-rose-200 bg-rose-50 text-rose-800',
          statusTone === 'info' && 'border-sky-200 bg-sky-50 text-sky-800',
        )}>
          {status}
        </p>
      ) : null}
    </AuthShell>
  );
}
