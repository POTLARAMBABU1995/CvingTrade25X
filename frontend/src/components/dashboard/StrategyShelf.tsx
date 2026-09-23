import { motion } from 'framer-motion';
import { STRATEGY_CARDS } from '../../data/dashboard';
import { ArrowUpRightIcon, SparkIcon } from '../ui/Icons';
import { Surface } from '../ui/Surface';

export function StrategyShelf() {
  return (
    <div className="grid gap-4 xl:grid-cols-3">
      {STRATEGY_CARDS.map((card, index) => (
        <motion.div
          key={card.title}
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{ duration: 0.45, delay: index * 0.06, ease: [0.22, 1, 0.36, 1] }}
        >
          <Surface className="h-full p-5">
            <div className="flex h-full flex-col gap-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.3em] text-dim">Strategy profile</p>
                  <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-text">{card.title}</h3>
                </div>
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-cyan/10 text-cyan">
                  <SparkIcon className="h-4 w-4" />
                </div>
              </div>
              <p className="text-sm leading-6 text-muted">{card.subtitle}</p>
              <div className="grid grid-cols-3 gap-3 rounded-[24px] border border-slate-200/70 bg-white/75 p-3 backdrop-blur-xl">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.26em] text-dim">Composite</p>
                  <p className="mt-2 text-sm font-semibold text-text">{card.score}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.26em] text-dim">Hit rate</p>
                  <p className="mt-2 text-sm font-semibold text-emerald">{card.hitRate}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.26em] text-dim">Risk</p>
                  <p className="mt-2 text-sm font-semibold text-text">{card.risk}</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {card.tags.map((tag) => (
                  <span key={tag} className="rounded-full border border-slate-200/70 bg-white/75 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.24em] text-muted backdrop-blur-xl">
                    {tag}
                  </span>
                ))}
              </div>
              <button className="focus-ring mt-auto flex items-center gap-2 self-start rounded-full border border-slate-200/70 bg-white/75 px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-text transition hover:border-[rgb(var(--page-accent-rgb)/0.22)] hover:bg-[rgb(var(--page-accent-rgb)/0.08)]">
                Open model
                <ArrowUpRightIcon className="h-4 w-4" />
              </button>
            </div>
          </Surface>
        </motion.div>
      ))}
    </div>
  );
}
