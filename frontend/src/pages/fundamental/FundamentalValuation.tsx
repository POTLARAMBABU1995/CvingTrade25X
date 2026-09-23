import { FundamentalCardGrid } from '../../components/fundamental/cards/FundamentalCardGrid';
import { DividendPayoutTrendChart } from '../../components/fundamental/charts/DividendPayoutTrendChart';
import { getMockFundamentalSummary } from '../../services/fundamental/fundamentalApi';
import { FundamentalModulePage } from './FundamentalModulePage';

export function FundamentalValuation() {
  const summary = getMockFundamentalSummary('RELIANCE');
  const valuationCards = summary.cards.filter((card) => ['valuation', 'dividend'].includes(card.section));

  return (
    <FundamentalModulePage title="Valuation" description="P/E, dividend payout, earnings yield, margin of safety, and valuation comfort score.">
      <FundamentalCardGrid cards={valuationCards} />
      <DividendPayoutTrendChart />
    </FundamentalModulePage>
  );
}
