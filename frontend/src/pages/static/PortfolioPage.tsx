import { PortfolioGallery } from '../../components/static/PortfolioGallery';
import { PageHeader } from '../../components/ui/PageHeader';

export function PortfolioPage() {
  return (
    <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-6 px-4 py-6 lg:px-8">
      <PageHeader title="Portfolio Gallery" />
      <PortfolioGallery />
    </div>
  );
}
