param(
  [string]$TaskName = 'CvingTrade25X_NSE_MarketData_Automation',
  [string]$UserId = ''
)

$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runnerPath = Join-Path $projectRoot 'scripts\run_nse_marketdata_automation.ps1'
if (-not (Test-Path $runnerPath)) {
  throw "Runner script not found: $runnerPath"
}

$powerShellExe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$actionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`""
$action = New-ScheduledTaskAction -Execute $powerShellExe -Argument $actionArgs -WorkingDirectory $projectRoot

$pollingStart = (Get-Date).Date.AddHours(17)
if ($pollingStart -lt (Get-Date)) {
  $pollingStart = (Get-Date).AddMinutes(1)
}
$pollingTrigger = New-ScheduledTaskTrigger `
  -Once `
  -At $pollingStart `
  -RepetitionInterval (New-TimeSpan -Minutes 5) `
  -RepetitionDuration (New-TimeSpan -Days 3650)

$logonTrigger = New-ScheduledTaskTrigger -AtLogOn

$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries

if (-not $UserId) {
  $UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
}
$principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger @($logonTrigger, $pollingTrigger) `
  -Settings $settings `
  -Principal $principal `
  -Force | Out-Null

Write-Host "Scheduled task registered: $TaskName"
Write-Host "Runner: $runnerPath"
Write-Host "Triggers: At logon + 5-minute polling from $($pollingStart.ToString('yyyy-MM-dd HH:mm:ss')) for 3650 days."
Write-Host "Note: The backend scheduler enforces the 17:00 IST market-data window before running inserts."
