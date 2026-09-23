import { AnimatePresence, motion } from 'framer-motion';
import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

type ToastProps = {
  open: boolean;
  title: string;
  description: string;
  icon?: ReactNode;
  placement?: 'bottom-right' | 'top-right';
  tone?: 'info' | 'success' | 'warn' | 'danger';
  onClose?: () => void;
};

const toneClasses = {
  info: {
    shell: 'border-[rgb(var(--page-accent-rgb)/0.2)] bg-white/92 dark:border-[rgb(var(--page-accent-rgb)/0.35)] dark:bg-slate-900/92',
    icon: 'bg-cyan/12 text-cyan',
  },
  success: {
    shell: 'border-emerald/24 bg-white/92 dark:border-emerald-500/38 dark:bg-slate-900/92',
    icon: 'bg-emerald/12 text-emerald',
  },
  warn: {
    shell: 'border-amber/24 bg-white/92 dark:border-amber-500/38 dark:bg-slate-900/92',
    icon: 'bg-amber/12 text-amber',
  },
  danger: {
    shell: 'border-crimson/24 bg-white/92 dark:border-rose-500/38 dark:bg-slate-900/92',
    icon: 'bg-crimson/12 text-crimson',
  },
};

const placementClasses = {
  'bottom-right': 'bottom-6 right-6',
  'top-right': 'right-4 top-20 sm:right-6 sm:top-24',
} as const;

export function Toast({
  open,
  title,
  description,
  icon,
  placement = 'bottom-right',
  tone = 'info',
  onClose,
}: ToastProps) {
  const toneStyle = toneClasses[tone];

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          initial={{ opacity: 0, y: 20, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 16, scale: 0.96 }}
          transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
          className={cn(
            'fixed z-50 flex max-w-sm items-start gap-3 rounded-3xl border px-4 py-4 shadow-float backdrop-blur-xl',
            placementClasses[placement],
            toneStyle.shell,
          )}
          role="status"
          aria-live="polite"
        >
          <div className={cn('mt-1 flex h-9 w-9 items-center justify-center rounded-2xl', toneStyle.icon)}>
            {icon}
          </div>
          <div className="space-y-1">
            <p className="text-sm font-semibold text-text">{title}</p>
            <p className="text-xs leading-5 text-muted">{description}</p>
          </div>
          {onClose ? (
            <button
              type="button"
              className="focus-ring ml-auto rounded-full px-2 py-1 text-[11px] uppercase tracking-[0.22em] text-dim transition hover:text-text"
              onClick={onClose}
              aria-label="Dismiss notification"
            >
              Close
            </button>
          ) : null}
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
