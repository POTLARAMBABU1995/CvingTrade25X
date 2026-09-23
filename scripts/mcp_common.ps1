$ErrorActionPreference = 'Stop'
$script:McpRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $PSScriptRoot 'import_mcp_local_env.ps1')
$script:McpRuntime = Join-Path $McpRoot 'runtime\mcp'
$script:McpPython = Join-Path $McpRoot '.venv-mcp\Scripts\python.exe'
$script:McpState = Join-Path $McpRuntime 'managed_mcp.json'
$script:McpStopped = Join-Path $McpRuntime 'operator_stopped'
New-Item -ItemType Directory -Force -Path $McpRuntime | Out-Null

function Write-McpEvent([string]$Event, [string]$Status) {
  $directory = Join-Path $McpRoot 'runtime\logs'
  New-Item -ItemType Directory -Force -Path $directory | Out-Null
  $log = Join-Path $directory 'watchdog.log'
  if ((Test-Path $log) -and (Get-Item $log).Length -gt 10485760) {
    for ($i = 4; $i -ge 1; $i--) {
      if (Test-Path "$log.$i") { Move-Item -LiteralPath "$log.$i" -Destination "$log.$($i+1)" -Force }
    }
    Move-Item -LiteralPath $log -Destination "$log.1" -Force
  }
  @{timestamp=[DateTimeOffset]::UtcNow.ToString('o'); event=$Event; status=$Status} |
    ConvertTo-Json -Compress | Add-Content -LiteralPath $log
}
function Get-McpHttpCode([string]$Url) {
  try {
    $request = [Net.HttpWebRequest]::Create($Url)
    $request.Timeout = 5000
    $request.AllowAutoRedirect = $false
    $response = $request.GetResponse()
    try { return [int]$response.StatusCode } finally { $response.Close() }
  } catch [Net.WebException] {
    if ($_.Exception.Response) {
      $response = $_.Exception.Response
      try { return [int]$response.StatusCode } finally { $response.Close() }
    }
    return 0
  }
}
function Get-McpListeners {
  # CIM may be unavailable in restricted sessions. netstat is read-only and
  # reports ownership without interpreting an access failure as an empty port.
  $lines = & netstat.exe -ano -p tcp
  if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect listener ownership; refusing lifecycle changes.' }
  foreach ($line in $lines) {
    if ($line -match '^\s*TCP\s+(\S+):1729\s+\S+\s+LISTENING\s+(\d+)\s*$') {
      [pscustomobject]@{LocalAddress=$Matches[1]; OwningProcess=[int]$Matches[2]}
    }
  }
}
function Test-McpHealthy { (Get-McpHttpCode 'http://127.0.0.1:1729/mcp') -eq 401 }
function Get-McpOwnedProcess {
  if (-not (Test-Path -LiteralPath $McpState)) { return $null }
  $state = Get-Content -Raw -LiteralPath $McpState | ConvertFrom-Json
  $process = Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue
  if (-not $process) { return $null }
  $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)"
  if ($process.Path -ne [string]$state.executable -or $process.ProcessName -notmatch "^python" -or $process.StartTime.ToUniversalTime().Ticks.ToString() -ne [string]$state.start_ticks -or
      $cim.CommandLine -notmatch 'backend\.mcp_server\.cli\s+serve' -or [string]$state.root -ne $McpRoot) {
    throw 'MCP process ownership mismatch; no process was stopped.'
  }
  return $process
}
function Enter-McpLock {
  $path = Join-Path $McpRuntime 'lifecycle.lock'
  try { return [IO.File]::Open($path, 'OpenOrCreate', 'ReadWrite', 'None') }
  catch { throw 'Another MCP lifecycle operation is running.' }
}
function Assert-McpConfig {
  if (-not (Test-Path -LiteralPath $McpPython)) { throw 'Run scripts\setup_mcp_venv.cmd first.' }
  if ($env:CVING_MCP_HOST -and $env:CVING_MCP_HOST -ne '127.0.0.1') { throw 'MCP host must be 127.0.0.1.' }
  if ($env:CVING_MCP_PORT -and $env:CVING_MCP_PORT -ne '1729') { throw 'MCP port must be 1729.' }
  if ($env:CVING_MCP_PATH -and $env:CVING_MCP_PATH -ne '/mcp') { throw 'MCP path must be /mcp.' }
  if (-not $env:CVING_MCP_AUTH_MODE) { $env:CVING_MCP_AUTH_MODE = 'bearer' }
  if ($env:CVING_MCP_AUTH_MODE -notin @('bearer','oauth','oauth-server')) { throw 'Authenticated MCP is required.' }
  if ($env:CVING_MCP_AUTH_MODE -in @('bearer','oauth-server') -and ([string]$env:CVING_MCP_BEARER_TOKEN).Length -lt 32) {
    throw 'A bearer token of at least 32 characters is required; values are never printed.'
  }
  Push-Location $McpRoot
  try {
    & $McpPython -c 'from backend.mcp_server.config import McpSettings; from backend.mcp_server.database_guard import pool_options; import mcp,oracledb; McpSettings.from_env().validate_http_security(); pool_options(oracledb)' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'MCP import/configuration validation failed.' }
  } finally { Pop-Location }
}
function Start-McpCore {
  Assert-McpConfig
  $listeners = @(Get-McpListeners)
  if ($listeners.Count) {
    if (@($listeners | Where-Object LocalAddress -ne '127.0.0.1').Count) { throw 'Unsafe listener on port 1729; left untouched.' }
    if (Test-McpHealthy) { Write-McpEvent 'START' 'ALREADY_HEALTHY'; return }
    throw 'Port 1729 is occupied and not healthy; nothing was killed.'
  }
  $owned = Get-McpOwnedProcess
  if ($owned) { throw 'Owned MCP is still starting or hung; use restart_mcp.ps1.' }
  $process = Start-Process -FilePath $McpPython -ArgumentList @('-m','backend.mcp_server.cli','serve','--transport','streamable-http','--host','127.0.0.1','--port','1729','--path','/mcp') -WorkingDirectory $McpRoot -PassThru -WindowStyle Hidden
  @{pid=$process.Id; start_ticks=$process.StartTime.ToUniversalTime().Ticks.ToString(); executable=$McpPython; root=$McpRoot} |
    ConvertTo-Json | Set-Content -LiteralPath $McpState -Encoding UTF8
  for ($attempt=0; $attempt -lt 30; $attempt++) {
    $process.Refresh()
    if ($process.HasExited) { break }
    if (Test-McpHealthy) {
      $bound = @(Get-McpListeners)
      if ($bound.Count -ne 1 -or $bound[0].LocalAddress -ne '127.0.0.1') { throw 'Listener changed during startup.' }
      $listenerPid = $bound[0].OwningProcess
      if ($listenerPid -ne $process.Id) {
        $child = Get-CimInstance Win32_Process -Filter "ProcessId=$listenerPid"
        if ($child.ParentProcessId -ne $process.Id -or $child.CommandLine -notmatch 'backend\.mcp_server\.cli') { throw 'Listener is not the launched MCP; left untouched.' }
      }
      # Windows venv launchers can spawn the real interpreter as a child.
      # Track the listener itself so stopping the launcher cannot orphan it.
      $listenerProcess = Get-Process -Id $listenerPid -ErrorAction Stop
      @{pid=$listenerPid; start_ticks=$listenerProcess.StartTime.ToUniversalTime().Ticks.ToString(); executable=$listenerProcess.Path; root=$McpRoot} |
        ConvertTo-Json | Set-Content -LiteralPath $McpState -Encoding UTF8
      Write-McpEvent 'START' "HEALTHY PID $listenerPid"
      return
    }
    $process.Refresh()
    if ($process.HasExited) { break }
    Start-Sleep -Seconds 1
  }
  throw 'MCP failed the health gate; inspect runtime\logs\mcp.log.'
}
function Stop-McpCore {
  $process = Get-McpOwnedProcess
  if ($process) {
    Stop-Process -InputObject $process -ErrorAction Stop
    $process.WaitForExit(10000) | Out-Null
    if (-not $process.HasExited) { throw 'MCP did not stop.' }
    Write-McpEvent 'STOP' "PID $($process.Id)"
  } elseif (@(Get-McpListeners).Count) {
    throw 'Listener is not owned by the managed launcher; left untouched.'
  }
}
function Get-CloudflareMode {
  if ($env:CVING_CLOUDFLARE_MODE) {
    if ($env:CVING_CLOUDFLARE_MODE -notin @('named','quick','disabled')) { throw 'Invalid Cloudflare mode.' }
    return $env:CVING_CLOUDFLARE_MODE
  }
  if ($env:CVING_QUICK_TUNNEL_ENABLED -match '^(1|true|yes|on)$') { return 'quick' }
  return 'disabled'
}
function Get-CloudflaredBinary {
  $candidates = @($env:CVING_CLOUDFLARE_EXE, "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe", "$env:ProgramFiles\cloudflared\cloudflared.exe", (Join-Path $McpRoot 'cloudflared.exe'))
  $command = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
  if ($command) { $candidates += $command.Source }
  foreach ($candidate in $candidates) { if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return [IO.Path]::GetFullPath($candidate) } }
  throw 'cloudflared is not installed; install it explicitly from Cloudflare.'
}
function Get-McpPublicUrl {
  $value = $env:CVING_MCP_PUBLIC_URL
  if (-not $value -and $env:CVING_MCP_PUBLIC_HOST) { $value = "https://$($env:CVING_MCP_PUBLIC_HOST)/mcp" }
  if (-not $value -and (Get-CloudflareMode) -eq 'quick') {
    $path = Join-Path $McpRuntime 'remote_mcp_url.txt'
    if (Test-Path $path) { $value = (Get-Content -Raw $path).Trim().Trim([char]0xFEFF) }
  }
  if (-not $value) { return '' }
  $uri = [uri]$value
  if ($uri.Scheme -ne 'https' -or -not $uri.Host -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -ne '/mcp') { throw 'Public URL must be HTTPS with /mcp and no credentials/query/fragment.' }
  return $uri.AbsoluteUri
}
function Assert-McpAdministrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  if (-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'This installation action requires an elevated PowerShell window.'
  }
}
