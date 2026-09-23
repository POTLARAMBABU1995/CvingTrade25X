[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'cloudflare_common.ps1')
if ((Get-CloudflareMode) -eq 'disabled') { return }
if ((Get-CloudflareMode) -eq 'quick') {
  & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'stop_quick_tunnel.ps1')
  if ($LASTEXITCODE -ne 0) { throw 'Quick Tunnel stop failed.' }
} elseif (Get-OwnedCloudflareService) {
  Stop-Service cloudflared
  (Get-Service cloudflared).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(20))
}
