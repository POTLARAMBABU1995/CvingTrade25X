import { SearchIcon } from '../ui/Icons';
import { Input } from '../ui/Input';

type TechnicalSearchInputProps = {
  ariaLabel?: string;
  id?: string;
  onChange: (value: string) => void;
  placeholder?: string;
  showDecor?: boolean;
  value: string;
};

export function TechnicalSearchInput({
  ariaLabel = 'Search stocks',
  id,
  onChange,
  placeholder = 'Search NSE/BSE symbols',
  showDecor = true,
  value,
}: TechnicalSearchInputProps) {
  return (
    <div className="sr-search">
      {showDecor ? <span className="sr-search__decor" aria-hidden="true"><SearchIcon className="h-4 w-4" /></span> : null}
      <Input
        id={id}
        className="sr-search__input"
        variant="light"
        type="search"
        placeholder={placeholder}
        autoComplete="off"
        aria-label={ariaLabel}
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
      />
    </div>
  );
}
