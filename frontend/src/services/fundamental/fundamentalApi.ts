import { legacyApiGet } from '../../api/client';
import { normalizeSymbol } from './fundamentalFormatters';
import type { FundamentalCard, FundamentalMetricRow, FundamentalPeerRow, FundamentalSummary } from './fundamentalTypes';

type CardInput = Omit<FundamentalCard, 'key'> & { key: string };

const mockCard = (card: CardInput): FundamentalCard => card;
const liveFundamentalApiEnabled = import.meta.env.VITE_FUNDAMENTAL_API_ENABLED === 'true';

const today = () => new Date().toISOString().slice(0, 10);

export function getMockFundamentalSummary(symbolInput = 'RELIANCE'): FundamentalSummary {
  const symbol = normalizeSymbol(symbolInput) || 'RELIANCE';

  return {
    symbol,
    companyName: symbol === 'RELIANCE' ? 'Reliance Industries' : `${symbol} Limited`,
    exchange: 'NSE',
    sector: symbol === 'RELIANCE' ? 'Refineries & Marketing' : 'Nifty 500',
    marketCap: 'Rs. 19,85,420 Cr',
    currentPrice: 'Rs. 2,948.55',
    overallScore: 82,
    overallStatus: 'Good Fundamental',
    lastUpdated: today(),
    cards: [
      mockCard({
        key: 'overall_score',
        title: 'Overall Fundamental Score',
        value: '82/100',
        numericValue: 82,
        status: 'GOOD',
        color: 'green',
        description: 'Quality, growth, cash flow, and governance are above the watch threshold.',
        trend: 'up',
        tooltip: 'Score >= 70 maps to Good Fundamental. Score >= 85 maps to Strong Fundamental.',
        section: 'overall',
      }),
      mockCard({
        key: 'growth_strength',
        title: 'Growth Strength',
        value: 'Strong',
        numericValue: 78,
        status: 'GOOD',
        color: 'green',
        description: 'Sales and profit growth are above the deterministic threshold.',
        trend: 'up',
        tooltip: 'Based on 3Y/5Y sales CAGR and profit CAGR.',
        section: 'growth',
      }),
      mockCard({
        key: 'future_growth',
        title: 'Future Growth Visibility',
        value: 'Visible',
        numericValue: 76,
        status: 'GOOD',
        color: 'green',
        description: 'Expansion visibility, stable margin, and sector tailwinds support the future view.',
        trend: 'up',
        tooltip: 'Positive sales/profit growth, capex visibility, sector tailwind, and stable margin.',
        section: 'growth',
      }),
      mockCard({
        key: 'profit_loss_strength',
        title: 'Profit & Loss Strength',
        value: 'Strong P&L',
        numericValue: 81,
        status: 'GOOD',
        color: 'green',
        description: 'Operating margin and EPS trend remain healthy.',
        trend: 'up',
        tooltip: 'Strong when OPM is stable/increasing and net profit plus EPS are growing.',
        section: 'profit_loss',
      }),
      mockCard({
        key: 'cash_flow_strength',
        title: 'Cash Flow Strength',
        value: '88/100',
        numericValue: 88,
        status: 'EXCELLENT',
        color: 'green',
        description: 'CFO is positive, FCF is positive, and CFO/PAT is above 0.8.',
        trend: 'up',
        tooltip: 'Strong when CFO is positive, CFO/PAT >= 0.8, and free cash flow is positive.',
        section: 'cash_flow',
      }),
      mockCard({
        key: 'balance_sheet_strength',
        title: 'Balance Sheet Strength',
        value: 'Strong',
        numericValue: 84,
        status: 'GOOD',
        color: 'green',
        description: 'Debt/equity and interest coverage are inside safe bands.',
        trend: 'flat',
        tooltip: 'Strong when Debt/Equity <= 0.5, Interest Coverage >= 5, and Current Ratio >= 1.2.',
        section: 'balance_sheet',
      }),
      mockCard({
        key: 'peer_strength',
        title: 'Peer Strength',
        value: 'Top Quartile',
        numericValue: 74,
        status: 'GOOD',
        color: 'green',
        description: 'ROCE and scale are ahead of sector median.',
        trend: 'up',
        tooltip: 'Compares ROCE, sales growth, profit growth, margin, and valuation against peer median.',
        section: 'peers',
      }),
      mockCard({
        key: 'qoq_strength',
        title: 'Quarter-on-Quarter Result Strength',
        value: 'Mixed QoQ',
        numericValue: 58,
        status: 'WATCH',
        color: 'amber',
        description: 'Sales improved, but profit growth needs confirmation next quarter.',
        trend: 'flat',
        tooltip: 'Strong QoQ requires both QoQ sales growth and QoQ profit growth to be positive.',
        section: 'growth',
      }),
      mockCard({
        key: 'yoy_strength',
        title: 'Year-on-Year Result Strength',
        value: 'Strong YoY',
        numericValue: 79,
        status: 'GOOD',
        color: 'green',
        description: 'YoY sales and profit growth are both above 8%.',
        trend: 'up',
        tooltip: 'Strong YoY requires YoY sales growth > 8 and YoY profit growth > 8.',
        section: 'growth',
      }),
      mockCard({
        key: 'promoter_pledge',
        title: 'Promoter Pledge Risk',
        value: '0%',
        numericValue: 0,
        status: 'EXCELLENT',
        color: 'green',
        description: 'No promoter pledge detected.',
        trend: 'flat',
        tooltip: '0 pledge is Excellent. >5% is Risk and >20% is High Risk / Weak.',
        section: 'governance',
      }),
      mockCard({
        key: 'governance_quality',
        title: 'Governance Quality',
        value: 'Strong',
        numericValue: 86,
        status: 'EXCELLENT',
        color: 'green',
        description: 'No pledge, no auditor flag, and promoter holding is stable.',
        trend: 'up',
        tooltip: 'Strong governance requires no pledge, no auditor red flags, and stable/increasing promoter holding.',
        section: 'governance',
      }),
      mockCard({
        key: 'debt_risk',
        title: 'Debt Risk',
        value: 'Low',
        numericValue: 18,
        status: 'GOOD',
        color: 'green',
        description: 'Debt ratios are manageable against earnings and cash flow.',
        trend: 'down',
        tooltip: 'Weak when Debt/Equity > 1.5 or Interest Coverage < 2.',
        section: 'risk',
      }),
      mockCard({
        key: 'valuation_comfort',
        title: 'Valuation Comfort',
        value: 'Fair',
        numericValue: 61,
        status: 'AVERAGE',
        color: 'amber',
        description: 'Valuation is near sector median; not cheap but supported by quality.',
        trend: 'flat',
        tooltip: 'Attractive when PE is below sector median and growth is strong.',
        section: 'valuation',
      }),
      mockCard({
        key: 'dividend_payout',
        title: 'Dividend Payout %',
        value: '38%',
        numericValue: 38,
        status: 'GOOD',
        color: 'green',
        description: 'Payout is healthy and supported by free cash flow.',
        trend: 'flat',
        tooltip: 'Healthy when payout is between 10% and 60% with positive FCF.',
        section: 'dividend',
      }),
      mockCard({
        key: 'roe_strength',
        title: 'ROE Strength',
        value: '16.8%',
        numericValue: 16.8,
        status: 'GOOD',
        color: 'green',
        description: 'Return on equity remains comfortably above market average.',
        trend: 'up',
        tooltip: 'Higher and stable ROE improves return-ratio strength.',
        section: 'returns',
      }),
      mockCard({
        key: 'roce_strength',
        title: 'ROCE Strength',
        value: '18.4%',
        numericValue: 18.4,
        status: 'GOOD',
        color: 'green',
        description: 'Capital efficiency is ahead of peer median.',
        trend: 'up',
        tooltip: 'ROCE is compared with sector median and trend stability.',
        section: 'returns',
      }),
      mockCard({
        key: 'margin_strength',
        title: 'Margin Strength',
        value: 'Stable',
        numericValue: 72,
        status: 'GOOD',
        color: 'green',
        description: 'OPM trend is stable with no sharp margin decline.',
        trend: 'flat',
        tooltip: 'Margin weakness is flagged when OPM or net margin falls persistently.',
        section: 'profit_loss',
      }),
      mockCard({
        key: 'sales_growth',
        title: 'Sales Growth',
        value: '11.6%',
        numericValue: 11.6,
        status: 'GOOD',
        color: 'green',
        description: 'Sales CAGR is close to strong-growth territory.',
        trend: 'up',
        tooltip: 'Growth bands use 3Y and 5Y CAGR, with 12% as the strong threshold.',
        section: 'growth',
      }),
      mockCard({
        key: 'profit_growth',
        title: 'Profit Growth',
        value: '13.2%',
        numericValue: 13.2,
        status: 'EXCELLENT',
        color: 'green',
        description: 'Profit CAGR is above the strong-growth threshold.',
        trend: 'up',
        tooltip: 'Profit CAGR >= 12% supports Strong Growth.',
        section: 'growth',
      }),
      mockCard({
        key: 'free_cash_flow',
        title: 'Free Cash Flow Strength',
        value: 'Positive',
        numericValue: 82,
        status: 'GOOD',
        color: 'green',
        description: 'Free cash flow is positive after capex.',
        trend: 'up',
        tooltip: 'Positive and improving FCF strengthens cash-flow quality.',
        section: 'cash_flow',
      }),
      mockCard({
        key: 'earnings_quality',
        title: 'Earnings Quality',
        value: 'High',
        numericValue: 83,
        status: 'GOOD',
        color: 'green',
        description: 'Cash conversion supports reported profits.',
        trend: 'up',
        tooltip: 'Earnings quality uses CFO/PAT, FCF, margin stability, and one-off income checks.',
        section: 'profit_loss',
      }),
      mockCard({
        key: 'moat_strength',
        title: 'Moat Strength',
        value: 'Strong',
        numericValue: 80,
        status: 'GOOD',
        color: 'green',
        description: 'Scale, sector position, and returns support competitive strength.',
        trend: 'up',
        tooltip: 'Moat is a deterministic placeholder in Phase 1 and will later use peer-relative metrics.',
        section: 'peers',
      }),
      mockCard({
        key: 'management_quality',
        title: 'Management Quality',
        value: 'Strong',
        numericValue: 84,
        status: 'GOOD',
        color: 'green',
        description: 'Governance inputs are clean in the current snapshot.',
        trend: 'flat',
        tooltip: 'Uses promoter trend, pledge, auditor flags, and related-party flags.',
        section: 'governance',
      }),
      mockCard({
        key: 'risk_matrix',
        title: 'Risk Matrix',
        value: 'Controlled',
        numericValue: 28,
        status: 'GOOD',
        color: 'green',
        description: 'No high-severity balance sheet, pledge, or cash-flow alert is active.',
        trend: 'down',
        tooltip: 'Combines debt, pledge, falling sales/profit, negative cash flow, valuation, margin, and governance risks.',
        section: 'risk',
      }),
    ],
  };
}

