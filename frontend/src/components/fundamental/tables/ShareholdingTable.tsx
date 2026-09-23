import { FINANCIAL_YEARS, SHAREHOLDING_ROWS } from '../../../services/fundamental/fundamentalApi';
import { FundamentalMetricTable } from './FundamentalMetricTable';

export function ShareholdingTable() {
  return <FundamentalMetricTable title="Shareholding Pattern" years={FINANCIAL_YEARS} rows={SHAREHOLDING_ROWS} />;
}
