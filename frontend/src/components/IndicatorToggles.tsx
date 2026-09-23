import { motion } from 'framer-motion';

export type IndicatorState = {
  ema20: boolean;
  ema50: boolean;
  ema200: boolean;
  rsi: boolean;
  macd: boolean;
  atr: boolean;
};

export type IndicatorTogglesProps = {
  value: IndicatorState;
  onChange: (next: IndicatorState) => void;
};

const TOGGLES: Array<{ key: keyof IndicatorState; label: string; tone: string }> = [
  { key: 'ema20', label: 'EMA 20', tone: 'from-amber/24 to-amber/5' },
  { key: 'ema50', label: 'EMA 50', tone: 'from-cyan/24 to-cyan/5' },
  { key: 'ema200', label: 'EMA 200', tone: 'from-white/14 to-transparent' },
  { key: 'rsi', label: 'RSI 14', tone: 'from-emerald/24 to-emerald/5' },
  { key: 'macd', label: 'MACD', tone: 'from-cyan/24 to-cyan/5' },
  { key: 'atr', label: 'ATR 14', tone: 'from-crimson/20 to-crimson/5' },
];

export default function IndicatorToggles({ value, onChange }: IndicatorTogglesProps) {
  return (
    <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
      {TOGGLES.map((toggle) => {
        const active = value[toggle.key];
        return (
          <motion.button
            key={toggle.key}
            type="button"
            whileTap={{ scale: 0.985 }}
            className={`focus-ring flex items-center justify-between gap-3 rounded-[22px] border px-4 py-3 text-left transition ${
              active
                ? 'border-[rgb(var(--page-accent-rgb)/0.22)] bg-white/86 text-text shadow-soft backdrop-blur-xl'
                : 'border-slate-200/70 bg-white/70 text-muted backdrop-blur-xl hover:border-[rgb(var(--page-accent-rgb)/0.16)] hover:text-text'
            }`}
            onClick={() => onChange({ ...value, [toggle.key]: !value[toggle.key] })}
          >
            <div>
              <p className="text-sm font-semibold">{toggle.label}</p>
              <p className="mt-1 text-[10px] uppercase tracking-[0.26em] text-dim">Overlay</p>
            </div>
            <span className={`relative flex h-8 w-14 items-center rounded-full border border-slate-200/70 bg-gradient-to-r ${toggle.tone}`}>
              <span className={`absolute h-6 w-6 rounded-full bg-white shadow-soft transition ${active ? 'translate-x-7' : 'translate-x-1'}`} />
            </span>
          </motion.button>
        );
      })}
    </div>
  );
}
