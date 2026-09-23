import { motion } from 'framer-motion';
import { SECTOR_PULSE } from '../../data/dashboard';
import { Surface } from '../ui/Surface';

function intensityClasses(intensity: number) {
  if (intensity >= 80) return 'border-emerald/25 bg-emerald/14 text-emerald';
  if (intensity >= 50) return 'border-amber/22 bg-amber/12 text-amber';
  return 'border-crimson/20 bg-crimson/10 text-crimson';
}

export function SectorHeatmap() {
  return (
    <Surface className="p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.32em] text-dim">Sector rotation</p>
          <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-text">Leadership heatmap</h3>
        </div>
        <span className="rounded-full border border-slate-200/70 bg-white/75 px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.24em] text-muted backdrop-blur-xl">
          Weekly regime
        </span>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-3">
        {SECTOR_PULSE.map((item, index) => (
          <motion.div
            key={item.name}
            initial={{ opacity: 0, scale: 0.96 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true, amount: 0.35 }}
            transition={{ duration: 0.35, delay: index * 0.04 }}
            className={`rounded-[24px] border p-4 ${intensityClasses(item.intensity)}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-text">{item.name}</p>
                <p className="mt-1 text-[11px] uppercase tracking-[0.26em] text-dim">Weight {item.weight}</p>
              </div>
              <span className="rounded-full border border-white/50 bg-white/65 px-2 py-1 text-[10px] font-semibold text-text backdrop-blur-xl">
                {item.intensity}
              </span>
            </div>
            <p className="mt-5 text-xl font-semibold tracking-[-0.03em] text-text">{item.change}</p>
          </motion.div>
        ))}
      </div>
    </Surface>
  );
}
