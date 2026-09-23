param(
  [string]$TaskName = 'CvingTrade25X_Manual_SR_Image_Inbox_Every_8H',
  [switch]$RunOnlyWhenLoggedOn
)

$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runnerPath = Join-Path $projectRoot 'scripts\run_manual_sr_image_inbox_automation.ps1'
if (-not (Test-Path $runnerPath)) {
  throw "Runner script not found: $runnerPath"
}

$powerShellExe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$taskRun = "`"$powerShellExe`" -NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`""

$args = @(
  '/Create',
  '/TN', $TaskName,
  '/TR', $taskRun,
  '/SC', 'HOURLY',
  '/MO', '8',
  '/RL', 'LIMITED',
  '/F'
)

if ($RunOnlyWhenLoggedOn) {
  $args += '/IT'
} else {
  $args += @('/RU', $env:USERNAME, '/NP')
}

$null = & schtasks.exe @args
if ($LASTEXITCODE -ne 0) {
  throw "Failed to register scheduled task via schtasks.exe (exit code $LASTEXITCODE)."
}

Write-Host "Scheduled task registered: $TaskName"
Write-Host "Runner: $runnerPath"
Write-Host "Triggers: Every 8 hours."
if ($RunOnlyWhenLoggedOn) {
  Write-Host "Principal: current interactive session only."
} else {
  Write-Host "Principal: $env:USERNAME without stored password."
}
