# Unreleased

- QQ 官方适配器移除「主动消息使用 Markdown」配置项：主动消息默认使用 Markdown，插件仍可通过 `MessageChain.use_markdown(False)` 强制纯文本。
- QQ Official: remove the `use_markdown` platform option. Proactive messages now default to Markdown; plugins can still force plain text with `MessageChain.use_markdown(False)`.

- The plugin marketplace's Category dropdown moves to an expandable row of localized category filters with plugin counts. The row shows **All** and the total plugin count even when the selected source has no categories. Market installs save the category in the existing installation record.

- QQ Official: failed image uploads no longer log base64 payloads, avoiding dashboard freezes from oversized log entries. Retry attempts decrease from five to three, with one summary warning.

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

### Tool approval and permission modes / 工具审批与权限档位

- 新增「需要审批的工具」（`agent.config.misc.tool_approval.tools`）和审批超时：名单内的工具执行前需要发起人批准。ChatUI 在输入框上方显示审批卡片，结果收进这轮回复的运行详情；其他平台发送确认码，支持按钮的平台附带按钮。只有发起人的回复有效，后台唤醒不会被当作答复。
- Add **Tools requiring approval** (`agent.config.misc.tool_approval.tools`) and an approval timeout. Listed tools wait for the requester's approval: ChatUI shows an approval card above the input box and keeps the outcome in the reply's run details; other platforms get a reply code, plus buttons where supported. Only the requester's reply counts, and background wakeups never answer an approval.
- 批准创建或修改定时任务（`future_task`）时，同时批准任务到点运行时用到的名单内工具；未经批准的任务向创建者请求批准。
- Approving the creation or edit of a scheduled task (`future_task`) also approves the listed tools it uses on schedule. Tasks created without approval ask their creator.
- ChatUI 新增按对话的权限档位（工作区 / 请求批准 / 完全访问），位于输入框加号旁边。档位只会收窄角色的本地权限策略；「完全访问」不会传给定时任务。审批卡片上的「本对话不再询问」不会放宽访问：在「请求批准」下切到「完全访问」，在「工作区」下保持工作区并显示「工作区 · 不再询问」。新增 `permission_mode` 请求字段（含 `workspace_no_ask`）和 `PUT /api/v1/chat/sessions/{session_id}/permission-mode`（只能修改自己的 WebChat 会话）。
- Add per-conversation permission modes in ChatUI (Workspace / Ask for approval / Full access) next to **+** in the input box. Modes only narrow the role's local permission policy, and Full access never passes to scheduled tasks. **Don't ask again in this conversation** on an approval card never widens access: from Ask for approval it switches to Full access, and from Workspace it stays in the workspace, shown as **Workspace · not asking**. Chat requests accept `permission_mode` (including `workspace_no_ask`), and `PUT /api/v1/chat/sessions/{session_id}/permission-mode` changes it for the caller's own WebChat sessions.
- `ActionRow` 新增可选字段 `single_use`、`title`、`detail`、`tool_call_id`，目前只有 WebChat 使用。
- `ActionRow` gains optional `single_use`, `title`, `detail`, and `tool_call_id` fields, used by WebChat only for now.

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
