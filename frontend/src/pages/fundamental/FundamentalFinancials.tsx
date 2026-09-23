import { BalanceSheetTable } from '../../components/fundamental/tables/BalanceSheetTable';
import { CashFlowTable } from '../../components/fundamental/tables/CashFlowTable';
import { ProfitLossTable } from '../../components/fundamental/tables/ProfitLossTable';
import { FundamentalModulePage } from './FundamentalModulePage';

export function FundamentalFinancials() {
  return (
    <FundamentalModulePage title="Financials" description="Premium financial statement surface for P&L, balance sheet, and cash-flow quality.">
      <ProfitLossTable />
      <BalanceSheetTable />
      <CashFlowTable />
    </FundamentalModulePage>
  );
}
