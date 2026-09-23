import { TECHNICAL_INDICATOR_CONFIGS } from '../../adapters/technicalIndicatorAdapter';
import { TechnicalIndicatorPage } from './TechnicalIndicatorPage';

export function RSI50() {
  return <TechnicalIndicatorPage config={TECHNICAL_INDICATOR_CONFIGS.rsi50} />;
}
