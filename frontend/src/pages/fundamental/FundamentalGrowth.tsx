import { FundamentalCardGrid } from '../../components/fundamental/cards/FundamentalCardGrid';
import { ProfitGrowthChart } from '../../components/fundamental/charts/ProfitGrowthChart';
import { RevenueGrowthChart } from '../../components/fundamental/charts/RevenueGrowthChart';
import { QuarterlyResultsTable } from '../../components/fundamental/tables/QuarterlyResultsTable';
import { YearlyResultsTable } from '../../components/fundamental/tables/YearlyResultsTable';
import { getMockFundamentalSummary } from '../../services/fundamental/fundamentalApi';
import { FundamentalModulePage } from './FundamentalModulePage';

export function FundamentalGrowth() {
  const summary = getMockFundamentalSummary('RELIANCE');
  const growthCards = summary.cards.filter((card) => card.section === 'growth');

  return (
    <FundamentalModulePage title="Growth" description="Sales CAGR, profit CAGR, EPS growth, QoQ strength, YoY strength, and future growth visibility.">
      <FundamentalCardGrid cards={growthCards} />
      <div className="grid gap-4 xl:grid-cols-2">
        <RevenueGrowthChart />
        <ProfitGrowthChart />
      </div>
      <QuarterlyResultsTable />
      <YearlyResultsTable />
    </FundamentalModulePage>
  );
}
