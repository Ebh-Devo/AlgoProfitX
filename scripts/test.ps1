[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot "common.ps1")
Import-BackendEnvironment

if (-not $env:TEST_DATABASE_URL) {
    throw "TEST_DATABASE_URL is required. Create backend/.env from backend/.env.example."
}

Assert-DatabaseName -DatabaseUrl $env:TEST_DATABASE_URL -ExpectedDatabase "tradeebh_test"
$env:DATABASE_URL = $env:TEST_DATABASE_URL

Invoke-BackendPython -Arguments @("-m", "alembic", "-c", "alembic.ini", "upgrade", "head")
Invoke-BackendPython -Arguments @("-m", "pytest")
