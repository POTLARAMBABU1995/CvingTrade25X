import { ROCETrendChart } from '../../components/fundamental/charts/ROCETrendChart';
import { ROETrendChart } from '../../components/fundamental/charts/ROETrendChart';
import { RatioTable } from '../../components/fundamental/tables/RatioTable';
import { FundamentalModulePage } from './FundamentalModulePage';

export function FundamentalRatios() {
  return (
    <FundamentalModulePage title="Ratios" description="Return ratios and capital efficiency signals that support the final scorecard.">
      <div className="grid gap-4 xl:grid-cols-2">
        <ROETrendChart />
        <ROCETrendChart />
      </div>
      <RatioTable />
    </FundamentalModulePage>
  );
}
