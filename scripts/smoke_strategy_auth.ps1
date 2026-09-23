param(
  [string]$BaseUrl = $(if ($env:CVING_BASE_URL) { $env:CVING_BASE_URL } else { 'http://127.0.0.1:5055' }),
  [string]$Identifier = $env:CVING_SMOKE_IDENTIFIER,
  [string]$Password = $env:CVING_SMOKE_PASSWORD,
  [string]$Mpin = $env:CVING_SMOKE_MPIN,
  [string]$SessionToken = $env:CVING_SESSION_TOKEN,
  [ValidateSet('daily', 'weekly', 'monthly', 'yearly')]
  [string]$Timeframe = 'daily',
  [switch]$Refresh,
  [switch]$KeepSession,
  [int]$TimeoutSec = 120
)

$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $projectRoot

function Join-SmokeUrl {
  param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$Path
  )
  $normalizedRoot = $Root.TrimEnd('/')
  $normalizedPath = if ($Path.StartsWith('/')) { $Path } else { "/$Path" }
  return "$normalizedRoot$normalizedPath"
}

function ConvertFrom-SmokeJson {
  param([string]$Text)
  if ([string]::IsNullOrWhiteSpace($Text)) {
    return $null
  }
  try {
    return $Text | ConvertFrom-Json
  } catch {
    return $null
  }
}

function Get-ObjectProperty {
  param(
    $Object,
    [Parameter(Mandatory = $true)][string[]]$Names
  )
  if ($null -eq $Object) {
    return $null
  }
  foreach ($name in $Names) {
    $property = $Object.PSObject.Properties[$name]
    if ($null -ne $property -and $null -ne $property.Value -and "$($property.Value)".Trim() -ne '') {
      return $property.Value
    }
  }
  return $null
}

function Get-ArrayCount {
  param($Value)
  if ($null -eq $Value) {
    return $null
  }
  if ($Value -is [System.Array]) {
    return $Value.Count
  }
  if ($Value -is [System.Collections.ICollection]) {
    return $Value.Count
  }
  return $null
}

function Get-SmokeRowsCount {
  param($Json)
  if ($null -eq $Json) {
    return $null
  }
  $direct = Get-ArrayCount -Value $Json
  if ($null -ne $direct) {
    return $direct
  }
  foreach ($propertyName in @('rows', 'data', 'items', 'results')) {
    $count = Get-ArrayCount -Value (Get-ObjectProperty -Object $Json -Names @($propertyName))
    if ($null -ne $count) {
      return $count
    }
  }
  $payload = Get-ObjectProperty -Object $Json -Names @('payload')
  if ($null -ne $payload) {
    $count = Get-ArrayCount -Value (Get-ObjectProperty -Object $payload -Names @('rows'))
    if ($null -ne $count) {
      return $count
    }
  }
  return $null
}

function Get-SmokeMeta {
  param($Json)
  if ($null -eq $Json) {
    return $null
  }
  return Get-ObjectProperty -Object $Json -Names @('meta')
}

function Get-SmokeLatestDate {
  param($Json)
  $meta = Get-SmokeMeta -Json $Json
  $value = Get-ObjectProperty -Object $Json -Names @(
    'latestLtcDate',
    'maxLtcDate',
    'ltcDate',
    'ltc_date',
    'as_of_date',
    'tradingDate',
    'tradeDate'
  )
  if ($null -ne $value) {
    return $value
  }
  return Get-ObjectProperty -Object $meta -Names @(
    'latestLtcDate',
    'maxLtcDate',
    'ltcDate',
    'ltc_date',
    'endDate',
    'cutoffDateIso',
    'as_of_date',
    'tradingDate',
    'tradeDate'
  )
}

function Get-SmokeStaleReasons {
  param($Json)
  $meta = Get-SmokeMeta -Json $Json
  $value = Get-ObjectProperty -Object $Json -Names @('staleReasons', 'stale_reasons')
  if ($null -eq $value) {
    $value = Get-ObjectProperty -Object $meta -Names @('staleReasons', 'stale_reasons')
  }
  if ($null -eq $value) {
    return ''
  }
  if ($value -is [System.Array]) {
    return (($value | ForEach-Object { "$_".Trim() } | Where-Object { $_ }) -join ',')
  }
  return "$value"
}

function Get-SmokeFlag {
  param(
    $Json,
    [Parameter(Mandatory = $true)][string[]]$Names
  )
  $meta = Get-SmokeMeta -Json $Json
  $value = Get-ObjectProperty -Object $Json -Names $Names
  if ($null -eq $value) {
    $value = Get-ObjectProperty -Object $meta -Names $Names
  }
  if ($null -eq $value) {
    return ''
  }
  return "$value"
}

