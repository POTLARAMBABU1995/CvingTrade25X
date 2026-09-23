import { TECHNICAL_SCREENER_CONFIGS } from '../../adapters/technicalScreenerAdapter';
import { TechnicalScreenerPage } from './TechnicalScreenerPage';

export function PriceActionAnalysis() {
  return <TechnicalScreenerPage config={TECHNICAL_SCREENER_CONFIGS.priceActionAnalysis} />;
}
