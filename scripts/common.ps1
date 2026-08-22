Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RepositoryRoot {
    return (Split-Path -Parent $PSScriptRoot)
}

function Get-BackendPath {
    return (Join-Path (Get-RepositoryRoot) "backend")
}

function Get-VenvPython {
    $python = Join-Path (Get-RepositoryRoot) ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Virtual environment not found. Run scripts\\bootstrap-windows.ps1 first."
    }

    return $python
}

function Import-BackendEnvironment {
    $environmentFile = Join-Path (Get-BackendPath) ".env"
    if (-not (Test-Path -LiteralPath $environmentFile)) {
        return
    }

    foreach ($line in Get-Content -LiteralPath $environmentFile) {
        $trimmedLine = $line.Trim()
        if (-not $trimmedLine -or $trimmedLine.StartsWith("#")) {
            continue
        }

        if ($trimmedLine -notmatch "^([^=]+)=(.*)$") {
            throw "Invalid line in ${environmentFile}: $line"
        }

        [Environment]::SetEnvironmentVariable(
            $Matches[1].Trim(),
            $Matches[2].Trim(),
            "Process"
        )
    }
}

function Assert-DatabaseName {
    param(
        [Parameter(Mandatory)]
        [string]$DatabaseUrl,
        [Parameter(Mandatory)]
        [string]$ExpectedDatabase
    )

    if ($DatabaseUrl -notmatch "/([^/?#]+)(?:[?#].*)?$") {
        throw "Database URL does not contain a database name."
    }

    if ($Matches[1] -ne $ExpectedDatabase) {
        throw "Expected database '$ExpectedDatabase', but the URL targets '$($Matches[1])'."
    }
}

function Invoke-BackendPython {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $python = Get-VenvPython
    $backend = Get-BackendPath
    Push-Location $backend
    try {
        & $python @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Python command failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}