function Invoke-SmokeRequest {
  param(
    [Parameter(Mandatory = $true)][string]$Method,
    [Parameter(Mandatory = $true)][string]$Path,
    [hashtable]$Headers = @{},
    $Body = $null
  )

  $uri = Join-SmokeUrl -Root $BaseUrl -Path $Path
  $requestHeaders = @{}
  foreach ($key in $Headers.Keys) {
    $requestHeaders[$key] = $Headers[$key]
  }
  if (-not $requestHeaders.ContainsKey('X-Request-ID')) {
    $requestHeaders['X-Request-ID'] = "CVT25X-SMOKE-$([guid]::NewGuid().ToString('N').Substring(0, 12).ToUpperInvariant())"
  }

  $parameters = @{
    Method = $Method
    Uri = $uri
    Headers = $requestHeaders
    TimeoutSec = $TimeoutSec
    UseBasicParsing = $true
    ErrorAction = 'Stop'
  }
  if ($null -ne $Body) {
    $parameters['Body'] = ($Body | ConvertTo-Json -Depth 12)
    $parameters['ContentType'] = 'application/json'
  }

  $timer = [System.Diagnostics.Stopwatch]::StartNew()
  try {
    $response = Invoke-WebRequest @parameters
    $timer.Stop()
    $content = [string]$response.Content
    $json = ConvertFrom-SmokeJson -Text $content
    return [pscustomobject]@{
      Ok = $true
      Method = $Method
      Path = $Path
      Uri = $uri
      StatusCode = [int]$response.StatusCode
      DurationMs = [int]$timer.ElapsedMilliseconds
      RequestId = [string]$response.Headers['X-Request-ID']
      Content = $content
      Json = $json
      Error = ''
    }
  } catch {
    $timer.Stop()
    $statusCode = 0
    $content = ''
    $requestId = ''
    $response = $_.Exception.Response
    if ($null -ne $response) {
      try {
        $statusCode = [int]$response.StatusCode
      } catch {
        $statusCode = 0
      }
      try {
        $requestId = [string]$response.Headers['X-Request-ID']
      } catch {
        $requestId = ''
      }
      try {
        $stream = $response.GetResponseStream()
        if ($null -ne $stream) {
          $reader = New-Object System.IO.StreamReader($stream)
          $content = $reader.ReadToEnd()
        }
      } catch {
        $content = ''
      }
    }
    $json = ConvertFrom-SmokeJson -Text $content
    return [pscustomobject]@{
      Ok = $false
      Method = $Method
      Path = $Path
      Uri = $uri
      StatusCode = $statusCode
      DurationMs = [int]$timer.ElapsedMilliseconds
      RequestId = $requestId
      Content = $content
      Json = $json
      Error = $_.Exception.Message
    }
  }
}

function Get-SessionTokenFromLoginResponse {
  param($Json)
  if ($null -eq $Json) {
    return ''
  }
  $token = Get-ObjectProperty -Object $Json -Names @('session_token')
  if ($null -ne $token) {
    return "$token"
  }
  $session = Get-ObjectProperty -Object $Json -Names @('session')
  $token = Get-ObjectProperty -Object $session -Names @('token')
  if ($null -ne $token) {
    return "$token"
  }
  return ''
}

function New-AuthHeaders {
  param([Parameter(Mandatory = $true)][string]$Token)
  return @{
    Authorization = "Bearer $Token"
    'X-Session-Token' = $Token
    'X-Client-Action' = 'strategy-auth-smoke'
    'X-Client-Component' = 'scripts/smoke_strategy_auth.ps1'
  }
}

function New-StrategyQueryPath {
  param(
    [Parameter(Mandatory = $true)][string]$Endpoint,
    [Parameter(Mandatory = $true)][string]$QueryKey
  )
  $pairs = [System.Collections.Generic.List[string]]::new()
  $pairs.Add("$QueryKey=$([uri]::EscapeDataString($Timeframe))")
  if ($Refresh) {
    $pairs.Add('refresh=1')
  }
  return "$Endpoint?$($pairs -join '&')"
}

$createdSession = $false
$token = "$SessionToken".Trim()

if (-not $token) {
  if ([string]::IsNullOrWhiteSpace($Identifier) -or ([string]::IsNullOrWhiteSpace($Password) -and [string]::IsNullOrWhiteSpace($Mpin))) {
    throw "Provide -SessionToken or set CVING_SESSION_TOKEN, or provide -Identifier with -Password/-Mpin (or CVING_SMOKE_IDENTIFIER plus CVING_SMOKE_PASSWORD/CVING_SMOKE_MPIN)."
  }

  $loginBody = @{
    identifier = $Identifier
  }
  if (-not [string]::IsNullOrWhiteSpace($Password)) {
    $loginBody['password'] = $Password
  } else {
    $loginBody['mpin'] = $Mpin
  }

  Write-Host "Logging in through /api/auth/login as $Identifier..."
  $loginResponse = Invoke-SmokeRequest -Method 'POST' -Path '/api/auth/login' -Body $loginBody
  if (-not $loginResponse.Ok) {
    $message = Get-ObjectProperty -Object $loginResponse.Json -Names @('message', 'error', 'detail')
    if (-not $message) {
      $message = $loginResponse.Error
    }
    throw "Login failed. status=$($loginResponse.StatusCode) requestId=$($loginResponse.RequestId) message=$message"
  }

  $token = Get-SessionTokenFromLoginResponse -Json $loginResponse.Json
  if ([string]::IsNullOrWhiteSpace($token)) {
    throw 'Login succeeded but no session token was returned.'
  }
  $createdSession = $true
}

