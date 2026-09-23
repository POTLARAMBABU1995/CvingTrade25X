import { CASH_FLOW_ROWS, FINANCIAL_YEARS } from '../../../services/fundamental/fundamentalApi';
import { FundamentalMetricTable } from './FundamentalMetricTable';

export function CashFlowTable() {
  return <FundamentalMetricTable title="Cash Flow" years={FINANCIAL_YEARS} rows={CASH_FLOW_ROWS} />;
}
