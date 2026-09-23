[CmdletBinding()]
param()

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
. (Join-Path $PSScriptRoot "import_mcp_local_env.ps1")
$runtimeDir = Join-Path $projectRoot "runtime\mcp"
$metadataFile = Join-Path $runtimeDir "remote_mcp.json"
$cloudflaredPidFile = Join-Path $runtimeDir "cloudflared.pid"
$authMode = if ($env:CVING_MCP_AUTH_MODE) { $env:CVING_MCP_AUTH_MODE.ToLowerInvariant() } else { "bearer" }
$token = if ($authMode -eq "oauth") { [string]$env:CVING_MCP_OAUTH_ACCESS_TOKEN } else { [string]$env:CVING_MCP_BEARER_TOKEN }
$headers = @{}
if ($token) { $headers.Authorization = "Bearer $token" }

$localStatus = "DOWN"
$oracleStatus = "NOT READY"
try {
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:1729/healthz" -Headers $headers -TimeoutSec 5
  if ($health.status -eq "OK") { $localStatus = "UP" }
  $ready = Invoke-RestMethod -Uri "http://127.0.0.1:1729/readyz" -Headers $headers -TimeoutSec 15
  if ($ready.ready -eq $true -or $ready.status -eq "OK") { $oracleStatus = "READY" }
} catch { }

$cloudflareStatus = "STOPPED"
if (Test-Path -LiteralPath $cloudflaredPidFile -PathType Leaf) {
  try {
    $state = Get-Content -Raw -LiteralPath $cloudflaredPidFile | ConvertFrom-Json
    $process = Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue
    if ($process -and $process.ProcessName -eq "cloudflared") { $cloudflareStatus = "RUNNING" }
  } catch { }
}

$publicHost = "NONE"
$remoteMcp = if ($env:CVING_MCP_PUBLIC_URL) { [string]$env:CVING_MCP_PUBLIC_URL } else { "NONE" }
$remoteReachable = "NO"
$tools = "UNKNOWN"
if (Test-Path -LiteralPath $metadataFile -PathType Leaf) {
  try {
    $metadata = Get-Content -Raw -LiteralPath $metadataFile | ConvertFrom-Json
    if ($metadata.active -eq $true) {
      if ($metadata.base_url) { $publicHost = [string]$metadata.base_url }
      if ($metadata.mcp_url) { $remoteMcp = [string]$metadata.mcp_url }
      if ($metadata.remote_validation -eq "PASS") { $remoteReachable = "YES" }
      if ($metadata.tool_count) { $tools = [string]$metadata.tool_count }
    }
  } catch { }
}
if ($remoteMcp -ne "NONE" -and $publicHost -eq "NONE") {
  try { $publicHost = ([uri]$remoteMcp).GetLeftPart([System.UriPartial]::Authority) } catch { }
}

Write-Host "========================================="
Write-Host " CvingTrade25X Remote MCP"
Write-Host "========================================="
Write-Host ("Local MCP       : {0}" -f $localStatus)
Write-Host "Port            : 1729"
Write-Host "Transport       : Streamable HTTP"
Write-Host ("Authentication  : {0}" -f $authMode.ToUpperInvariant())
Write-Host "Auth status     : ENABLED"
Write-Host ("Cloudflare      : {0}" -f $cloudflareStatus)
Write-Host ("Public Host     : {0}" -f $publicHost)
Write-Host ("Remote MCP      : {0}" -f $remoteMcp)
Write-Host ("Remote Reachable: {0}" -f $remoteReachable)
Write-Host ("Oracle          : {0}" -f $oracleStatus)
Write-Host ("MCP Tools       : {0}" -f $tools)
Write-Host "========================================="
