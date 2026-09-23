import type { ReactNode } from 'react';
import { getMarketCapToneClass, type MarketCapCategory } from '../../adapters/technicalMarketCap';

type TechnicalMarketCapCellProps = {
  children: ReactNode;
  className?: string;
  copyText?: string;
  onCopy?: (value: string) => void;
  tone?: MarketCapCategory;
  title?: string;
};

export function TechnicalMarketCapCell({
  children,
  className,
  copyText,
  onCopy,
  tone,
  title,
}: TechnicalMarketCapCellProps) {
  const toneClass = getMarketCapToneClass(tone);
  const isCopyable = typeof copyText === 'string';
  const combinedClassName = [toneClass, className].filter(Boolean).join(' ') || undefined;
  const handleCopy = () => {
    if (!isCopyable) return;
    const value = copyText ?? '';
    if (onCopy) {
      onCopy(value);
      return;
    }
    const clipboard = navigator.clipboard;
    if (!clipboard) return;
    clipboard.writeText(value).catch(() => undefined);
  };

  return (
    <span
      className={combinedClassName}
      role={isCopyable ? 'button' : undefined}
      tabIndex={isCopyable ? 0 : undefined}
      title={title ?? (isCopyable ? `Copy ${copyText}` : undefined)}
      style={isCopyable ? { cursor: 'copy', userSelect: 'text' } : undefined}
      onClick={isCopyable ? handleCopy : undefined}
      onKeyDown={isCopyable ? (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        handleCopy();
      } : undefined}
    >
      {children}
    </span>
  );
}
