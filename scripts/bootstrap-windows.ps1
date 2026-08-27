[CmdletBinding()]
param(
    [string]$PythonCommand = "python"
)

. (Join-Path $PSScriptRoot "common.ps1")

$python = Get-Command $PythonCommand -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python 3.13 was not found. Install CPython 3.13 x64 and ensure '$PythonCommand' is on PATH."
}

$version = & $python.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $version.Trim() -ne "3.13") {
    throw "AlgoProfitX supports Python 3.13. Found '$($version.Trim())'."
}

$root = Get-RepositoryRoot
$venv = Join-Path $root ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating virtual environment at $venv"
    & $python.Source -m venv $venv
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create the virtual environment."
    }
}

$lockFile = Join-Path (Get-BackendPath) "requirements.lock"
Write-Host "Installing pinned dependencies from backend/requirements.lock"
& $venvPython -m pip install --requirement $lockFile
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

$environmentFile = Join-Path (Get-BackendPath) ".env"
if (-not (Test-Path -LiteralPath $environmentFile)) {
    Write-Warning "Create backend/.env from backend/.env.example before running migrations or the API."
}

Write-Host "Bootstrap complete."
