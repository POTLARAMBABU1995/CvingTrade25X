param(
  [switch]$DryRun,
  [switch]$Once
)

$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $projectRoot

$pythonCandidates = @(
  (Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'),
  (Join-Path $projectRoot '.venv\Scripts\python.exe')
)

$pythonExe = $null
foreach ($candidate in $pythonCandidates) {
  if (Test-Path $candidate) {
    $pythonExe = $candidate
    break
  }
}

if (-not $pythonExe) {
  $pythonExe = 'python'
}

$arguments = @('-m', 'backend.automation.nse_marketdata_scheduler', '--once')
if ($DryRun) {
  $arguments += '--dry-run'
}

& $pythonExe @arguments
exit $LASTEXITCODE
