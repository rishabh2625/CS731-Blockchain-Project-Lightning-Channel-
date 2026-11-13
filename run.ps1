param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot '.venv312\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $PythonPath)) { $PythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Create the Python environment as described in README.md first.' }
Push-Location $ProjectRoot
try {
    & $PythonPath -m lnchannel @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }
