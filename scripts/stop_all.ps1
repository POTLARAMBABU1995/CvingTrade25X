$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'mcp_common.ps1')
'Manual stop' | Set-Content $McpStopped
$task = Get-ScheduledTask -TaskName 'CVING_MCP_Watchdog' -ErrorAction SilentlyContinue
if ($task -and $task.Description -eq "Managed MCP: $McpRoot") { Stop-ScheduledTask -TaskName 'CVING_MCP_Watchdog' }
try { & (Join-Path $PSScriptRoot 'stop_cloudflared.ps1') }
finally { & (Join-Path $PSScriptRoot 'stop_mcp.ps1') }
