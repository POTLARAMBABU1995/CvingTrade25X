import { motion, useReducedMotion } from 'framer-motion';
import type { HTMLMotionProps } from 'framer-motion';
import { cn } from '../../lib/cn';

export type SurfaceProps = HTMLMotionProps<'div'> & {
  glow?: boolean;
};

export function Surface({ className, glow = false, ...props }: SurfaceProps) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      whileHover={reduceMotion ? undefined : { y: -4, scale: 1.004 }}
      transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        'surface-card relative overflow-hidden rounded-[28px] shadow-panel backdrop-blur-xl',
        glow && 'premium-ring',
        className,
      )}
      {...props}
    />
  );
}
