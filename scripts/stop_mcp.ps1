[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'mcp_common.ps1')
$lock = Enter-McpLock
try {
  'Manual stop: watchdog recovery paused until explicit start.' | Set-Content -LiteralPath $McpStopped
  Stop-McpCore
} finally { $lock.Dispose() }
