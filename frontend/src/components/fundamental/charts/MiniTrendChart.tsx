type MiniTrendChartProps = {
  title: string;
  values?: number[];
  color?: string;
};

const defaultValues = [42, 48, 46, 55, 61, 68, 74];

function buildPath(values: number[]): string {
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = Math.max(max - min, 1);
  return values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * 240;
      const y = 90 - ((value - min) / range) * 70;
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
}

export function MiniTrendChart({ title, values = defaultValues, color = '#10b981' }: MiniTrendChartProps) {
  const path = buildPath(values);

  return (
    <section className="rounded-[26px] border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-4">
        <h3 className="text-sm font-bold uppercase tracking-[0.18em] text-slate-500">{title}</h3>
        <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700">improving</span>
      </div>
      <svg className="mt-5 h-[120px] w-full overflow-visible" viewBox="0 0 240 100" role="img" aria-label={`${title} trend`}>
        <path d="M0 92 H240" stroke="#e2e8f0" strokeWidth="1" />
        <path d="M0 58 H240" stroke="#e2e8f0" strokeWidth="1" strokeDasharray="4 6" />
        <path d="M0 24 H240" stroke="#e2e8f0" strokeWidth="1" strokeDasharray="4 6" />
        <path d={path} fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </section>
  );
}
