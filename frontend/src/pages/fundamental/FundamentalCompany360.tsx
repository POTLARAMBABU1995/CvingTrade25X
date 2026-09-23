import { useMemo, useState } from 'react';
import { FundamentalCardGrid } from '../../components/fundamental/cards/FundamentalCardGrid';
import { BalanceSheetTable } from '../../components/fundamental/tables/BalanceSheetTable';
import { CashFlowTable } from '../../components/fundamental/tables/CashFlowTable';
import { PeerComparisonTable } from '../../components/fundamental/tables/PeerComparisonTable';
import { ProfitLossTable } from '../../components/fundamental/tables/ProfitLossTable';
import { RatioTable } from '../../components/fundamental/tables/RatioTable';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/Tabs';
import { getMockFundamentalSummary } from '../../services/fundamental/fundamentalApi';
import type { FundamentalCard } from '../../services/fundamental/fundamentalTypes';
import { FundamentalModulePage } from './FundamentalModulePage';

const tabs = ['Overview', 'P&L', 'Balance Sheet', 'Cash Flow', 'Ratios', 'Growth', 'Peers', 'Governance', 'Valuation', 'Risk Matrix', 'Investment Thesis'] as const;

export function FundamentalCompany360() {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>('Overview');
  const summary = useMemo(() => getMockFundamentalSummary('RELIANCE'), []);
  const cardsBySection = (section: FundamentalCard['section']) => summary.cards.filter((card) => card.section === section);

  return (
    <FundamentalModulePage
      title="Company 360"
      description="A tabbed company view that keeps the first implementation isolated while matching the future route structure."
    >
      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as (typeof tabs)[number])}>
        <TabsList className="rounded-[28px] p-3">
          {tabs.map((tab) => (
            <TabsTrigger
              key={tab}
              value={tab}
            >
              {tab}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="Overview">
          <FundamentalCardGrid cards={summary.cards.slice(0, 9)} />
        </TabsContent>
        <TabsContent value="P&L">
          <ProfitLossTable />
        </TabsContent>
        <TabsContent value="Balance Sheet">
          <BalanceSheetTable />
        </TabsContent>
        <TabsContent value="Cash Flow">
          <CashFlowTable />
        </TabsContent>
        <TabsContent value="Ratios">
          <RatioTable />
        </TabsContent>
        <TabsContent value="Growth">
          <FundamentalCardGrid cards={cardsBySection('growth')} />
        </TabsContent>
        <TabsContent value="Peers">
          <PeerComparisonTable />
        </TabsContent>
        <TabsContent value="Governance">
          <FundamentalCardGrid cards={cardsBySection('governance')} />
        </TabsContent>
        <TabsContent value="Valuation">
          <FundamentalCardGrid cards={cardsBySection('valuation')} />
        </TabsContent>
        <TabsContent value="Risk Matrix">
          <FundamentalCardGrid cards={cardsBySection('risk')} />
        </TabsContent>
        <TabsContent value="Investment Thesis">
          <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-2xl font-bold tracking-[-0.04em] text-slate-950">Investment Thesis</h2>
            <p className="mt-3 max-w-3xl text-slate-600">
              Strong cash conversion, stable margin, clean pledge status, and peer-relative scale support a constructive quality view. Valuation remains a watch area.
            </p>
          </section>
        </TabsContent>
      </Tabs>
    </FundamentalModulePage>
  );
}
