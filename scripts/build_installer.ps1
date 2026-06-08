param(
    [switch]$Clean,
    [switch]$IncludeOfflineChromium,
    [switch]$SkipVerification,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Utf8NoBomFile {
    param(
        [string]$Path,
        [string]$Content
    )

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Resolve-PythonCommand {
    param(
        [string]$ProjectRoot
    )

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        return $venvPython
    }

    return "python"
}

function Resolve-InnoCompilerPath {
    param(
        [string]$ProjectRoot
    )

    $compilerPath = Join-Path $ProjectRoot "tools\inno\portable\ISCC.exe"
    if (Test-Path $compilerPath) {
        return $compilerPath
    }
    $compilerPath = Join-Path $ProjectRoot "tools\inno\ISCC.exe"
    if (Test-Path $compilerPath) {
        return $compilerPath
    }

    throw "未找到项目内 Inno Setup 编译器。请先准备 tools\inno\ISCC.exe。"
}

function Assert-PyInstallerAvailable {
    param(
        [string]$PythonCommand
    )

    & $PythonCommand -m PyInstaller --version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "未检测到 PyInstaller。请先执行：$PythonCommand -m pip install -r requirements-build.txt"
    }
}

function Resolve-PyInstallerVersionText {
    param(
        [string]$PythonCommand
    )

    $version = & $PythonCommand -m PyInstaller --version 2>$null | Select-Object -First 1
    if ($LASTEXITCODE -ne 0 -or -not $version) {
        return "未安装"
    }
    return $version
}

function Resolve-AppVersion {
    param(
        [string]$ProjectRoot,
        [string]$PythonCommand
    )

    $escapedProjectRoot = $ProjectRoot.Replace("'", "''")
    $version = & $PythonCommand -c "import sys; sys.path.insert(0, r'$escapedProjectRoot'); from desktop_py.version import APP_VERSION; print(APP_VERSION)"
    if ($LASTEXITCODE -ne 0) {
        throw "读取应用版本失败，请检查 desktop_py\\version.py。"
    }
    $normalizedVersion = ($version | Select-Object -First 1).Trim()
    if (-not $normalizedVersion) {
        throw "应用版本不能为空，请检查 desktop_py\\version.py。"
    }
    return $normalizedVersion
}

function Invoke-LocalVerification {
    param(
        [string]$ProjectRoot
    )

    $verifyScript = Join-Path $ProjectRoot "scripts\verify_local.ps1"
    if (-not (Test-Path $verifyScript)) {
        throw "未找到本地验证脚本：scripts\verify_local.ps1"
    }
    Write-Host "开始执行构建前本地验证..."
    & $verifyScript
    if ($LASTEXITCODE -ne 0) {
        throw "构建前本地验证失败，请修复后重新构建。"
    }
}

