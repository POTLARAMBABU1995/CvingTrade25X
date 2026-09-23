$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'mcp_common.ps1')
Assert-McpAdministrator
Assert-McpConfig
if ((Get-CloudflareMode) -ne 'disabled') { Get-CloudflaredBinary | Out-Null }
& (Join-Path $PSScriptRoot 'install_mcp_autostart.ps1')
& (Join-Path $PSScriptRoot 'start_mcp.ps1')
if ((Get-CloudflareMode) -eq 'named') { & (Join-Path $PSScriptRoot 'install_cloudflared_service.ps1') }
& (Join-Path $PSScriptRoot 'start_all.ps1')
