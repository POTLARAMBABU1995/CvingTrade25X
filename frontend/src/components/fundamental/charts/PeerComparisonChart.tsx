import { MiniTrendChart } from './MiniTrendChart';

export function PeerComparisonChart() {
  return <MiniTrendChart title="Peer Median Comparison" values={[50, 55, 61, 67, 72, 77, 82]} color="#111827" />;
}