function Resolve-OfflineRuntimeSource {
    param(
        [string]$ProjectRoot
    )

    $runtimePath = Join-Path $ProjectRoot "ms-playwright"
    if (-not (Test-Path $runtimePath)) {
        throw "未找到离线浏览器运行时目录。请先准备项目根目录下的 ms-playwright。"
    }
    return $runtimePath
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Resolve-PythonCommand -ProjectRoot $projectRoot
$env:PYTHONDONTWRITEBYTECODE = "1"
$cacheRoot = Join-Path $projectRoot ".cache"
$buildCacheRoot = Join-Path $cacheRoot "build"
$distRoot = Join-Path $projectRoot "dist"
$installerSourceRoot = Join-Path $buildCacheRoot "installer-source"
$pyInstallerWorkRoot = Join-Path $buildCacheRoot "pyinstaller"
$appName = "小程序工具"
$appVersion = Resolve-AppVersion -ProjectRoot $projectRoot -PythonCommand $pythonExe
$appPublisher = "本地构建"
$installerSourceDir = Join-Path $installerSourceRoot $appName
$installerExeName = "$appName.exe"
$outputBaseFilename = if ($IncludeOfflineChromium) { "$appName-离线版" } else { "$appName-标准版" }
$appAssetsPath = Join-Path $projectRoot "assets"
$appIconPath = Join-Path $appAssetsPath "app_icon.ico"
$transactionComplaintRulesPath = Join-Path $projectRoot "desktop_py\core\transaction_complaint_rules.json"
$innoCompiler = Resolve-InnoCompilerPath -ProjectRoot $projectRoot
if ($DryRun) {
    Write-Host ""
    Write-Host "══════════════════════════════════════════════"
    Write-Host "  构建 Dry-Run 模式"
    Write-Host "══════════════════════════════════════════════"
    Write-Host "项目根目录:      $projectRoot"
    Write-Host "应用名称:        $appName"
    Write-Host "应用版本:        $appVersion"
    Write-Host "应用发布者:      $appPublisher"
    Write-Host "输出文件名:      $outputBaseFilename"
    Write-Host "应用图标:        $(if (Test-Path $appIconPath) { '存在' } else { '不存在！' })"
    Write-Host "Inno编译器:      $innoCompiler"
    Write-Host "PyInstaller:     $(Resolve-PyInstallerVersionText -PythonCommand $pythonExe)"
    Write-Host "离线运行时:      $(if ($IncludeOfflineChromium) { '包含' } else { '不包含' })"
    if (-not $SkipVerification) { Write-Host "本地验证:        启用" } else { Write-Host "本地验证:        跳过" }
    Write-Host "══════════════════════════════════════════════"
    Write-Host ""
    Write-Host "Dry-Run 模式完成。传入 -IncludeOfflineChromium 包含离线浏览器。"
    exit 0
}
if (-not $SkipVerification) {
    Invoke-LocalVerification -ProjectRoot $projectRoot
}
Assert-PyInstallerAvailable -PythonCommand $pythonExe
if (-not (Test-Path $appIconPath)) {
    throw "未找到应用图标：assets\app_icon.ico"
}
$offlineRuntimeSource = if ($IncludeOfflineChromium) {
    Resolve-OfflineRuntimeSource -ProjectRoot $projectRoot
} else {
    ""
}

$installerScript = if ($Clean) {
    Join-Path $PSScriptRoot "installer_clean.iss"
} else {
    throw "当前仅支持基于干净源目录构建安装包，请传入 -Clean。"
}

Push-Location $projectRoot
try {
    if (-not (Test-Path $distRoot)) {
        New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
    }
    if (Test-Path $installerSourceRoot) {
        Remove-Item -LiteralPath $installerSourceRoot -Recurse -Force
    }
    if (Test-Path $pyInstallerWorkRoot) {
        Remove-Item -LiteralPath $pyInstallerWorkRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $installerSourceRoot -Force | Out-Null

    Write-Host "开始构建安装包..."
    & $pythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --onedir `
        --distpath $installerSourceRoot `
        --workpath $pyInstallerWorkRoot `
        --specpath $installerSourceRoot `
        --name $appName `
        --icon $appIconPath `
        --add-data "$appAssetsPath;assets" `
        --collect-all playwright `
        desktop_main.py

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 构建失败，退出码：$LASTEXITCODE"
    }

    foreach ($name in @(
        "_internal\playwright\driver\package\.local-browsers",
        "_internal\playwright\driver\package\.links"
    )) {
        $target = Join-Path $installerSourceDir $name
        if (Test-Path $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
    }

    foreach ($name in @("data", "storage", "browser_profile", "output")) {
        $target = Join-Path $installerSourceDir $name
        New-Item -ItemType Directory -Path $target -Force | Out-Null
    }

    Write-Utf8NoBomFile -Path (Join-Path $installerSourceDir "data\accounts.json") -Content "[]`n"
    Write-Utf8NoBomFile -Path (Join-Path $installerSourceDir "data\settings.json") -Content @'
{
  "feishu_webhook": "",
  "login_wait_seconds": 120,
  "headless_fetch": true,
  "browser_profile_dir": "",
  "current_main_account_name": "",
  "auto_fetch_push_enabled": false,
  "startup_enabled": false,
  "diagnostic_retention_days": 14
}
'@

    foreach ($name in @("README.md", "requirements.txt")) {
        $source = Join-Path $projectRoot $name
        if (Test-Path $source) {
            Copy-Item -LiteralPath $source -Destination $installerSourceDir -Force
        }
    }

    if (Test-Path $transactionComplaintRulesPath) {
        Copy-Item -LiteralPath $transactionComplaintRulesPath -Destination (Join-Path $installerSourceDir "data") -Force
    }

    if ($IncludeOfflineChromium) {
        $offlineRuntimeTarget = Join-Path $installerSourceDir "ms-playwright"
        Copy-Item -LiteralPath $offlineRuntimeSource -Destination $offlineRuntimeTarget -Recurse -Force
    }

    $tempBuildRoot = Join-Path $env:TEMP ("xcx_build_{0}" -f [guid]::NewGuid())
    $tempSourceDir = Join-Path $tempBuildRoot "app"
    $tempInstallerDir = Join-Path $tempBuildRoot "installer"
    New-Item -ItemType Directory -Path $tempInstallerDir -Force | Out-Null
    Copy-Item -LiteralPath $installerSourceDir -Destination $tempSourceDir -Recurse -Force
    $tempAppIconPath = Join-Path $tempBuildRoot "app_icon.ico"
    Copy-Item -LiteralPath $appIconPath -Destination $tempAppIconPath -Force

    $issContent = Get-Content -LiteralPath $installerScript -Raw
    $defines = @"
#define MyAppName "$appName"
#define MyAppVersion "$appVersion"
#define MyAppPublisher "$appPublisher"
#define MyAppExeName "$installerExeName"
#define MySourceDir "$tempSourceDir"
#define MyOutputBaseFilename "$outputBaseFilename"
#define MyOutputDir "$tempInstallerDir"
#define MyAppIconPath "$tempAppIconPath"

"@
    $tempIssScript = Join-Path $tempBuildRoot "installer.iss"
    Write-Utf8NoBomFile -Path $tempIssScript -Content ($defines + $issContent)

    Push-Location $tempBuildRoot
    try {
        & $innoCompiler $tempIssScript
        if ($LASTEXITCODE -ne 0) {
            throw "Inno Setup 编译失败，退出码：$LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
    if (Test-Path $installerSourceRoot) {
        Remove-Item -LiteralPath $installerSourceRoot -Recurse -Force
    }
    # 将临时目录的输出复制回项目 dist 目录
    $projectInstallerDir = Join-Path $distRoot "installer"
    if (-not (Test-Path $projectInstallerDir)) {
        New-Item -ItemType Directory -Path $projectInstallerDir -Force | Out-Null
    }
    $expectedInstallerPath = Join-Path $tempInstallerDir "$outputBaseFilename.exe"
    if (-not (Test-Path -LiteralPath $expectedInstallerPath)) {
        throw "未找到安装包输出文件：$expectedInstallerPath"
    }
    Copy-Item -LiteralPath $expectedInstallerPath -Destination $projectInstallerDir -Force
    Remove-Item -LiteralPath $tempBuildRoot -Recurse -Force -ErrorAction SilentlyContinue
    if ($IncludeOfflineChromium) {
        Write-Host "离线版安装包构建完成：$(Join-Path $distRoot "installer\$outputBaseFilename.exe")"
    } else {
        Write-Host "标准版安装包构建完成：$(Join-Path $distRoot "installer\$outputBaseFilename.exe")"
    }
}
finally {
    Pop-Location
}
