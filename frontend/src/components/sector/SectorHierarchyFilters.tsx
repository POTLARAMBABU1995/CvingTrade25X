import { ActionButton, SearchInput } from '../../pages/ops/opsPageHelpers';
import { Select } from '../ui/Select';

type Option = {
  label: string;
  value: string;
};

type SectorHierarchyFiltersProps = {
  industryOptions: Option[];
  onIndustryChange: (value: string) => void;
  onParentChange: (value: string) => void;
  onRefresh: () => void;
  onSearchChange: (value: string) => void;
  onSubSectorChange: (value: string) => void;
  parentOptions: Option[];
  refreshing: boolean;
  search: string;
  selectedIndustry: string;
  selectedParent: string;
  selectedSubSector: string;
  subSectorOptions: Option[];
};

export function SectorHierarchyFilters({
  industryOptions,
  onIndustryChange,
  onParentChange,
  onRefresh,
  onSearchChange,
  onSubSectorChange,
  parentOptions,
  refreshing,
  search,
  selectedIndustry,
  selectedParent,
  selectedSubSector,
  subSectorOptions,
}: SectorHierarchyFiltersProps) {
  return (
    <div className="sector-hierarchy-filters" aria-label="Sector hierarchy filters">
      <Select
        className="sr-select sector-hierarchy-select"
        variant="light"
        value={selectedParent}
        onChange={(event) => onParentChange(event.currentTarget.value)}
        aria-label="Select parent sector"
        disabled={!parentOptions.length}
      >
        <option value="">Select Parent Sector</option>
        {parentOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
      </Select>

      <Select
        className="sr-select sector-hierarchy-select"
        variant="light"
        value={selectedIndustry}
        onChange={(event) => onIndustryChange(event.currentTarget.value)}
        aria-label="Select industry sector"
        disabled={!selectedParent}
      >
        <option value="">Select Industry / Sector</option>
        {industryOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
      </Select>

      <Select
        className="sr-select sector-hierarchy-select"
        variant="light"
        value={selectedSubSector}
        onChange={(event) => onSubSectorChange(event.currentTarget.value)}
        aria-label="Select sub-sector"
        disabled={!selectedIndustry}
      >
        <option value="">Select Sub-Sector</option>
        {subSectorOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
      </Select>

      <div className="sector-hierarchy-search">
        <SearchInput
          value={search}
          onChange={onSearchChange}
          placeholder="Search symbol / industry / sub-sector"
          showDecor={false}
        />
      </div>

      <ActionButton disabled={refreshing} onClick={onRefresh}>{refreshing ? 'Refreshing' : 'Refresh'}</ActionButton>
    </div>
  );
}