export async function fetchFundamentalCards(symbol: string, signal?: AbortSignal): Promise<FundamentalSummary> {
  const normalized = normalizeSymbol(symbol) || 'RELIANCE';
  if (!liveFundamentalApiEnabled) {
    return getMockFundamentalSummary(normalized);
  }

  try {
    const response = await legacyApiGet<FundamentalSummary>(`/api/fundamental/cards/${normalized}`, undefined, {
      signal,
      timeoutMs: 3000,
    });
    if (response?.cards?.length) {
      return response;
    }
  } catch {
    // Phase 1 intentionally falls back to deterministic mock data until the isolated backend endpoints are added.
  }
  return getMockFundamentalSummary(normalized);
}

export const FINANCIAL_YEARS = ['Mar 2022', 'Mar 2023', 'Mar 2024', 'Mar 2025', 'TTM'];

export const PROFIT_LOSS_ROWS: FundamentalMetricRow[] = [
  { metric: 'Sales', values: { 'Mar 2022': '699,962', 'Mar 2023': '876,396', 'Mar 2024': '917,308', 'Mar 2025': '956,114', TTM: '982,441' }, emphasis: true },
  { metric: 'Expenses', values: { 'Mar 2022': '604,391', 'Mar 2023': '770,142', 'Mar 2024': '801,982', 'Mar 2025': '832,404', TTM: '852,114' } },
  { metric: 'Operating Profit', values: { 'Mar 2022': '95,571', 'Mar 2023': '106,254', 'Mar 2024': '115,326', 'Mar 2025': '123,710', TTM: '130,327' }, emphasis: true },
  { metric: 'OPM %', values: { 'Mar 2022': '13.7%', 'Mar 2023': '12.1%', 'Mar 2024': '12.6%', 'Mar 2025': '12.9%', TTM: '13.3%' }, emphasis: true },
  { metric: 'Other Income', values: { 'Mar 2022': '18,421', 'Mar 2023': '16,938', 'Mar 2024': '19,102', 'Mar 2025': '20,441', TTM: '21,012' } },
  { metric: 'Interest', values: { 'Mar 2022': '19,571', 'Mar 2023': '21,189', 'Mar 2024': '22,013', 'Mar 2025': '21,742', TTM: '21,088' } },
  { metric: 'Depreciation', values: { 'Mar 2022': '29,782', 'Mar 2023': '34,224', 'Mar 2024': '36,617', 'Mar 2025': '38,140', TTM: '39,004' } },
  { metric: 'Profit Before Tax', values: { 'Mar 2022': '64,639', 'Mar 2023': '67,779', 'Mar 2024': '75,798', 'Mar 2025': '84,269', TTM: '91,247' }, emphasis: true },
  { metric: 'Tax %', values: { 'Mar 2022': '24%', 'Mar 2023': '25%', 'Mar 2024': '24%', 'Mar 2025': '24%', TTM: '24%' } },
  { metric: 'Net Profit', values: { 'Mar 2022': '49,128', 'Mar 2023': '50,951', 'Mar 2024': '57,084', 'Mar 2025': '64,044', TTM: '69,348' }, emphasis: true },
  { metric: 'EPS', values: { 'Mar 2022': '72.6', 'Mar 2023': '75.3', 'Mar 2024': '84.2', 'Mar 2025': '94.5', TTM: '102.3' }, emphasis: true },
];

