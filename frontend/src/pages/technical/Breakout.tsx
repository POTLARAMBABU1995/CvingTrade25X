import { TECHNICAL_SCREENER_CONFIGS } from '../../adapters/technicalScreenerAdapter';
import { TechnicalScreenerPage } from './TechnicalScreenerPage';

export function Breakout() {
  return <TechnicalScreenerPage config={TECHNICAL_SCREENER_CONFIGS.breakout} />;
}
