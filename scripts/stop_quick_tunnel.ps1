[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$quickLockDir = Join-Path $projectRoot "runtime\mcp"
New-Item -ItemType Directory -Force $quickLockDir | Out-Null
$quickLifecycleLock = [IO.File]::Open((Join-Path $quickLockDir "quick-lifecycle.lock"), "OpenOrCreate", "ReadWrite", "None")
# The dedicated PowerShell process releases this handle on every exit path.
$python = Join-Path $projectRoot ".venv-mcp\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = "python" }
$settingsJson = & $python (Join-Path $projectRoot "scripts\quick_tunnel_settings.py")
if ($LASTEXITCODE -ne 0) { Write-Error "INVALID_TUNNEL_CONFIG: Quick Tunnel settings validation failed; nothing was stopped."; exit 2 }
$quickSettings = $settingsJson | ConvertFrom-Json
$pidFile = [string]$quickSettings.pid_file
$baseUrlFile = [string]$quickSettings.base_url_file
$urlFile = [string]$quickSettings.public_url_file
$startedAtFile = [string]$quickSettings.started_at_file
$metadataFile = [string]$quickSettings.metadata_file

if (-not (Test-Path -LiteralPath $pidFile)) {
  Write-Host "cloudflared: STOPPED (no owned PID state)"
  exit 0
}

try { $state = Get-Content -Raw -LiteralPath $pidFile | ConvertFrom-Json } catch {
  Write-Error "INVALID_PID_STATE: refusing to stop any process. Remove the stale PID file after inspection."
  exit 2
}
$process = Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue
if ($process) {
  $actualPath = $null
  try { $actualPath = [System.IO.Path]::GetFullPath($process.Path) } catch { }
  $expectedPath = [System.IO.Path]::GetFullPath([string]$state.cloudflared_path)
  if (-not $state.start_ticks -or $process.StartTime.ToUniversalTime().Ticks.ToString() -ne [string]$state.start_ticks -or $process.ProcessName -ne "cloudflared" -or -not $actualPath -or $actualPath -ne $expectedPath) {
    Write-Error "PID_OWNERSHIP_MISMATCH: PID $($state.pid) is not the recorded CvingTrade25X cloudflared process; nothing was stopped."
    exit 3
  }
  Stop-Process -Id $process.Id
  Wait-Process -Id $process.Id -Timeout 10 -ErrorAction SilentlyContinue
  Write-Host "cloudflared: STOPPED (owned PID $($state.pid))"
} else {
  Write-Host "cloudflared: STOPPED (stale owned PID $($state.pid))"
}

Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $baseUrlFile -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $urlFile -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $startedAtFile -Force -ErrorAction SilentlyContinue
$metadata = [ordered]@{}
if (Test-Path -LiteralPath $metadataFile) {
  try {
    $current = Get-Content -Raw -LiteralPath $metadataFile | ConvertFrom-Json
    foreach ($property in $current.PSObject.Properties) { $metadata[$property.Name] = $property.Value }
  } catch { }
}
$metadata["active"] = $false
$metadata["stopped_at"] = [DateTimeOffset]::UtcNow.ToString("o")
$metadata["inactive_reason"] = "owned process stopped"
$metadata | ConvertTo-Json | Set-Content -LiteralPath $metadataFile -Encoding utf8
