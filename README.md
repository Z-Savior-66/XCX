# 小程序工具

这个项目名为“小程序工具”，用于管理微信小游戏后台账号，保存登录态，并抓取“未成年人支付退款”页面中的处理截止时间。当前仓库以 Python 桌面版为唯一抓取实现。

## 功能

- 多账号配置管理
- 每个账号单独保存登录态
- 支持在微信后台页面内自动切换账号后抓取
- 支持配置共享浏览器资料目录，复用本机浏览器账号池
- 支持读取“切换账号”弹窗中的账号列表并导入
- 支持自动识别抓取时的当前实际账号名
- 支持单账号抓取、批量抓取、飞书汇总发送
- 支持每日自动抓取并推送
- 支持飞书发送失败后手动补发

## 依赖

```powershell
python -m pip install -r requirements.txt
```

说明：

- 首次启动桌面程序时，如果缺少 Playwright 浏览器资源，程序会自动联网下载安装 Chromium
- 打包后的安装版默认不再内置 Chromium，以减小包体
- 当前抓取逻辑已按职责拆分为 `fetcher.py` 兼容入口层、`fetcher_switching.py`、`fetcher_session.py`、`fetcher_pipeline.py`、`fetcher_support.py` 与 `fetcher_page_strategy.py`

## 浏览器运行时交付策略

- **默认策略**：安装版不内置 Chromium，首次启动时在线下载到项目运行目录下的 `ms-playwright/`
- **离线策略**：若目标环境无法联网，需要在交付前预置完整的 Playwright Chromium 运行时，确保程序首次启动时不再触发下载
- **适用建议**：
  - 办公网或普通开发环境：使用默认在线安装策略，减小安装包体积
  - 内网、弱网或离线终端：使用离线预置策略，避免首次启动失败

### 离线预置建议

如果目标环境不能联网，建议按以下方式准备离线运行时：

1. 在可联网环境执行 `playwright install chromium`
2. 将生成的 `ms-playwright/` 完整目录与应用一起交付
3. 确保运行目录中存在：
   - `chromium-*`
   - `chromium_headless_shell-*`
   - `ffmpeg-*`
4. 首次启动前确认程序运行目录具备这些资源，避免再触发在线下载

### 标准版与离线版选择建议

- **标准版**：适合办公网络或常规开发环境，优点是安装包更小
- **离线版**：适合内网、弱网、无法联网终端，优点是交付更稳定

## 安装包构建依赖

先安装构建依赖：

```powershell
python -m pip install -r requirements-build.txt
```

项目打安装包时只使用项目目录内的便携版 Inno Setup 编译器，不依赖系统安装版。

固定路径：

- `tools/inno/ISCC.exe`

当前仓库已经准备好项目内 Inno Setup 目录；如果后续重新部署环境，请把完整的 Inno Setup 目录内容放到 `tools/inno/`，不要只复制单个 `ISCC.exe`。

### 构建安装包

构建脚本默认会先执行完整本地验证：

```powershell
pwsh ./scripts/verify_local.ps1
```

验证通过后再执行安装包构建：

```powershell
pwsh ./scripts/build_installer.ps1 -Clean
```

如果本机缺少 `PyInstaller`，构建脚本会直接报错并提示安装 `requirements-build.txt`。

如果只是复现历史构建且已经在同一工作区刚完成验证，可以显式追加 `-SkipVerification` 跳过构建前验证；常规交付不建议跳过。

### 构建离线版安装包

如果需要离线版，请先在项目根目录准备完整的 `ms-playwright/`，然后执行：

```powershell
pwsh ./scripts/build_installer.ps1 -Clean -IncludeOfflineChromium
```

说明：

- **标准版**：不内置 Chromium，首次启动在线下载
- **离线版**：安装包内预置 `ms-playwright/`，首次启动不再依赖联网下载

## 启动桌面程序

```powershell
python desktop_main.py
```

## 开发模式启动

如果你在修改 PySide6 界面，希望保存代码后自动重启桌面应用，可以使用：

```powershell
python desktop_dev.py
```

说明：

- 会监听 `desktop_main.py` 和 `desktop_py/**/*.py`
- 检测到文件变化后会自动关闭旧进程并重新启动
- 按 `Ctrl+C` 可停止开发模式

## 桌面版命令行辅助

### 指定账号重新登录

```powershell
python desktop_py_cli.py login --account "账号名称"
```

### 批量抓取全部启用账号

```powershell
python desktop_py_cli.py fetch-all
```

### 抓取并发送飞书汇总

```powershell
python desktop_py_cli.py notify
```

