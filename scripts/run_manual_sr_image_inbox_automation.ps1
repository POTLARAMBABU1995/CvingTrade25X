param(
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $projectRoot

$pythonCandidates = @(
  (Join-Path $projectRoot '.venv\Scripts\python.exe'),
  (Join-Path $projectRoot 'venv\Scripts\python.exe'),
  (Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'),
  'python'
)

$pythonExe = $null
$nativeErrorHandlingSupported = $null -ne (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue)
foreach ($candidate in $pythonCandidates) {
  if ($candidate -ne 'python' -and -not (Test-Path $candidate)) {
    continue
  }

  $probeExitCode = 1
  if ($nativeErrorHandlingSupported) {
    $previousNativeErrorPreference = $PSNativeCommandUseErrorActionPreference
    $PSNativeCommandUseErrorActionPreference = $false
  }

  try {
    & $candidate -c 'import numpy, oracledb' *> $null
    $probeExitCode = $LASTEXITCODE
  } catch {
    $probeExitCode = 1
  } finally {
    if ($nativeErrorHandlingSupported) {
      $PSNativeCommandUseErrorActionPreference = $previousNativeErrorPreference
    }
  }

  if ($probeExitCode -eq 0) {
    $pythonExe = $candidate
    break
  }
}

if (-not $pythonExe) {
  $pythonExe = 'python'
}

$scanArgs = @('-m', 'batch.jobs.manage_manual_sr_image_queue', '--scan', '--move-known')
& $pythonExe @scanArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$processScript = @'
import json
import sys
from pathlib import Path

from batch.jobs.extract_manual_sr_levels_from_images import process_payloads
from batch.jobs.load_manual_sr_levels import build_merge_rows, load_payloads, split_rows_by_db_presence

manifest_path = Path('batch/manual_sr_image_queue/05_manifests/queue_index.json')
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

def payload_needs_extraction(payload_path):
    try:
        document = json.loads(Path(payload_path).read_text(encoding='utf-8-sig'))
    except Exception:
        return False
    records = document.get('records') if isinstance(document, dict) else None
    if not isinstance(records, list):
        return False
    for record in records:
        if isinstance(record, dict) and not record.get('sr_levels'):
            return True
    return False

def payload_has_missing_db_rows(payload_path):
    if not payload_path:
        return False
    try:
        rows = build_merge_rows(load_payloads(files=[payload_path]))
        if not rows:
            return False
        missing, _present = split_rows_by_db_presence(rows)
        return bool(missing)
    except Exception as exc:
        print(json.dumps({
            'warning': 'db_presence_check_failed',
            'payload_path': payload_path,
            'error': str(exc),
        }), file=sys.stderr)
        return False

payload_items = list(manifest.get('pending_images', []))
payload_items.extend(
    item for item in manifest.get('already_processed_images', [])
    if payload_needs_extraction(item.get('payload_path')) or payload_has_missing_db_rows(item.get('payload_path'))
)
payloads = [item['payload_path'] for item in payload_items if item.get('payload_path')]
dry_run = '--dry-run' in sys.argv

if dry_run or not payloads:
    print(json.dumps({
        'dry_run': dry_run,
        'payloads_scanned': 0,
        'pending_payloads': len(payloads),
        'skipped': dry_run or not payloads,
    }, indent=2))
    raise SystemExit(0)

result = process_payloads(
    files=payloads,
    directory=None,
    pattern='*.json',
    overwrite=False,
    insert_db=True,
    only_missing=True,
    move_processed=True,
    sync_db_groups=False,
)
print(json.dumps(result, indent=2, default=str))
'@

$processArgs = @('-c', $processScript)
if ($DryRun) {
  $processArgs += '--dry-run'
}

& $pythonExe @processArgs
exit $LASTEXITCODE
