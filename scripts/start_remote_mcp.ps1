[CmdletBinding()]
param([string]$TestSymbol = "")
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'start_all.ps1')
