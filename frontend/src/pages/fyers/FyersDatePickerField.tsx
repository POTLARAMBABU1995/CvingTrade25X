import { useMemo } from 'react';
import { Button } from '../../components/ui/Button';
import { Select } from '../../components/ui/Select';
import { cn } from '../../lib/cn';

type FyersDatePickerFieldProps = {
  allowEmpty?: boolean;
  className?: string;
  invalid?: boolean;
  label: string;
  maxDate?: string;
  maxYear?: number;
  minYear?: number;
  onChange: (value: string) => void;
  value: string;
};

const MONTH_OPTIONS = [
  { value: '01', label: 'Jan' },
  { value: '02', label: 'Feb' },
  { value: '03', label: 'Mar' },
  { value: '04', label: 'Apr' },
  { value: '05', label: 'May' },
  { value: '06', label: 'Jun' },
  { value: '07', label: 'Jul' },
  { value: '08', label: 'Aug' },
  { value: '09', label: 'Sep' },
  { value: '10', label: 'Oct' },
  { value: '11', label: 'Nov' },
  { value: '12', label: 'Dec' },
];

function pad(value: number) {
  return String(value).padStart(2, '0');
}

function parseParts(value: string) {
  const match = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return { year: '', month: '', day: '' };
  return {
    year: match[1],
    month: match[2],
    day: match[3],
  };
}

function daysInMonth(year: string, month: string) {
  const yearNumber = Number(year);
  const monthNumber = Number(month);
  if (!Number.isFinite(yearNumber) || !Number.isFinite(monthNumber) || monthNumber < 1 || monthNumber > 12) {
    return 31;
  }
  return new Date(yearNumber, monthNumber, 0).getDate();
}

function buildIso(year: string, month: string, day: string) {
  if (!year || !month || !day) return '';
  return `${year}-${month}-${day}`;
}

function formatPreview(value: string) {
  const { year, month, day } = parseParts(value);
  if (!year || !month || !day) return 'All dates';
  return `${day}-${month}-${year}`;
}

export function FyersDatePickerField({
  allowEmpty = false,
  className,
  invalid = false,
  label,
  maxDate,
  maxYear,
  minYear = 1990,
  onChange,
  value,
}: FyersDatePickerFieldProps) {
  const todayYear = new Date().getFullYear();
  const { year, month, day } = parseParts(value);
  const resolvedMaxYear = Math.max(minYear, maxYear ?? todayYear + 1);
  const years = useMemo(() => {
    const items: string[] = [];
    for (let current = resolvedMaxYear; current >= minYear; current -= 1) {
      items.push(String(current));
    }
    return items;
  }, [minYear, resolvedMaxYear]);

  const totalDays = daysInMonth(year, month);
  const dayOptions = useMemo(() => {
    const { year: maxYearPart, month: maxMonthPart, day: maxDayPart } = parseParts(maxDate || '');
    const maxDay = year === maxYearPart && month === maxMonthPart ? Number(maxDayPart) : totalDays;
    return Array.from({ length: totalDays }, (_, index) => ({
      disabled: Number(index + 1) > maxDay,
      value: pad(index + 1),
    }));
  }, [maxDate, month, totalDays, year]);

  function updateDate(nextYear: string, nextMonth: string, nextDay: string) {
    const clampedDay = nextDay && Number(nextDay) > daysInMonth(nextYear, nextMonth)
      ? pad(daysInMonth(nextYear, nextMonth))
      : nextDay;
    if (allowEmpty && !nextYear && !nextMonth && !clampedDay) {
      onChange('');
      return;
    }
    const nextValue = buildIso(nextYear, nextMonth, clampedDay);
    if (maxDate && nextValue && nextValue > maxDate) return;
    onChange(nextValue);
  }

  return (
    <label className={cn('database-react-field fyers-date-picker', className)}>
      <span>{label}</span>
      <div className="fyers-date-picker__row">
        <Select
          className="fyers-date-picker__control"
          invalid={invalid}
          variant="light"
          value={year}
          onChange={(event) => updateDate(event.currentTarget.value, month, day)}
        >
          <option value="">{allowEmpty ? 'Year' : 'Select year'}</option>
          {years.map((option) => <option key={option} value={option}>{option}</option>)}
        </Select>
        <Select
          className="fyers-date-picker__control"
          invalid={invalid}
          variant="light"
          value={month}
          onChange={(event) => updateDate(year, event.currentTarget.value, day)}
        >
          <option value="">{allowEmpty ? 'Month' : 'Select month'}</option>
          {MONTH_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </Select>
        <Select
          className="fyers-date-picker__control"
          invalid={invalid}
          variant="light"
          value={day}
          onChange={(event) => updateDate(year, month, event.currentTarget.value)}
        >
          <option value="">{allowEmpty ? 'Date' : 'Select date'}</option>
          {dayOptions.map((option) => <option key={option.value} disabled={option.disabled} value={option.value}>{option.value}</option>)}
        </Select>
      </div>
      <div className="fyers-date-picker__meta">
        <span>{formatPreview(value)}</span>
        {allowEmpty && value ? (
          <Button size="sm" type="button" variant="ghost" onClick={() => onChange('')}>
            Clear
          </Button>
        ) : null}
      </div>
    </label>
  );
}
