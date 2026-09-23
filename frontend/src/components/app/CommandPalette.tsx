import { AnimatePresence, motion } from 'framer-motion';
import type { Dispatch, SetStateAction } from 'react';
import { PRIMARY_NAV, STRATEGY_CARDS, WATCHLIST } from '../../data/dashboard';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/Dialog';
import { SearchIcon } from '../ui/Icons';
import { Input } from '../ui/Input';

type CommandPaletteProps = {
  open: boolean;
  setOpen: Dispatch<SetStateAction<boolean>>;
};

export function CommandPalette({ open, setOpen }: CommandPaletteProps) {
  const quickActions = [
    ...PRIMARY_NAV.map((item) => ({ label: item.label, detail: item.hint })),
    ...STRATEGY_CARDS.slice(0, 2).map((item) => ({ label: item.title, detail: 'Open strategy profile' })),
    ...WATCHLIST.slice(0, 2).map((item) => ({ label: item.symbol, detail: item.thesis })),
  ];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        tone="surface"
        align="top"
        hideCloseButton
        className="max-w-none w-[min(680px,calc(100vw-2rem))] p-5"
      >
        <DialogHeader className="sr-only">
          <DialogTitle>Command palette</DialogTitle>
          <DialogDescription>Jump to sectors, strategies, symbols, or workflows inside the React workspace.</DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-3 rounded-[24px] border border-slate-200/70 bg-white/80 px-4 py-3 backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-900/80">
          <SearchIcon className="h-4 w-4 text-cyan" />
          <Input
            autoFocus
            variant="surface"
            placeholder="Jump to sectors, strategies, symbols, or workflows"
            className="h-auto border-none bg-transparent px-0 py-0 text-sm text-text shadow-none placeholder:text-dim focus:bg-transparent"
          />
          <span className="rounded-full border border-slate-200/70 bg-white/70 px-2 py-1 text-[10px] uppercase tracking-[0.24em] text-dim backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-950/70 dark:text-slate-400">Esc</span>
        </div>
        <div className="mt-5 space-y-2">
          <AnimatePresence>
            {quickActions.map((action) => (
              <motion.button
                key={`${action.label}-${action.detail}`}
                type="button"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 8 }}
                onClick={() => setOpen(false)}
                className="focus-ring flex w-full items-center justify-between rounded-[22px] border border-transparent bg-white/75 px-4 py-4 text-left transition hover:border-[rgb(var(--page-accent-rgb)/0.16)] hover:bg-[rgb(var(--page-accent-rgb)/0.06)] dark:bg-slate-900/72 dark:hover:border-slate-700/70 dark:hover:bg-slate-900/88"
              >
                <div>
                  <p className="text-sm font-medium text-text">{action.label}</p>
                  <p className="mt-1 text-xs uppercase tracking-[0.24em] text-dim dark:text-slate-400">{action.detail}</p>
                </div>
                <span className="rounded-full border border-slate-200/70 bg-white/70 px-3 py-2 text-[10px] uppercase tracking-[0.24em] text-muted backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-950/70 dark:text-slate-400">Open</span>
              </motion.button>
            ))}
          </AnimatePresence>
        </div>
      </DialogContent>
    </Dialog>
  );
}
