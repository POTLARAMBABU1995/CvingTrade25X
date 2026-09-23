import { AnimatePresence, motion } from 'framer-motion';
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react';
import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/utils';

type DialogContextValue = {
  mounted: boolean;
  onOpenChange: (open: boolean) => void;
  open: boolean;
};

const DialogContext = createContext<DialogContextValue | null>(null);

function useDialogContext() {
  const context = useContext(DialogContext);

  if (!context) {
    throw new Error('Dialog components must be used within UiDialog.');
  }

  return context;
}

export type UiDialogProps = {
  children: ReactNode;
  onOpenChange: (open: boolean) => void;
  open: boolean;
};

export function UiDialog({ children, onOpenChange, open }: UiDialogProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted || !open) {
      return undefined;
    }

    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onOpenChange(false);
      }
    };

    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [mounted, onOpenChange, open]);

  const contextValue = useMemo(() => ({ mounted, onOpenChange, open }), [mounted, onOpenChange, open]);

  return <DialogContext.Provider value={contextValue}>{children}</DialogContext.Provider>;
}

export type UiDialogTone = 'surface' | 'light';
export type UiDialogAlign = 'top' | 'center';

export type UiDialogContentProps = {
  align?: UiDialogAlign;
  children: ReactNode;
  className?: string;
  hideCloseButton?: boolean;
  overlayClassName?: string;
  tone?: UiDialogTone;
};

const dialogToneClasses: Record<UiDialogTone, string> = {
  surface: 'border-line/60 bg-white/90 text-text shadow-float backdrop-blur-2xl dark:border-slate-700/70 dark:bg-slate-900/92 dark:text-slate-100',
  light: 'border-slate-200 bg-white text-slate-950 shadow-2xl dark:border-slate-700/70 dark:bg-slate-900 dark:text-slate-100',
};

const dialogAlignClasses: Record<UiDialogAlign, string> = {
  top: 'items-start pt-16 md:pt-20',
  center: 'items-center py-8',
};

export function UiDialogContent({
  align = 'top',
  children,
  className,
  hideCloseButton = false,
  overlayClassName,
  tone = 'surface',
}: UiDialogContentProps) {
  const context = useDialogContext();

  if (!context.mounted) {
    return null;
  }

  return createPortal(
    <AnimatePresence>
      {context.open ? (
        <div className={cn('fixed inset-0 z-50 flex justify-center px-4', dialogAlignClasses[align])}>
            <motion.button
              type="button"
              aria-label="Close dialog"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            className={cn('fixed inset-0 bg-white/50 backdrop-blur-md dark:bg-slate-950/60', overlayClassName)}
              onClick={() => context.onOpenChange(false)}
            />
          <motion.div
            initial={{ opacity: 0, y: align === 'center' ? 14 : -18, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: align === 'center' ? 10 : -12, scale: 0.96 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            role="dialog"
            aria-modal="true"
            data-slot="dialog-content"
            className={cn(
              'relative z-10 w-full max-w-2xl rounded-[32px] border p-5',
              dialogToneClasses[tone],
              className,
            )}
          >
            {!hideCloseButton ? (
              <button
                type="button"
                className={cn(
                  'focus-ring absolute right-4 top-4 rounded-full px-2 py-1 text-[11px] uppercase tracking-[0.22em] transition',
                  tone === 'light' ? 'text-slate-500 hover:text-slate-950 dark:text-slate-400 dark:hover:text-slate-100' : 'text-dim hover:text-text dark:text-slate-400 dark:hover:text-slate-100',
                )}
                onClick={() => context.onOpenChange(false)}
                aria-label="Close dialog"
              >
                Close
              </button>
            ) : null}
            {children}
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>,
    document.body,
  );
}

export function UiDialogHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="dialog-header" className={cn('flex flex-col gap-2', className)} {...props} />;
}

export function UiDialogTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      data-slot="dialog-title"
      className={cn('text-xl font-bold tracking-[-0.03em]', className)}
      {...props}
    />
  );
}

export function UiDialogDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      data-slot="dialog-description"
      className={cn('text-sm leading-6 text-muted', className)}
      {...props}
    />
  );
}

export function UiDialogFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="dialog-footer" className={cn('mt-4 flex flex-wrap justify-end gap-3', className)} {...props} />;
}

export type UiDialogCloseProps = ButtonHTMLAttributes<HTMLButtonElement>;

export function UiDialogClose({ children = 'Close', className, onClick, type = 'button', ...props }: UiDialogCloseProps) {
  const context = useDialogContext();

  return (
    <button
      type={type}
      data-slot="dialog-close"
      className={cn('focus-ring rounded-full px-2 py-1 text-[11px] uppercase tracking-[0.22em] text-dim transition hover:text-text', className)}
      onClick={(event) => {
        onClick?.(event);
        if (!event.defaultPrevented) {
          context.onOpenChange(false);
        }
      }}
      {...props}
    >
      {children}
    </button>
  );
}
