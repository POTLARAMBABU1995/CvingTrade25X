import type { ComponentType, SVGProps } from 'react';
import { FormEvent, useState } from 'react';
import { ArrowUpRightIcon, ChartIcon, LayersIcon } from '../../components/ui/Icons';
import { BrandMark } from '../../components/ui/BrandMark';
import {
  UiButton,
  UiCard,
  UiDialog,
  UiDialogContent,
  UiDialogDescription,
  UiDialogFooter,
  UiDialogHeader,
  UiDialogTitle,
  UiInput,
  UiSelect,
} from '../../components/ui/shadcn-wrappers';
import { cn } from '../../lib/cn';
import { loginWithMpin, loginWithPassword, registerUser } from '../../services/auth/authApi';
import { persistAuthSession } from '../auth/authSession';
import { ThemeToggle } from '../../components/ThemeToggle';

type ModalMode = 'login' | 'register' | null;
type LoginMode = 'mpin' | 'password';

type FeatureCardConfig = {
  accent: 'emerald' | 'sky' | 'rose';
  copy: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  title: string;
};

const featureCards: readonly FeatureCardConfig[] = [
  {
    accent: 'emerald',
    icon: ArrowUpRightIcon,
    title: 'Market Movers',
    copy: 'Top gainers/losers, advances/declines, and volume shockers at a glance.',
  },
  {
    accent: 'sky',
    icon: ChartIcon,
    title: 'Technicals',
    copy: 'EMA, RSI, MACD, ATR functions baked in for screeners and alerts.',
  },
  {
    accent: 'rose',
    icon: LayersIcon,
    title: 'Portfolio Gallery',
    copy: 'Responsive image grid with lightbox for reports and charts.',
  },
];

const companyLinks = ['Contact Us', 'About Us', 'In the Media', 'Investor Relations', 'Webinars', 'Careers'];
const investmentLinks = ['Stocks', 'Mutual Funds', 'SIP with 100 Rupees', 'SIP with 500 Rupees', 'Upcoming IPO'];
const calculatorLinks = [
  'Brokerage Calculator',
  'SIP Calculator',
  'Lumpsum Calculator',
  'CAGR Calculator',
  'Dividend Yield Calculator',
  'Future Value Calculator',
  'Compound Interest Rate Calculator',
  'FD Calculator',
  'RD Calculator',
  'Present Value Calculator',
  'EBITDA Calculator',
  'Mutual Fund Returns Calculator',
  'PPF Calculator',
  'EMI Calculator',
];

function featureAccentClasses(accent: FeatureCardConfig['accent']): string {
  switch (accent) {
    case 'emerald':
      return 'border-emerald/20 bg-emerald/10 text-emerald dark:border-emerald/30 dark:bg-emerald/10 dark:text-emerald';
    case 'sky':
      return 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300';
    case 'rose':
      return 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300';
  }
}

function LandingHeader({ onOpenModal }: { onOpenModal: (mode: ModalMode) => void }) {
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/90 backdrop-blur-2xl dark:border-slate-800/80 dark:bg-slate-950/82">
      <div className="mx-auto flex min-h-[72px] w-full max-w-[1680px] flex-wrap items-center gap-3 px-4 lg:flex-nowrap lg:px-8">
        <a className="shrink-0 flex items-center gap-2 whitespace-nowrap text-xl font-black text-slate-950 dark:text-slate-100" href="/app/home">
          <BrandMark size="sm" />
        </a>
        <nav className="flex min-w-0 flex-1 flex-wrap items-center gap-3 text-sm font-black text-slate-800 dark:text-slate-200" aria-label="Landing">
          <a className="rounded-full px-3 py-2 transition hover:bg-sky-50 hover:text-sky-700 dark:hover:bg-slate-800 dark:hover:text-white" href="/app/dashboard">Dashboard</a>
          <a className="rounded-full px-3 py-2 transition hover:bg-sky-50 hover:text-sky-700 dark:hover:bg-slate-800 dark:hover:text-white" href="#ai">AIChatbot</a>
          <a className="rounded-full px-3 py-2 transition hover:bg-sky-50 hover:text-sky-700 dark:hover:bg-slate-800 dark:hover:text-white" href="#support">Support</a>
          <a className="rounded-full px-3 py-2 transition hover:bg-sky-50 hover:text-sky-700 dark:hover:bg-slate-800 dark:hover:text-white" href="#about">About Us</a>
        </nav>
        <div className="ml-auto flex shrink-0 flex-nowrap items-center justify-end gap-2">
          <ThemeToggle />
          <UiSelect
            aria-label="Language"
            className="h-10 min-w-0 shrink-0 rounded-full px-2"
            defaultValue="EN"
            style={{ width: '4rem', minWidth: '4rem', maxWidth: '4rem' }}
            variant="light"
          >
            {['EN', 'HI', 'BN', 'TA', 'TE', 'MR', 'GU', 'KN', 'ML'].map((lang) => (
              <option key={lang} value={lang}>{lang}</option>
            ))}
          </UiSelect>
          <UiButton className="shrink-0 whitespace-nowrap" size="sm" variant="secondary" onClick={() => onOpenModal('login')}>
            Login
          </UiButton>
          <UiButton className="shrink-0 whitespace-nowrap" size="sm" variant="primary" onClick={() => onOpenModal('register')}>
            Register
          </UiButton>
        </div>
      </div>
    </header>
  );
}

