[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'cloudflare_common.ps1')
Assert-McpAdministrator
$config = Get-NamedTunnelArguments
if (Get-OwnedCloudflareService) { Write-Output 'Owned Cloudflare service already installed.'; return }
# Local-managed credentials stay in an ACL-protected file, never in arguments.
& $config.binary service install *> $null
if ($LASTEXITCODE -ne 0) { throw 'Cloudflare service installation failed; no existing service was replaced.' }
$imagePath = '"' + $config.binary + '" --no-autoupdate tunnel --config "' + $config.config + '" run ' + $config.tunnel
$installed = Get-CimInstance Win32_Service -Filter "Name='cloudflared'"
$result = Invoke-CimMethod -InputObject $installed -MethodName Change -Arguments @{PathName=$imagePath; StartMode='Automatic'}
if ($result.ReturnValue -ne 0) { throw 'Service configuration failed; inspect the installed cloudflared service.' }
@{root=$McpRoot; image_path=$imagePath} | ConvertTo-Json | Set-Content $CloudflareOwnership
& sc.exe failure cloudflared reset= 600 actions= restart/5000/restart/10000/restart/20000 | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cloudflare service recovery configuration failed.' }
& (Join-Path $PSScriptRoot 'start_cloudflared.ps1')
