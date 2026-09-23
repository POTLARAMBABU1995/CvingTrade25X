import { CashFlowTrendChart } from '../../components/fundamental/charts/CashFlowTrendChart';
import { CashFlowTable } from '../../components/fundamental/tables/CashFlowTable';
import { FundamentalModulePage } from './FundamentalModulePage';

export function FundamentalCashFlow() {
  return (
    <FundamentalModulePage title="Cash Flow" description="CFO, CFO/PAT, free cash flow, capex, and cash conversion quality.">
      <CashFlowTrendChart />
      <CashFlowTable />
    </FundamentalModulePage>
  );
}