## 桌面版使用方式

1. 打开桌面程序，点击“新增账号”
2. 只填写账号名称；登录态文件路径可以留空，程序会自动生成
3. 选中账号后点击“保存登录态”
4. 在弹出的浏览器里手动登录微信后台
5. 登录完成后等待程序自动保存登录态
6. 如果你希望稳定使用页面内“切换账号”，建议先在“全局设置”中选择共享浏览器资料父目录
7. 程序会在你选择的父目录下自动创建 `browser_profile/`，并把共享浏览器资料统一放在该专用目录内
8. 若资料目录或登录态里已包含多个可切换账号，后续新增其他账号名称时可复用同一份资料
9. 也可以选中一个已登录账号后点击“导入账号列表”，自动读取切换账号弹窗中的账号名
10. 点击“抓取选中”或“抓取并推送”
11. 配置飞书 Webhook 后点击“推送飞书”

## 登录态保存与续期

桌面版同时支持两类 Playwright 登录态来源：

- `storage/*.json`：账号级 `storage_state` 快照，保存 Cookie、localStorage 和 IndexedDB 等页面状态。
- `browser_profile/`：专用持久化浏览器资料目录，用于复用微信后台账号池和页面内切换账号状态。

建议在“全局设置”中使用程序创建的专用 `browser_profile/`，不要指向 Chrome、Edge 或其他日常浏览器的默认资料目录，避免资料目录被外部浏览器锁定或污染。自动续期不再只看当前页面是否仍可访问，而是先写入临时登录态文件，再用该临时文件新建浏览器上下文复验；只有保存后复验通过，才会替换正式 `storage/*.json`，并在替换前保留备份。

自动续期日志会展示最近续期时间、保存后复验结果、连续失败次数，以及基于 Cookie 剩余寿命或登录态健康诊断得出的下次调度原因。出现以下情况时，建议重新保存登录态：

- `storage/*.json` 缺失、不可读或内容不是有效登录态。
- 自动续期保存后复验失败。
- 微信后台页面提示登录超时或需要重新登录。
- 自动续期连续失败。
- 微信后台页面结构变化，导致程序无法确认当前账号信息。

入口账号用于承载共享登录态和浏览器资料目录，不代表微信后台“切换账号”弹窗中的真实账号。自动续期探测到当前登录态有效后，会从同一登录态文件下已启用的导入账号中选择轮换目标，并且不会把入口账号名称加入轮换候选；如果微信后台根页或登录超时页仍可恢复，程序会先尝试点击左上角“小程序”入口再判定登录态失败。

## 数据文件

- `data/accounts.json`：账号配置
- `data/settings.json`：全局设置
- `storage/*.json`：各账号登录态
- `output/desktop_py/<账号>/`：抓取产物
- `output/desktop_py/diagnostic_index.json`：最近一次批量抓取诊断索引
- `ms-playwright/`：首次运行后下载的浏览器运行时

## 诊断产物治理

抓取失败时，程序会在 `output/desktop_py/<账号>/` 下保留 `fetch_manifest.json`、`page.html`、`iframe.html`、`iframe.txt`、`responses.json` 等诊断产物，用于定位页面结构、接口响应和规则版本。批量抓取会在 `output/desktop_py/diagnostic_index.json` 生成最近一次批量诊断索引，用于快速定位失败账号和对应 manifest。界面日志不会输出这些本地路径，避免日常日志噪声；抓取结果 `result.json` 属于业务结果，不会被诊断清理删除。

默认保留最近 14 天内的诊断产物。每次抓取结果落盘后，程序只会清理超过保留期的诊断文件，并跳过 `result.json`、账号配置、登录态文件和其它业务数据。

## 存储边界

当前版本的配置和抓取结果存储以本地 JSON 文件为主，这个方案只针对当前单机桌面工具场景。

- **适用范围**：
  - 单机使用
  - 单进程写入
  - 轻量配置与抓取结果留存
- **当前不覆盖的能力**：
  - 多人协同
  - 并发写入协调
  - 审计级历史追踪
  - 集中调度与任务队列
- **后续升级触发条件**：
  - 多人共用同一套账号数据
  - 需要集中查看历史抓取记录
  - 需要更强的调度、审计或状态管理能力

## 本地运行数据治理

以下目录可能包含真实业务状态或登录态，禁止在常规清理中自动删除：

- `data/`：账号配置与全局设置
- `storage/`：账号登录态文件
- `browser_profile/`：共享浏览器资料目录
- `ms-playwright/`：已下载的 Playwright 浏览器运行时，离线环境可能依赖该目录

