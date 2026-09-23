import { cn } from '../../lib/cn';
import { formatDiagnosticForCopy, getLatestDiagnostic } from '../../lib/diagnostics';
import { CopyTextButton } from './CopyTextButton';

type ErrorAlertCardProps = {
  className?: string;
  context?: string;
  message?: string | null;
};

export function ErrorAlertCard({ className, context, message }: ErrorAlertCardProps) {
  const text = String(message || '').trim() || 'Unknown error';
  const copyPayload = formatDiagnosticForCopy(
    getLatestDiagnostic(),
    context ? `${context}: ${text}` : text,
  );
  return (
    <section className={cn('card ema-error-card cving-error-alert', className)} role="alert">
      <p className="cving-error-alert__message">{context ? `${context}: ${text}` : text}</p>
      <CopyTextButton text={copyPayload} label="Copy" />
    </section>
  );
}
