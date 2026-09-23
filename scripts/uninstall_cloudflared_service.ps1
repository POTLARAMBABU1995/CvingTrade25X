[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'cloudflare_common.ps1')
Assert-McpAdministrator
if (Get-OwnedCloudflareService) {
  Stop-Service cloudflared
  $binary = Get-CloudflaredBinary
  & $binary service uninstall *> $null
  if ($LASTEXITCODE -ne 0) { throw 'Cloudflare service uninstall failed.' }
  Remove-Item -LiteralPath $CloudflareOwnership
}
