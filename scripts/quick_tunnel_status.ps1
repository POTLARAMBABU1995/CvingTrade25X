[CmdletBinding()]
param()

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$python = Join-Path $projectRoot ".venv-mcp\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = "python" }
$settingsJson = & $python (Join-Path $projectRoot "scripts\quick_tunnel_settings.py")
if ($LASTEXITCODE -ne 0) { Write-Error "INVALID_TUNNEL_CONFIG: Quick Tunnel settings validation failed."; exit 2 }
$quickSettings = $settingsJson | ConvertFrom-Json
$origin = [string]$quickSettings.origin
$mcpPath = [string]$quickSettings.mcp_path
$pidFile = [string]$quickSettings.pid_file
$metadataFile = [string]$quickSettings.metadata_file

$localStatus = "DOWN"
$oracleStatus = "UNAVAILABLE"
try {
  $health = Invoke-RestMethod -Uri "$origin/healthz" -TimeoutSec 5
  if ($health.status -eq "OK") { $localStatus = "RUNNING" }
  $ready = Invoke-RestMethod -Uri "$origin/readyz" -TimeoutSec 10
  if ($ready.ready -eq $true -or $ready.status -eq "OK") { $oracleStatus = "AVAILABLE" }
} catch { }

$tunnelStatus = "STOPPED"
if (Test-Path -LiteralPath $pidFile) {
  try {
    $state = Get-Content -Raw -LiteralPath $pidFile | ConvertFrom-Json
    $process = Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue
    if ($process -and $process.ProcessName -eq "cloudflared") { $tunnelStatus = "RUNNING" }
  } catch { }
}

$publicMcp = "NONE"
$remoteValidation = "NOT TESTED"
$authMode = if ($env:CVING_MCP_AUTH_MODE) { $env:CVING_MCP_AUTH_MODE } else { "bearer" }
if (Test-Path -LiteralPath $metadataFile) {
  try {
    $metadata = Get-Content -Raw -LiteralPath $metadataFile | ConvertFrom-Json
    if ($metadata.active -eq $true -and $metadata.mcp_url) { $publicMcp = $metadata.mcp_url }
    if ($metadata.remote_validation) { $remoteValidation = $metadata.remote_validation }
    if ($metadata.authentication) { $authMode = $metadata.authentication }
  } catch { }
}

Write-Host "Local MCP: $localStatus"
Write-Host "Local endpoint: $origin$mcpPath"
Write-Host "Oracle: $oracleStatus via safe health only"
Write-Host "cloudflared: $tunnelStatus"
Write-Host "Public MCP: $publicMcp"
Write-Host "Remote validation: $remoteValidation"
Write-Host "Authentication: $authMode"
