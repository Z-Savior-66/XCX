# 小程序工具

用于管理微信小游戏后台账号，保存登录态，并抓取“未成年人支付退款”页面中的处理截止时间。当前仓库以 Python 桌面版为唯一抓取实现。

## 核心功能

- 多账号配置与登录态保存
- 共享浏览器资料目录与后台账号池复用
- 微信后台内自动切换账号并抓取退款处理截止时间
- 单账号抓取、批量抓取、每日自动抓取并推送
- 飞书汇总发送与失败后手动补发

## 安装依赖

```powershell
python -m pip install -r requirements.txt
```

首次启动时，如果缺少 Playwright Chromium，程序会自动下载到运行目录下的 `ms-playwright/`。离线环境需要提前准备完整 `ms-playwright/` 目录。

## 启动

桌面程序：

```powershell
python desktop_main.py
```

开发模式会监听 Python 文件变化并自动重启桌面程序：

```powershell
python desktop_dev.py
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
python desktop_py_cli.py login --account "账号名称"
python desktop_py_cli.py fetch-all
python desktop_py_cli.py notify
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
python -m pip install -r requirements-build.txt
```

安装包构建依赖项目内便携版 Inno Setup：

```text
tools/inno/ISCC.exe
```

构建标准版安装包：

```powershell
pwsh ./scripts/build_installer.ps1 -Clean
```

构建离线版安装包前，需要先在项目根目录准备完整 `ms-playwright/`：

```powershell
pwsh ./scripts/build_installer.ps1 -Clean -IncludeOfflineChromium
```
