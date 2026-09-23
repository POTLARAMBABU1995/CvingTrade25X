import { FINANCIAL_YEARS, RATIO_ROWS } from '../../../services/fundamental/fundamentalApi';
import { FundamentalMetricTable } from './FundamentalMetricTable';

export function RatioTable() {
  return <FundamentalMetricTable title="Return Ratios" years={FINANCIAL_YEARS} rows={RATIO_ROWS} />;
}
