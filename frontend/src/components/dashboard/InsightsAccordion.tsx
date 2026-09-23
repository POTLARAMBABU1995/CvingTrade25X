import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { INSIGHTS } from '../../data/dashboard';
import { ChevronRightIcon } from '../ui/Icons';
import { Surface } from '../ui/Surface';

export function InsightsAccordion() {
  const [openId, setOpenId] = useState(INSIGHTS[0]?.title ?? '');

  return (
    <Surface className="p-5">
      <div>
        <p className="text-[11px] uppercase tracking-[0.32em] text-dim">Research brief</p>
        <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-text">Desk notes and execution framing</h3>
      </div>
      <div className="mt-5 space-y-3">
        {INSIGHTS.map((item) => {
          const isOpen = openId === item.title;
          return (
            <div key={item.title} className="rounded-[24px] border border-slate-200/70 bg-white/75 px-4 py-4 backdrop-blur-xl">
              <button
                type="button"
                className="focus-ring flex w-full items-start justify-between gap-4 text-left"
                onClick={() => setOpenId(isOpen ? '' : item.title)}
              >
                <div>
                  <p className="text-sm font-semibold text-text">{item.title}</p>
                  <p className="mt-1 text-sm leading-6 text-muted">{item.summary}</p>
                </div>
                <ChevronRightIcon className={`mt-1 h-4 w-4 flex-none text-dim transition ${isOpen ? 'rotate-90' : ''}`} />
              </button>
              <AnimatePresence initial={false}>
                {isOpen ? (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                    className="overflow-hidden"
                  >
                    <p className="pt-4 text-sm leading-6 text-muted">{item.detail}</p>
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </Surface>
  );
}
