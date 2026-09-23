import { motion } from 'framer-motion';
import type { Timeframe } from '../types';

export type TimeframeSelectorProps = {
  value: Timeframe;
  onChange: (tf: Timeframe) => void;
};

const OPTIONS: Array<{ value: Timeframe; label: string; hint: string }> = [
  { value: '1D', label: '1D', hint: 'Session' },
  { value: '1W', label: '1W', hint: 'Swing' },
  { value: '1M', label: '1M', hint: 'Position' },
  { value: '1Y', label: '1Y', hint: 'Cycle' },
];

export default function TimeframeSelector({ value, onChange }: TimeframeSelectorProps) {
  return (
    <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
      {OPTIONS.map((option) => {
        const active = value === option.value;
        return (
          <motion.button
            key={option.value}
            type="button"
            whileTap={{ scale: 0.98 }}
            className={`focus-ring rounded-[22px] border px-4 py-3 text-left transition ${
              active
                ? 'border-[rgb(var(--page-accent-rgb)/0.24)] bg-[rgb(var(--page-accent-rgb)/0.12)] text-text shadow-glow'
                : 'border-slate-200/70 bg-white/82 text-muted hover:border-[rgb(var(--page-accent-rgb)/0.18)] hover:text-text'
            }`}
            onClick={() => onChange(option.value)}
          >
            <p className="text-sm font-semibold tracking-[0.04em]">{option.label}</p>
            <p className="mt-1 text-[10px] uppercase tracking-[0.28em] text-dim">{option.hint}</p>
          </motion.button>
        );
      })}
    </div>
  );
}
