import { TECHNICAL_INDICATOR_CONFIGS } from '../../adapters/technicalIndicatorAdapter';
import { TechnicalIndicatorPage } from './TechnicalIndicatorPage';

export function MACD() {
  return <TechnicalIndicatorPage config={TECHNICAL_INDICATOR_CONFIGS.macd} />;
}
