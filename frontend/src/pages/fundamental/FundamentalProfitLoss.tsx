import { ProfitGrowthChart } from '../../components/fundamental/charts/ProfitGrowthChart';
import { MarginTrendChart } from '../../components/fundamental/charts/MarginTrendChart';
import { ProfitLossTable } from '../../components/fundamental/tables/ProfitLossTable';
import { FundamentalModulePage } from './FundamentalModulePage';

export function FundamentalProfitLoss() {
  return (
    <FundamentalModulePage title="Profit & Loss" description="Screener-like P&L table with cleaner spacing, sticky first column, and readable growth context.">
      <div className="grid gap-4 xl:grid-cols-2">
        <ProfitGrowthChart />
        <MarginTrendChart />
      </div>
      <ProfitLossTable />
    </FundamentalModulePage>
  );
}
