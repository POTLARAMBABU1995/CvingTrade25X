import { BALANCE_SHEET_ROWS, FINANCIAL_YEARS } from '../../../services/fundamental/fundamentalApi';
import { FundamentalMetricTable } from './FundamentalMetricTable';

export function BalanceSheetTable() {
  return <FundamentalMetricTable title="Balance Sheet" years={FINANCIAL_YEARS} rows={BALANCE_SHEET_ROWS} />;
}
