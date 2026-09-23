import { STOCKEDGE_SECTOR_ROTATION_PAGE } from '../../data/sectorNav';
import { SectorRotationPage } from './SectorRotationPage';

export function StockEdgeSectorRotationPage() {
  return (
    <SectorRotationPage
      activeSectorPage={STOCKEDGE_SECTOR_ROTATION_PAGE}
      experience="stockedge"
    />
  );
}
