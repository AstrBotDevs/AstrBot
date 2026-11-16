# Unreleased

- WebUI: Rename **Extensions → Installed → Update All** to **Extensions → Installed → Batch Update Plugins**. List available plugin updates with checkboxes, select all by default, and update only checked plugins. Disable confirmation when none are selected.

- Move session-waiter dispatch from the built-in plugin's `handle_session_control_agent` handler into the core pipeline. Admit matching follow-up input without a mention or wake prefix, and dispatch after access/safety checks and preprocessing but before ordinary plugin handlers or the Agent. Preserve the existing `@session_waiter` API.

- Fix plugin installation failing with `FileExistsError` in NAS and similar environments where cross-device (`EXDEV`) errors make system temporary directories unusable and Python falls back to the working directory. Use `.astrbot-tmp` when the temporary path conflicts with the `.astrbot` initialization marker file. ([#10784](https://github.com/AstrBotDevs/AstrBot/pull/10784))

- Simplify Context Management Strategy settings: Handling for History Limits or Context Window Pressure → Compression Strategy; Model Provider ID for Context Compression → Compression Model. Move maximum turns, discarded turns, compression instruction, recent-context ratio and fallback context window size under the collapsed More Settings section. Preserve existing configuration keys, defaults and runtime behavior.

- Add SerpApi Google News search with publisher, author, publication time, and WebUI citation support.

- Add compact data-cleanup checkboxes to the existing bot deletion dialog. Custom rules, preferences, configuration routes and scheduled tasks are selected by default; AI conversations, message history, local traces and usage statistics are retained unless selected. Preserve shared resources and match adapter IDs exactly.

- Resolve Lark group-message sender names through the existing user-info lookup, sharing the same per-user cache with private chats (30 minutes for successful names and one minute for failures). Application senders skip user-directory lookups.

- Sort session-source candidates by the latest existing conversation, alias or sender `updated_at`, descending. Deduplicate user suggestions by platform instance and sender ID before applying the result limit, retaining the newest matching record while preserving per-session metadata in storage.

- Fetch Lark group metadata before creating inbound events, using the same one-hour success cache, five-minute failure cache, bounded size and lookup timeout as QQ Official. Automatic enrichment requests only group details; explicit `event.get_group()` continues to fetch member lists while sharing the metadata cache.

- Fetch QQ Official group names before creating inbound events in both WebSocket and Webhook adapters. Share a bounded per-bot cache with `event.get_group()`, caching successful names for one hour and failed or empty lookups for five minutes, coalescing concurrent requests and limiting each lookup to three seconds.

- Add hover copy icon buttons to both user and session-source entries, including selected entries. Hidden copy buttons take no layout space, matching the ChatUI session-list behavior. Copy raw sender IDs or full UMOs without changing selections; support keyboard focus and touch devices.

- Display full UMOs in gray parentheses beside session names, with platform logos and plain bot IDs below. Use the interface font throughout the list. Keep candidate titles on one line and selected titles on at most two lines, ellipsizing long values while exposing the full name and UMO on hover. Add blue group-chat and green private-chat badges using the same colors as Agent/Command badges on the trace page.

- Paginate user suggestions after platform-aware deduplication, with 50 results per page, previous/next controls and selections preserved across pages. Searching and refreshing return to the first page.

- Record sender IDs and names per UMO on awakened messages and include them in backups. Administrator IDs now use the dedicated `_special: sender_id` selector with nickname search, platform labels and direct ID addition when no search results match; values remain raw sender IDs. Old entry: Add More → Edit List Items. New entry: Select users (button and dialog).

- Unify bot session bindings, whitelist settings (`_special: umo`), conversation filters, custom rules/groups and future-task session choices in a shared session-selection dialog. Replace scattered dropdowns, generic list editors and group transfer lists with Select session sources (previously Select sessions); rename Known sessions to Recorded session sources and explain UMO below the dialog title; retain parent-page saving and advanced wildcard-rule editing. Bot bindings restrict results to the exact platform instance via the `platformId` prop and API filter. Future-task No delivery target filtering is a separate checkbox.

- QQ Official: a failed image upload no longer dumps the base64 payload into the log (a single multi-MB line could freeze log writing and the web dashboard), and image upload retries drop from 5 to 3 with a single summary warning instead of one per attempt.

- QQ Official: failed image uploads no longer log base64 payloads, avoiding dashboard freezes from oversized log entries. Retry attempts decrease from five to three, with one summary warning.

### Overview page / 总览页

- 欢迎 → 总览：保留 `/welcome` 地址，显示每日用量对比、系统状态和机器人错误详情。
- Welcome → Overview: Keep `/welcome` accessible and show daily usage comparisons, system status, and bot error details.
- 总览统计并入 `/api/v1/stats`，新增 `daily_usage` 与 `system`，移除开发阶段的 `/api/v1/stats/overview`。使用 `sections` 选择 `messages`、`daily_usage`、`process`、`system` 或 `instances`；省略时返回全部数据。旧接口 `/api/stat/get` 同样支持。
- Consolidate overview metrics into `/api/v1/stats`, adding `daily_usage` and `system` and removing the development-only `/api/v1/stats/overview`. Use `sections` to select `messages`, `daily_usage`, `process`, `system`, or `instances`; omit it for the full response. Legacy `/api/stat/get` also supports this parameter.

### Plugin AI documentation / 插件 AI 文档

- 调用 AI → AI：按模型、Agent、工具、会话与对话、其他拆分文档。多 Agent 编排归入构建自定义 Agent 的示例，人格管理归入其他；原 AI 地址保留为概览入口。
- Call AI → AI: Split the guide into Models, Agents, Tools, Sessions and Conversations, and Other APIs. Place multi-agent orchestration under custom Agent construction and persona management under Other APIs. Keep the original AI URL as an overview.
