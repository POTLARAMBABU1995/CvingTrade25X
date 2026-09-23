import type { ReactNode } from 'react';
import { ArrowDownRightIcon, ArrowUpRightIcon, BearIcon, BullIcon, ChartIcon } from '../../components/ui/Icons';
import { BrandMark } from '../../components/ui/BrandMark';
import { handleInternalNavigationClick } from '../../utils/internalNavigation';

type AuthShellProps = {
  children: ReactNode;
  eyebrow: string;
  title: string;
};

const benefits = [
  'Probability-led equity research with disciplined risk awareness.',
  'Protected workspace for technical screens, sectors, and market review.',
  'Focused NSE intelligence for repeatable trading decisions.',
] as const;

export function AuthShell({ children, eyebrow, title }: AuthShellProps) {
  return (
    <div className="page-theme--auth legacy-react-shell fundamental-app min-h-screen overflow-x-hidden bg-[linear-gradient(135deg,#f7faf8_0%,#eef7f1_44%,#fff7f4_100%)] text-slate-950 dark:bg-[linear-gradient(135deg,#07110d_0%,#101827_50%,#1a1012_100%)] dark:text-slate-100">
      <header className="sticky top-0 z-40 border-b border-slate-200/70 bg-white/84 backdrop-blur-2xl dark:border-slate-800/80 dark:bg-slate-950/82">
        <div className="mx-auto flex min-h-[70px] w-full max-w-[1180px] flex-wrap items-center justify-between gap-4 px-4 lg:px-6">
          <a className="flex items-center gap-3 text-lg font-black text-slate-950 dark:text-slate-100" href="/app/home" onClick={(event) => handleInternalNavigationClick(event, '/app/home')}>
            <BrandMark size="sm" />
          </a>
          <nav className="flex flex-wrap items-center gap-2 text-sm font-black" aria-label="Auth navigation">
            <a className="rounded-lg px-4 py-2 text-slate-600 transition hover:bg-emerald/10 hover:text-slate-950 dark:text-slate-300 dark:hover:text-white" href="/app/dashboard" onClick={(event) => handleInternalNavigationClick(event, '/app/dashboard')}>Dashboard</a>
            <a className="rounded-lg px-4 py-2 text-slate-600 transition hover:bg-emerald/10 hover:text-slate-950 dark:text-slate-300 dark:hover:text-white" href="/app/home#support" onClick={(event) => handleInternalNavigationClick(event, '/app/home#support')}>Support</a>
            <a className="rounded-lg px-4 py-2 text-slate-600 transition hover:bg-emerald/10 hover:text-slate-950 dark:text-slate-300 dark:hover:text-white" href="/app/home#ai" onClick={(event) => handleInternalNavigationClick(event, '/app/home#ai')}>AI Chatbot</a>
          </nav>
        </div>
      </header>

      <main className="relative mx-auto grid min-h-[calc(100vh-70px)] w-full max-w-[1180px] place-items-center px-4 py-10 lg:px-6">
        <div className="grid w-full overflow-hidden rounded-lg border border-slate-200/80 bg-white/88 shadow-[0_28px_70px_rgba(15,23,42,0.12)] backdrop-blur-2xl dark:border-slate-800/85 dark:bg-slate-950/84 dark:shadow-[0_28px_80px_rgba(0,0,0,0.42)] lg:grid-cols-[1.05fr_0.95fr]">
          <section className="relative order-2 overflow-hidden border-b border-slate-200/80 bg-[linear-gradient(145deg,rgba(5,150,105,0.12),rgba(255,255,255,0.78)_48%,rgba(225,29,72,0.1))] p-7 dark:border-slate-800/80 dark:bg-[linear-gradient(145deg,rgba(16,185,129,0.16),rgba(15,23,42,0.88)_48%,rgba(244,63,94,0.12))] md:p-9 lg:order-1 lg:border-b-0 lg:border-r">
            <div className="relative">
              <span className="inline-flex rounded-lg border border-emerald/30 bg-white/82 px-3 py-1 text-xs font-black uppercase tracking-[0.2em] text-emerald backdrop-blur-xl dark:border-emerald/30 dark:bg-emerald/10 dark:text-emerald">{eyebrow}</span>
              <h1 className="mt-4 text-4xl font-black text-slate-950 dark:text-white md:text-5xl">{title}</h1>
              <p className="mt-4 max-w-xl text-sm font-black uppercase tracking-[0.18em] text-slate-600 dark:text-slate-300">
                Pure Equity Trading • NSE Market Intelligence
              </p>
              <p className="mt-4 max-w-xl text-2xl font-black leading-tight text-slate-950 dark:text-slate-100">
                Trading is probability, not gambling.
              </p>
              <div className="mt-7 grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-emerald/30 bg-white/82 p-4 shadow-sm dark:border-emerald/30 dark:bg-slate-900/72">
                  <div className="flex items-center justify-between gap-3">
                    <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-emerald/12 text-emerald dark:text-emerald">
                      <BullIcon className="h-5 w-5" />
                    </span>
                    <ArrowUpRightIcon className="h-5 w-5 text-emerald dark:text-emerald" />
                  </div>
                  <p className="mt-4 text-sm font-black text-slate-950 dark:text-slate-100">Bullish Momentum</p>
                  <p className="mt-1 text-xs font-semibold text-slate-500 dark:text-slate-400">Strength with discipline</p>
                </div>
                <div className="rounded-lg border border-rose-200/80 bg-white/82 p-4 shadow-sm dark:border-rose-500/30 dark:bg-slate-900/72">
                  <div className="flex items-center justify-between gap-3">
                    <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-rose-500/12 text-rose-700 dark:text-rose-300">
                      <BearIcon className="h-5 w-5" />
                    </span>
                    <ArrowDownRightIcon className="h-5 w-5 text-rose-600 dark:text-rose-300" />
                  </div>
                  <p className="mt-4 text-sm font-black text-slate-950 dark:text-slate-100">Bearish Pressure</p>
                  <p className="mt-1 text-xs font-semibold text-slate-500 dark:text-slate-400">Risk before reward</p>
                </div>
              </div>
              <ul className="mt-7 grid gap-3 text-sm font-semibold text-slate-700 dark:text-slate-300">
                {benefits.map((benefit) => (
                  <li key={benefit} className="flex gap-3">
                    <span className="mt-1.5 inline-flex h-5 w-5 flex-none items-center justify-center rounded-lg border border-emerald/25 bg-emerald/10 text-emerald dark:border-emerald/30 dark:bg-emerald/10 dark:text-emerald">
                      <ChartIcon className="h-3 w-3" />
                    </span>
                    <span>{benefit}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-8 rounded-lg border border-slate-200/80 bg-white/78 px-4 py-3 text-xs font-black uppercase tracking-[0.18em] text-slate-700 backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-900/78 dark:text-slate-300">
                Secure access for equity research and trading analysis.
              </div>
            </div>
          </section>

          <section className="order-1 bg-white/96 p-6 text-slate-950 dark:bg-slate-950/92 dark:text-slate-100 md:p-8 lg:order-2">
            {children}
          </section>
        </div>
      </main>
    </div>
  );
}
