Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$env:QT_QPA_PLATFORM = "offscreen"

$verificationSteps = @(
    @{
        Name      = "format check"
        Command   = "python"
        Arguments = @("-m", "ruff", "format", "--check", ".")
    }
    @{
        Name      = "lint check"
        Command   = "python"
        Arguments = @("-m", "ruff", "check", ".")
    }
    @{
        Name      = "type check"
        Command   = "python"
        Arguments = @("-m", "mypy")
    }
    @{
        Name      = "unittest"
        Command   = "python"
        Arguments = @("-m", "unittest", "discover", "-s", "py_tests", "-v")
    }
    @{
        Name      = "pytest"
        Command   = "python"
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
