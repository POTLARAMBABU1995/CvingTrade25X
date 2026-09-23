import type { ReactNode } from 'react';
import { PageHeader } from '../../components/ui/PageHeader';

type FundamentalModulePageProps = {
  title: string;
  description: string;
  children: ReactNode;
  actions?: ReactNode;
};

export function FundamentalModulePage({ title, description, children, actions }: FundamentalModulePageProps) {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={title} />
      {children}
    </div>
  );
}
