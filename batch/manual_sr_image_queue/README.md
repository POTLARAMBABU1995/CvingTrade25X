# Manual SR Image Queue

Use this folder tree to collect TradingView chart screenshots before manual SR extraction and to build reusable datasets for agent training and RAG.

## Folder structure
- `01_inbox/`
  Drop new chart images here.
- `02_processed/`
  Move images here after SR levels are extracted and inserted.
- `03_rejected/`
  Move unusable images here.
- `04_payloads/`
  JSON annotation payloads used for DB insertion and agent-learning metadata.
- `05_manifests/`
  Queue index files generated from the inbox.
- `06_training_corpus/`
  JSONL exports for model training or offline analysis.
- `07_rag_exports/`
  JSONL exports optimized for retrieval pipelines.
- `08_already_processed/`
  Images skipped automatically because the same filename is already referenced by an existing payload.
- `annotation_taxonomy.json`
  Controlled vocabulary for trend, market phase, price action state, and chart patterns.

## Recommended filename format
Use this naming pattern so the queue manager can infer symbol and source timeframe:

```text
SYMBOL__SOURCE_TF__YYYY-MM-DD.png
```

Examples:
- `AARTIIND__1W__2026-03-14.png`
- `TANLA__1W__2026-03-14.jpg`
- `RELIANCE__1D__2026-03-14.png`

If the filename does not follow the pattern, the script still works, but symbol/date guesses may be weak.

## Skip mechanism for already processed images
The queue manager now checks every inbox image filename against `source_image` values already present in payload JSON files.

If the same filename is already known:
- it is marked as `already_processed`
- it is skipped from payload generation
- it can be moved automatically into `08_already_processed/`

This keeps the inbox focused only on new images.

## Annotation payload model
The queue manager creates skeleton payloads with:
- `sr_levels`
- `analysis.trend_direction`
- `analysis.market_phase`
- `analysis.price_action_state`
- `analysis.chart_patterns`
- `analysis.pattern_bias`
- `analysis.entry_bias`
- `analysis.narrative`
- `agent_training.use_for_rag`
- `agent_training.use_for_training`

This keeps chart-image labels reusable for:
- SR insertion into Oracle
- price action / trend / consolidation classification
- chart-pattern labeling
- training corpus generation
- RAG document generation

## Multi-image rule for one stock
A stock can have many screenshots. Keep one payload per image if that is easier, but use the same `symbol` and `tf = "1D"` in every payload.

When you later load the directory:
- all payload files are processed together
- rows are merged by `symbol + tf + level_type + sr_levels`
- overlapping levels from multiple images update the same stock row instead of creating duplicates

This is the expected workflow for broad coverage across Nifty 500.

## Unattended auto-ingestion
When the Flask app starts with `CVING_ENABLE_MANUAL_SR_IMAGE_AUTO_INGEST=1`, the manual SR image auto-ingest scheduler watches `01_inbox/` without human intervention. The Windows startup launcher enables this manual-SR watcher by default while keeping the broader `CVING_ENABLE_BACKGROUND_JOBS` group disabled unless explicitly overridden.

For every supported image found in `01_inbox/`, the scheduler:
- creates or refreshes the payload skeleton
- extracts TradingView right-axis SR labels from the screenshot
- inserts only missing rows into `PRICE_ACTION_SR_LEVELS_MANUALLY`
- moves DB-confirmed images to `02_processed/`
- moves unreadable OCR images to `03_rejected/`
- moves known duplicate filenames to `08_already_processed/`

If `01_inbox/` has no images, the scheduler records an idle cycle and does not run the extraction/DB process. This prevents repeated processing on empty folders.

Auto-ingestion can be controlled with environment variables:
- `CVING_ENABLE_MANUAL_SR_IMAGE_AUTO_INGEST=1|0` (Flask startup gate; Windows launcher default `1`)
- `MANUAL_SR_IMAGE_AUTO_INGEST_ENABLED=true|false` (default `true`)
- `MANUAL_SR_IMAGE_AUTO_INGEST_STARTUP_DELAY_SEC=15`
- `MANUAL_SR_IMAGE_AUTO_INGEST_INTERVAL_SEC=60`

