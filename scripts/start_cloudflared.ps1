[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'cloudflare_common.ps1')
$mode = Get-CloudflareMode
if ($mode -eq 'disabled') { return }
if (-not (Test-McpHealthy)) { throw 'MCP must pass local health before tunnel start.' }
if ($mode -eq 'quick') {
  Write-Warning 'Quick Tunnel URL is temporary and may change after restart.'
  $env:CVING_QUICK_TUNNEL_ENABLED = 'true'
  & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start_quick_tunnel.ps1') -Detach
  if ($LASTEXITCODE -ne 0) { throw 'Quick Tunnel start failed.' }
} else {
  $service = Get-OwnedCloudflareService
  if (-not $service) { throw 'Install the named Cloudflare service first.' }
  if ($service.State -ne 'Running') { Start-Service cloudflared }
  (Get-Service cloudflared).WaitForStatus('Running', [TimeSpan]::FromSeconds(20))
}
$url = Get-McpPublicUrl
foreach ($delay in @(0,5,10,20,40,60)) {
  if ($delay) { Start-Sleep -Seconds $delay }
  if ($url -and (Get-McpHttpCode $url) -eq 401) { Write-McpEvent 'TUNNEL' 'PUBLIC_401_EXPECTED'; return }
}
throw 'DEGRADED: local MCP is healthy, remote access is unavailable.'
