[CmdletBinding()]
param([switch]$Once)
. (Join-Path $PSScriptRoot 'mcp_common.ps1')
$watchLock = [IO.File]::Open((Join-Path $McpRuntime 'watchdog.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
try {
  do {
    [DateTimeOffset]::UtcNow.ToString('o') | Set-Content (Join-Path $McpRuntime 'watchdog.heartbeat')
    if (-not (Test-Path $McpStopped)) {
      $code = Get-McpHttpCode 'http://127.0.0.1:1729/mcp'
      for ($retry=0; $code -eq 0 -and $retry -lt 2; $retry++) {
        Start-Sleep -Seconds 2
        $code = Get-McpHttpCode 'http://127.0.0.1:1729/mcp'
      }
      if ($code -eq 0) {
        $lock = $null
        try {
          $lock = Enter-McpLock
          if (-not (Test-Path $McpStopped)) {
            $historyPath = Join-Path $McpRuntime 'restart_history.json'
            $history = @()
            if (Test-Path $historyPath) { $decoded = Get-Content -Raw $historyPath | ConvertFrom-Json; $history = @(foreach ($entry in $decoded) { [long]$entry }) }
            $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
            $history = @($history | Where-Object { $_ -gt ($now - 600) })
            if ($history.Count -ge 5) {
              Write-McpEvent 'WATCHDOG' 'CRITICAL restart budget exhausted; manual start required'
              'Restart budget exhausted' | Set-Content $McpStopped
            } else {
              # Persist attempted restarts before launch so failures consume budget.
              ConvertTo-Json -InputObject ([long[]]@($history + $now)) | Set-Content $historyPath
              Stop-McpCore
              Start-McpCore
            }
          }
        } catch { Write-McpEvent 'WATCHDOG' 'RECOVERY_FAILED ownership/configuration/health check' }
        finally { if ($lock) { $lock.Dispose() } }
      } elseif ($code -ne 401) { Write-McpEvent 'WATCHDOG' "DEGRADED HTTP $code; no restart" }
      # Tunnel failure never triggers an MCP/Oracle restart.
      if ($code -eq 401 -and (Get-CloudflareMode) -ne 'disabled') {
        try { & (Join-Path $PSScriptRoot 'start_cloudflared.ps1') }
        catch { Write-McpEvent 'TUNNEL' 'DEGRADED remote connectivity unavailable' }
      }
    }
    if (-not $Once) { Start-Sleep -Seconds 30 }
  } while (-not $Once)
} finally { $watchLock.Dispose() }
