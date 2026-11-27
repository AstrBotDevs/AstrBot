# Unreleased

### Chat usage statistics / 聊天用量统计

- Chat Provider 按上游请求尝试记录用量。`insert_provider_stat()` 和旧轮次统计表 `provider_stats` 进入弃用期。历史轮次继续计入 Token 总量，备份仍可导入和导出。
- Chat Providers record usage per upstream attempt. The legacy `insert_provider_stat()` method and `provider_stats` table are deprecated. Historical turn totals continue to contribute to token totals and remain supported in backups.
- 计划在至少一个稳定版本周期后迁移历史轮次汇总。迁移将保留 Token 总量和备份恢复能力，旧表将在验证跨版本升级与备份恢复后退场。
- Historical turn aggregates are planned for migration after at least one stable release cycle. The migration will preserve token totals and backup restore support. Retirement of the legacy table follows verification of direct upgrades and backup restores.

- QQ 官方适配器移除「主动消息使用 Markdown」配置项：主动消息默认使用 Markdown，插件仍可通过 `MessageChain.use_markdown(False)` 强制纯文本。
- QQ Official: remove the `use_markdown` platform option. Proactive messages now default to Markdown; plugins can still force plain text with `MessageChain.use_markdown(False)`.

- The plugin marketplace's Category dropdown moves to an expandable row of localized category filters with plugin counts. The row shows **All** and the total plugin count even when the selected source has no categories. Market installs save the category in the existing installation record.

- QQ Official: failed image uploads no longer log base64 payloads, avoiding dashboard freezes from oversized log entries. Retry attempts decrease from five to three, with one summary warning.

- Audio: Outbound voice messages no longer transcode MP3 payloads to WAV, which inflated base64 bodies by roughly 4.4x for long audio and could exceed platform frame limits; Satori and WebChat now derive the MIME type and file extension from the actual payload.

- Session waiters now wake their timeout task immediately when completed early, avoiding stale asyncio tasks for the remainder of the configured timeout.

- 「插件 → 管理行为 → 函数工具」现在只列出插件工具。Agent 运行时工具由配置文件的 AI 功能设置控制，MCP 工具可在「插件 → MCP」查看。
- Extensions → Handlers → Function Tools now lists plugin tools. Configure Agent runtime tools in the profile's AI capability settings and view MCP tools under Extensions → MCP Servers.

### ChatUI history / ChatUI 历史记录

- 一轮回复只保存为一条历史记录：流式分段、工具调用和按钮卡片都更新同一条记录，刷新后不再拆成多个气泡（SSE 与 WebSocket 相同）。已拆开的旧记录不会合并。
- Each assistant turn is saved as one history record. Streamed segments, tool calls and button cards update the same record, so a reply no longer splits into several bubbles after a reload (SSE and WebSocket alike). Records split before this change are not merged.
- 工具调用在开始时就占好位置，结果到达后原地更新：中途保存不再把调用拆成两半，耗时正确，后面的按钮卡片也不会排到调用前面。
- A tool call takes its place when it starts and is completed in place when its result arrives, so mid-turn saves no longer split it, its duration is correct, and a later button card stays after it.
- 回复结束时仍未返回的工具调用标为「已中断，结果未知」（实时和刷新后一致），不再一直计时。
- A tool call still without a result when the reply ends is marked **Interrupted, result unknown**, live and after a reload, instead of showing a running timer.
- 同一轮里两段模型消息之间没有工具调用时，补一个段落分隔，避免文字连在一起；只作用于 WebChat，其他平台的输出不变。
- When two model messages in one turn follow each other without a tool call in between, WebChat inserts a paragraph break so the text does not run together. Other platforms are unchanged.
- 按钮回调的数据库读写在工作线程执行（所有平台共用）。回调写入成功后才发送按钮，过期一天以上的回调会从缓存和数据库中清理。
- Button callback database reads and writes run on worker threads across all platforms. Buttons are sent after registration commits, and callbacks expired for over a day are removed from the cache and database.
- 分块上传的清理任务在没有事件循环时不再留下未等待的协程。
- The chunked-upload cleanup task no longer leaves an unawaited coroutine when no event loop is running.

