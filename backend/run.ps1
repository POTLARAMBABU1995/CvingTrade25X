$ErrorActionPreference = 'Stop'

if (-not (Test-Path .venv)) {
  python -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt

$envFile = Join-Path (Split-Path $PSScriptRoot -Parent) '.env'
if (Test-Path $envFile) {
  foreach ($line in Get-Content $envFile) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) { continue }
    $parts = $trimmed.Split('=', 2)
    $key = $parts[0].Trim()
    $value = $parts[1].Trim().Trim('"').Trim("'")
    if ($key -and -not (Get-Item "Env:$key" -ErrorAction SilentlyContinue)) {
      Set-Item "Env:$key" $value
    }
  }
}

# Set Oracle defaults if not present
if (-not $env:ORACLE_USER) { $env:ORACLE_USER = 'CVING_APP' }
if (-not $env:ORACLE_PORT) { $env:ORACLE_PORT = '1521' }
if (-not $env:ORACLE_HOST) { $env:ORACLE_HOST = '127.0.0.1' }
if (-not $env:ORACLE_SERVICE_NAME -and -not $env:ORACLE_SERVICE -and -not $env:ORACLE_SID) { $env:ORACLE_SERVICE_NAME = 'cvingpdb.local' }
if (-not $env:ORACLE_PASSWORD) { throw 'ORACLE_PASSWORD must be set via .env or the process environment.' }
if (-not $env:REGISTER_DB_BACKEND) { $env:REGISTER_DB_BACKEND = 'oracle' }
if (-not $env:PORT) { $env:PORT = '5055' }
if (-not $env:FLASK_DEBUG) { $env:FLASK_DEBUG = '0' }

python app.py
