import { useEffect, useState } from 'react';
import { CommandPalette } from './components/app/CommandPalette';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { ErrorBoundary } from './components/ErrorBoundary';
import { PageShell } from './components/app/PageShell';
import { Sidebar } from './components/app/Sidebar';
import { TopBar } from './components/app/TopBar';
import { CvingLegacyHeader } from './components/navigation/CvingLegacyHeader';
import { SparkIcon } from './components/ui/Icons';
import { Toast } from './components/ui/Toast';
import { NseJobGlobalPoller } from './components/app/NseJobGlobalPoller';
import ChartPage from './pages/ChartPage';
import { FundamentalLayout } from './components/fundamental/layout/FundamentalLayout';
import { FundamentalAutoIngestion } from './pages/fundamental/FundamentalAutoIngestion';
import { FundamentalBalanceSheet } from './pages/fundamental/FundamentalBalanceSheet';
import { FundamentalCashFlow } from './pages/fundamental/FundamentalCashFlow';
import { FundamentalCompany360 } from './pages/fundamental/FundamentalCompany360';
import { FundamentalDashboard } from './pages/fundamental/FundamentalDashboard';
import { FundamentalFinancials } from './pages/fundamental/FundamentalFinancials';
import { FundamentalGovernance } from './pages/fundamental/FundamentalGovernance';
import { FundamentalGrowth } from './pages/fundamental/FundamentalGrowth';
import { FundamentalInvestmentThesis } from './pages/fundamental/FundamentalInvestmentThesis';
import { FundamentalPeerComparison } from './pages/fundamental/FundamentalPeerComparison';
import { FundamentalProfitLoss } from './pages/fundamental/FundamentalProfitLoss';
import { FundamentalRatios } from './pages/fundamental/FundamentalRatios';
import { FundamentalReports } from './pages/fundamental/FundamentalReports';
import { FundamentalRiskMatrix } from './pages/fundamental/FundamentalRiskMatrix';
import { FundamentalValuation } from './pages/fundamental/FundamentalValuation';
import { FyersAutomationPage } from './pages/fyers/FyersAutomationPage';
import { FyersFailedSymbolsPage } from './pages/fyers/FyersFailedSymbolsPage';
import { FyersHoldingsPage } from './pages/fyers/FyersHoldingsPage';
import { Nifty500SyncPage } from './pages/fyers/Nifty500SyncPage';
import {
  findSectorPageByPath,
} from './data/sectorNav';
import { LoginPage } from './pages/auth/LoginPage';
import { RegisterPage } from './pages/auth/RegisterPage';
import { DashboardPage } from './pages/dashboard/DashboardPage';
import { WatchlistPage } from './pages/watchlist/WatchlistPage';
import { CorporateActionsPage } from './pages/ops/CorporateActionsPage';
import { HistoricalDataPage } from './pages/ops/HistoricalDataPage';
import { NseDeliveryDataPage } from './pages/ops/NseDeliveryDataPage';
import { NseFfmcPage } from './pages/ops/NseFfmcPage';
import { NseMarketCapIndexPage } from './pages/ops/NseMarketCapIndexPage';
import { NseMarketCapPage } from './pages/ops/NseMarketCapPage';
import { ServerControlPage } from './pages/ops/ServerControlPage';
import { StockHistoryPage } from './pages/ops/StockHistoryPage';
import { SectorRotationPage } from './pages/sector/SectorRotationPage';
import { StockEdgeSectorRotationPage } from './pages/sector/StockEdgeSectorRotationPage';
import { SectorOverviewPage } from './pages/sector/SectorOverviewPage';
import { SectorStocksRedirect } from './pages/sector/SectorStocksRedirect';
import { SectorWiseStocksPage } from './pages/sector/SectorWiseStocksPage';
import { AsuraStrategyPage } from './pages/strategy/AsuraStrategyPage';
import { AsuraV3StrategyPage } from './pages/strategy/AsuraV3StrategyPage';
import { BhramhaputraStrategyPage } from './pages/strategy/BhramhaputraStrategyPage';
import { BhramhastraStrategyPage } from './pages/strategy/BhramhastraStrategyPage';
import { GangaStrategyPage } from './pages/strategy/GangaStrategyPage';
import { KaveriStrategyPage } from './pages/strategy/KaveriStrategyPage';
import { PrudviStrategyPage } from './pages/strategy/PrudviStrategyPage';
import { StrategyOverviewPage } from './pages/strategy/StrategyOverviewPage';
import { StockChartStrategyPage } from './pages/strategy/StockChartStrategyPage';
import { ThrinethraStrategyPage } from './pages/strategy/ThrinethraStrategyPage';
import { ThrisulStrategyPage } from './pages/strategy/ThrisulStrategyPage';
import { YamunaStrategyPage } from './pages/strategy/YamunaStrategyPage';
import { HomePage } from './pages/static/HomePage';
import { PortfolioPage } from './pages/static/PortfolioPage';
import { PhaseOneWorkspacePage } from './pages/phase-one/PhaseOneWorkspacePage';
import { isPhaseOnePath } from './data/phaseOneNav';
import { ADX } from './pages/technical/ADX';
import { ATR14 } from './pages/technical/ATR14';
import { Breakout } from './pages/technical/Breakout';
import { ChartPatterns } from './pages/technical/ChartPatterns';
import { Delivery } from './pages/technical/Delivery';
import { EMA } from './pages/technical/EMA';
import { MACD } from './pages/technical/MACD';
import { PriceActionAnalysis } from './pages/technical/PriceActionAnalysis';
import { PriceActionSR } from './pages/technical/PriceActionSR';
import { RSI50 } from './pages/technical/RSI50';
import { StrongTechnicals } from './pages/technical/StrongTechnicals';
import { SupportResistance } from './pages/technical/SupportResistance';
import { TrendIndicatorRedirect } from './pages/technical/TrendIndicatorRedirect';
import { Trendline } from './pages/technical/Trendline';
import { VOLUME } from './pages/technical/VOLUME';

