[CmdletBinding()]
param(
    [string]$HostName = "localhost",
    [int]$Port = 5432,
    [string]$Superuser = "postgres",
    [string]$PsqlPath,
    [securestring]$SuperuserPassword,
    [switch]$UsePgPass
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($PsqlPath) {
    if (-not (Test-Path -LiteralPath $PsqlPath)) {
        throw "psql was not found at '$PsqlPath'."
    }
    $psqlExecutable = $PsqlPath
}
else {
    $psql = Get-Command psql -ErrorAction SilentlyContinue
    if ($psql) {
        $psqlExecutable = $psql.Source
    }
    else {
        $standardInstall = Get-ChildItem "${env:ProgramFiles}\\PostgreSQL\\*\\bin\\psql.exe" -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            Select-Object -First 1 -ExpandProperty FullName
        if (-not $standardInstall) {
            throw "psql was not found. Install PostgreSQL 16 or later (including command-line tools) and add its bin directory to PATH."
        }
        $psqlExecutable = $standardInstall
    }
}

function ConvertTo-PlainText {
    param([securestring]$Value)

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Invoke-Psql {
    param(
        [Parameter(Mandatory)]
        [string]$Command,
        [switch]$Quiet
    )

    $arguments = @(
        "--host", $HostName,
        "--port", $Port,
        "--username", $Superuser,
        "--dbname", "postgres",
        "--no-password",
        "--set", "ON_ERROR_STOP=1",
        "--command", $Command
    )
    if ($Quiet) {
        $arguments += @("--tuples-only", "--no-align", "--quiet")
    }

    $output = & $psqlExecutable @arguments 2>&1
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        $details = ($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
        throw "psql command failed with exit code $exitCode. $details"
    }

    return ($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
}

function Test-PostgresObject {
    param([Parameter(Mandatory)][string]$Sql)

    # SELECT EXISTS always returns one row, avoiding PowerShell's $null result
    # for a successful zero-row query.
    return ((Invoke-Psql -Command $Sql -Quiet).Trim() -eq "t")
}

$hadPgPassword = Test-Path Env:PGPASSWORD
$previousPgPassword = $env:PGPASSWORD
$managedPgPassword = $false

if (-not $UsePgPass) {
    if (-not $SuperuserPassword) {
        $SuperuserPassword = Read-Host -AsSecureString "Password for PostgreSQL superuser '$Superuser' (press Enter to use .pgpass or trust authentication)"
    }

    if ($SuperuserPassword.Length -gt 0) {
        $env:PGPASSWORD = ConvertTo-PlainText $SuperuserPassword
        $managedPgPassword = $true
    }
}

try {
    Invoke-Psql -Command "SELECT 1" | Out-Null

    if (-not (Test-PostgresObject -Sql "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradebh')")) {
        Invoke-Psql -Command "CREATE ROLE tradebh LOGIN" | Out-Null
        Write-Host "Set the password for application role 'tradebh' when psql prompts."
        Invoke-Psql -Command "\password tradebh" | Out-Null
    }

    foreach ($database in @("tradeebh", "tradeebh_test")) {
        if (-not (Test-PostgresObject -Sql "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = '$database')")) {
            Invoke-Psql -Command "CREATE DATABASE $database OWNER tradebh" | Out-Null
            Write-Host "Created database '$database'."
        }
        else {
            Write-Host "Database '$database' already exists; left unchanged."
        }
    }

    Write-Host "PostgreSQL is ready. Existing roles and databases were left unchanged."
}
finally {
    if ($managedPgPassword) {
        if ($hadPgPassword) {
            $env:PGPASSWORD = $previousPgPassword
        }
        else {
            Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
        }
    }
}
