import { FINANCIAL_YEARS, PROFIT_LOSS_ROWS } from '../../../services/fundamental/fundamentalApi';
import { FundamentalMetricTable } from './FundamentalMetricTable';

export function ProfitLossTable() {
  return (
    <FundamentalMetricTable
      title="Profit & Loss"
      years={FINANCIAL_YEARS}
      rows={PROFIT_LOSS_ROWS}
      note="Premium screener-style table with sticky metric column and horizontal scroll."
    />
  );
}
