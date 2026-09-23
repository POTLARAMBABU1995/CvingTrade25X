import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react';
import { createContext, useContext, useMemo } from 'react';
import { cn } from '@/lib/utils';

type TabsContextValue = {
  value: string;
  onValueChange: (value: string) => void;
};

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabsContext() {
  const context = useContext(TabsContext);

  if (!context) {
    throw new Error('Tabs components must be used within UiTabs.');
  }

  return context;
}

export type UiTabsProps = HTMLAttributes<HTMLDivElement> & {
  onValueChange: (value: string) => void;
  value: string;
};

export function UiTabs({ children, className, onValueChange, value, ...props }: UiTabsProps) {
  const contextValue = useMemo(() => ({ onValueChange, value }), [onValueChange, value]);

  return (
    <TabsContext.Provider value={contextValue}>
      <div data-slot="tabs" className={cn('flex flex-col gap-4', className)} {...props}>
        {children}
      </div>
    </TabsContext.Provider>
  );
}

export function UiTabsList({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="tabs-list"
      role="tablist"
      className={cn('flex flex-wrap gap-2 overflow-x-auto rounded-[28px] border border-slate-200/70 bg-white/84 p-3 shadow-[0_12px_28px_rgba(15,23,42,0.06)] backdrop-blur-xl dark:border-slate-700/70 dark:bg-slate-900/80 dark:shadow-[0_12px_28px_rgba(2,6,23,0.28)]', className)}
      {...props}
    />
  );
}

export type UiTabsTriggerProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  value: string;
};

export function UiTabsTrigger({ children, className, onClick, type = 'button', value, ...props }: UiTabsTriggerProps) {
  const context = useTabsContext();
  const active = context.value === value;

  return (
    <button
      type={type}
      data-slot="tabs-trigger"
      role="tab"
      aria-selected={active}
      data-state={active ? 'active' : 'inactive'}
      className={cn(
        'focus-ring whitespace-nowrap rounded-full px-4 py-2 text-sm font-bold transition',
        active ? 'bg-gradient-to-r from-[rgb(var(--page-accent-rgb))] to-[rgb(var(--page-accent-rgb-2))] text-white shadow-[0_14px_28px_rgba(59,130,246,0.18)]' : 'bg-slate-50 text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:bg-slate-900/70 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100',
        className,
      )}
      onClick={(event) => {
        onClick?.(event);
        if (!event.defaultPrevented) {
          context.onValueChange(value);
        }
      }}
      {...props}
    >
      {children}
    </button>
  );
}

export type UiTabsContentProps = HTMLAttributes<HTMLDivElement> & {
  forceMount?: boolean;
  value: string;
};

export function UiTabsContent({ children, className, forceMount = false, value, ...props }: UiTabsContentProps) {
  const context = useTabsContext();
  const active = context.value === value;

  if (!active && !forceMount) {
    return null;
  }

  return (
    <div
      data-slot="tabs-content"
      role="tabpanel"
      hidden={!active}
      className={cn('min-w-0', className)}
      {...props}
    >
      {children}
    </div>
  );
}

export function UiTabsHeader({ children, className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div data-slot="tabs-header" className={cn('flex flex-wrap items-center justify-between gap-3', className)} {...props}>
      {children as ReactNode}
    </div>
  );
}
