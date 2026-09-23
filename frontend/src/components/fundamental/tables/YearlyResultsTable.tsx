import { FINANCIAL_YEARS, YEARLY_RESULTS_ROWS } from '../../../services/fundamental/fundamentalApi';
import { FundamentalMetricTable } from './FundamentalMetricTable';

export function YearlyResultsTable() {
  return <FundamentalMetricTable title="Yearly Results" years={FINANCIAL_YEARS} rows={YEARLY_RESULTS_ROWS} />;
}
