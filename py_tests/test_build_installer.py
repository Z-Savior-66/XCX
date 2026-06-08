import unittest
from pathlib import Path

from desktop_py.version import APP_VERSION, __version__

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_installer.ps1"
INSTALLER_ISS_PATH = Path(__file__).resolve().parents[1] / "scripts" / "installer_clean.iss"


class BuildInstallerScriptTestCase(unittest.TestCase):
    def test_build_script_uses_project_inno_compiler(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("tools\\inno\\ISCC.exe", content)
        self.assertIn("Resolve-InnoCompilerPath", content)

    def test_build_script_collects_playwright_driver_assets(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("--collect-all playwright", content)
        self.assertIn("_internal\\playwright\\driver\\package\\.local-browsers", content)

    def test_installer_uses_runtime_data_for_blocked_accounts(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        installer_content = INSTALLER_ISS_PATH.read_text(encoding="utf-8")

        self.assertNotIn("desktop_py\\core\\blocked_accounts.json", content)
        self.assertNotIn("blocked_accounts.json", installer_content)

    def test_installer_output_dir_is_defined_by_build_script(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        installer_content = INSTALLER_ISS_PATH.read_text(encoding="utf-8")

        self.assertIn('#define MyOutputDir "$tempInstallerDir"', content)
        self.assertIn("#ifndef MyOutputDir", installer_content)
        self.assertIn("OutputDir={#MyOutputDir}", installer_content)

    def test_build_script_does_not_remove_shared_temp_dist_directory(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertNotIn('Join-Path $env:TEMP "dist"', content)
        self.assertNotIn('Remove-Item -LiteralPath (Join-Path $env:TEMP "dist")', content)

    def test_build_script_uses_unique_temp_build_root(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("[guid]::NewGuid()", content)
        self.assertIn('Join-Path $env:TEMP ("xcx_build_{0}" -f [guid]::NewGuid())', content)
        self.assertNotIn('$tempBuildRoot = Join-Path $env:TEMP "xcx_build"', content)

    def test_build_script_checks_inno_exit_code_and_expected_installer(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("& $innoCompiler $tempIssScript", content)
        self.assertIn("if ($LASTEXITCODE -ne 0)", content)
        self.assertIn("Inno Setup 编译失败", content)
        self.assertIn('$expectedInstallerPath = Join-Path $tempInstallerDir "$outputBaseFilename.exe"', content)
        self.assertIn("Test-Path -LiteralPath $expectedInstallerPath", content)
        self.assertIn("未找到安装包输出文件", content)
        self.assertIn("Copy-Item -LiteralPath $expectedInstallerPath", content)

    def test_build_script_checks_pyinstaller_build_exit_code(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        start = content.index("& $pythonExe -m PyInstaller `")
        end = content.index("foreach ($name in @(")
        build_block = content[start:end]

        self.assertIn("if ($LASTEXITCODE -ne 0)", build_block)
        self.assertIn("PyInstaller 构建失败", build_block)

    def test_build_script_always_checks_expected_installer_path(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        expected_path_index = content.index(
            '$expectedInstallerPath = Join-Path $tempInstallerDir "$outputBaseFilename.exe"'
        )
        temp_dir_guard_index = content.find("if (Test-Path $tempInstallerDir)")

        self.assertEqual(temp_dir_guard_index, -1)
        self.assertIn("if (-not (Test-Path -LiteralPath $expectedInstallerPath))", content[expected_path_index:])
        self.assertIn("Copy-Item -LiteralPath $expectedInstallerPath", content[expected_path_index:])

    def test_build_script_places_temporary_outputs_under_cache_root(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        installer_content = INSTALLER_ISS_PATH.read_text(encoding="utf-8")

        self.assertIn('$cacheRoot = Join-Path $projectRoot ".cache"', content)
        self.assertIn('$env:PYTHONDONTWRITEBYTECODE = "1"', content)
        self.assertIn('$buildCacheRoot = Join-Path $cacheRoot "build"', content)
        self.assertIn('$installerSourceRoot = Join-Path $buildCacheRoot "installer-source"', content)
        self.assertIn('$pyInstallerWorkRoot = Join-Path $buildCacheRoot "pyinstaller"', content)
        self.assertIn("--workpath $pyInstallerWorkRoot", content)
        self.assertIn('MySourceDir "..\\.cache\\build\\installer-source\\小程序工具"', installer_content)

    def test_build_script_requires_clean_mode(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn('throw "当前仅支持基于干净源目录构建安装包，请传入 -Clean。"', content)

    def test_build_script_supports_offline_runtime_mode(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("[switch]$IncludeOfflineChromium", content)
        self.assertIn("Resolve-OfflineRuntimeSource -ProjectRoot $projectRoot", content)
        self.assertIn(
            "Copy-Item -LiteralPath $offlineRuntimeSource -Destination $offlineRuntimeTarget -Recurse -Force", content
        )

    def test_build_script_runs_local_verification_by_default(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("[switch]$SkipVerification", content)
        self.assertIn('Join-Path $ProjectRoot "scripts\\verify_local.ps1"', content)
        self.assertIn("Invoke-LocalVerification -ProjectRoot $projectRoot", content)
        self.assertIn("构建前本地验证失败，请修复后重新构建。", content)

    def test_build_script_copies_transaction_complaint_rules(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("desktop_py\\core\\transaction_complaint_rules.json", content)
        self.assertIn(
            'Copy-Item -LiteralPath $transactionComplaintRulesPath -Destination (Join-Path $installerSourceDir "data") -Force',
            content,
        )

    def test_build_script_passes_release_metadata_to_inno(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("function Resolve-AppVersion", content)
        self.assertIn("from desktop_py.version import APP_VERSION", content)
        self.assertIn("$appVersion = Resolve-AppVersion -ProjectRoot $projectRoot", content)
        self.assertNotIn('$appVersion = "1.0.0"', content)
        self.assertIn('$appPublisher = "本地构建"', content)
        self.assertIn('#define MyAppVersion "$appVersion"', content)
        self.assertIn('#define MyAppPublisher "$appPublisher"', content)
        self.assertIn('#define MyAppIconPath "$tempAppIconPath"', content)
        self.assertIn("--icon $appIconPath", content)
        self.assertIn('--add-data "$appAssetsPath;assets"', content)

    def test_build_script_resolves_python_command_once_and_reuses_it(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("function Resolve-PythonCommand", content)
        self.assertEqual(content.count("Resolve-PythonCommand -ProjectRoot $projectRoot"), 1)
        self.assertIn("$pythonExe = Resolve-PythonCommand -ProjectRoot $projectRoot", content)
        self.assertIn("Resolve-AppVersion -ProjectRoot $projectRoot -PythonCommand $pythonExe", content)
        self.assertIn("Assert-PyInstallerAvailable -PythonCommand $pythonExe", content)
        self.assertIn("Resolve-PyInstallerVersionText -PythonCommand $pythonExe", content)
        self.assertIn("& $pythonExe -m PyInstaller", content)

    def test_build_script_checks_pyinstaller_exit_code(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        start = content.index("function Assert-PyInstallerAvailable")
        end = content.index("function Resolve-PyInstallerVersionText")
        function_body = content[start:end]

        self.assertIn("& $PythonCommand -m PyInstaller --version | Out-Null", function_body)
        self.assertIn("if ($LASTEXITCODE -ne 0)", function_body)
        self.assertIn(
            'throw "未检测到 PyInstaller。请先执行：$PythonCommand -m pip install -r requirements-build.txt"',
            function_body,
        )

    def test_build_script_does_not_use_bare_python_for_build_checks(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertNotIn("python -m PyInstaller --version", content)
        self.assertNotIn("$version = & python -c", content)

    def test_version_module_exposes_single_app_version(self):
        self.assertEqual(APP_VERSION, "1.0.0")
        self.assertEqual(__version__, APP_VERSION)

    def test_installer_preserves_user_data_directories(self):
        content = INSTALLER_ISS_PATH.read_text(encoding="utf-8")

        self.assertIn("[Dirs]", content)
        self.assertIn('Name: "{app}\\data"', content)
        self.assertIn('Name: "{app}\\storage"', content)
        self.assertIn('Name: "{app}\\browser_profile"', content)
        self.assertIn('Name: "{app}\\output"', content)
        self.assertIn('Excludes: "data\\*,storage\\*,browser_profile\\*,output\\*"', content)
        self.assertIn(
            'Source: "{#MySourceDir}\\data\\accounts.json"; DestDir: "{app}\\data"; Flags: ignoreversion onlyifdoesntexist',
            content,
        )
        self.assertIn(
            'Source: "{#MySourceDir}\\data\\settings.json"; DestDir: "{app}\\data"; Flags: ignoreversion onlyifdoesntexist',
            content,
        )
        self.assertIn(
            'Source: "{#MySourceDir}\\data\\transaction_complaint_rules.json"; DestDir: "{app}\\data"; Flags: ignoreversion onlyifdoesntexist',
            content,
        )

    def test_build_script_initial_settings_include_startup_option(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn('"startup_enabled": false', content)

    def test_installer_uses_branded_release_metadata(self):
        content = INSTALLER_ISS_PATH.read_text(encoding="utf-8")

        self.assertIn("AppVersion={#MyAppVersion}", content)
        self.assertIn("AppVerName={#MyAppName} {#MyAppVersion}", content)
        self.assertIn("AppPublisher={#MyAppPublisher}", content)
        self.assertIn("SetupIconFile={#MyAppIconPath}", content)
        self.assertIn("VersionInfoVersion={#MyAppVersion}", content)
        self.assertIn("VersionInfoCompany={#MyAppPublisher}", content)

    def test_installer_uses_chinese_professional_wizard_text(self):
        content = INSTALLER_ISS_PATH.read_text(encoding="utf-8")

        self.assertIn("SetupAppRunningError=检测到 %1 正在运行。", content)
        self.assertIn("WelcomeLabel1=欢迎安装 [name]", content)
        self.assertIn("安装前会保留已有账号配置、浏览器资料和历史输出", content)
        self.assertIn("FinishedLabelNoIcons=[name] 已安装完成。", content)
        self.assertIn("已有账号配置、浏览器资料和历史输出会继续保留", content)
        self.assertIn("ClickFinish=点击“完成”退出安装程序。", content)
        self.assertIn("ShowReadmeCheck=是，我想查看 README 文件", content)

    def test_installer_translates_built_in_running_application_page(self):
        content = INSTALLER_ISS_PATH.read_text(encoding="utf-8")

        self.assertIn("ApplicationsFound=以下程序正在使用安装程序需要更新的文件。", content)
        self.assertIn("ApplicationsFound2=以下程序正在使用安装程序需要更新的文件。", content)
        self.assertIn("CloseApplications=自动关闭这些程序(&A)", content)
        self.assertIn("DontCloseApplications=不关闭这些程序(&D)", content)
        self.assertIn("ErrorCloseApplications=安装程序无法自动关闭全部程序。", content)

    def test_installer_translates_install_progress_messages(self):
        content = INSTALLER_ISS_PATH.read_text(encoding="utf-8")

        self.assertIn("StatusClosingApplications=正在关闭程序...", content)
        self.assertIn("StatusExtractFiles=正在解压文件...", content)
        self.assertIn("StatusCreateIcons=正在创建快捷方式...", content)
        self.assertIn("StatusSavingUninstall=正在保存卸载信息...", content)
        self.assertIn("StatusRunProgram=正在完成安装...", content)
        self.assertIn("StatusRestartingApplications=正在重新启动程序...", content)

    def test_installer_closes_running_app_automatically(self):
        content = INSTALLER_ISS_PATH.read_text(encoding="utf-8")

        self.assertIn("function IsAppRunning(): Boolean;", content)
        self.assertIn("function CloseRunningApp(): Boolean;", content)
        self.assertIn("function InitializeSetup(): Boolean;", content)
        self.assertIn("function InitializeUninstall(): Boolean;", content)
        self.assertIn("tasklist /FI", content)
        self.assertIn("IMAGENAME eq {#MyAppExeName}", content)
        self.assertIn("taskkill /IM {#MyAppExeName} /T /F", content)
        self.assertIn("检测到 {#MyAppName} 仍在运行，安装程序无法自动关闭它。", content)
        self.assertIn("请手动关闭程序窗口和托盘图标后重新运行安装程序。", content)
        self.assertNotIn("MB_RETRYCANCEL", content)
        self.assertNotIn("请先关闭程序窗口和托盘图标，然后点击“重试”继续安装。", content)
        self.assertNotIn("请先关闭程序窗口和托盘图标，然后点击“重试”继续卸载。", content)

    def test_installer_asks_before_removing_business_data(self):
        content = INSTALLER_ISS_PATH.read_text(encoding="utf-8")

        self.assertIn("procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);", content)
        self.assertIn("是否同时删除本机业务数据？", content)
        self.assertIn("MB_YESNO or MB_DEFBUTTON2", content)
        self.assertIn("DelTree(ExpandConstant('{app}\\data')", content)
        self.assertIn("DelTree(ExpandConstant('{app}\\storage')", content)
        self.assertIn("DelTree(ExpandConstant('{app}\\browser_profile')", content)
        self.assertIn("DelTree(ExpandConstant('{app}\\output')", content)


if __name__ == "__main__":
    unittest.main()
