[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$NoReload
)

. (Join-Path $PSScriptRoot "common.ps1")
Import-BackendEnvironment

if (-not $env:DATABASE_URL) {
    throw "DATABASE_URL is required. Create backend/.env from backend/.env.example."
}
Assert-DatabaseName -DatabaseUrl $env:DATABASE_URL -ExpectedDatabase "tradeebh"

$arguments = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $Port)
if (-not $NoReload) {
    $arguments += "--reload"
}

Invoke-BackendPython -Arguments $arguments
