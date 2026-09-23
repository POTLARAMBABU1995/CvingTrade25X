import type { ReactNode } from 'react';
import type { KpiTone } from '../../types';
import { KpiStatCard } from '../ui/KpiStatCard';

type KpiCardProps = {
  label: string;
  value: string;
  change?: string;
  icon?: ReactNode;
  tone?: KpiTone;
};

export function KpiCard({ label, value, change, icon, tone = 'cyan' }: KpiCardProps) {
  return (
    <KpiStatCard
      card={{
        id: label,
        label,
        value,
        change,
        icon,
        tone,
      }}
    />
  );
}
