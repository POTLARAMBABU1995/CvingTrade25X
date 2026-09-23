export type NseAutomationCellFormat = 'count' | 'date' | 'dateOnly' | 'flag' | 'number' | 'source' | 'text';

export type NseAutomationColumnConfig = {
  aliases: readonly string[];
  format: NseAutomationCellFormat;
  key: string;
  label: string;
};

export type NseAutomationKpiConfig = {
  aliases: readonly string[] | 'tradeDate';
  format: NseAutomationCellFormat;
  label: string;
  source?: 'data' | 'summary';
};

export type NseAutomationPageConfig = {
  activeDatabasePage: string;
  copy: string;
  endpointBase: string;
  fullRunEndpoint?: string;
  heading: string;
  kpis: readonly NseAutomationKpiConfig[];
  processExistingEndpoint?: string;
  rowColumns: readonly NseAutomationColumnConfig[];
  tableTitle: string;
  verificationPage: 'DELIVERY' | 'FFMC' | 'MARKET_CAP';
};

const commonKpis = [
  { label: 'Trade Date', aliases: 'tradeDate', format: 'dateOnly' },
  { label: 'Success Rows', aliases: ['successRows', 'success_rows'], format: 'count' },
  { label: 'Manual Rows', aliases: ['manualRows', 'manual_rows'], format: 'flag' },
  { label: 'Automation Rows', aliases: ['automationRows', 'automation_rows'], format: 'flag' },
  { label: 'Inserted Rows', aliases: ['insertedRows', 'inserted_rows', 'successRows'], format: 'count' },
  { label: 'Failure Rows', aliases: ['failureRows', 'failure_rows'], format: 'count' },
  { label: 'Skipped Rows', aliases: ['skippedRows', 'skipped_rows'], format: 'count' },
] satisfies readonly NseAutomationKpiConfig[];

const commonColumns = [
  { key: 'symbol', label: 'Symbol', aliases: ['symbol', 'SYMBOL', 'script', 'SCRIPT'], format: 'text' },
  { key: 'status', label: 'Status', aliases: ['status', 'STATUS', 'fetch_status', 'fetchStatus', 'FETCH_STATUS'], format: 'text' },
] satisfies readonly NseAutomationColumnConfig[];

const commonDateColumns = [
  { key: 'fetched', label: 'Trade Date', aliases: ['trade_date', 'TRADE_DATE', 'tradeDate', 'fetched_timestamp', 'fetchedTimestamp', 'fetch_ts'], format: 'dateOnly' },
  { key: 'insertion', label: 'Insertion', aliases: ['insertion_source', 'insertionSource', 'source_name', 'sourceName', 'source'], format: 'source' },
  { key: 'insertedRows', label: 'Inserted Rows', aliases: ['inserted_rows', 'insertedRows', 'inserted_count', 'insertedCount', 'success_rows', 'successRows'], format: 'count' },
] satisfies readonly NseAutomationColumnConfig[];

export const NSE_AUTOMATION_PAGE_CONFIGS = {
  marketCap: {
    activeDatabasePage: '/app/database/nse-market-cap',
    copy: 'Download the official NSE PR archive, extract the MCAP CSV, load only NIFTY500-matched symbols into Oracle, and track every stage from the UI.',
    endpointBase: '/api/marketdata/nse-mcap',
    fullRunEndpoint: '/api/marketdata/nse-mcap/pipeline/start',
    heading: 'NSE Market Cap',
    kpis: [
      ...commonKpis,
      { label: 'Total MCAP in Crores', aliases: ['totalMcapCrSum', 'total_mcap_cr_sum'], format: 'number' },
      { label: 'File Rows', aliases: ['fileRows', 'file_rows'], format: 'count' },
      { label: 'Quote Rows', aliases: ['quoteRows', 'quote_rows'], format: 'count' },
    ],
    rowColumns: [
      ...commonColumns,
      { key: 'totalMcap', label: 'Total MCAP (Cr)', aliases: ['total_mcap_cr', 'totalMcapCr', 'market_cap_cr', 'market_cap_crores', 'marketCapCrores'], format: 'number' },
      ...commonDateColumns,
      { key: 'source', label: 'Source', aliases: ['source_name', 'source', 'sourceName', 'file_source'], format: 'text' },
    ],
    processExistingEndpoint: '/api/marketdata/nse-mcap/process-existing-csv-symbols',
    tableTitle: 'Latest Rows',
    verificationPage: 'MARKET_CAP',
  },
  ffmc: {
    activeDatabasePage: '/app/database/nse-ffmc',
    copy: 'Load the local NIFTY500 universe, enrich free-float market cap from the verified NSE quote source, and track the full run from the UI.',
    endpointBase: '/api/marketdata/nse-ffmc',
    fullRunEndpoint: '/api/marketdata/nse-ffmc/pipeline/start',
    heading: 'NSE FFMC',
    kpis: [
      ...commonKpis,
      { label: 'Total FFMC in Crores', aliases: ['ffmcCrSum', 'ffmc_cr_sum', 'totalMcapCrSum'], format: 'number' },
    ],
    rowColumns: [
      ...commonColumns,
      { key: 'ffmc', label: 'FFMC (Cr)', aliases: ['ffmc_cr', 'ffmcCr', 'total_mcap_cr'], format: 'number' },
      ...commonDateColumns,
    ],
    processExistingEndpoint: '/api/marketdata/nse-ffmc/process-existing-csv-symbols',
    tableTitle: 'Latest Rows',
    verificationPage: 'FFMC',
  },
  delivery: {
    activeDatabasePage: '/app/database/nse-delivery-data',
    copy: 'Download the official NSE security deliverable file, extract and validate the CSV, load only NIFTY500-matched symbols into Oracle, and track the full delivery-data pipeline from the UI.',
    endpointBase: '/api/marketdata/nse-delivery',
    fullRunEndpoint: '/api/marketdata/nse-delivery/pipeline/start',
    heading: 'NSE Delivery Data',
    kpis: [
      ...commonKpis,
      { label: 'Delivery Rows', aliases: ['deliveryRows', 'delivery_rows'], format: 'count' },
      { label: 'Loaded Rows', aliases: ['totalRows', 'total_rows'], format: 'count' },
      { label: 'Avg Delivery %', aliases: ['deliveryPctAvg', 'delivery_pct_avg'], format: 'number' },
    ],
    rowColumns: [
      ...commonColumns,
      { key: 'deliveryQty', label: 'Delivery Qty', aliases: ['delivery_qty', 'deliveryQty', 'delivery_quantity'], format: 'count' },
      ...commonDateColumns,
      { key: 'series', label: 'Series', aliases: ['series', 'SERIES'], format: 'text' },
      { key: 'close', label: 'Close', aliases: ['close_price', 'closePrice', 'close'], format: 'number' },
      { key: 'deliveryPct', label: 'Delivery %', aliases: ['delivery_pct', 'deliveryPct'], format: 'number' },
      { key: 'tradedQty', label: 'Traded Qty', aliases: ['traded_qty', 'tradedQty'], format: 'count' },
    ],
    processExistingEndpoint: '/api/marketdata/nse-delivery/process-existing-csv-symbols',
    tableTitle: 'Latest Rows',
    verificationPage: 'DELIVERY',
  },
} satisfies Record<'delivery' | 'ffmc' | 'marketCap', NseAutomationPageConfig>;
