import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

type PageHeaderProps = {
  actions?: ReactNode;
  className?: string;
  title: string;
};

export function PageHeader({ actions, className, title }: PageHeaderProps) {
  return (
    <header className={cn('ui-page-header', className)}>
      <h1 className="ui-page-header__title">{title}</h1>
      {actions ? <div className="ui-page-header__actions">{actions}</div> : null}
    </header>
  );
}
