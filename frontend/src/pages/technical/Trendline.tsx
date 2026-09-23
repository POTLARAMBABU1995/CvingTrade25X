import { TECHNICAL_SCREENER_CONFIGS } from '../../adapters/technicalScreenerAdapter';
import { TechnicalScreenerPage } from './TechnicalScreenerPage';

export function Trendline() {
  return <TechnicalScreenerPage config={TECHNICAL_SCREENER_CONFIGS.trendline} />;
}
