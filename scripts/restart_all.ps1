$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'stop_all.ps1')
& (Join-Path $PSScriptRoot 'start_all.ps1')
