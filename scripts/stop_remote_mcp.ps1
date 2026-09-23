[CmdletBinding()]
param([switch]$All)
$ErrorActionPreference = 'Stop'
if ($All) { & (Join-Path $PSScriptRoot 'stop_all.ps1') }
else { & (Join-Path $PSScriptRoot 'stop_cloudflared.ps1') }
