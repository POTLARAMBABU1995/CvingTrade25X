import { TECHNICAL_INDICATOR_CONFIGS } from '../../adapters/technicalIndicatorAdapter';
import { TechnicalIndicatorPage } from './TechnicalIndicatorPage';

export function ADX() {
  return <TechnicalIndicatorPage config={TECHNICAL_INDICATOR_CONFIGS.adx} />;
}
