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
