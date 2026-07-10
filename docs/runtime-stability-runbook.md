# AstrBot 本地稳定运行排障说明

这份说明记录当前本地 AstrBot + NapCat / OneBot + QQTools 浏览器搜索的稳定运行方式。

## 启动

在 PowerShell 中执行：

```powershell
Set-Location "D:\Project files\AstrBotCore"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\start_astrbot.ps1"
```

如果已有旧实例占用 `6185` 或 `6199`，脚本会拒绝重复启动，并显示占用端口的 PID。

`start_astrbot.bat` 和 `scripts\start_with_logs.ps1` 都只是兼容入口，会转发到 `start_astrbot.ps1`，不会绕过配置守护、健康检查和端口保护。

## 安全重启

推荐用脚本自动停掉明确属于当前 AstrBotCore 的旧进程，再启动新实例：

```powershell
Set-Location "D:\Project files\AstrBotCore"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\start_astrbot.ps1" -StopExisting
```

默认不带 `-StopExisting` 时，脚本只会显示停止计划，不会停进程。

## 配置和运行态检查

完整检查：

```powershell
Set-Location "D:\Project files\AstrBotCore"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\start_astrbot.ps1" -FullCheck
```

`-FullCheck` 等价于 `-CheckOnly -RuntimeCheck -BrowserCheck -StartupSignals`。

浏览器搜索底座检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\start_astrbot.ps1" -CheckOnly -BrowserSmoke
```

`BrowserSmoke` 只启动一次本地 headless Chrome 打开 `about:blank`，不访问外网。

## 当前插件整合策略

主回复链路：

- SpectreCore 负责主动/普通回复。
- QQTools 提供本地浏览器搜索工具。
- Meme Manager 保留低频表情回复。
- SelfLearning 保留好感度、情绪、基础消息采集和社交上下文。

关闭或降级的慢路径：

- LivingMemory 已禁用：当前没有 Embedding Provider，加载时会等待并触发 30 秒超时。
- Bilibili 已禁用：当前没有凭据，会产生定时告警。
- SelfLearning 的黑话学习、风格学习、ML 分析、记忆图、知识图关闭，避免每条消息触发重流程。
- Tavily / BoCha / Brave / Firecrawl / Exa / Baidu 这类 API-key 搜索工具已禁用，避免没有 key 时模型误调用。

网络搜索走 QQTools 浏览器工具：

- `browser_open`
- `browser_search`
- `browser_click`
- `browser_input`
- `browser_scroll`
- `browser_get_link`

## 预期 OK 信号

重启后运行检查中应看到：

```text
OK plugins.disabled_slow
OK tools.api_search_disabled
OK tools.browser_available
OK qqtools.browser
OK self_learning.balanced
OK browser.playwright
OK browser.executable
OK browser.proxy
OK runtime.dashboard_port
OK runtime.onebot_ws_port
```

发送 QQ 测试消息后，启动信号检查应尽量看到：

```text
aiocqhttp(OneBot v11) 适配器已连接
Browser tools registered
好感度管理服务启动成功
```

## 不应再出现的坏信号

```text
等待插件初始化超时
等待 Provider 就绪
Tavily API key is not configured
RESOURCE_EXHAUSTED
```

如果这些再次出现，先运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\start_astrbot.ps1" -FullCheck
```

## 当前保留的 WARN

`platform.id_whitelist` 为空时不是故障。AstrBot 的白名单检查源码会在列表为空时直接跳过过滤，所以它等价于“不限制会话 ID”。

如果后续只想允许固定私聊或固定群触发，再把会话 ID 写入 `platform_settings.id_whitelist`。

`runtime.file_log` 如果提示：

```text
astrbot.log does not exist yet
```

说明当前运行的是旧进程，还没重启加载文件日志配置。执行 `-StopExisting` 重启即可。

## browser_search restart signal

After the browser-search integration is installed, `-FullCheck` should show:

```text
OK startup.qqtools_browser_search_registered
```

If it shows WARN, the current AstrBot process was started before `browser_search` was registered. Restart with:

```powershell
PowerShell -NoProfile -ExecutionPolicy Bypass -File "D:\Project files\AstrBotCore\start_astrbot.ps1" -StopExisting
```

`runtime.restart_needed` compares the running AstrBot process start time with watched plugin files. If a plugin file is newer than the process, restart before testing QQ behavior.

## browser_search QQ test

After restarting, send a QQ message such as:

```text
帮我查一下今天的新闻
```

Then verify the search path with:

```powershell
PowerShell -NoProfile -ExecutionPolicy Bypass -File "D:\Project files\AstrBotCore\start_astrbot.ps1" -CheckOnly -SearchSignals
```

Expected signal:

```text
OK search.browser_search_used
```

You can also run the combined post-restart check after sending the QQ test message:

```powershell
PowerShell -NoProfile -ExecutionPolicy Bypass -File "D:\Project files\AstrBotCore\start_astrbot.ps1" -PostRestartCheck -FailOnWarn
```

For final acceptance, run the smoke version. It also launches a headless browser once:

```powershell
PowerShell -NoProfile -ExecutionPolicy Bypass -File "D:\Project files\AstrBotCore\start_astrbot.ps1" -PostRestartSmokeCheck -FailOnWarn
```
