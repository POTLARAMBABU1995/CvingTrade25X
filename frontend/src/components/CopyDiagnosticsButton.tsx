import { useEffect, useState } from 'react';
import { cn } from '../lib/cn';
import { copyText } from '../lib/clipboard';
import {
  formatDiagnosticForCopy,
  getLatestDiagnostic,
  subscribeDiagnostics,
  type DiagnosticEntry,
} from '../lib/diagnostics';
import { CopyIcon } from './ui/Icons';

type CopyDiagnosticsButtonProps = {
  className?: string;
  compact?: boolean;
  diagnostic?: DiagnosticEntry | null;
  extraMessage?: string;
};

export function CopyDiagnosticsButton({
  className,
  compact = true,
  diagnostic,
  extraMessage = '',
}: CopyDiagnosticsButtonProps) {
  const [copied, setCopied] = useState(false);
  const [latest, setLatest] = useState<DiagnosticEntry | null>(() => diagnostic ?? getLatestDiagnostic());

  useEffect(() => {
    if (diagnostic) {
      setLatest(diagnostic);
      return undefined;
    }
    return subscribeDiagnostics(() => setLatest(getLatestDiagnostic()));
  }, [diagnostic]);

  useEffect(() => {
    if (!copied) return undefined;
    const id = window.setTimeout(() => setCopied(false), 1400);
    return () => window.clearTimeout(id);
  }, [copied]);

  return (
    <button
      type="button"
      aria-label={copied ? 'Copied' : 'Copy diagnostics'}
      title={copied ? 'Copied' : 'Copy diagnostics'}
      className={cn(
        compact ? 'cving-header-action cving-header-action--icon' : 'cving-copy-button',
        copied && 'is-copied',
        className,
      )}
      onClick={async () => {
        try {
          const text = formatDiagnosticForCopy(latest, extraMessage);
          await copyText(text);
          setCopied(true);
        } catch {
          setCopied(false);
        }
      }}
    >
      <CopyIcon className="h-4 w-4" />
      <span className={compact ? 'sr-only' : 'cving-copy-button__state'}>{copied ? 'Copied' : 'Copy'}</span>
      {compact ? <span className="cving-header-action__hint">{copied ? 'Copied' : 'Copy'}</span> : null}
    </button>
  );
}
