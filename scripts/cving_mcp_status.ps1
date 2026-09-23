[CmdletBinding()]
param([switch]$AsJson)
. (Join-Path $PSScriptRoot 'mcp_common.ps1')
$code = Get-McpHttpCode 'http://127.0.0.1:1729/mcp'
$health = Get-McpHttpCode 'http://127.0.0.1:1729/health'
$mode = Get-CloudflareMode
$url = Get-McpPublicUrl
$remote = 0
if ($url -and $mode -ne 'disabled') { $remote = Get-McpHttpCode $url }
$listeners = @(Get-McpListeners)
$task = Get-ScheduledTask -TaskName 'CVING_MCP_AutoStart' -ErrorAction SilentlyContinue
$service = Get-Service cloudflared -ErrorAction SilentlyContinue
$heartbeat = Join-Path $McpRuntime 'watchdog.heartbeat'
$watchdog = 'INACTIVE'
if ((Test-Path $heartbeat) -and ((Get-Date).ToUniversalTime() - (Get-Item $heartbeat).LastWriteTimeUtc).TotalSeconds -lt 240 -and -not (Test-Path $McpStopped)) { $watchdog = 'ACTIVE' }
$overall = 'DOWN'
if ($code -eq 401) {
  $overall = 'HEALTHY'
  if ($health -ne 200 -or ($mode -ne 'disabled' -and $remote -ne 401)) { $overall = 'DEGRADED' }
}
$status = [ordered]@{
  MCP = $(if ($code) {'RUNNING'} else {'STOPPED'})
  PID = @($listeners | ForEach-Object OwningProcess)
  LocalEndpoint = 'http://127.0.0.1:1729/mcp'
  Port = $(if ($listeners.Count) {'LISTENING'} else {'CLOSED'})
  Authentication = $(if ($code -eq 401) {'ENABLED: 401 EXPECTED'} else {'UNVERIFIED'})
  LocalHttp = $code
  Oracle = $(if ($health -eq 200) {'REACHABLE'} elseif ($health -eq 503) {'UNAVAILABLE'} else {'UNVERIFIED'})
  CloudflareMode = $mode
  CloudflaredService = $(if ($service) {$service.Status.ToString()} else {'NOT INSTALLED'})
  PublicUrl = $url
  PublicConnectivity = $(if ($mode -eq 'disabled') {'DISABLED'} elseif ($remote -eq 401) {'REACHABLE: 401 EXPECTED'} else {'UNREACHABLE'})
  Autostart = $(if ($task -and $task.State -ne 'Disabled') {'ENABLED'} else {'DISABLED'})
  Watchdog = $watchdog
  Overall = $overall
}
if ($AsJson) { $status | ConvertTo-Json } else { [pscustomobject]$status | Format-List }