function AuthModal({
  mode,
  onClose,
  onModeChange,
}: {
  mode: ModalMode;
  onClose: () => void;
  onModeChange: (mode: ModalMode) => void;
}) {
  const [loginMode, setLoginMode] = useState<LoginMode>('password');
  const [status, setStatus] = useState('');

  if (!mode) return null;

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setStatus('Signing in...');
    try {
      const identifier = String(data.get('identifier') || '').trim();
      const response = loginMode === 'mpin'
        ? await loginWithMpin({ identifier, mpin: String(data.get('mpin') || '') })
        : await loginWithPassword({ identifier, password: String(data.get('password') || '') });
      persistAuthSession(response);
      setStatus('Login successful. Opening dashboard...');
      window.location.href = '/app/dashboard';
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  async function submitRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setStatus('Creating account...');
    try {
      await registerUser({
        client_id: String(data.get('client_id') || '').trim() || undefined,
        dob: String(data.get('dob') || ''),
        email: String(data.get('email') || ''),
        full_name: String(data.get('full_name') || ''),
        mobileNumber: String(data.get('mobile') || ''),
        mpin: String(data.get('mpin') || '') || undefined,
        password: String(data.get('password') || ''),
      });
      setStatus('Registration successful. Login with your client ID.');
      onModeChange('login');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <UiDialog
      open={Boolean(mode)}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <UiDialogContent align="center" className="max-w-2xl" tone="light">
        <UiDialogHeader>
          <UiDialogTitle>{mode === 'login' ? 'Login' : 'Register'}</UiDialogTitle>
          <UiDialogDescription>
            Existing API contracts are reused without changing auth backend behavior.
          </UiDialogDescription>
        </UiDialogHeader>

        {mode === 'login' ? (
          <form className="mt-6 grid gap-4" onSubmit={(event) => void submitLogin(event)}>
            <div className="flex gap-2">
              <UiButton
                className="flex-1"
                onClick={() => setLoginMode('password')}
                size="sm"
                variant={loginMode === 'password' ? 'primary' : 'secondary'}
                type="button"
              >
                Password
              </UiButton>
              <UiButton
                className="flex-1"
                onClick={() => setLoginMode('mpin')}
                size="sm"
                variant={loginMode === 'mpin' ? 'primary' : 'secondary'}
                type="button"
              >
                MPIN
              </UiButton>
            </div>
            <label className="grid gap-2 text-sm font-bold text-slate-700 dark:text-slate-200" htmlFor="home-login-identifier">
              Client ID / Mobile / Email
              <UiInput id="home-login-identifier" name="identifier" variant="light" autoComplete="username" required />
            </label>
            {loginMode === 'mpin' ? (
              <label className="grid gap-2 text-sm font-bold text-slate-700 dark:text-slate-200" htmlFor="home-login-mpin">
                MPIN
                <UiInput
                  id="home-login-mpin"
                  name="mpin"
                  type="password"
                  variant="light"
                  maxLength={6}
                  required
                />
              </label>
            ) : (
              <label className="grid gap-2 text-sm font-bold text-slate-700 dark:text-slate-200" htmlFor="home-login-password">
                Password
                <UiInput id="home-login-password" name="password" type="password" variant="light" required />
              </label>
            )}
            <UiButton fullWidth size="lg" type="submit" variant="primary">
              Login
            </UiButton>
          </form>
        ) : (
          <form className="mt-6 grid gap-4" onSubmit={(event) => void submitRegister(event)}>
            <label className="grid gap-2 text-sm font-bold text-slate-700 dark:text-slate-200" htmlFor="home-register-full-name">
              Full Name
              <UiInput id="home-register-full-name" name="full_name" variant="light" required />
            </label>
            <label className="grid gap-2 text-sm font-bold text-slate-700 dark:text-slate-200" htmlFor="home-register-email">
              Email
              <UiInput id="home-register-email" name="email" type="email" variant="light" required />
            </label>
            <label className="grid gap-2 text-sm font-bold text-slate-700 dark:text-slate-200" htmlFor="home-register-mobile">
              Registered Mobile Number
              <UiInput id="home-register-mobile" name="mobile" maxLength={10} variant="light" required />
            </label>
            <label className="grid gap-2 text-sm font-bold text-slate-700 dark:text-slate-200" htmlFor="home-register-dob">
              Date of Birth
              <UiInput id="home-register-dob" name="dob" type="date" variant="light" required />
            </label>
            <label className="grid gap-2 text-sm font-bold text-slate-700 dark:text-slate-200" htmlFor="home-register-client-id">
              Client ID
              <UiInput id="home-register-client-id" name="client_id" variant="light" />
            </label>
            <label className="grid gap-2 text-sm font-bold text-slate-700 dark:text-slate-200" htmlFor="home-register-password">
              Password
              <UiInput id="home-register-password" name="password" type="password" variant="light" required />
            </label>
            <label className="grid gap-2 text-sm font-bold text-slate-700 dark:text-slate-200" htmlFor="home-register-mpin">
              MPIN
              <UiInput id="home-register-mpin" name="mpin" maxLength={6} type="password" variant="light" />
            </label>
            <UiButton fullWidth size="lg" type="submit" variant="primary">
              Create Account
            </UiButton>
          </form>
        )}

        <UiDialogFooter className="mt-6 justify-between">
          <UiButton
            className="px-0"
            onClick={() => onModeChange(mode === 'login' ? 'register' : 'login')}
            size="sm"
            variant="ghost"
            type="button"
          >
            {mode === 'login' ? 'Create account' : 'Back to login'}
          </UiButton>
          <UiButton onClick={onClose} size="sm" variant="secondary" type="button">
            Close
          </UiButton>
        </UiDialogFooter>

        {status ? (
          <p className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm font-bold text-slate-700 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-200">
            {status}
          </p>
        ) : null}
      </UiDialogContent>
    </UiDialog>
  );
}

function FeatureCard({ feature }: { feature: FeatureCardConfig }) {
  const Icon = feature.icon;

  return (
    <UiCard padding="lg" variant="surface" className="text-center">
      <div className={cn('mx-auto grid h-12 w-12 place-items-center rounded-2xl border', featureAccentClasses(feature.accent))}>
        <Icon className="h-5 w-5" />
      </div>
      <h3 className="mt-4 text-xl font-black text-slate-950 dark:text-slate-100">{feature.title}</h3>
      <p className="mt-2 text-sm font-semibold leading-6 text-slate-600 dark:text-slate-400">{feature.copy}</p>
    </UiCard>
  );
}

function FooterColumn({ links, title }: { links: readonly string[]; title: string }) {
  return (
    <UiCard padding="md" variant="subtle" className="h-full">
      <h4 className="mb-3 text-lg font-black text-slate-950 dark:text-slate-100">{title}</h4>
      <ul className="grid gap-2 text-sm font-semibold text-slate-600 dark:text-slate-300">
        {links.map((link) => (
          <li key={link}>
            <a className="transition hover:text-sky-700 dark:hover:text-white" href="#support">{link}</a>
          </li>
        ))}
      </ul>
    </UiCard>
  );
}

export function HomePage() {
  const [modal, setModal] = useState<ModalMode>(null);

  return (
    <div className="page-theme--dashboard legacy-react-shell fundamental-app min-h-screen overflow-x-hidden bg-[linear-gradient(180deg,#f8fbff_0%,#eef4fb_100%)] text-slate-950 dark:bg-[linear-gradient(180deg,#020617_0%,#0f172a_100%)] dark:text-slate-100">
      <LandingHeader onOpenModal={setModal} />

      <main>
        <section className="mx-auto grid w-full max-w-[1680px] place-items-center px-4 py-16 text-center lg:px-8">
          <h1 className="max-w-4xl text-4xl font-black tracking-[-0.04em] leading-[1.02] text-slate-950 dark:text-slate-100 sm:text-5xl lg:max-w-none lg:whitespace-nowrap lg:text-5xl xl:text-6xl">
            Trade Smarter. Faster. Confidently.
          </h1>
          <p className="mt-4 max-w-3xl text-lg font-semibold leading-8 text-slate-600 dark:text-slate-400">
            Momentum and trend tools for Indian markets with simple onboarding.
          </p>
        </section>

        <section className="mx-auto grid w-full max-w-[1680px] gap-4 px-4 py-8 md:grid-cols-3 lg:px-8">
          {featureCards.map((feature) => (
            <FeatureCard key={feature.title} feature={feature} />
          ))}
        </section>

        <section className="mx-auto w-full max-w-[1680px] px-4 py-6 lg:px-8">
          <UiCard padding="lg" variant="light">
            <h2 className="text-2xl font-black text-slate-950 dark:text-slate-100">Announcements</h2>
            <ul className="mt-4 grid gap-3 text-sm font-semibold text-slate-600 dark:text-slate-300">
              <li className="rounded-2xl border border-slate-100 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/70">
                No active announcements. Market dashboards and technical screens remain available.
              </li>
            </ul>
          </UiCard>
        </section>

        <span id="ai" className="sr-only" aria-hidden="true" />
      </main>

      <footer className="site-footer border-t border-slate-200 bg-white/80 dark:border-slate-800 dark:bg-slate-950/80">
        <div className="mx-auto w-full max-w-[1680px] px-4 py-10 lg:px-8">
          <section className="grid gap-8 md:grid-cols-4">
            <UiCard id="about" padding="md" variant="subtle">
              <h4 className="mb-3 text-lg font-black text-slate-950 dark:text-slate-100">About Us</h4>
              <p className="text-sm font-semibold leading-6 text-slate-600 dark:text-slate-300">
                CvingTrade25X is one of India&apos;s purely trade on stocks. We offer services investing advices index on Nifty 500 stocks only.
              </p>
            </UiCard>
            <FooterColumn links={companyLinks} title="Company Overview" />
            <FooterColumn links={investmentLinks} title="Investment Options" />
            <FooterColumn links={calculatorLinks} title="Calculators" />
          </section>
          <section className="mt-8 grid gap-8 md:grid-cols-3">
            <FooterColumn links={['Knowledge Center', 'Smart Money', 'News', 'Fundamental Research', 'Technical Research', 'Company Reports']} title="Learn to Earn" />
            <FooterColumn links={['IPO', 'Income tax', 'Analyst Corner']} title="Share Market" />
            <FooterColumn links={['Share Market', 'Announcements', 'Share Market Holidays 2025', 'Share Market Glossary', '52-week High', '52-week Low', 'Top Gainers', 'Top Losers']} title="Market Outlook" />
          </section>
          <UiCard id="support" padding="md" variant="subtle" className="mt-8 text-sm font-semibold leading-7 text-slate-600 dark:text-slate-300">
            <strong className="text-slate-950 dark:text-slate-100">Support:</strong> Address: Bangalore 560029 - Phone/WhatsApp: <a className="text-sky-700 dark:text-sky-300" href="tel:9000862901">9000862901</a> - Mailid: <a className="text-sky-700 dark:text-sky-300" href="mailto:cvingtrade25x@gmail.com">cvingtrade25x@gmail.com</a>
          </UiCard>
          <section className="mt-8 grid gap-2 text-sm leading-6 text-slate-500 dark:text-slate-400">
            <h4 className="text-base font-black text-slate-950 dark:text-slate-100">Disclaimer</h4>
            <p>Investments in securities market are subject to market risk, read all the related documents carefully before investing.</p>
            <p>We collect, retain, and use your contact information for legitimate business purposes only, to contact you and provide product and service updates.</p>
            <p>We do not sell or rent your contact information to third parties.</p>
            <p>Please note that by submitting details, you authorize us to call or SMS you even if you are registered under DND for a period of 12 months.</p>
            <p>Copyright@2026-CvingTrade25X - All rights reserved.</p>
          </section>
        </div>
      </footer>

      <AuthModal mode={modal} onClose={() => setModal(null)} onModeChange={setModal} />
    </div>
  );
}
