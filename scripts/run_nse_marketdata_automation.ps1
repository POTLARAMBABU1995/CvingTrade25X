param(
  [switch]$DryRun,
  [switch]$Once
)

$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $projectRoot

$pythonCandidates = @(
  (Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'),
  (Join-Path $projectRoot '.venv\Scripts\python.exe'),
  (Join-Path $projectRoot 'venv\Scripts\python.exe'),
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
    & $candidate -c 'import oracledb, openpyxl, xlrd, pandas' *> $null
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
  throw 'No Python runtime with NSE dependencies found. Install the existing requirements in a project virtual environment.'
}

$arguments = @('-m', 'backend.automation.nse_marketdata_scheduler', '--once')
if ($DryRun) {
  $arguments += '--dry-run'
}

& $pythonExe @arguments
exit $LASTEXITCODE