Run one unattended cycle manually for validation:

```powershell
python -m backend.automation.manual_sr_image_auto_ingest --once
```

Run a standalone watcher outside Flask if needed:

```powershell
python -m backend.automation.manual_sr_image_auto_ingest --watch --interval-seconds 60
```

## Workflow
1. Put TradingView images into `01_inbox/`.
2. Keep the Flask app running with `CVING_ENABLE_MANUAL_SR_IMAGE_AUTO_INGEST=1`, or run the unattended one-shot command above for validation.
3. Review `02_processed/`, `03_rejected/`, `08_already_processed/`, and `05_manifests/queue_index.json` for the latest queue outcome.

## Commands
Create or refresh queue index and payload skeletons:

```powershell
python -m batch.jobs.manage_manual_sr_image_queue --scan
```

Create the queue index and automatically move already-known filenames out of inbox:

```powershell
python -m batch.jobs.manage_manual_sr_image_queue --scan --move-known
```

Move one image after processing:

```powershell
python -m batch.jobs.manage_manual_sr_image_queue --move AARTIIND__1W__2026-03-14.png --status processed
```

Move one known duplicate image manually:

```powershell
python -m batch.jobs.manage_manual_sr_image_queue --move AARTIIND__1W__2026-03-14.png --status already_processed
```

Load one payload file into Oracle:

```powershell
python -m batch.jobs.load_manual_sr_levels --file batch\manual_sr_image_queue\04_payloads\AARTIIND__1W__2026-03-14.json
```

Load all payloads in the queue directory and merge same-stock levels from multiple images:

```powershell
python -m batch.jobs.load_manual_sr_levels --dir batch\manual_sr_image_queue\04_payloads
```

Build training and RAG corpora from all payloads:

```powershell
python -m batch.jobs.build_manual_sr_training_corpus
```

Run the reusable learning pipeline and write a run manifest:

```powershell
python -m batch.jobs.run_manual_sr_agent_pipeline --scan
```

Run the same pipeline on the existing manual payloads in `batch/config`:

```powershell
python -m batch.jobs.run_manual_sr_agent_pipeline --payload-dir batch\config --skip-db
```

Build corpus without Oracle OHLCV enrichment:

```powershell
python -m batch.jobs.build_manual_sr_training_corpus --skip-db
```

## Output model
The generated payload skeleton always defaults to:
- `tf = "1D"`
- `level_type = "MANUAL"`

So even if the source chart is weekly or monthly, you can still store the final SR levels as daily rows while keeping source-timeframe context for agents.

## Reuse for agent learning
Each annotated payload can become three reusable assets:
- Oracle SR inserts through `load_manual_sr_levels.py` into `PRICE_ACTION_SR_LEVELS_MANUALLY` only
- training rows in `06_training_corpus/manual_sr_training_dataset.jsonl`
- retrieval rows in `07_rag_exports/manual_sr_rag_documents.jsonl`

This means the same screenshot can later support price-action classification, trend detection, consolidation labeling, and chart-pattern retrieval without redesigning the data format.


## Direct extraction helper
The unattended scheduler uses the same reusable helper. You can still run it directly for targeted validation:

```powershell
python -m batch.jobs.extract_manual_sr_levels_from_images --dir batch\manual_sr_image_queue\04_payloads --insert-db --only-missing --move-processed
```

This helper auto-reads the right-axis SR labels from TradingView screenshots and writes the extracted values back into the existing payload JSON files before the normal `load_manual_sr_levels.py` merge into `PRICE_ACTION_SR_LEVELS_MANUALLY`. The `SR_LEVELS.html` technical page remains separate and continues to use the dynamic SR flow.

