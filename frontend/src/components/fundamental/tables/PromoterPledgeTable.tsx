import { FINANCIAL_YEARS, PROMOTER_PLEDGE_ROWS } from '../../../services/fundamental/fundamentalApi';
import { FundamentalMetricTable } from './FundamentalMetricTable';

export function PromoterPledgeTable() {
  return <FundamentalMetricTable title="Promoter Pledge" years={FINANCIAL_YEARS} rows={PROMOTER_PLEDGE_ROWS} />;
}
