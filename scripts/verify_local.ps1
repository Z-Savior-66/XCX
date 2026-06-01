Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$cacheRoot = Join-Path $projectRoot ".cache"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython) {
    $pythonCommand = $venvPython
}
else {
    $pythonCommand = "python"
}
$env:QT_QPA_PLATFORM = "offscreen"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPYCACHEPREFIX = Join-Path $cacheRoot "pycache"
New-Item -ItemType Directory -Path $env:PYTHONPYCACHEPREFIX -Force | Out-Null

$verificationSteps = @(
    @{
        Name      = "format check"
        Command   = $pythonCommand
        Arguments = @("-m", "ruff", "format", "--check", ".")
    }
    @{
        Name      = "lint check"
        Command   = $pythonCommand
        Arguments = @("-m", "ruff", "check", ".")
    }
    @{
        Name      = "type check"
        Command   = $pythonCommand
        Arguments = @("-m", "mypy")
    }
    @{
        Name      = "unittest"
        Command   = $pythonCommand
        Arguments = @("-m", "unittest", "discover", "-s", "py_tests", "-v")
    }
    @{
        Name      = "pytest"
        Command   = $pythonCommand
        Arguments = @("-m", "pytest", "py_tests", "-q")
    }
)

Push-Location $projectRoot
try {
    foreach ($step in $verificationSteps) {
        $displayCommand = "$($step.Command) $($step.Arguments -join ' ')"
        $arguments = $step.Arguments

        Write-Host ""
        Write-Host "Starting verification: $($step.Name)"
        Write-Host "Command: $displayCommand"

        & $step.Command @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Verification failed: $displayCommand"
        }
    }

    Write-Host ""
    Write-Host "Local verification passed."
}
catch {
    Write-Error $_
    exit 1
}
finally {
    Pop-Location
}
