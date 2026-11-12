# Unreleased

- QQ Official: a failed image upload no longer dumps the base64 payload into the log (a single multi-MB line could freeze log writing and the web dashboard), and image upload retries drop from 5 to 3 with a single summary warning instead of one per attempt.

### Overview page / 总览页

- 欢迎 → 总览：保留 `/welcome` 地址，按主题色重排今日统计、快速引导和资源入口，不使用波浪背景。机器人报错时显示问题数量，点击可查看错误详情。
- Welcome → Overview: Preserve `/welcome`, add daily usage comparisons, and arrange setup and resource cards using the selected theme. Bot errors appear as an issue count with a details dialog.

- 总览：在统计卡片与快速引导、相关资源之间加入紧凑系统状态栏，展示运行时长和服务器 CPU、内存及数据分区磁盘用量。
- Overview: Place a compact system status bar between usage cards and setup/resources, showing process uptime and host CPU, memory, and data-filesystem disk usage.
