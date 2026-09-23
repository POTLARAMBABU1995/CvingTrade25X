import { useEffect } from 'react';
import { SectorMigrationLayout } from './SectorMigrationLayout';
import { navigateToInternalRoute } from '../../utils/internalNavigation';

export function SectorStocksRedirect() {
  useEffect(() => {
    const target = `/app/sector/stocks/auto${window.location.search || ''}${window.location.hash || ''}`;
    navigateToInternalRoute(target);
  }, []);

  return (
    <SectorMigrationLayout activeSectorPage="/app/sector/stocks/auto" className="sector-wise-react-page">
      <div className="sector-compact-page-header">
        <h1 className="sector-compact-page-title">Redirecting to Sector Wise Stocks</h1>
      </div>
      <p className="sector-rotation-page-meta">Opening the default Sector Wise Stocks page...</p>
    </SectorMigrationLayout>
  );
}
