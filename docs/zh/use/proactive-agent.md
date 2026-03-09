# 主动型能力

AstrBot 引入了主动 Agent（Proactive Agent）系统，使 AstrBot 不仅能被动响应用户，还能通过给自己下达未来的任务来在未来的指定时刻主动执行任务并向用户主动反馈结果（文本、图片、文件都可）。

![](https://files.astrbot.app/docs/source/images/proactive-agent/image.png)

在 v4.14.0 引入，目前是**实验性功能**，未稳定。

## 未来任务 (FutureTask)

主 Agent 现在可以管理一个全局的 **Cron Job 列表**，为未来的自己设置任务。

### 功能特点

- **自我唤醒**：AstrBot 会在预定时间自动唤醒并执行任务。
- **任务反馈**：执行完成后，AstrBot 会将结果告知任务布置方。
- **WebUI 管理**：你可以在 WebUI 的“定时任务”页面查看、编辑或删除已设置的任务。

### 如何使用

> [!TIP]
> 首先，确保配置中 “主动型能力” 已启用。

主 Agent 拥有管理定时任务的能力。你可以直接对它说：
- “明天早上 8 点提醒我开会”
- “每周五下午 5 点总结本周的工作日志”
- “帮我定一个 10 分钟后的闹钟”

主 Agent 会调用内置的定时任务工具来安排这些计划。

你可以在 AstrBot WebUI 左侧导航栏中点击 **未来任务** 来查看和管理所有未来任务。

![](https://files.astrbot.app/docs/source/images/proactive-agent/image-1.png)

### 支持的平台

“定时任务”的设置支持所有平台，然而，由于部分平台没有开放主动消息推送的 API，因此只有以下平台支持 AstrBot 主动向用户推送结果：

- Telegram
- OneBot v11
- Slack
- 飞书 (Lark)
- Discord
- Misskey
- Satori

## 多媒体消息的发送

为了方便 Agent 直接向用户发送图片、音频、视频等文件，AstrBot 默认提供了一个 `send_message_to_user` 工具。

### 功能特点
- **直接发送**：Agent 可以直接将生成或获取的多媒体文件发送给用户，而无需通过复杂的文本转换。
- **支持多种格式**：支持图片、文件、音频、视频等。
