import { FundamentalCardGrid } from '../../components/fundamental/cards/FundamentalCardGrid';
import { PromoterPledgeTable } from '../../components/fundamental/tables/PromoterPledgeTable';
import { ShareholdingTable } from '../../components/fundamental/tables/ShareholdingTable';
import { getMockFundamentalSummary } from '../../services/fundamental/fundamentalApi';
import { FundamentalModulePage } from './FundamentalModulePage';

export function FundamentalGovernance() {
  const summary = getMockFundamentalSummary('RELIANCE');
  const governanceCards = summary.cards.filter((card) => card.section === 'governance');

  return (
    <FundamentalModulePage title="Governance" description="Promoter holding, pledge risk, auditor flags, RPT flags, and management quality in a red/yellow/green view.">
      <FundamentalCardGrid cards={governanceCards} />
      <PromoterPledgeTable />
      <ShareholdingTable />
    </FundamentalModulePage>
  );
}