### Overview page / 总览页

- 欢迎 → 总览：保留 `/welcome` 地址，显示每日用量对比、系统状态和机器人错误详情。
- Welcome → Overview: Keep `/welcome` accessible and show daily usage comparisons, system status, and bot error details.
- 总览统计并入 `/api/v1/stats`，新增 `daily_usage` 与 `system`，移除开发阶段的 `/api/v1/stats/overview`。使用 `sections` 选择 `messages`、`daily_usage`、`process`、`system` 或 `instances`；省略时返回全部数据。旧接口 `/api/stat/get` 同样支持。
- Consolidate overview metrics into `/api/v1/stats`, adding `daily_usage` and `system` and removing the development-only `/api/v1/stats/overview`. Use `sections` to select `messages`, `daily_usage`, `process`, `system`, or `instances`; omit it for the full response. Legacy `/api/stat/get` also supports this parameter.

### Plugin AI documentation / 插件 AI 文档

- 调用 AI → AI：按模型、Agent、工具、会话与对话、其他拆分文档。多 Agent 编排归入构建自定义 Agent 的示例，人格管理归入其他；原 AI 地址保留为概览入口。
- Call AI → AI: Split the guide into Models, Agents, Tools, Sessions and Conversations, and Other APIs. Place multi-agent orchestration under custom Agent construction and persona management under Other APIs. Keep the original AI URL as an overview.

### Plugin view documentation / 插件视图文档

- 插件可视化视图、ChatUI 交互卡片 → 可折叠的「插件可视化视图」章节，按独立插件页面、消息交互组件、工作台页面组织教程；共享 Bridge API 和后端 Web API 单独列出。旧文档链接及章节锚点跳转到对应新页面。
- Plugin Views and ChatUI Cards → one collapsible Plugin Views section with standalone page, message component, and workbench tutorials, plus shared Bridge and backend Web API references. Previous document URLs and section anchors redirect to their new locations.

- 三类视图教程分别提供 Meme Manager 独立页面、阅读清单消息演示、上下文用量常驻工作台示例，并附实机截图及示例插件。
- Add target-specific examples: Meme Manager for standalone pages, an interactive reading list for messages, and a resident context-usage workbench, with screenshots and example plugins.

### Plugin view registration / 插件视图注册

- `Star.chatui_views` → `metadata.yaml` 的 `views`：默认标题和描述随声明保存，i18n 的 `views.<name>`（兼容 `pages.<name>`）按字段覆盖；没有翻译时回退到 metadata。旧的独立页面声明省略 target 时仍为 `plugin_page`。
- Move view declarations from `Star.chatui_views` to `metadata.yaml` under `views`. Keep default labels in metadata and override them with i18n `views.<name>` (legacy `pages.<name>` remains supported). Existing declarations without a target remain standalone `plugin_page` views.
- `chat_workbench` + `launcher=True` → `chat_workbench_with_launcher`：同一视图既能由消息或工具打开，也能从工作台「＋」打开。只由插件打开的视图继续使用 `chat_workbench`。
- Replace `chat_workbench` + `launcher=True` with `chat_workbench_with_launcher` for views that can open from messages/tools and from **+**. Keep `chat_workbench` for plugin-opened views without a launcher entry.

### First-run onboarding / 首次使用引导

- 新增首次使用引导（`/chat/onboarding`）：在原生 ChatUI 中通过对话与内嵌交互卡片依次完成使用须知确认、AI 模型配置与测活、在线试聊及消息平台接入。仅在全新安装完成账户初始化后自动进入，已有配置、升级、重置密码和普通登录不会触发；仍可从「系统设置 → 维护 → 重新进入首次引导」手动打开。
- Add conversational first-run onboarding inside ChatUI (`/chat/onboarding`) with inline interactive widgets for usage notice, AI model setup & connection testing, live model trial, and messaging platform setup. Triggered automatically only after account setup on a fresh installation; upgrades, existing configs, password resets, and ordinary logins skip it, while manual reentry remains available in Settings → Maintenance.
