import type { ReactNode } from 'react';

export type KpiTone = 'cyan' | 'amber' | 'emerald' | 'crimson' | 'slate';
export type KpiTrend = 'up' | 'down' | 'flat';

export type KpiCard = {
  id: string;
  label: string;
  value: string;
  change?: string;
  subtext?: string;
  status?: string;
  trend?: KpiTrend;
  tooltip?: string;
  tone?: KpiTone;
  colorToken?: string;
  icon?: ReactNode;
  iconKey?: string;
};
