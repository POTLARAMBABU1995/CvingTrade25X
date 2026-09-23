[CmdletBinding()]
param(
  [string]$TestSymbol = "",
  [switch]$Detach
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$quickLockDir = Join-Path $projectRoot "runtime\mcp"
New-Item -ItemType Directory -Force $quickLockDir | Out-Null
$quickLifecycleLock = [IO.File]::Open((Join-Path $quickLockDir "quick-lifecycle.lock"), "OpenOrCreate", "ReadWrite", "None")
# The dedicated PowerShell process releases this handle on every exit path.
. (Join-Path $PSScriptRoot "import_mcp_local_env.ps1")
$python = Join-Path $projectRoot ".venv-mcp\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = "python" }
$settingsJson = & $python (Join-Path $projectRoot "scripts\quick_tunnel_settings.py")
if ($LASTEXITCODE -ne 0) { Write-Error "INVALID_TUNNEL_CONFIG: Quick Tunnel settings validation failed."; exit 2 }
$quickSettings = $settingsJson | ConvertFrom-Json
$origin = [string]$quickSettings.origin
$mcpPath = [string]$quickSettings.mcp_path
$localMcpUrl = "$origin$mcpPath"
$authMode = if ($env:CVING_MCP_AUTH_MODE) { $env:CVING_MCP_AUTH_MODE.ToLowerInvariant() } else { "bearer" }
$allowNoAuth = $env:CVING_MCP_ALLOW_PUBLIC_NOAUTH_TEST -match "^(1|true|yes|on)$"
$startupTimeout = [int]$quickSettings.startup_timeout_seconds
$logFile = [string]$quickSettings.log_file
$runtimeDir = Split-Path -Parent ([string]$quickSettings.metadata_file)
$stdoutFile = Join-Path $runtimeDir "cloudflared.stdout.log"
$pidFile = [string]$quickSettings.pid_file
$baseUrlFile = [string]$quickSettings.base_url_file
$urlFile = [string]$quickSettings.public_url_file
$startedAtFile = [string]$quickSettings.started_at_file
$metadataFile = [string]$quickSettings.metadata_file

function Fail([string]$Code, [string]$Message) {
  Write-Error "$Code`: $Message"
  exit 2
}

if ($origin -notmatch "^http://(127\.0\.0\.1|localhost|\[::1\])(?::\d+)?$") {
  Fail "INVALID_TUNNEL_ORIGIN" "Only a loopback HTTP origin without a path is allowed."
}
if ($origin -match ":1521$") { Fail "ORACLE_PUBLIC_EXPOSURE_BLOCKED" "Oracle port 1521 must never be tunneled." }
if (([uri]$origin).Port -ne 1729) { Fail "INVALID_MCP_PORT" "Remote MCP tunneling is fixed to loopback port 1729." }

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
  $knownCloudflared = @(
    (Join-Path ${env:ProgramFiles(x86)} "cloudflared\cloudflared.exe"),
    (Join-Path $env:ProgramFiles "cloudflared\cloudflared.exe")
  ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
  if ($knownCloudflared) { $cloudflared = Get-Item -LiteralPath $knownCloudflared }
}
if (-not $cloudflared) {
  Write-Host "CLOUDFLARED_NOT_FOUND"
  Write-Host "Install the current Windows executable or MSI from Cloudflare's official downloads page:"
  Write-Host "https://developers.cloudflare.com/tunnel/downloads/"
  exit 3
}
$cloudflaredPath = if ($cloudflared.Source) { $cloudflared.Source } else { $cloudflared.FullName }
$cloudflaredVersion = (& $cloudflaredPath --version 2>&1 | Out-String).Trim()
Write-Host "cloudflared: $cloudflaredVersion"

if (Test-Path -LiteralPath $pidFile -PathType Leaf) {
  try { $existingState = Get-Content -Raw -LiteralPath $pidFile | ConvertFrom-Json } catch {
    Fail "INVALID_PID_STATE" "Inspect runtime\mcp\cloudflared.pid before retrying."
  }
  $existingProcess = Get-Process -Id ([int]$existingState.pid) -ErrorAction SilentlyContinue
  if ($existingProcess) {
    $actualPath = $null
    try { $actualPath = [System.IO.Path]::GetFullPath($existingProcess.Path) } catch { }
    $expectedPath = [System.IO.Path]::GetFullPath([string]$existingState.cloudflared_path)
    if (-not $existingState.start_ticks -or $existingProcess.StartTime.ToUniversalTime().Ticks.ToString() -ne [string]$existingState.start_ticks -or $existingProcess.ProcessName -ne "cloudflared" -or -not $actualPath -or $actualPath -ne $expectedPath) {
      Fail "PID_OWNERSHIP_MISMATCH" "The recorded PID belongs to another process; nothing was changed."
    }
    Write-Host "cloudflared is already running as owned PID $($existingState.pid)."
    exit 0
  }
  Remove-Item -LiteralPath $pidFile -Force
  Remove-Item -LiteralPath $baseUrlFile,$urlFile,$startedAtFile -Force -ErrorAction SilentlyContinue
}

if ($authMode -notin @("none", "bearer", "oauth", "oauth-server")) { Fail "REMOTE_AUTH_REQUIRED" "Use none, bearer, oauth, or oauth-server." }
if ($authMode -eq "none" -and -not $allowNoAuth) {
  Fail "PUBLIC_NOAUTH_DISABLED" "Set CVING_MCP_ALLOW_PUBLIC_NOAUTH_TEST=true only for an explicit short anonymous test."
}
if (($authMode -eq "bearer" -or $authMode -eq "oauth-server") -and ([string]$env:CVING_MCP_BEARER_TOKEN).Length -lt 32) {
  Fail "REMOTE_AUTH_REQUIRED" "$authMode mode requires CVING_MCP_BEARER_TOKEN with at least 32 characters."
}
if ($authMode -eq "oauth" -and -not $env:CVING_MCP_OAUTH_ACCESS_TOKEN) {
  Fail "REMOTE_AUTH_REQUIRED" "OAuth validation requires CVING_MCP_OAUTH_ACCESS_TOKEN; OAuth provider settings remain on the MCP server."
}
if ($authMode -eq "none") {
  Write-Warning "PUBLIC NO-AUTH TEST ENABLED: this creates a public read-only endpoint. Keep the test brief and stop the tunnel immediately afterward."
}

$userProfilePath = [Environment]::GetFolderPath("UserProfile")
$cloudflareConfigDirectory = Join-Path $userProfilePath ".cloudflared"
$conflicts = @("config.yaml", "config.yml") | ForEach-Object { Join-Path $cloudflareConfigDirectory $_ } | Where-Object { Test-Path -LiteralPath $_ }
if ($conflicts.Count -gt 0) {
  Write-Warning "Cloudflare says Quick Tunnels may not work while a global config.yml/config.yaml exists. No file was changed: $($conflicts -join ', ')"
}

$tokenEnv = if ($authMode -eq "oauth") { "CVING_MCP_OAUTH_ACCESS_TOKEN" } else { "CVING_MCP_BEARER_TOKEN" }
$localArgs = @((Join-Path $projectRoot "scripts\validate_local_mcp.py"), "--url", $localMcpUrl, "--auth-mode", $authMode, "--token-env", $tokenEnv)
if ($TestSymbol) { $localArgs += @("--test-symbol", $TestSymbol) }
& $python @localArgs
if ($LASTEXITCODE -ne 0) { Fail "LOCAL_MCP_UNHEALTHY" "Local MCP validation failed at $localMcpUrl." }

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
if ((Test-Path -LiteralPath $logFile) -and (Get-Item -LiteralPath $logFile).Length -gt 5242880) {
  Move-Item -LiteralPath $logFile -Destination "$logFile.1" -Force
}
Set-Content -LiteralPath $logFile -Value "" -Encoding utf8
Set-Content -LiteralPath $stdoutFile -Value "" -Encoding utf8
$originAuthority = ([uri]$origin).Authority
$arguments = @(
  "tunnel",
  "--url", $origin,
  "--http-host-header", $originAuthority,
  "--loglevel", "info"
)
$process = Start-Process -FilePath $cloudflaredPath -ArgumentList $arguments -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdoutFile -RedirectStandardError $logFile
$pidState = [ordered]@{
  pid = $process.Id
  start_ticks = $process.StartTime.ToUniversalTime().Ticks.ToString()
  cloudflared_path = [System.IO.Path]::GetFullPath($cloudflaredPath)
  created_at = [DateTimeOffset]::UtcNow.ToString("o")
  local_origin = $origin
}
$pidState | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding utf8

$baseUrl = $null
$deadline = [DateTimeOffset]::UtcNow.AddSeconds($startupTimeout)
while ([DateTimeOffset]::UtcNow -lt $deadline -and -not $process.HasExited) {
  Start-Sleep -Milliseconds 250
  $combinedLog = ((Get-Content -Raw -LiteralPath $logFile -ErrorAction SilentlyContinue) + "`n" + (Get-Content -Raw -LiteralPath $stdoutFile -ErrorAction SilentlyContinue))
  $match = [regex]::Match($combinedLog, "https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com", [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
  if ($match.Success) { $baseUrl = $match.Value.ToLowerInvariant().TrimEnd("/"); break }
}
if (-not $baseUrl) {
  if (-not $process.HasExited) { Stop-Process -Id $process.Id -ErrorAction SilentlyContinue }
  Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
  Fail "TUNNEL_URL_NOT_FOUND" "No generated trycloudflare.com URL appeared within $startupTimeout seconds. Review $logFile."
}

$remoteMcpUrl = "$baseUrl$mcpPath"
$startedAt = [DateTimeOffset]::UtcNow.ToString("o")
$metadata = [ordered]@{
  provider = "cloudflare"
  type = "quick"
  base_url = $baseUrl
  mcp_url = $remoteMcpUrl
  created_at = $startedAt
  local_origin = $origin
  temporary = $true
  active = $true
  pid = $process.Id
  start_ticks = $process.StartTime.ToUniversalTime().Ticks.ToString()
  cloudflared_path = [System.IO.Path]::GetFullPath($cloudflaredPath)
  cloudflared_version = $cloudflaredVersion
  authentication = $authMode
  remote_validation = "NOT TESTED"
}
$baseUrl | Set-Content -LiteralPath $baseUrlFile -Encoding utf8
$remoteMcpUrl | Set-Content -LiteralPath $urlFile -Encoding utf8
$startedAt | Set-Content -LiteralPath $startedAtFile -Encoding utf8
$metadata | ConvertTo-Json | Set-Content -LiteralPath $metadataFile -Encoding utf8

Write-Host "===================================================="
Write-Host "CvingTrade25X Remote MCP"
Write-Host "===================================================="
Write-Host "Local MCP:"
Write-Host $localMcpUrl
Write-Host ""
Write-Host "Temporary Remote MCP:"
Write-Host $remoteMcpUrl
Write-Host ""
Write-Host "Tunnel:"
Write-Host "Cloudflare Quick Tunnel"
Write-Host ""
Write-Host "Temporary URL:"
Write-Host "YES"
Write-Host ""
Write-Host "Authentication:"
Write-Host $authMode
Write-Host ""
Write-Host "Oracle public:"
Write-Host "NO"
Write-Host "===================================================="

$remoteArgs = @((Join-Path $projectRoot "scripts\validate_remote_mcp.py"), "--url", $remoteMcpUrl, "--auth-mode", $authMode, "--token-env", $tokenEnv)
if ($TestSymbol) { $remoteArgs += @("--test-symbol", $TestSymbol, "--analyze-symbol") }
$remoteOutput = (& $python @remoteArgs 2>&1 | Out-String).Trim()
Write-Host $remoteOutput
$remoteExitCode = $LASTEXITCODE
$metadata.remote_validation = if ($remoteExitCode -eq 0) { "PASS" } else { "FAIL" }
try {
  $remoteReport = $remoteOutput | ConvertFrom-Json
  if ($remoteReport.checks.tools_list.status -eq "PASS") {
    $metadata.tool_count = @($remoteReport.checks.tools_list.tools).Count
  }
} catch { }
$metadata | ConvertTo-Json | Set-Content -LiteralPath $metadataFile -Encoding utf8
if ($remoteExitCode -ne 0) {
  Write-Warning "REMOTE_MCP_UNREACHABLE: the tunnel is running, but remote MCP validation did not pass. No PASS is claimed."
}

Write-Host "IMPORTANT: This Quick Tunnel URL is temporary. If cloudflared restarts, update your remote AI client's MCP URL."
if ($Detach) {
  Write-Host "cloudflared continues in the background as owned PID $($process.Id)."
  exit 0
}
Write-Host "Press Ctrl+C to stop this owned tunnel."
try {
  while (-not $process.HasExited) { Wait-Process -Id $process.Id -Timeout 2 -ErrorAction SilentlyContinue }
}
finally {
  & (Join-Path $PSScriptRoot "stop_quick_tunnel.ps1")
}
