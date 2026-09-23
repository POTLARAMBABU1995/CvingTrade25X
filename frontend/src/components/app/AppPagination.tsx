import { cn } from '../../lib/cn';

export type PaginationItem = number | 'ellipsis';

export function buildPaginationPages(currentPage: number, totalPages: number, windowSize = 2): PaginationItem[] {
  if (totalPages <= 0) return [];
  const clamped = Math.min(Math.max(currentPage, 1), totalPages);
  const numbers = new Set<number>([1, totalPages]);
  for (let page = clamped - windowSize; page <= clamped + windowSize; page += 1) {
    if (page > 0 && page <= totalPages) {
      numbers.add(page);
    }
  }
  const pages = Array.from(numbers).sort((a, b) => a - b);
  const items: PaginationItem[] = [];
  pages.forEach((page, index) => {
    const previous = pages[index - 1];
    if (previous !== undefined && page - previous > 1) {
      items.push('ellipsis');
    }
    items.push(page);
  });
  return items;
}

type AppPaginationProps = {
  className?: string;
  currentPage: number;
  onPageChange: (page: number) => void;
  totalPages: number;
};

export function AppPagination({ className, currentPage, onPageChange, totalPages }: AppPaginationProps) {
  if (totalPages <= 1) {
    return null;
  }

  const clamped = Math.min(Math.max(currentPage, 1), totalPages);
  const items = buildPaginationPages(clamped, totalPages);

  return (
    <nav className={cn('pagination-container', className)} aria-label="Table pagination">
      <div className="pagination">
        <button
          type="button"
          className="page-btn"
          disabled={clamped <= 1}
          onClick={() => onPageChange(clamped - 1)}
        >
          Prev
        </button>
        {items.map((item, index) => item === 'ellipsis' ? (
          <span key={`ellipsis-${index}`} className="page-ellipsis">...</span>
        ) : (
          <button
            type="button"
            key={item}
            className={item === clamped ? 'page-number page-number--active' : 'page-number'}
            aria-current={item === clamped ? 'page' : undefined}
            onClick={() => onPageChange(item)}
          >
            {item}
          </button>
        ))}
        <button
          type="button"
          className="page-btn"
          disabled={clamped >= totalPages}
          onClick={() => onPageChange(clamped + 1)}
        >
          Next
        </button>
      </div>
    </nav>
  );
}
