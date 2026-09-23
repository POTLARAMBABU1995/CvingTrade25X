import { motion } from 'framer-motion';
import { BellIcon, DotGridIcon, SearchIcon, SparkIcon } from '../ui/Icons';

type TopBarProps = {
  onOpenCommand: () => void;
};

export function TopBar({ onOpenCommand }: TopBarProps) {
  return (
    <motion.header
      initial={{ opacity: 0, y: -18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className="sticky top-4 z-40 rounded-[30px] border border-slate-200/70 bg-white/78 px-4 py-3 shadow-soft backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-900/78"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <button
          type="button"
          onClick={onOpenCommand}
          className="focus-ring flex min-w-[280px] flex-1 items-center gap-3 rounded-[22px] border border-slate-200/70 bg-white/78 px-4 py-3 text-left text-sm text-muted transition hover:border-[rgb(var(--page-accent-rgb)/0.18)] hover:text-text dark:border-slate-700/70 dark:bg-slate-900/78 dark:text-slate-300 dark:hover:text-slate-100"
        >
          <SearchIcon className="h-4 w-4 text-cyan" />
          <span className="flex-1">Search workspaces, symbols, sectors, and saved setups</span>
          <span className="rounded-full border border-slate-200/70 bg-white/70 px-2 py-1 text-[10px] uppercase tracking-[0.28em] text-dim backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-950/70 dark:text-slate-400">Ctrl K</span>
        </button>

        <div className="flex items-center gap-3">
          <div className="hidden rounded-[22px] border border-slate-200/70 bg-white/78 px-4 py-3 md:flex md:items-center md:gap-3 backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-900/78">
            <span className="flex h-9 w-9 items-center justify-center rounded-2xl bg-cyan/12 text-cyan">
              <SparkIcon className="h-4 w-4" />
            </span>
            <div>
              <p className="text-[11px] uppercase tracking-[0.32em] text-dim dark:text-slate-400">System</p>
              <p className="text-sm font-medium text-text">Research rail online</p>
            </div>
          </div>
          <button className="focus-ring flex h-12 w-12 items-center justify-center rounded-2xl border border-slate-200/70 bg-white/78 text-muted backdrop-blur-xl hover:border-[rgb(var(--page-accent-rgb)/0.18)] hover:text-text dark:border-slate-700/70 dark:bg-slate-900/78 dark:text-slate-300">
            <BellIcon className="h-4 w-4" />
          </button>
          <button className="focus-ring flex h-12 w-12 items-center justify-center rounded-2xl border border-slate-200/70 bg-white/78 text-muted backdrop-blur-xl hover:border-[rgb(var(--page-accent-rgb)/0.18)] hover:text-text dark:border-slate-700/70 dark:bg-slate-900/78 dark:text-slate-300">
            <DotGridIcon className="h-4 w-4" />
          </button>
        </div>
      </div>
    </motion.header>
  );
}
