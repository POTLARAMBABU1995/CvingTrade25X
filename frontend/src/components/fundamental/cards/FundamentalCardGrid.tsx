import { FundamentalScoreCard } from './FundamentalScoreCard';
import type { FundamentalCard } from '../../../services/fundamental/fundamentalTypes';

type FundamentalCardGridProps = {
  cards: FundamentalCard[];
};

export function FundamentalCardGrid({ cards }: FundamentalCardGridProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {cards.map((card) => (
        <FundamentalScoreCard key={card.key} card={card} compact />
      ))}
    </div>
  );
}
