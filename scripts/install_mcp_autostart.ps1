[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'mcp_common.ps1')
Assert-McpAdministrator
Assert-McpConfig
$taskName = 'CVING_MCP_AutoStart'
$watchName = 'CVING_MCP_Watchdog'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
foreach ($item in @(@($taskName,'start_all.ps1'), @($watchName,'mcp_watchdog.ps1'))) {
  $arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot $item[1]) + '"'
  $existing = Get-ScheduledTask -TaskName $item[0] -ErrorAction SilentlyContinue
  if ($existing -and (@($existing.Actions).Count -ne 1 -or $existing.Actions[0].Arguments -ne $arguments -or $existing.Actions[0].Execute -ne $powershell)) {
    throw 'Task name is already used by a different action; left untouched.'
  }
  $action = New-ScheduledTaskAction -Execute $powershell -Argument $arguments -WorkingDirectory $McpRoot
  Register-ScheduledTask -TaskName $item[0] -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Managed MCP: $McpRoot" -Force | Out-Null
}
Write-Output 'MCP autostart installed for this user logon. No password is stored.'
