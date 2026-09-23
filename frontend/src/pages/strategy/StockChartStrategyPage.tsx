import { StrategyMigrationLayout } from './StrategyMigrationLayout';
import { StockChartPage } from './stock-chart/StockChartPage';

export function StockChartStrategyPage() {
  return (
    <StrategyMigrationLayout activeStrategyPage="/app/strategy/stock-chart" fullWidth>
      <StockChartPage />
    </StrategyMigrationLayout>
  );
}
