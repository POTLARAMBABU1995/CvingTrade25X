$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'mcp_common.ps1')
$script:McpRuntime = Join-Path $McpRoot 'runtime\reports\mcp-lifecycle-test'
New-Item -ItemType Directory -Force $McpRuntime | Out-Null
$script:McpState = Join-Path $McpRuntime 'managed_mcp.json'
$script:McpStopped = Join-Path $McpRuntime 'operator_stopped'
function Assert-McpConfig {}
function Write-McpEvent($Event,$Status) {}
function Get-McpListeners { [pscustomobject]@{LocalAddress='127.0.0.1';OwningProcess=123} }
function Test-McpHealthy { $true }
function Start-Process { throw 'Duplicate launch attempted' }
Start-McpCore
function Test-McpHealthy { $false }
$blocked = $false
try { Start-McpCore } catch { $blocked = $_.Exception.Message -like '*occupied*' }
if (-not $blocked) { throw 'Unknown occupied listener was not rejected' }
function Get-McpOwnedProcess { throw 'Ownership mismatch' }
function Stop-Process { throw 'Unrelated process stop attempted' }
$blocked = $false
try { Stop-McpCore } catch { $blocked = $_.Exception.Message -eq 'Ownership mismatch' }
if (-not $blocked) { throw 'Stop ownership guard failed' }
# Exercise the real watchdog body with isolated I/O and controlled health.
$body = Get-Content -Raw (Join-Path $PSScriptRoot 'mcp_watchdog.ps1')
$body = $body.Replace(". (Join-Path `$PSScriptRoot 'mcp_common.ps1')", '')
function Get-McpHttpCode { 0 }
function Start-Sleep {}
function Get-CloudflareMode { 'disabled' }
$script:starts=0
$script:stops=0
function Start-McpCore { $script:starts++ }
function Stop-McpCore { $script:stops++ }
if (Test-Path $McpStopped) { Remove-Item -LiteralPath $McpStopped }
'[]' | Set-Content (Join-Path $McpRuntime 'restart_history.json')
$watchdog = [scriptblock]::Create($body)
1..6 | ForEach-Object { & $watchdog -Once }
if ($script:starts -ne 5 -or $script:stops -ne 5 -or -not (Test-Path $McpStopped)) { throw 'Restart throttle failed' }
& $watchdog -Once
if ($script:starts -ne 5) { throw 'Manual stop was ignored' }
Write-Output 'PASS: duplicate start, occupied port, ownership, recovery, 5/10-minute throttle, manual stop.'
