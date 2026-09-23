import { QUARTERLY_RESULTS_ROWS } from '../../../services/fundamental/fundamentalApi';
import { FundamentalMetricTable } from './FundamentalMetricTable';

const quarters = ['Dec 2024', 'Mar 2025', 'Jun 2025', 'Sep 2025', 'Dec 2025'];

export function QuarterlyResultsTable() {
  return <FundamentalMetricTable title="Quarterly Results" years={quarters} rows={QUARTERLY_RESULTS_ROWS} />;
}
