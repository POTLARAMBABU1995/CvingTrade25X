import { TECHNICAL_INDICATOR_CONFIGS } from '../../adapters/technicalIndicatorAdapter';
import { TechnicalIndicatorPage } from './TechnicalIndicatorPage';

export function ATR14() {
  return <TechnicalIndicatorPage config={TECHNICAL_INDICATOR_CONFIGS.atr14} />;
}
