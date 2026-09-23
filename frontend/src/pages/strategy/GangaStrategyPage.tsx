import ChartPage from '../ChartPage';
import { StrategyMigrationLayout } from './StrategyMigrationLayout';
import { cn } from '../../lib/cn';
import { useTechnicalThemeMode } from '../technical/technicalPageGuards';

export function GangaStrategyPage() {
  const themeMode = useTechnicalThemeMode();

  return (
    <StrategyMigrationLayout activeStrategyPage="/app/strategy/ganga" fullWidth>
      <div className={cn(
        'mb-5 rounded-[28px] border p-5 shadow-sm',
        themeMode === 'dark'
          ? 'border-slate-700 bg-slate-900/80 text-slate-100 shadow-[0_20px_48px_rgba(2,6,23,0.38)]'
          : 'border-sky-200 bg-white text-slate-950',
      )}>
        <p className="text-xs font-black uppercase tracking-[0.28em] text-sky-700 dark:text-sky-300">Strategy</p>
        <h1 className="mt-2 text-3xl font-black tracking-[-0.04em] text-slate-950 dark:text-slate-100">Ganga Charting Studio</h1>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600 dark:text-slate-300">
          React TSX migration of the legacy Ganga iframe page. The chart workspace now runs directly on the single Flask port without an iframe.
        </p>
      </div>
      <div className="rounded-[30px] border border-slate-200/70 bg-white/86 p-4 text-text shadow-[0_24px_60px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-950/82 dark:shadow-[0_24px_60px_rgba(2,6,23,0.38)]">
        <ChartPage />
      </div>
    </StrategyMigrationLayout>
  );
}
