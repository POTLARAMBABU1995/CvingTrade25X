$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $pythonExe)) {
  throw "Python virtual environment not found at $pythonExe"
}

Set-Location $repoRoot

& $pythonExe 'db\migration\restore_cving_app.py'
& $pythonExe 'db\migration\validate_cving_app.py'