function readCurrentLocation() {
  return {
    hash: window.location.hash,
    pathname: window.location.pathname,
    search: window.location.search,
  };
}

export function isPublicPhase4Path(pathname: string): boolean {
  const normalizedPath = pathname.toLowerCase();
  return [
    '/',
    '/app/home',
    '/home',
    '/index',
    '/app/auth/login',
    '/login',
    '/app/auth/register',
    '/register',
    '/app/database/nse-market-cap',
    '/database/nse-market-cap',
    '/nse-market-cap',
    '/nse_market_cap',
    '/app/database/nse-ffmc',
    '/database/nse-ffmc',
    '/nse-ffmc',
    '/nse_ffmc',
    '/app/database/nse-delivery-data',
    '/database/nse-delivery-data',
    '/nse-delivery-data',
    '/nse_delivery_data',
  ].includes(normalizedPath);
}

function renderFundamentalPage(pathname: string) {
  switch (pathname) {
    case '/fundamental/company-360':
      return <FundamentalCompany360 />;
    case '/fundamental/financials':
      return <FundamentalFinancials />;
    case '/fundamental/profit-loss':
      return <FundamentalProfitLoss />;
    case '/fundamental/balance-sheet':
      return <FundamentalBalanceSheet />;
    case '/fundamental/cash-flow':
      return <FundamentalCashFlow />;
    case '/fundamental/ratios':
      return <FundamentalRatios />;
    case '/fundamental/peers':
      return <FundamentalPeerComparison />;
    case '/fundamental/growth':
      return <FundamentalGrowth />;
    case '/fundamental/governance':
      return <FundamentalGovernance />;
    case '/fundamental/valuation':
      return <FundamentalValuation />;
    case '/fundamental/risk-matrix':
      return <FundamentalRiskMatrix />;
    case '/fundamental/investment-thesis':
      return <FundamentalInvestmentThesis />;
    case '/fundamental/reports':
      return <FundamentalReports />;
    case '/fundamental/auto-ingestion':
      return <FundamentalAutoIngestion />;
    case '/fundamental':
    default:
      return <FundamentalDashboard />;
  }
}

