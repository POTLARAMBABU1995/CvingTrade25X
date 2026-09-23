. (Join-Path $PSScriptRoot 'mcp_common.ps1')
$script:CloudflareOwnership = Join-Path $McpRuntime 'cloudflare_service.json'
function Get-OwnedCloudflareService {
  $service = Get-CimInstance Win32_Service -Filter "Name='cloudflared'"
  if (-not $service) { return $null }
  if (-not (Test-Path $CloudflareOwnership)) { throw 'Existing cloudflared service is unmanaged; left untouched.' }
  $record = Get-Content -Raw $CloudflareOwnership | ConvertFrom-Json
  if ($record.root -ne $McpRoot -or $record.image_path -ne $service.PathName) { throw 'Cloudflare service ownership mismatch.' }
  return $service
}
function Get-NamedTunnelArguments {
  if ((Get-CloudflareMode) -ne 'named') { throw 'Named tunnel mode is required.' }
  $publicUrl = Get-McpPublicUrl
  if (-not $publicUrl) { throw 'Set CVING_MCP_PUBLIC_HOST or CVING_MCP_PUBLIC_URL.' }
  $tunnelId = $env:CVING_CLOUDFLARE_TUNNEL_ID
  if ($tunnelId -notmatch '^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$') { throw 'Set the existing named tunnel UUID.' }
  $config = $env:CVING_CLOUDFLARE_CONFIG
  if (-not $config -or -not [IO.Path]::IsPathRooted($config) -or -not (Test-Path -LiteralPath $config)) { throw 'Set an absolute Cloudflare config file path.' }
  $binary = Get-CloudflaredBinary
  # Use Cloudflare's parser rather than interpreting YAML in PowerShell.
  & $binary tunnel --config $config ingress validate *> $null
  if ($LASTEXITCODE -ne 0) { throw 'Cloudflare ingress configuration is invalid.' }
  # Restrict this service to one local MCP route and a deny catch-all.
  $text = Get-Content -Raw -LiteralPath $config
  $services = [regex]::Matches($text, '(?m)^\s*(?:-\s*)?service:\s*["'']?([^\s"''#]+)')
  if ($services.Count -ne 2 -or $services[0].Groups[1].Value -ne 'http://127.0.0.1:1729' -or $services[1].Groups[1].Value -ne 'http_status:404') { throw 'Named tunnel must route only to 127.0.0.1:1729 with a final http_status:404 rule.' }
  $hostName = ([uri]$publicUrl).Host
  if ($text -notmatch ('(?m)^\s*-?\s*hostname:\s*["'']?' + [regex]::Escape($hostName) + '["'']?\s*$')) { throw 'Tunnel hostname does not match public URL.' }
  return @{binary=$binary; config=$config; tunnel=$tunnelId}
}
