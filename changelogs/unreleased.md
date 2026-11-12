# Unreleased

- QQ Official: a failed image upload no longer dumps the base64 payload into the log (a single multi-MB line could freeze log writing and the web dashboard), and image upload retries drop from 5 to 3 with a single summary warning instead of one per attempt.

### Overview page / 总览页

- 欢迎 → 总览：保留 `/welcome` 地址，按主题色重排今日统计、快速引导和资源入口，不使用波浪背景。机器人报错时显示问题数量，点击可查看错误详情。
- Welcome → Overview: Preserve `/welcome`, add daily usage comparisons, and arrange setup and resource cards using the selected theme. Bot errors appear as an issue count with a details dialog.

- 总览：在统计卡片与快速引导、相关资源之间加入紧凑系统状态栏，展示运行时长和服务器 CPU、内存及数据分区磁盘用量。
- Overview: Place a compact system status bar between usage cards and setup/resources, showing process uptime and host CPU, memory, and data-filesystem disk usage.

- 总览统计合并至 `/api/v1/stats`：新增 `daily_usage` 与 `system`，保留现有字段和统计口径；移除开发阶段的 `/api/v1/stats/overview` 接口。
- Consolidate overview metrics into `/api/v1/stats` with additive `daily_usage` and `system` fields, preserving existing statistics. Remove the development-only `/api/v1/stats/overview` endpoint.

- `/api/v1/stats` 支持 `sections` 按需计算和返回 `messages`、`daily_usage`、`process`、`system`、`instances`。总览与统计页分别请求所需分类，不传参数仍返回全部数据；旧版 `/api/stat/get` 同样支持。
- Add on-demand `sections` to `/api/v1/stats` and legacy `/api/stat/get`: `messages`, `daily_usage`, `process`, `system`, and `instances`. Overview and Statistics request only their required categories; omitted sections retain the full response.