function renderPhase4Page(pathname: string) {
  const normalizedPath = pathname.toLowerCase();

  if (isPhaseOnePath(normalizedPath)) {
    return <PhaseOneWorkspacePage currentPath={normalizedPath} />;
  }

  const sectorPage = findSectorPageByPath(normalizedPath);

  if (sectorPage) {
    return <SectorWiseStocksPage sectorPage={sectorPage} />;
  }

  const dynamicSectorPath = normalizedPath.match(/^\/app\/sector\/stocks\/([a-z0-9-]+)$/);
  if (dynamicSectorPath) {
    const initialSectorCode = dynamicSectorPath[1].replace(/-/g, '_').toUpperCase();
    return <SectorWiseStocksPage dynamicMode initialSectorCode={initialSectorCode} />;
  }

  switch (normalizedPath) {
    case '/':
    case '/app/home':
    case '/home':
    case '/index':
      return <HomePage />;
    case '/app/auth/login':
    case '/login':
      return <LoginPage />;
    case '/app/auth/register':
    case '/register':
      return <RegisterPage />;
    case '/app/dashboard':
    case '/dashboard':
      return <DashboardPage />;
    case '/app/tradesetup':
    case '/tradesetup':
      return <WatchlistPage />;
    case '/app/portfolio':
    case '/portfolio':
      return <PortfolioPage />;
    case '/trendindicator':
      return <TrendIndicatorRedirect />;
    case '/app/technical/ema':
    case '/technical/ema':
    case '/ema':
      return <EMA />;
    case '/app/technical/rsi50':
    case '/technical/rsi50':
    case '/rsi50':
      return <RSI50 />;
    case '/app/technical/macd':
    case '/technical/macd':
    case '/macd':
      return <MACD />;
    case '/app/technical/atr14':
    case '/technical/atr14':
    case '/atr14':
      return <ATR14 />;
    case '/app/technical/adx':
    case '/technical/adx':
    case '/adx':
      return <ADX />;
    case '/app/technical/price-action':
    case '/technical/price-action':
    case '/price-action':
    case '/priceaction':
      return <PriceActionSR />;
    case '/app/technical/price-action-analysis':
    case '/technical/price-action-analysis':
    case '/price-action-analysis':
    case '/priceactionanalysis':
      return <PriceActionAnalysis />;
    case '/app/technical/trendline':
    case '/technical/trendline':
    case '/trendline':
      return <Trendline />;
    case '/app/technical/breakout':
    case '/technical/breakout':
    case '/breakout':
      return <Breakout />;
    case '/app/technical/chart-patterns':
    case '/technical/chart-patterns':
    case '/chart-patterns':
    case '/chartpatterns':
      return <ChartPatterns />;
    case '/app/technical/strong-technicals':
    case '/technical/strong-technicals':
    case '/strong-technicals':
    case '/strongtechnicals':
      return <StrongTechnicals />;
    case '/app/technical/support-resistance':
    case '/technical/support-resistance':
    case '/support-resistance':
    case '/sr_levels':
      return <SupportResistance />;
    case '/app/technical/volume':
    case '/technical/volume':
    case '/volume':
      return <VOLUME />;
    case '/app/technical/delivery':
    case '/technical/delivery':
    case '/delivery':
      return <Delivery />;
    case '/app/database/stock-history':
    case '/database/stock-history':
    case '/database':
      return <StockHistoryPage />;
    case '/app/database/historical-data':
    case '/database/historical-data':
    case '/historical-data':
    case '/historical_data':
      return <HistoricalDataPage />;
    case '/app/database/corporate-actions':
    case '/database/corporate-actions':
    case '/corporate-actions':
    case '/corporateactions':
      return <CorporateActionsPage />;
    case '/app/database/nse-market-cap':
    case '/database/nse-market-cap':
    case '/nse-market-cap':
    case '/nse_market_cap':
      return <NseMarketCapPage />;
    case '/app/database/nse-market-cap-index':
    case '/database/nse-market-cap-index':
    case '/nse-market-cap-index':
    case '/nse_marketcap_index':
      return <NseMarketCapIndexPage />;
    case '/app/database/nse-ffmc':
    case '/database/nse-ffmc':
    case '/nse-ffmc':
    case '/nse_ffmc':
      return <NseFfmcPage />;
    case '/app/database/nse-delivery-data':
    case '/database/nse-delivery-data':
    case '/nse-delivery-data':
    case '/nse_delivery_data':
      return <NseDeliveryDataPage />;
    case '/app/database/server':
    case '/database/server':
    case '/server':
      return <ServerControlPage />;
    case '/app/fyers/automation':
    case '/fyers/automation':
    case '/fyersapi':
      return <FyersAutomationPage />;
    case '/app/fyers/failed-symbols':
    case '/fyers/failed-symbols':
    case '/failed-symbols':
      return <FyersFailedSymbolsPage />;
    case '/app/fyers/holdings':
    case '/fyers/holdings':
    case '/holdings':
      return <FyersHoldingsPage />;
    case '/app/fyers/nifty500-sync':
    case '/fyers/nifty500-sync':
    case '/nifty500-sync':
    case '/niftyt500':
      return <Nifty500SyncPage />;
    case '/app/sector/rotation':
    case '/sector/rotation':
    case '/sectorrotation':
      return <SectorRotationPage />;
    case '/app/sector/stockedge-rotation':
    case '/sector/stockedge-rotation':
    case '/stockedge-sector-rotation':
      return <StockEdgeSectorRotationPage />;
    case '/app/sector/overview':
    case '/sector/overview':
    case '/sector-overview':
      return <SectorOverviewPage />;
    case '/app/sector/stocks':
    case '/sector/stocks':
    case '/sector-wise-stocks':
    case '/sector-wise':
      return <SectorStocksRedirect />;
    case '/app/strategy':
    case '/strategy':
      return <StrategyOverviewPage />;
    case '/app/strategy/stock-chart':
    case '/strategy/stock-chart':
    case '/stock-chart':
    case '/stockchart':
      return <StockChartStrategyPage />;
    case '/app/strategy/asura':
    case '/strategy/asura':
    case '/asura':
      return <AsuraStrategyPage />;
    case '/app/strategy/asura-v3':
    case '/strategy/asura-v3':
    case '/asura-v3':
      return <AsuraV3StrategyPage />;
    case '/app/strategy/bhramhaputra':
    case '/strategy/bhramhaputra':
    case '/bhramhaputra':
      return <BhramhaputraStrategyPage />;
    case '/app/strategy/bhramhastra':
    case '/strategy/bhramhastra':
    case '/bhramhastra':
      return <BhramhastraStrategyPage />;
    case '/app/strategy/ganga':
    case '/strategy/ganga':
    case '/ganga':
      return <GangaStrategyPage />;
    case '/kaveri':
    case '/app/strategy/kaveri':
    case '/strategy/kaveri':
      return <KaveriStrategyPage />;
    case '/prudvi':
    case '/app/strategy/prudvi':
    case '/strategy/prudvi':
      return <PrudviStrategyPage />;
    case '/thrinethra':
    case '/app/strategy/thrinethra':
    case '/strategy/thrinethra':
      return <ThrinethraStrategyPage />;
    case '/thrisul':
    case '/app/strategy/thrisul':
    case '/strategy/thrisul':
      return <ThrisulStrategyPage />;
    case '/app/strategy/yamuna':
    case '/strategy/yamuna':
    case '/yamuna':
      return <YamunaStrategyPage />;
    default:
      return null;
  }
}

