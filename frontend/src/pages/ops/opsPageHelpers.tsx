import type { ReactNode } from 'react';
import { AppDataTable, type AppDataTableColumn } from '../../components/app/AppDataTable';
import { TechnicalSearchInput } from '../../components/app/TechnicalSearchInput';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { PageHeader } from '../../components/ui/PageHeader';
import { Select } from '../../components/ui/Select';
import { formatCellByKind, pickField, safeLegacyText, type UnknownRecord } from '../../adapters/databasePageAdapter';

export type GenericColumn = {
  aliases: readonly string[];
  dataCol: string;
  format?: 'count' | 'date' | 'dateOnly' | 'number' | 'source' | 'text';
  key: string;
  label: string;
  sortType?: 'date' | 'number' | 'string';
};

export function PageHero({ title }: { title: string }) {
  return <PageHeader title={title} />;
}

export function KpiGrid({ items }: { items: Array<{ className?: string; label: string; value: ReactNode }> }) {
  return (
    <section className="technical-summary-grid database-react-kpi-grid">
      {items.map((item) => (
        <article className={['technical-summary-card', item.className].filter(Boolean).join(' ')} key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </article>
      ))}
    </section>
  );
}

export function SearchInput({
  showDecor: _showDecor = true,
  onChange,
  placeholder = 'Search NSE/BSE symbols',
  value,
}: {
  showDecor?: boolean;
  onChange: (value: string) => void;
  placeholder?: string;
  value: string;
}) {
  return <TechnicalSearchInput value={value} onChange={onChange} placeholder={placeholder} showDecor={_showDecor} />;
}

export function SelectField({
  children,
  label,
  onChange,
  value,
}: {
  children: ReactNode;
  label: string;
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <label className="database-react-field">
      <span>{label}</span>
      <Select className="sr-select" variant="light" value={value} onChange={(event) => onChange(event.currentTarget.value)}>
        {children}
      </Select>
    </label>
  );
}

export function TextField({
  label,
  onChange,
  placeholder,
  type = 'text',
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  value: string;
}) {
  return (
    <label className="database-react-field">
      <span>{label}</span>
      <Input
        variant="light"
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.currentTarget.value)}
      />
    </label>
  );
}

export function ActionButton({
  children,
  disabled,
  onClick,
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <Button className="preset-btn" variant="secondary" type="button" disabled={disabled} onClick={onClick}>
      {children}
    </Button>
  );
}

function sortValue(row: UnknownRecord, column: GenericColumn): string | number | null {
  const value = pickField(row, column.aliases);
  if (value === null || value === undefined || value === '') return null;
  if (column.sortType === 'number') {
    const parsed = Number(String(value).replace(/,/g, '').replace(/%/g, ''));
    return Number.isFinite(parsed) ? parsed : null;
  }
  return String(value);
}

export function GenericDataTable({
  columns,
  emptyMessage,
  pageSize,
  rows,
  tableClassName,
  tableId,
}: {
  columns: readonly GenericColumn[];
  emptyMessage?: string;
  pageSize: number;
  rows: UnknownRecord[];
  tableClassName?: string;
  tableId: string;
}) {
  const tableColumns: Array<AppDataTableColumn<UnknownRecord>> = columns.map((column) => ({
    dataCol: column.dataCol,
    getSortValue: (row) => sortValue(row, column),
    key: column.key,
    label: column.label,
    renderCell: (row) => formatCellByKind(pickField(row, column.aliases), column.format ?? 'text'),
    sortType: column.sortType ?? 'string',
  }));

  return (
    <AppDataTable
      columns={tableColumns}
      emptyMessage={emptyMessage}
      getRowKey={(row, index) => `${safeLegacyText(pickField(row, ['symbol', 'SYMBOL', 'script', 'SCRIPT']), 'row')}-${index}`}
      pageSize={pageSize}
      rows={rows}
      showTopPagination
      tableClassName={tableClassName}
      tableId={tableId}
    />
  );
}
