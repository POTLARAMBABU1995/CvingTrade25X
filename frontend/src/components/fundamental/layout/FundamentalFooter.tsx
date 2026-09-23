type FundamentalFooterProps = {
  lastUpdated?: string;
};

export function FundamentalFooter({ lastUpdated }: FundamentalFooterProps) {
  return (
    <footer className="border-t border-slate-200 bg-white/70">
      <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-3 px-4 py-6 text-sm text-slate-500 lg:flex-row lg:items-center lg:justify-between lg:px-8">
        <div>
          <span className="font-semibold text-slate-800">CvingTrade25X</span>
          <span className="mx-2 text-slate-300">/</span>
          Fundamental Analysis Engine
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span>Educational research only</span>
          <span>NSE / BSE / SEBI references</span>
          <span>Last updated: {lastUpdated ?? 'Pending backend sync'}</span>
        </div>
      </div>
    </footer>
  );
}
