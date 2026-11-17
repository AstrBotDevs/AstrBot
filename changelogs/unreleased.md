# Unreleased

- QQ Official: failed image uploads no longer log base64 payloads, avoiding dashboard freezes from oversized log entries. Retry attempts decrease from five to three, with one summary warning.

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

### Model requests / 模型请求

- OpenAI 兼容接口：只有报错明确表示模型不支持工具时，才去掉工具重试，同时去掉 `tool_choice`；警告中附带原始报错。其他和工具有关的错误（如工具参数结构不合法）不再被吞掉。
- OpenAI-compatible APIs: Retry without tools only when the error says the model does not support tools, and drop `tool_choice` together with the tools. The warning includes the original error. Other tool-related errors, such as invalid tool schemas, are no longer hidden.
- Anthropic：除系统提示外，对话末尾也设置缓存断点，工具循环的下一步和下一轮对话可以直接命中历史缓存。断点在清理消息之后设置，并计入工具定义（包括自定义请求体中的工具）上已有的断点，总数不超过 4 个。
- Anthropic: Mark the end of the conversation as a cache breakpoint in addition to the system prompt, so the next tool-loop step and the next turn read the history from the cache. Breakpoints are placed after messages are sanitized and count existing markers on tool definitions, including tools from the custom request body, staying within the limit of four.
- 上下文压缩按本次请求实际使用的模型查找上下文窗口；压缩前的用量以上一次请求上报的 Token 数为基准，加上之后新增消息的估算。
- Context compression looks up the context window of the model actually used for the request. Usage before compression starts from the tokens reported for the previous request and adds an estimate for messages added since.
- 当前模型不能接收音频且未开启语音识别时，模型会收到一条说明，提示用户开启语音识别或换用支持音频的模型，而不是只看到 `[Audio]`。
- When the current model cannot receive audio and speech recognition is off, the model receives a note asking it to tell the user to enable speech recognition or switch to an audio-capable model, instead of a bare `[Audio]` placeholder.
