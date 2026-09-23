import { useEffect, useState } from 'react';
import { cn } from '../../lib/cn';
import { copyText } from '../../lib/clipboard';
import { CopyIcon } from './Icons';

type CopyTextButtonProps = {
  className?: string;
  label?: string;
  text: string;
};

export function CopyTextButton({ className, label = 'Copy', text }: CopyTextButtonProps) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return undefined;
    const id = window.setTimeout(() => setCopied(false), 1400);
    return () => window.clearTimeout(id);
  }, [copied]);

  return (
    <button
      type="button"
      className={cn('cving-copy-button', className)}
      aria-label={copied ? 'Copied' : label}
      title={copied ? 'Copied' : label}
      onClick={async () => {
        try {
          await copyText(text || '');
          setCopied(true);
        } catch {
          setCopied(false);
        }
      }}
    >
      <CopyIcon className="h-4 w-4" />
      <span className="cving-copy-button__state">{copied ? 'Copied' : label}</span>
    </button>
  );
}
