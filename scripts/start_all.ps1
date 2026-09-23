$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'mcp_common.ps1')
& (Join-Path $PSScriptRoot 'start_mcp.ps1')
try { & (Join-Path $PSScriptRoot 'start_cloudflared.ps1') }
finally {
  $task = Get-ScheduledTask -TaskName 'CVING_MCP_Watchdog' -ErrorAction SilentlyContinue
  if ($task -and $task.Description -eq "Managed MCP: $McpRoot") { Start-ScheduledTask -TaskName 'CVING_MCP_Watchdog' }
  & (Join-Path $PSScriptRoot 'cving_mcp_status.ps1')
}
