#ifndef MyAppName
  #define MyAppName "小程序工具"
#endif
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#ifndef MyAppPublisher
  #define MyAppPublisher "本地构建"
#endif
#ifndef MyAppExeName
  #define MyAppExeName "小程序工具.exe"
#endif
#ifndef MySourceDir
  #define MySourceDir "..\.cache\build\installer-source\小程序工具"
#endif
#ifndef MyOutputBaseFilename
  #define MyOutputBaseFilename "小程序工具"
#endif
#ifndef MyAppIconPath
  #define MyAppIconPath "..\assets\app_icon.ico"
#endif

[Setup]
AppId={{D2FF7E71-2A97-4F97-AB7B-4F1EA1A5B1F2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=..\dist\installer
OutputBaseFilename={#MyOutputBaseFilename}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={#MyAppIconPath}
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Messages]
SetupWindowTitle=安装 - %1
SetupAppTitle=安装程序
SetupLdrStartupMessage=即将安装 %1。是否继续？
SetupFileMissing=安装目录中缺少文件 %1。请修复此问题，或重新获取完整安装包。
SetupFileCorrupt=安装文件已损坏。请重新获取完整安装包。
SetupFileCorruptOrWrongVer=安装文件已损坏，或与当前安装程序版本不兼容。请修复此问题，或重新获取完整安装包。
SetupAlreadyRunning=安装程序已在运行。
ButtonBack=< 上一步(&B)
ButtonNext=下一步(&N) >
ButtonInstall=安装(&I)
ButtonOK=确定
ButtonCancel=取消
ButtonYes=是(&Y)
ButtonYesToAll=全部是(&A)
ButtonNo=否(&N)
ButtonNoToAll=全部否(&O)
ButtonFinish=完成(&F)
ButtonBrowse=浏览(&B)...
ButtonWizardBrowse=浏览(&R)...
ButtonNewFolder=新建文件夹(&M)
AboutSetupMenuItem=关于安装程序(&A)...
AboutSetupTitle=关于安装程序
AboutSetupMessage=%1 版本 %2%n%3%n%n%1 主页：%n%4
ExitSetupTitle=退出安装
ExitSetupMessage=安装尚未完成。如果现在退出，程序将不会被安装。%n%n以后可以重新运行安装程序完成安装。%n%n确定要退出安装吗？
SetupAppRunningError=检测到 %1 正在运行。%n%n请先关闭程序窗口和托盘图标，然后点击“确定”继续安装；如果暂时不安装，请点击“取消”退出。
UninstallAppRunningError=卸载程序检测到 %1 正在运行。%n%n请先关闭所有相关程序，然后点击“确定”继续，或点击“取消”退出卸载。
ClickNext=点击“下一步”继续，或点击“取消”退出安装。
WelcomeLabel1=欢迎安装 [name]
WelcomeLabel2=此向导将安装 [name/ver]。安装前会保留已有账号配置、浏览器资料和历史输出。%n%n建议继续前关闭正在运行的 [name]。
WizardSelectDir=选择安装位置
SelectDirDesc=[name] 要安装到哪里？
SelectDirLabel3=安装程序将把 [name] 安装到以下文件夹。
SelectDirBrowseLabel=点击“下一步”继续。如果要选择其他文件夹，请点击“浏览”。
DiskSpaceGBLabel=至少需要 [gb] GB 可用磁盘空间。
DiskSpaceMBLabel=至少需要 [mb] MB 可用磁盘空间。
DiskSpaceWarningTitle=磁盘空间不足
DiskSpaceWarning=安装至少需要 %1 KB 可用空间，但所选磁盘当前只有 %2 KB 可用。%n%n是否仍要继续？
WizardSelectTasks=选择附加任务
SelectTasksDesc=需要执行哪些附加任务？
SelectTasksLabel2=请选择安装 [name] 时要执行的附加任务，然后点击“下一步”。
WizardReady=准备安装
ReadyLabel1=安装程序已准备好开始将 [name] 安装到你的电脑。
ReadyLabel2a=点击“安装”开始安装；如需查看或修改设置，请点击“上一步”。
ReadyMemoTasks=附加任务：
WizardPreparing=正在准备安装
PreparingDesc=安装程序正在准备将 [name] 安装到你的电脑。
PreviousInstallNotCompleted=之前的安装或卸载尚未完成。你需要重新启动电脑来完成该操作。%n%n重新启动后，请再次运行安装程序以完成 [name] 的安装。
CannotContinue=安装程序无法继续。请点击“取消”退出。
ApplicationsFound=以下程序正在使用安装程序需要更新的文件。建议允许安装程序自动关闭这些程序。
ApplicationsFound2=以下程序正在使用安装程序需要更新的文件。建议允许安装程序自动关闭这些程序。安装完成后，安装程序会尝试重新启动这些程序。
CloseApplications=自动关闭这些程序(&A)
DontCloseApplications=不关闭这些程序(&D)
ErrorCloseApplications=安装程序无法自动关闭全部程序。建议先手动关闭正在使用待更新文件的程序，然后继续安装。
PrepareToInstallNeedsRestart=安装程序需要重新启动电脑。重新启动后，请再次运行安装程序以完成 [name] 的安装。%n%n是否现在重新启动？
WizardInstalling=正在安装
InstallingLabel=请稍候，安装程序正在安装 [name]。
FinishedHeadingLabel=正在完成 [name] 安装向导
FinishedLabelNoIcons=[name] 已安装完成。已有账号配置、浏览器资料和历史输出会继续保留。
FinishedLabel=[name] 已安装完成。你可以通过已创建的快捷方式启动应用，已有账号配置、浏览器资料和历史输出会继续保留。
ClickFinish=点击“完成”退出安装程序。
FinishedRestartLabel=要完成 [name] 的安装，需要重新启动电脑。是否现在重新启动？
FinishedRestartMessage=要完成 [name] 的安装，需要重新启动电脑。%n%n是否现在重新启动？
ShowReadmeCheck=是，我想查看 README 文件
YesRadio=是，立即重新启动电脑(&Y)
NoRadio=否，稍后我会自行重新启动电脑(&N)
RunEntryExec=运行 %1
RunEntryShellExec=查看 %1
SetupAborted=安装未完成。%n%n请修复问题后重新运行安装程序。
AbortRetryIgnoreSelectAction=选择操作
AbortRetryIgnoreRetry=重试(&T)
AbortRetryIgnoreIgnore=忽略错误并继续(&I)
AbortRetryIgnoreCancel=取消安装
RetryCancelSelectAction=选择操作
RetryCancelRetry=重试(&T)
RetryCancelCancel=取消
StatusClosingApplications=正在关闭程序...
StatusCreateDirs=正在创建目录...
StatusExtractFiles=正在解压文件...
StatusDownloadFiles=正在下载文件...
StatusCreateIcons=正在创建快捷方式...
StatusCreateIniEntries=正在创建 INI 项...
StatusCreateRegistryEntries=正在创建注册表项...
StatusRegisterFiles=正在注册文件...
StatusSavingUninstall=正在保存卸载信息...
StatusRunProgram=正在完成安装...
StatusRestartingApplications=正在重新启动程序...
StatusRollback=正在回滚更改...
ErrorFunctionFailedNoCode=%1 失败
ErrorFunctionFailed=%1 失败；代码 %2
ErrorFunctionFailedWithMessage=%1 失败；代码 %2。%n%3
ErrorExecutingProgram=无法执行文件：%n%1

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[Dirs]
Name: "{app}\data"
Name: "{app}\storage"
Name: "{app}\browser_profile"
Name: "{app}\output"

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "data\*,storage\*,browser_profile\*,output\*"
Source: "{#MySourceDir}\data\accounts.json"; DestDir: "{app}\data"; Flags: ignoreversion onlyifdoesntexist
Source: "{#MySourceDir}\data\settings.json"; DestDir: "{app}\data"; Flags: ignoreversion onlyifdoesntexist
Source: "{#MySourceDir}\data\transaction_complaint_rules.json"; DestDir: "{app}\data"; Flags: ignoreversion onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
function IsAppRunning(): Boolean;
var
  ResultCode: Integer;
  OutputPath: String;
  OutputText: AnsiString;
begin
  OutputPath := ExpandConstant('{tmp}\running-app.txt');
  Exec(
    ExpandConstant('{cmd}'),
    '/C tasklist /FI "IMAGENAME eq {#MyAppExeName}" /NH > "' + OutputPath + '"',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );

  Result := False;
  if LoadStringFromFile(OutputPath, OutputText) then
    Result := Pos(UpperCase('{#MyAppExeName}'), UpperCase(String(OutputText))) > 0;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  while IsAppRunning() do begin
    if MsgBox(
      '检测到 {#MyAppName} 正在运行。' + #13#10 + #13#10 +
      '请先关闭程序窗口和托盘图标，然后点击“重试”继续安装。' + #13#10 +
      '如果暂时不安装，请点击“取消”退出。',
      mbConfirmation,
      MB_RETRYCANCEL
    ) = idCancel then begin
      Result := False;
      Exit;
    end;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  while IsAppRunning() do begin
    if MsgBox(
      '检测到 {#MyAppName} 正在运行。' + #13#10 + #13#10 +
      '请先关闭程序窗口和托盘图标，然后点击“重试”继续卸载。' + #13#10 +
      '如果暂时不卸载，请点击“取消”退出。',
      mbConfirmation,
      MB_RETRYCANCEL
    ) = idCancel then begin
      Result := False;
      Exit;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then begin
    if MsgBox(
      '是否同时删除本机业务数据？' + #13#10 + #13#10 +
      '选择“是”会删除账号配置、浏览器资料、历史输出和运行缓存。' + #13#10 +
      '选择“否”会保留这些数据，后续重新安装后仍可继续使用。',
      mbConfirmation,
      MB_YESNO or MB_DEFBUTTON2
    ) = idYes then begin
      DelTree(ExpandConstant('{app}\data'), True, True, True);
      DelTree(ExpandConstant('{app}\storage'), True, True, True);
      DelTree(ExpandConstant('{app}\browser_profile'), True, True, True);
      DelTree(ExpandConstant('{app}\output'), True, True, True);
    end;
  end;
end;
