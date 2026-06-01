# 小程序工具

用于管理微信小游戏后台账号，保存登录态，并抓取“未成年人支付退款”页面中的处理截止时间。当前仓库以 Python 桌面版为唯一抓取实现。

## 核心功能

- 多账号配置与登录态保存
- 共享浏览器资料目录与后台账号池复用
- 微信后台内自动切换账号并抓取退款处理截止时间
- 单账号抓取、批量抓取、每日自动抓取并推送
- 飞书汇总发送与失败后手动补发

## 安装依赖

建议始终使用项目内虚拟环境，避免系统 Python 与其他项目依赖互相影响：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

已激活虚拟环境时，也可以直接执行：

```powershell
python -m pip install -r requirements.txt
```

首次启动时，如果缺少 Playwright Chromium，程序会自动下载到运行目录下的 `ms-playwright/`。离线环境需要提前准备完整 `ms-playwright/` 目录。

## 启动

桌面程序：

```powershell
.\.venv\Scripts\python.exe desktop_main.py
```

开发模式会监听 Python 文件变化并自动重启桌面程序：

```powershell
.\.venv\Scripts\python.exe desktop_dev.py
```

如果已经激活 `.venv`，上述命令中的 `.\.venv\Scripts\python.exe` 可以简写为 `python`。

## 开发环境

### VS Code 调试

仓库提供 `.vscode/launch.json`，调试配置会显式使用项目虚拟环境：

```text
${workspaceFolder}\.venv\Scripts\python.exe
```

可直接使用以下调试项：

- `桌面程序：开发启动`：运行 `desktop_dev.py`，适合日常开发。
- `桌面程序：直接启动`：运行 `desktop_main.py`，适合复现启动流程。
- `命令行：登录账号`：执行 `desktop_py_cli.py login --account <账号名称>`。
- `命令行：批量抓取`：执行 `desktop_py_cli.py fetch-all`。
- `命令行：发送飞书汇总`：执行 `desktop_py_cli.py notify`。

如果 VS Code 仍提示缺少 `PySide6`，先执行 `Developer: Reload Window`，再确认当前解释器是项目内 `.venv\Scripts\python.exe`。

### 本地验证

安装运行依赖和验证依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
```

执行完整本地验证：

```powershell
pwsh ./scripts/verify_local.ps1
```

验证脚本会优先使用 `.venv\Scripts\python.exe`，不存在时才回退到系统 `python`。脚本包含以下步骤：

- Ruff 格式检查
- Ruff 静态检查
- mypy 类型检查
- unittest 全量测试
- pytest 全量测试

提交或打包前应先确保该脚本通过。

### 常见问题

`ModuleNotFoundError: No module named 'PySide6'`

通常是当前终端或编辑器使用了系统 Python，而不是项目 `.venv`。使用以下命令确认解释器：

```powershell
.\.venv\Scripts\python.exe -c "import sys, PySide6; print(sys.executable)"
```

如果该命令成功，而编辑器仍报错，说明编辑器解释器选择不正确，重新加载窗口或改用仓库提供的调试配置。

`开发模式已在运行`

开发模式通过本地端口防止重复启动。同一时间只保留一个 `desktop_dev.py` 进程；如异常退出后仍提示占用，先关闭残留 Python 进程再重试。

首次启动下载 Chromium 失败

确认网络可访问 Playwright 官方下载源后重启程序。离线环境需要提前准备完整 `ms-playwright/` 目录。

## 代码结构

```text
desktop_main.py              桌面程序入口
desktop_dev.py               文件变化自动重启的开发入口
desktop_py_cli.py            命令行辅助入口
desktop_py/app.py            QApplication、托盘、浏览器运行时初始化
desktop_py/core/             账号、抓取、登录态、通知、持久化等核心逻辑
desktop_py/ui/               PySide6 窗口、动作、后台任务与界面组件
py_tests/                    单元测试、UI 测试和抓取回放测试
scripts/verify_local.ps1     本地质量验证脚本
scripts/build_installer.ps1  安装包构建脚本
```

## 使用流程

1. 打开桌面程序，点击“新增账号”。
2. 填写账号名称，登录态路径可留空。
3. 选中账号，点击“保存登录态”，在弹出的浏览器中登录微信后台。
4. 如需复用后台账号池，在“全局设置”中选择共享浏览器资料父目录，程序会自动创建 `browser_profile/`。
5. 已登录后可点击“导入账号列表”，从后台“切换账号”弹窗读取账号名。
6. 点击“抓取选中”“抓取全部”或“抓取并推送”。
7. 配置飞书 Webhook 后，可发送或补发飞书汇总。

## 命令行辅助

```powershell
.\.venv\Scripts\python.exe desktop_py_cli.py login --account "账号名称"
.\.venv\Scripts\python.exe desktop_py_cli.py fetch-all
.\.venv\Scripts\python.exe desktop_py_cli.py notify
```

## 数据目录

以下目录可能包含真实业务状态或登录态，不要随意删除：

- `data/`：账号配置与全局设置
- `storage/`：账号登录态文件
- `browser_profile/`：共享浏览器资料目录
- `output/`：抓取结果与诊断产物
- `ms-playwright/`：Playwright 浏览器运行时，离线环境可能依赖

常用文件：

- `data/accounts.json`：账号配置
- `data/settings.json`：全局设置
- `storage/*.json`：账号登录态
- `output/desktop_py/<账号>/result.json`：账号抓取结果
- `output/desktop_py/diagnostic_index.json`：最近一次批量抓取索引

## 打包

安装构建依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

安装包构建依赖项目内便携版 Inno Setup：

```text
tools/inno/ISCC.exe
```

构建标准版安装包：

```powershell
pwsh ./scripts/build_installer.ps1 -Clean
```

构建脚本默认会先运行 `scripts/verify_local.ps1`，验证失败时不会继续生成安装包。

构建离线版安装包前，需要先在项目根目录准备完整 `ms-playwright/`：

```powershell
pwsh ./scripts/build_installer.ps1 -Clean -IncludeOfflineChromium
```
