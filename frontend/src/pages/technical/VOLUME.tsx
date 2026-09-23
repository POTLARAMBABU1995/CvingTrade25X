import { TECHNICAL_INDICATOR_CONFIGS } from '../../adapters/technicalIndicatorAdapter';
import { TechnicalIndicatorPage } from './TechnicalIndicatorPage';

export function VOLUME() {
  return <TechnicalIndicatorPage config={TECHNICAL_INDICATOR_CONFIGS.volume} />;
}