export const BALANCE_SHEET_ROWS: FundamentalMetricRow[] = [
  { metric: 'Total Assets', values: { 'Mar 2022': '1,492,821', 'Mar 2023': '1,635,021', 'Mar 2024': '1,766,224', 'Mar 2025': '1,842,556', TTM: '1,884,200' }, emphasis: true },
  { metric: 'Total Liabilities', values: { 'Mar 2022': '742,420', 'Mar 2023': '795,228', 'Mar 2024': '834,191', 'Mar 2025': '851,012', TTM: '862,440' } },
  { metric: 'Net Worth', values: { 'Mar 2022': '750,401', 'Mar 2023': '839,793', 'Mar 2024': '932,033', 'Mar 2025': '991,544', TTM: '1,021,760' }, emphasis: true },
  { metric: 'Debt', values: { 'Mar 2022': '266,305', 'Mar 2023': '287,212', 'Mar 2024': '291,334', 'Mar 2025': '282,211', TTM: '276,944' } },
  { metric: 'Debt/Equity', values: { 'Mar 2022': '0.35', 'Mar 2023': '0.34', 'Mar 2024': '0.31', 'Mar 2025': '0.28', TTM: '0.27' }, emphasis: true },
  { metric: 'Current Ratio', values: { 'Mar 2022': '1.22', 'Mar 2023': '1.26', 'Mar 2024': '1.28', 'Mar 2025': '1.31', TTM: '1.32' } },
  { metric: 'Interest Coverage', values: { 'Mar 2022': '4.9x', 'Mar 2023': '5.0x', 'Mar 2024': '5.2x', 'Mar 2025': '5.7x', TTM: '6.2x' }, emphasis: true },
];

