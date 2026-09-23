[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'mcp_common.ps1')
$lock = Enter-McpLock
try {
  Stop-McpCore
  if (Test-Path $McpStopped) { Remove-Item -LiteralPath $McpStopped }
  Start-McpCore
} finally { $lock.Dispose() }
