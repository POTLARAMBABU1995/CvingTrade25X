[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'mcp_common.ps1')
Assert-McpAdministrator
foreach ($name in @('CVING_MCP_AutoStart','CVING_MCP_Watchdog')) {
  $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
  if ($task) {
    if ($task.Description -ne "Managed MCP: $McpRoot") { throw 'Task ownership mismatch; left untouched.' }
    Stop-ScheduledTask -TaskName $name
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
  }
}
