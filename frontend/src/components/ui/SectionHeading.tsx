import { motion } from 'framer-motion';
import { cn } from '../../lib/cn';

type SectionHeadingProps = {
  eyebrow: string;
  title: string;
  subtitle: string;
  action?: React.ReactNode;
  className?: string;
};

export function SectionHeading({ eyebrow, title, subtitle, action, className }: SectionHeadingProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.35 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className={cn('flex flex-wrap items-end justify-between gap-4', className)}
    >
      <div className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.38em] text-dim">{eyebrow}</p>
        <div className="space-y-1">
          <h2 className="text-2xl font-semibold tracking-[-0.03em] text-text md:text-[2rem]">{title}</h2>
          <p className="max-w-2xl text-sm leading-6 text-muted">{subtitle}</p>
        </div>
      </div>
      {action ? <div className="flex items-center gap-3">{action}</div> : null}
    </motion.div>
  );
}