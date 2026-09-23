import { PeerComparisonChart } from '../../components/fundamental/charts/PeerComparisonChart';
import { PeerComparisonTable } from '../../components/fundamental/tables/PeerComparisonTable';
import { FundamentalModulePage } from './FundamentalModulePage';

export function FundamentalPeerComparison() {
  return (
    <FundamentalModulePage title="Peer Comparison" description="Peer rank, sector median comparison, valuation, quarterly growth, and ROCE in one premium table.">
      <PeerComparisonChart />
      <PeerComparisonTable />
    </FundamentalModulePage>
  );
}
