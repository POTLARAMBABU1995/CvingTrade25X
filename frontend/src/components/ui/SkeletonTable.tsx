import { cn } from '../../lib/cn';

type SkeletonTableProps = {
  rows?: number;
  cols?: number;
  className?: string;
};

export function SkeletonTable({ rows = 8, cols = 6, className }: SkeletonTableProps) {
  const safeRows = Math.max(1, rows);
  const safeCols = Math.max(1, cols);
  return (
    <div className={cn('ui-skeleton-table-wrap', className)} aria-hidden="true">
      <table className="ui-skeleton-table">
        <tbody>
          {Array.from({ length: safeRows }).map((_, rowIdx) => (
            <tr key={rowIdx}>
              {Array.from({ length: safeCols }).map((__, colIdx) => (
                <td key={colIdx}>
                  <span className="ui-skeleton-line" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

