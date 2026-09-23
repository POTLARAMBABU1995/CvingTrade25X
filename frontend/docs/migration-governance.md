# CvingTrade25X Frontend Migration Governance

This workspace uses a strangler migration. Legacy HTML/JS/CSS remains live until each React/TypeScript page proves parity.

## Mandatory controls

1. Visual parity gate
   - Preserve header/nav position, KPI grid layout, card padding, colors, table width, sticky columns, pagination, filters, search, dark mode, and toast behavior.
2. API contract snapshot testing
   - Capture representative JSON before and after migration.
   - Preserve backend field names in wire DTOs.
   - Normalize only in adapter functions.
3. Route coexistence strategy
   - Flask legacy app stays on `5055`.
   - FastAPI chart service stays on `8000`.
   - Vite frontend runs on `5174` by default.
   - `/legacy-api` proxies to Flask `/api/*`.
   - `/chart-api` proxies to FastAPI `/api/*`.
4. Wrapper-only shadcn adoption
   - shadcn-style primitives must be introduced only behind `src/components/ui/shadcn-wrappers/`.
   - Complex tables, KPI grids, chart surfaces, and sticky-column layouts must remain custom until parity is proven.
5. TypeScript strict-mode protection
   - `strict` stays enabled.
   - Do not weaken compiler options for convenience.
   - Avoid `any`; prefer typed wire DTOs and adapters.

## Migration workflow

1. Capture before screenshots and API snapshots.
2. Add or refine wire DTOs in `src/types/api`.
3. Add adapter functions that map wire DTOs to UI models in `src/services/**/`.
4. Build React/TS page or component without cutting over the legacy route.
5. Run `npm run validate:migration`.
6. Compare visual/API parity.
7. Keep legacy rollback available until explicit approval.

## Completion criteria per page

- React/TSX page renders successfully.
- Existing API request/response contract is unchanged.
- Oracle-backed values match the legacy page.
- Layout and dark mode match the legacy page.
- Browser console has no critical errors.
- `npm run typecheck`, `npm run build`, and `npm run test` pass.
