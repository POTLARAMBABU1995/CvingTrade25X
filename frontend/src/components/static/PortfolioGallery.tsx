import { useMemo, useState } from 'react';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/Dialog';

type PortfolioPanel = {
  accent: string;
  id: string;
  note: string;
  title: string;
  tone: string;
};

const portfolioPanels: PortfolioPanel[] = [
  {
    id: 'report-1',
    title: 'Report 1',
    note: 'Equity research summary',
    tone: 'from-emerald-500/20 via-white to-sky-500/20',
    accent: 'bg-emerald-500/80',
  },
  {
    id: 'report-2',
    title: 'Report 2',
    note: 'Trend and momentum view',
    tone: 'from-sky-500/20 via-white to-cyan-500/20',
    accent: 'bg-sky-500/80',
  },
  {
    id: 'report-3',
    title: 'Report 3',
    note: 'Sector breadth snapshot',
    tone: 'from-rose-500/20 via-white to-orange-500/20',
    accent: 'bg-rose-500/80',
  },
  {
    id: 'report-4',
    title: 'Report 4',
    note: 'Risk and support levels',
    tone: 'from-amber-500/20 via-white to-lime-500/20',
    accent: 'bg-amber-500/80',
  },
  {
    id: 'report-5',
    title: 'Report 5',
    note: 'Volume and participation',
    tone: 'from-violet-500/20 via-white to-fuchsia-500/20',
    accent: 'bg-violet-500/80',
  },
  {
    id: 'report-6',
    title: 'Report 6',
    note: 'Portfolio allocation',
    tone: 'from-slate-500/20 via-white to-indigo-500/20',
    accent: 'bg-slate-500/80',
  },
];

export function PortfolioGallery() {
  const [selectedImageId, setSelectedImageId] = useState<string | null>(null);
  const selectedImage = useMemo(
    () => portfolioPanels.find((image) => image.id === selectedImageId) ?? null,
    [selectedImageId],
  );

  return (
    <Dialog open={selectedImage !== null} onOpenChange={(open) => !open && setSelectedImageId(null)}>
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {portfolioPanels.map((image) => (
          <button
            key={image.id}
            type="button"
            className="group block text-left"
            onClick={() => setSelectedImageId(image.id)}
          >
            <Card variant="light" padding="none" className="overflow-hidden rounded-[28px] border-slate-200 shadow-sm transition duration-200 group-hover:-translate-y-1 group-hover:shadow-lg">
              <div className={`relative h-72 w-full overflow-hidden bg-gradient-to-br ${image.tone}`}>
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.8),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(255,255,255,0.55),transparent_28%)]" />
                <div className="absolute left-6 top-6 flex flex-col gap-3">
                  <span className={`h-3 w-24 rounded-full ${image.accent}`} />
                  <span className="h-16 w-16 rounded-3xl border border-white/60 bg-white/55 shadow-2xl backdrop-blur" />
                </div>
                <div className="absolute right-6 top-6 h-20 w-20 rounded-full border border-white/60 bg-white/30 shadow-lg backdrop-blur" />
                <div className="absolute inset-x-6 bottom-6 rounded-[24px] border border-white/60 bg-white/72 p-4 shadow-2xl backdrop-blur-xl">
                  <p className="text-sm font-black uppercase tracking-[0.18em] text-slate-500">{image.id}</p>
                  <p className="mt-2 text-lg font-black text-slate-950">{image.title}</p>
                  <p className="mt-1 text-sm font-medium text-slate-600">{image.note}</p>
                </div>
              </div>
              <div className="border-t border-slate-200 px-5 py-4">
                <p className="text-sm font-bold text-slate-950">{image.title}</p>
                <p className="mt-1 text-sm text-slate-500">Modern abstract preview rendered directly from React.</p>
              </div>
            </Card>
          </button>
        ))}
      </div>

      {selectedImage ? (
        <DialogContent tone="light" align="center" className="max-w-5xl overflow-hidden p-0">
          <DialogHeader className="sr-only">
            <DialogTitle>{selectedImage.title}</DialogTitle>
            <DialogDescription>Modern abstract lightbox preview for the migrated portfolio page.</DialogDescription>
          </DialogHeader>
          <div className="relative">
            <Button
              variant="secondary"
              className="absolute right-4 top-4 z-10 border-white/20 bg-white/85 text-slate-900 hover:bg-white"
              onClick={() => setSelectedImageId(null)}
            >
              Close
            </Button>
            <Card variant="light" padding="none" className="overflow-hidden rounded-[32px] shadow-2xl">
              <div className={`relative flex min-h-[72vh] w-full items-end overflow-hidden bg-gradient-to-br ${selectedImage.tone}`}>
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.9),transparent_30%),radial-gradient(circle_at_bottom_left,rgba(255,255,255,0.6),transparent_34%)]" />
                <div className="absolute left-10 top-10 flex flex-col gap-4">
                  <span className={`h-4 w-32 rounded-full ${selectedImage.accent}`} />
                  <span className="h-28 w-28 rounded-[32px] border border-white/60 bg-white/55 shadow-2xl backdrop-blur" />
                </div>
                <div className="absolute right-10 top-10 h-28 w-28 rounded-full border border-white/60 bg-white/30 shadow-lg backdrop-blur" />
                <div className="relative z-10 w-full border-t border-white/50 bg-white/72 px-8 py-7 backdrop-blur-xl">
                  <p className="text-sm font-black uppercase tracking-[0.2em] text-slate-500">{selectedImage.id}</p>
                  <p className="mt-2 text-3xl font-black text-slate-950">{selectedImage.title}</p>
                  <p className="mt-2 max-w-2xl text-base text-slate-600">{selectedImage.note}</p>
                </div>
              </div>
            </Card>
          </div>
        </DialogContent>
      ) : null}
    </Dialog>
  );
}
