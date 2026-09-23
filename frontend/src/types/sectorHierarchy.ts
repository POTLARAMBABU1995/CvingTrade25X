export interface SectorHierarchyParent {
  parentSector: string;
  stockCount: number;
}

export interface SectorHierarchyIndustry {
  parentSector: string;
  industrySector: string;
  stockCount: number;
}

export interface SectorHierarchySubSector {
  parentSector: string;
  industrySector: string;
  subSector: string;
  stockCount: number;
}

export interface SectorHierarchyStock {
  parentSector?: string | null;
  industrySector?: string | null;
  subSector?: string | null;
  index?: string | null;
  mcap?: number | null;
  mcapRank?: number | null;
  symbol: string;
  exchange: string;
}

export interface SectorHierarchyStocksPayload {
  parentSector?: string | null;
  industrySector?: string | null;
  subSector?: string | null;
  totalStocks: number;
  stocks: SectorHierarchyStock[];
}

export interface SectorHierarchySummary {
  parentSector: string;
  totalStocks: number;
  industries: Array<{
    industrySector: string;
    stockCount: number;
    subSectors: Array<{
      subSector: string;
      stockCount: number;
    }>;
  }>;
}

export interface SectorHierarchyTree {
  parentSector: string;
  totalStocks: number;
  industries: Array<{
    industrySector: string;
    stockCount: number;
    subSectors: Array<{
      subSector: string;
      stockCount: number;
      stocks: Array<{
        symbol: string;
        exchange: string;
      }>;
    }>;
  }>;
}

export interface SectorHierarchyMetadata {
  cacheKey: string;
  cached: boolean;
  generatedAt: string;
  totalParents?: number;
}

export interface SectorHierarchyApiResponse<TData> {
  success: boolean;
  data: TData;
  metadata?: SectorHierarchyMetadata;
  message?: string;
  errorCode?: string;
}
