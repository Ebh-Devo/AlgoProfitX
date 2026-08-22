[CmdletBinding()]
param(
    [ValidateSet("Development", "Test")]
    [string]$Target = "Development"
)

. (Join-Path $PSScriptRoot "common.ps1")
Import-BackendEnvironment

if ($Target -eq "Test") {
    if (-not $env:TEST_DATABASE_URL) {
        throw "TEST_DATABASE_URL is required to migrate the test database."
    }
    Assert-DatabaseName -DatabaseUrl $env:TEST_DATABASE_URL -ExpectedDatabase "tradeebh_test"
    $env:DATABASE_URL = $env:TEST_DATABASE_URL
}
else {
    if (-not $env:DATABASE_URL) {
        throw "DATABASE_URL is required. Create backend/.env from backend/.env.example."
    }
    Assert-DatabaseName -DatabaseUrl $env:DATABASE_URL -ExpectedDatabase "tradeebh"
}

Invoke-BackendPython -Arguments @("-m", "alembic", "-c", "alembic.ini", "upgrade", "head")
Invoke-BackendPython -Arguments @("-m", "alembic", "-c", "alembic.ini", "current", "--check-heads")
Write-Host "$Target migrations are at head."