$authHeaders = New-AuthHeaders -Token $token

Write-Host "Validating session with /api/auth/session..."
$sessionResponse = Invoke-SmokeRequest -Method 'GET' -Path '/api/auth/session' -Headers $authHeaders
if (-not $sessionResponse.Ok) {
  $message = Get-ObjectProperty -Object $sessionResponse.Json -Names @('message', 'error', 'detail')
  if (-not $message) {
    $message = $sessionResponse.Error
  }
  throw "Session validation failed. status=$($sessionResponse.StatusCode) requestId=$($sessionResponse.RequestId) message=$message"
}

$targets = @(
  @{
    Name = 'bhramhastra-page'
    Kind = 'page'
    Method = 'GET'
    Path = '/app/strategy/bhramhastra'
    ClientPage = '/app/strategy/bhramhastra'
  },
  @{
    Name = 'bhramhastra-data'
    Kind = 'strategy'
    Method = 'GET'
    Path = (New-StrategyQueryPath -Endpoint '/api/bhramhastra' -QueryKey 'timeframe')
    ClientPage = '/app/strategy/bhramhastra'
  },
  @{
    Name = 'bhramhastra-last-ltc'
    Kind = 'last-ltc'
    Method = 'GET'
    Path = '/api/bhramhastra/last-ltc-date'
    ClientPage = '/app/strategy/bhramhastra'
  },
  @{
    Name = 'bhramhaputra-page'
    Kind = 'page'
    Method = 'GET'
    Path = '/app/strategy/bhramhaputra'
    ClientPage = '/app/strategy/bhramhaputra'
  },
  @{
    Name = 'bhramhaputra-data'
    Kind = 'strategy'
    Method = 'GET'
    Path = (New-StrategyQueryPath -Endpoint '/api/bhramhaputra' -QueryKey 'tf')
    ClientPage = '/app/strategy/bhramhaputra'
  },
  @{
    Name = 'bhramhaputra-last-ltc'
    Kind = 'last-ltc'
    Method = 'GET'
    Path = '/api/bhramhaputra/last-ltc-date'
    ClientPage = '/app/strategy/bhramhaputra'
  }
)

Write-Host "Probing strategy routes at $BaseUrl with timeframe=$Timeframe refresh=$($Refresh.IsPresent)..."
$results = @()
foreach ($target in $targets) {
  $headers = @{}
  foreach ($key in $authHeaders.Keys) {
    $headers[$key] = $authHeaders[$key]
  }
  $headers['X-Client-Page'] = $target.ClientPage

  $response = Invoke-SmokeRequest -Method $target.Method -Path $target.Path -Headers $headers
  $json = $response.Json
  $rows = if ($target.Kind -eq 'strategy') { Get-SmokeRowsCount -Json $json } else { $null }
  $latestDate = Get-SmokeLatestDate -Json $json
  $stale = Get-SmokeFlag -Json $json -Names @('stale', 'is_stale')
  $refreshing = Get-SmokeFlag -Json $json -Names @('refreshing')
  $cached = Get-SmokeFlag -Json $json -Names @('cached')
  $statusText = Get-ObjectProperty -Object $json -Names @('status', 'message', 'error')
  $total = Get-ObjectProperty -Object $json -Names @('total', 'totalRows', 'total_rows', 'count', 'rowCount', 'row_count')
  $pageShell = ''
  if ($target.Kind -eq 'page') {
    if ($response.Content -match '<div[^>]+id=["'']root["'']' -or $response.Content -match 'react-assets' -or $response.Content -match 'React shell') {
      $pageShell = 'yes'
    } else {
      $pageShell = 'unknown'
    }
  }

  $results += [pscustomobject]@{
    Target = $target.Name
    Status = $response.StatusCode
    Ms = $response.DurationMs
    Rows = $rows
    Total = $total
    LatestDate = $latestDate
    Stale = $stale
    Refreshing = $refreshing
    Cached = $cached
    StaleReasons = Get-SmokeStaleReasons -Json $json
    PageShell = $pageShell
    RequestId = $response.RequestId
    Detail = $statusText
    Error = $response.Error
  }
}

$results | Format-Table -AutoSize

$failed = @($results | Where-Object { $_.Status -lt 200 -or $_.Status -ge 300 })
$unauthorized = @($results | Where-Object { $_.Status -eq 401 })

if ($createdSession -and -not $KeepSession) {
  try {
    [void](Invoke-SmokeRequest -Method 'POST' -Path '/api/auth/logout' -Headers $authHeaders -Body @{})
  } catch {
    Write-Warning "Smoke check completed, but logout failed: $($_.Exception.Message)"
  }
}

if ($unauthorized.Count -gt 0) {
  throw "Smoke check reached 401 on authenticated probes. Check token/session validity before debugging stale strategy status."
}

if ($failed.Count -gt 0) {
  throw "Smoke check failed for $($failed.Count) target(s). Review the table above and backend logs using RequestId."
}

Write-Host "Auth-aware strategy smoke check passed without 401 responses."
