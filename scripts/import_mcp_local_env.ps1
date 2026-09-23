$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$envFile = Join-Path $projectRoot ".env"
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) { return }

foreach ($rawLine in [System.IO.File]::ReadAllLines($envFile)) {
  $line = $rawLine.Trim()
  if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { continue }
  $parts = $line.Split(@("="), 2, [System.StringSplitOptions]::None)
  $name = $parts[0].Trim()
  if ($name -notmatch "^(CVING_MCP_|CVING_QUICK_TUNNEL_|CVING_CLOUDFLARE_)[A-Z0-9_]+$") { continue }
  if (Test-Path -LiteralPath "Env:$name") { continue }
  $value = $parts[1].Trim()
  if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
    $value = $value.Substring(1, $value.Length - 2)
  }
  Set-Item -LiteralPath "Env:$name" -Value $value
}