export const CASH_FLOW_ROWS: FundamentalMetricRow[] = [
  { metric: 'CFO', values: { 'Mar 2022': '89,214', 'Mar 2023': '96,331', 'Mar 2024': '102,918', 'Mar 2025': '112,410', TTM: '118,772' }, emphasis: true },
  { metric: 'CFO/PAT', values: { 'Mar 2022': '1.82', 'Mar 2023': '1.89', 'Mar 2024': '1.80', 'Mar 2025': '1.75', TTM: '1.71' }, emphasis: true },
  { metric: 'Free Cash Flow', values: { 'Mar 2022': '24,108', 'Mar 2023': '29,414', 'Mar 2024': '32,707', 'Mar 2025': '38,204', TTM: '41,533' }, emphasis: true },
  { metric: 'FCF Margin', values: { 'Mar 2022': '3.4%', 'Mar 2023': '3.4%', 'Mar 2024': '3.6%', 'Mar 2025': '4.0%', TTM: '4.2%' } },
  { metric: 'Capex Trend', values: { 'Mar 2022': '65,106', 'Mar 2023': '66,917', 'Mar 2024': '70,211', 'Mar 2025': '74,206', TTM: '77,239' } },
];

export const RATIO_ROWS: FundamentalMetricRow[] = [
  { metric: 'ROE %', values: { 'Mar 2022': '15.9%', 'Mar 2023': '15.1%', 'Mar 2024': '15.8%', 'Mar 2025': '16.5%', TTM: '16.8%' }, emphasis: true },
  { metric: 'ROCE %', values: { 'Mar 2022': '16.4%', 'Mar 2023': '16.9%', 'Mar 2024': '17.2%', 'Mar 2025': '18.0%', TTM: '18.4%' }, emphasis: true },
  { metric: 'ROA %', values: { 'Mar 2022': '4.1%', 'Mar 2023': '4.0%', 'Mar 2024': '4.3%', 'Mar 2025': '4.6%', TTM: '4.8%' } },
  { metric: 'Asset Turnover', values: { 'Mar 2022': '0.47x', 'Mar 2023': '0.54x', 'Mar 2024': '0.52x', 'Mar 2025': '0.52x', TTM: '0.52x' } },
];