export default function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [toastOpen, setToastOpen] = useState(false);
  const [currentLocation, setCurrentLocation] = useState(readCurrentLocation);
  const pathname = currentLocation.pathname;
  const pageKey = `${currentLocation.pathname}${currentLocation.search}${currentLocation.hash}`;

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setCommandOpen((current) => !current);
      }

      if (event.key === 'Escape') {
        setCommandOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    if (!toastOpen) {
      return undefined;
    }

    const timeout = window.setTimeout(() => setToastOpen(false), 2600);
    return () => window.clearTimeout(timeout);
  }, [toastOpen]);

  useEffect(() => {
    const handlePopState = () => setCurrentLocation(readCurrentLocation());
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const phase4Page = renderPhase4Page(pathname);

  if (phase4Page) {
    const content = isPublicPhase4Path(pathname)
      ? phase4Page
      : <ProtectedRoute>{phase4Page}</ProtectedRoute>;
    return (
      <ErrorBoundary page={pathname} shell={<CvingLegacyHeader activeSection="none" />}>
        <NseJobGlobalPoller />
        <div key={pageKey}>{content}</div>
      </ErrorBoundary>
    );
  }

  if (pathname.startsWith('/fundamental')) {
    return (
      <ErrorBoundary page={pathname}>
        <NseJobGlobalPoller />
        <ProtectedRoute>
          <FundamentalLayout currentPath={pathname}>
            {renderFundamentalPage(pathname)}
          </FundamentalLayout>
        </ProtectedRoute>
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary page={pathname}>
      <NseJobGlobalPoller />
      <ProtectedRoute>
      <PageShell className="page-theme--dashboard app-background min-h-screen text-text">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute left-[-14rem] top-[-10rem] h-[28rem] w-[28rem] rounded-full bg-cyan/12 blur-[140px]" />
        <div className="absolute right-[-10rem] top-[8rem] h-[22rem] w-[22rem] rounded-full bg-amber/10 blur-[130px]" />
        <div className="absolute bottom-[-12rem] left-1/2 h-[32rem] w-[32rem] -translate-x-1/2 rounded-full bg-emerald/10 blur-[180px]" />
        <div className="absolute inset-x-0 top-0 h-full bg-grid-fade opacity-40" />
      </div>

      <div className="relative mx-auto flex min-h-screen w-full max-w-[1880px] gap-4 px-4 py-4 md:px-5">
        <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed((current) => !current)} />

        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <TopBar onOpenCommand={() => setCommandOpen(true)} />
          <ChartPage onSaved={() => setToastOpen(true)} />
        </div>
      </div>

      <CommandPalette open={commandOpen} setOpen={setCommandOpen} />
      <Toast
        open={toastOpen}
        title="Workspace synced"
        description="Chart annotations were saved without changing the live market data flow."
        icon={<SparkIcon className="h-4 w-4" />}
        tone="success"
        onClose={() => setToastOpen(false)}
      />
      </PageShell>
      </ProtectedRoute>
    </ErrorBoundary>
  );
}
