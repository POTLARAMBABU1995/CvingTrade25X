import { DebtTrendChart } from '../../components/fundamental/charts/DebtTrendChart';
import { BalanceSheetTable } from '../../components/fundamental/tables/BalanceSheetTable';
import { FundamentalModulePage } from './FundamentalModulePage';

export function FundamentalBalanceSheet() {
  return (
    <FundamentalModulePage title="Balance Sheet" description="Debt, net worth, liquidity, and interest coverage in a focused statement view.">
      <DebtTrendChart />
      <BalanceSheetTable />
    </FundamentalModulePage>
  );
}