export const QUARTERLY_RESULTS_ROWS: FundamentalMetricRow[] = [
  { metric: 'Sales', values: { 'Dec 2024': '234,991', 'Mar 2025': '241,144', 'Jun 2025': '246,930', 'Sep 2025': '250,612', 'Dec 2025': '258,764' }, emphasis: true },
  { metric: 'Operating Profit', values: { 'Dec 2024': '30,224', 'Mar 2025': '31,106', 'Jun 2025': '32,014', 'Sep 2025': '32,788', 'Dec 2025': '34,002' }, emphasis: true },
  { metric: 'Net Profit', values: { 'Dec 2024': '15,204', 'Mar 2025': '16,108', 'Jun 2025': '16,844', 'Sep 2025': '17,214', 'Dec 2025': '18,004' }, emphasis: true },
  { metric: 'QoQ Profit Growth', values: { 'Dec 2024': '3.2%', 'Mar 2025': '5.9%', 'Jun 2025': '4.6%', 'Sep 2025': '2.2%', 'Dec 2025': '4.6%' } },
];

export const YEARLY_RESULTS_ROWS = PROFIT_LOSS_ROWS;

export const SHAREHOLDING_ROWS: FundamentalMetricRow[] = [
  { metric: 'Promoter Holding', values: { 'Mar 2022': '50.6%', 'Mar 2023': '50.4%', 'Mar 2024': '50.3%', 'Mar 2025': '50.3%', TTM: '50.3%' }, emphasis: true },
  { metric: 'Promoter Pledge', values: { 'Mar 2022': '0%', 'Mar 2023': '0%', 'Mar 2024': '0%', 'Mar 2025': '0%', TTM: '0%' }, emphasis: true },
  { metric: 'FII Holding', values: { 'Mar 2022': '23.2%', 'Mar 2023': '22.5%', 'Mar 2024': '22.1%', 'Mar 2025': '21.9%', TTM: '22.0%' } },
  { metric: 'DII Holding', values: { 'Mar 2022': '14.4%', 'Mar 2023': '15.8%', 'Mar 2024': '16.3%', 'Mar 2025': '16.8%', TTM: '17.1%' } },
  { metric: 'Public Holding', values: { 'Mar 2022': '11.8%', 'Mar 2023': '11.3%', 'Mar 2024': '11.3%', 'Mar 2025': '11.0%', TTM: '10.6%' } },
];

export const PROMOTER_PLEDGE_ROWS = SHAREHOLDING_ROWS.filter((row) => row.metric.includes('Promoter'));

export const PEER_ROWS: FundamentalPeerRow[] = [
  { rank: 1, name: 'Reliance Industries', cmp: '2,948.55', pe: '27.8', marketCap: '19,85,420', dividendYield: '0.34%', netProfitQtr: '18,004', qtrProfitVar: '18.4%', salesQtr: '258,764', qtrSalesVar: '9.8%', roce: '18.4%', selected: true },
  { rank: 2, name: 'Indian Oil Corporation', cmp: '168.20', pe: '8.9', marketCap: '237,402', dividendYield: '3.1%', netProfitQtr: '7,188', qtrProfitVar: '7.2%', salesQtr: '202,110', qtrSalesVar: '4.4%', roce: '15.1%' },
  { rank: 3, name: 'Bharat Petroleum', cmp: '612.35', pe: '9.7', marketCap: '132,702', dividendYield: '2.7%', netProfitQtr: '4,812', qtrProfitVar: '6.8%', salesQtr: '118,622', qtrSalesVar: '3.9%', roce: '14.3%' },
  { rank: 4, name: 'Hindustan Petroleum', cmp: '487.90', pe: '10.4', marketCap: '103,891', dividendYield: '2.4%', netProfitQtr: '3,921', qtrProfitVar: '5.5%', salesQtr: '109,312', qtrSalesVar: '3.4%', roce: '13.8%' },
  { rank: 'Median', name: 'Sector Median', cmp: '-', pe: '10.4', marketCap: '132,702', dividendYield: '2.6%', netProfitQtr: '4,812', qtrProfitVar: '6.8%', salesQtr: '118,622', qtrSalesVar: '4.4%', roce: '14.3%', median: true },
];
