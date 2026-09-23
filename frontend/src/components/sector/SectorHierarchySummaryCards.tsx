import { UiCard } from '../ui/shadcn-wrappers/card';

type SectorHierarchySummaryCardsProps = {
  selectedIndustry: string;
  selectedParent: string;
  selectedSubSector: string;
  totalIndustries: number;
  totalParents: number;
  totalStocks: number;
  totalSubSectors: number;
};

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <UiCard variant="light" padding="sm" className="sector-hierarchy-stat-card">
      <p className="sector-hierarchy-stat-label">{label}</p>
      <p className="sector-hierarchy-stat-value">{value}</p>
    </UiCard>
  );
}

export function SectorHierarchySummaryCards({
  selectedIndustry,
  selectedParent,
  selectedSubSector,
  totalIndustries,
  totalParents,
  totalStocks,
  totalSubSectors,
}: SectorHierarchySummaryCardsProps) {
  return (
    <section className="sector-hierarchy-summary-grid">
      <StatCard label="Total Parent Sectors" value={totalParents.toLocaleString('en-IN')} />
      <StatCard label="Total Industries" value={totalIndustries.toLocaleString('en-IN')} />
      <StatCard label="Total Sub-Sectors" value={totalSubSectors.toLocaleString('en-IN')} />
      <StatCard label="Total Stocks" value={totalStocks.toLocaleString('en-IN')} />
      <StatCard label="Selected Parent" value={selectedParent || '-'} />
      <StatCard label="Selected Industry" value={selectedIndustry || '-'} />
      <StatCard label="Selected Sub-Sector" value={selectedSubSector || '-'} />
    </section>
  );
}