以下目录属于可再生成产物，可以在确认不需要历史输出后手动清理：

- `build/`：PyInstaller 和安装包构建临时目录
- `dist/`：安装包输出目录
- `output/`：抓取输出结果，清理前应确认不再需要历史记录

交付前建议先运行 `powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify_local.ps1`，再执行安装包构建。清理目录时只处理明确可再生成的产物，不要批量删除业务状态目录。

## 抓取说明

当前采集链路以微信后台页面为准，不直接依赖用户手工复制链接。程序会先进入微信后台首页，确认登录态和当前实际账号，再按需切换到目标账号，随后打开“未成年人支付退款”反馈页。详情页文本、关键网络响应和通知中心结果会共同参与判断，最终写入账号状态、日志和本地诊断产物。

### 采集结果

- 有待处理申请：账号列表会显示处理截止时间，状态显示为“完成”。
- 无待处理申请：账号列表会显示“无待处理”，状态显示为“完成”。
- 抓取失败：账号列表会显示简短失败原因，状态显示为“失败”。
- 通知中心命中目标未读消息时，飞书汇总会把通知结果追加到对应账号行。

### 诊断产物

每次采集都会在 `output/desktop_py/<账号>/` 下写入本地结果。常用文件如下：

- `result.json`：本次采集的最终结果，包括实际账号名、截止时间、页面地址和结果说明。
- `fetch_manifest.json`：本次采集的诊断清单，包括采集规则版本、步骤状态、失败类型、响应证据摘要和耗时。
- `output/desktop_py/diagnostic_index.json`：最近一次批量抓取索引，包括账号结果、错误码、耗时和 manifest 路径。
- `notifications.json`：通知中心命中的目标未读消息。
- `page.html`、`iframe.html`、`iframe.txt`、`responses.json`：失败或需要排查时保留的页面结构和响应片段。

排查时可到对应账号输出目录查看 `fetch_manifest.json`，再结合 `result.json` 和页面片段判断失败原因。

### 失败排查

- 提示登录超时或未进入后台页：重新保存登录态，确认微信后台可正常进入。
- 提示切换账号失败：确认共享浏览器资料目录中确实存在目标账号，并检查账号名称是否与微信后台一致。
- 提示页面未出现业务 iframe：优先查看 `fetch_manifest.json` 和 `page.html`，通常表示页面结构变化、链接失效、无权限或登录态失效。
- 提示未提取到处理截止时间：查看 `iframe.txt`、`iframe.html` 和 `responses.json`，确认页面文本或接口字段是否变化。
- 通知中心抓取失败：查看 `notification_page.html` 和 `notifications.json`，确认后台是否仍有通知中心入口。

### 维护验证

采集规则带有稳定版本号，当前规则版本会写入 `fetch_manifest.json`。维护者调整页面选择器、接口字段或响应匹配规则后，应先补充脱敏回放夹具，再运行本地验证：

```powershell
python -m unittest py_tests.test_fetcher_replay -v
python -m unittest py_tests.test_ui_fetch -v
pwsh ./scripts/verify_local.ps1
```

回放夹具位于 `py_tests/fixtures/fetcher/`，用于覆盖正常详情、空列表、接口字段变更、缺失 iframe、登录超时、通知中心失败和跨账号 token 串号等场景。

## 本地验证

推荐使用统一入口完成完整本地验证：

```powershell
pwsh ./scripts/verify_local.ps1
```

该脚本会设置 `QT_QPA_PLATFORM=offscreen`，并按顺序执行格式检查、静态检查、类型检查、`unittest` 与 `pytest`。任一命令失败时会立即退出并输出失败命令。

也可以单独运行测试：

```powershell
python -m unittest discover -s py_tests -v
```

### 安装包链路最小验证

```powershell
python -m unittest py_tests.test_browser_runtime py_tests.test_build_installer -v
```

## 工程检查

项目根目录已提供 `pyproject.toml`，当前统一使用 `ruff` 承担格式检查与静态检查。

### 格式检查

```powershell
ruff format --check .
```

### 静态检查

```powershell
ruff check .
```

### 类型检查试点

```powershell
python -m mypy
```

### 单元测试与 pytest 校验

```powershell
python -m unittest discover -s py_tests -v
python -m pytest py_tests -q
```

## 推荐本地交付流程

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
ruff format --check .
ruff check .
python -m mypy
python -m unittest discover -s py_tests -v
python -m pytest py_tests -q
pwsh ./scripts/build_installer.ps1 -Clean
```
