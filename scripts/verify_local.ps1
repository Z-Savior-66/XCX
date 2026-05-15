Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-VerificationStep {
    param(
        [string]$Name,
        [string]$Command,
        [string[]]$Arguments
    )

    $displayCommand = "$Command $($Arguments -join ' ')"
    Write-Host ""
    Write-Host "开始验证：$Name"
    Write-Host "执行命令：$displayCommand"

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "验证失败：$displayCommand"
    }
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$env:QT_QPA_PLATFORM = "offscreen"

Push-Location $projectRoot
try {
    Invoke-VerificationStep -Name "格式检查" -Command "ruff" -Arguments @("format", "--check", ".")
    Invoke-VerificationStep -Name "静态检查" -Command "ruff" -Arguments @("check", ".")
    Invoke-VerificationStep -Name "类型检查" -Command "python" -Arguments @("-m", "mypy")
    Invoke-VerificationStep -Name "unittest 全量测试" -Command "python" -Arguments @("-m", "unittest", "discover", "-s", "py_tests", "-v")
    Invoke-VerificationStep -Name "pytest 全量测试" -Command "python" -Arguments @("-m", "pytest", "py_tests", "-q")

    Write-Host ""
    Write-Host "本地验证全部通过。"
}
catch {
    Write-Error $_
    exit 1
}
finally {
    Pop-Location
}
