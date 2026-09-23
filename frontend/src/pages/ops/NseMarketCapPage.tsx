import { NseAutomationPage } from './NseAutomationPage';
import { NSE_AUTOMATION_PAGE_CONFIGS } from './nseAutomationConfigs';

export function NseMarketCapPage() {
  return <NseAutomationPage config={NSE_AUTOMATION_PAGE_CONFIGS.marketCap} />;
}
