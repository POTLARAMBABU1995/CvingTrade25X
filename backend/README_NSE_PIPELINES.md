# NSE Pipeline Automation

This project exposes non-UI runners for the three NSE ingestion flows:
- NSE Market Cap
- NSE FFMC
- NSE Delivery Data

## CLI
Run from `C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend`.

```powershell
python .\run_nse_pipeline.py --dataset market-cap --trade-date 2026-03-17
python .\run_nse_pipeline.py --dataset ffmc --trade-date 2026-03-17 --enrich-limit 100
python .\run_nse_pipeline.py --dataset delivery --trade-date 2026-03-17
python .\run_nse_pipeline.py --dataset all --trade-date 2026-03-17
```

Notes:
- All pipelines reuse local downloads when present.
- Market-cap and delivery loads filter to the configured NIFTY500 universe file.
- FFMC now writes to its own Oracle table and pipeline-run table, then enriches FFMC from the quote source when the support file has no FFMC column.

## Windows Task Scheduler
Program/script:
```text
C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
```

Arguments:
```text
-Command "Set-Location 'C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend'; python .\run_nse_pipeline.py --dataset all"
```

Recommended trigger:
- Daily on business days after the NSE source files are usually available.

## Validation
- `python .\run_nse_pipeline.py --dataset market-cap --trade-date 2026-03-17`
- `python .\run_nse_pipeline.py --dataset ffmc --trade-date 2026-03-17`
- `python .\run_nse_pipeline.py --dataset delivery --trade-date 2026-03-17`
- Run `backend\sql\validate_nse_ingestion_objects.sql` in Oracle after the first successful load.

