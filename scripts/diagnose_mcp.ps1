. (Join-Path $PSScriptRoot 'mcp_common.ps1')
$directory = Join-Path $McpRoot 'runtime\diagnostics'
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$path = Join-Path $directory ('diagnostic_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.txt')
& (Join-Path $PSScriptRoot 'cving_mcp_status.ps1') -AsJson | Set-Content $path
$url = Get-McpPublicUrl
if ($url) {
  try { Resolve-DnsName ([uri]$url).Host -ErrorAction Stop | Select-Object Name,Type,IPAddress | Out-String | Add-Content $path }
  catch { 'DNS: UNAVAILABLE' | Add-Content $path }
}
try { Get-NetFirewallProfile | Select-Object Name,Enabled | Out-String | Add-Content $path }
catch { 'Firewall status: UNAVAILABLE' | Add-Content $path }
try { Assert-McpConfig; 'Configuration: VALID' | Add-Content $path }
catch { 'Configuration: INVALID (secret values omitted)' | Add-Content $path }
# Only this implementation's allowlisted event log is included, never raw server logs.
$log = Join-Path $McpRoot 'runtime\logs\watchdog.log'
if (Test-Path $log) { Get-Content $log -Tail 20 | Add-Content $path }
Write-Output $path
