# 主动型能力

AstrBot 引入了主动 Agent（Proactive Agent）系统，使 AstrBot 不仅能被动响应用户，还能通过给自己下达未来的任务来在未来的指定时刻主动执行任务并向用户主动反馈结果（文本、图片、文件都可）。

![](https://files.astrbot.app/docs/source/images/proactive-agent/image.png)

目前这是一个**实验性功能**，尚未稳定。

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

### 时区

如果当前配置档的 `timezone` 填写了 IANA 时区名称（例如 `Asia/Shanghai`），Agent 创建的任务会使用该时区。周期任务和不带时区的一次性时间会按该时区解释，Agent 返回的任务时间也会转换为该时区显示。配置为空或无效时使用系统时区；无效值不会作为任务时区保存。一次性任务也可以直接使用带偏移量的 ISO 时间，例如 `2026-02-02T08:00:00+08:00`。

### 支持的平台

“定时任务”可以在任意平台会话中创建，但只有实现了主动发送的适配器才能在任务执行后把结果推回原会话。当前内置适配器包括：

- Telegram
- OneBot v11（aiocqhttp 与 NapCat）
- Slack
- 飞书 (Lark)
- Discord
- Misskey
- Satori
- KOOK
- LINE
- Mattermost
- 钉钉 (DingTalk)
- 企业微信（应用模式；客服模式不支持）
- 企业微信智能机器人
- 个人微信
- WebChat
- QQ 官方机器人（WebSocket 及 Webhook）

上述清单以当前内置适配器是否具体实现 `send_by_session()` 为准；仅凭元数据不能证明消息一定能够送达。具体行为仍受平台 API、权限、回复窗口和已保存会话路由限制。例如，企业微信智能机器人需要配置出站消息推送 Webhook，个人微信需要目标会话仍有有效的 context token，QQ 官方机器人需要可用的本地缓存会话状态。微信公众号不在清单中，因为其适配器会明确拒绝主动发送。插件提供的平台适配器则需要自行实现 `send_by_session()`。

## 多媒体消息的发送

为了方便 Agent 直接向用户发送图片、音频、视频等文件，AstrBot 默认提供了一个 `send_message_to_user` 工具。

### 功能特点

- **直接发送**：Agent 可以直接将生成或获取的多媒体文件发送给用户，而无需通过复杂的文本转换。
- **支持多种格式**：支持图片、文件、音频、视频等。
