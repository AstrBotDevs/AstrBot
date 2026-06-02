
# 接入 Telegram

## 支持的基本消息类型

> 版本 v4.15.0。

| 消息类型 | 是否支持接收 | 是否支持发送 | 备注 |
| --- | --- | --- | --- |
| 文本 | 是 | 是 | |
| 图片 | 是 | 是 | |
| 语音 | 是 | 是 | |
| 视频 | 是 | 是 | |
| 文件 | 是 | 是 | |
| Inline Keyboard | 是 | 是 | 支持按钮回调事件 |
| Reply Keyboard | - | 是 | 支持自定义回复键盘、移除键盘、强制回复 |
| Inline Query | 是 | 是 | 插件可监听并回答 inline query |


主动消息推送：支持。

## 交互增强事件

Telegram 适配器支持插件监听 callback query、inline query、chosen inline result、成员状态变更、成员加入/离开、poll、dice 等 Telegram 专属事件。插件需要使用自定义过滤器 `@filter.custom_filter(telegram_event_filter(...))` 注册处理函数，常见事件类型包括 `callback_query`、`inline_query`、`chosen_inline_result`、`chat_member`、`my_chat_member`、`member_joined`、`member_left`。

这些结构化事件默认不会进入普通 LLM 对话流程；请用 `telegram_event_filter(...)` 精确匹配后在插件里处理，否则用户点击按钮或触发 inline/member 事件时可能看起来“没有响应”。

按钮回调短示例：

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.platform.sources.telegram.filters import telegram_event_filter

@filter.custom_filter(telegram_event_filter("callback_query"))
async def on_telegram_button(self, event: AstrMessageEvent):
    data = event.get_interaction_data()
    await event.answer_interaction(f"已收到：{data}", show_alert=False)
```

完整 Inline Keyboard、Reply Keyboard、inline query answer 与回调处理示例见开发指南中的「Telegram 专属发送选项」。

## 1. 创建 Telegram Bot

首先，打开 Telegram，搜索 `BotFather`，点击 `Start`，然后发送 `/newbot`，按照提示输入你的机器人名字和用户名。

创建成功后，`BotFather` 会给你一个 `token`，请妥善保存。

如果需要在群聊中使用，需要关闭Bot的 [Privacy mode](https://core.telegram.org/bots/features#privacy-mode)，对 `BotFather` 发送  `/setprivacy` 命令，然后选择bot， 再选择 `Disable`。

## 2. 配置 AstrBot

1. 进入 AstrBot 的管理面板
2. 点击左边栏 `机器人`
3. 然后在右边的界面中，点击 `+ 创建机器人` 
4. 选择 `telegram`

弹出的配置项填写：

- ID(id)：随意填写，用于区分不同的消息平台实例。
- 启用(enable): 勾选。
- Bot Token: 你的 Telegram 机器人的 `token`。

请确保你的网络环境可以访问 Telegram。你可以使用 `配置页->其他配置->HTTP 代理` 设置全局代理，也可以在 Telegram 适配器里设置独立代理：

- `telegram_proxy`：仅用于此 Telegram 适配器的 Bot API 请求。
- `telegram_get_updates_proxy`：仅用于此 Telegram 适配器轮询 `getUpdates` 的请求。

### 更新模式

Telegram 默认使用 `telegram_update_mode="polling"`，通过 `getUpdates` 轮询接收 update。也可以切换为 `telegram_update_mode="webhook"` 使用 Telegram 适配器独立 webhook listener。

启用 webhook 模式时需要配置：

- `telegram_webhook_listen`：本地监听地址。
- `telegram_webhook_port`：本地监听端口。
- `telegram_webhook_url_path`：本地 webhook 路径。
- `telegram_webhook_url`：Telegram 可访问的 HTTPS 公开 URL，必填。
- `telegram_webhook_secret_token`：可选，用于校验 Telegram webhook 请求。
- `telegram_webhook_drop_pending_updates`：启动 webhook 时是否丢弃待处理 update。

如果通过 Nginx/Caddy 等反向代理提供 HTTPS，通常不需要填写 `telegram_webhook_cert_path` 和 `telegram_webhook_key_path`；只有让 `python-telegram-bot` 直接提供 HTTPS 时才需要填写证书和私钥路径。

## 命令注册

Telegram 适配器可以把 AstrBot 插件指令注册为 Telegram Bot Commands：

- `telegram_command_register`：是否启用命令注册。
- `telegram_command_auto_refresh`：是否在运行时自动刷新命令。
- `telegram_command_register_interval`：自动刷新间隔，单位为秒。
- `telegram_command_registered_plugins`：只注册所选插件提供的指令。留空表示注册全部已启用插件的指令。
- `telegram_command_scopes`：注册范围配置。默认值为 `[{"type": "default"}]`。

`telegram_command_scopes` 支持 Telegram Bot API 的这些范围：`default`、`all_private_chats`、`all_group_chats`、`all_chat_administrators`、`chat`、`chat_administrators`、`chat_member`。其中 `chat`、`chat_administrators` 需要 `chat_id`，`chat_member` 需要 `chat_id` 和 `user_id`。每个范围都可以额外设置 `language_code`。

示例：

```json
[
  {"type": "default", "language_code": "zh"},
  {"type": "chat", "chat_id": 123456789}
]
```

Telegram 每个 scope 最多支持 100 条命令。如果注册失败，请使用 `telegram_command_registered_plugins` 缩小要注册的插件范围。

## 流式输出

Telegram 平台支持流式输出。需要在「AI 配置」->「其他配置」中开启「流式输出」开关。

### 私聊流式输出

在私聊中，AstrBot 使用 Telegram Bot API v9.3 新增的 `sendMessageDraft` API 实现流式输出。这种方式会在私聊界面展示一个「正在输入」的草稿预览动画，体验更接近「打字机」效果，且避免了传统方案的消息闪烁、推送通知干扰和 API 编辑频率限制等问题。

### 群聊流式输出

在群聊中，由于 `sendMessageDraft` API 仅支持私聊，AstrBot 会自动回退到传统的 `send_message` + `edit_message_text` 方案。

:::warning
`sendMessageDraft` 功能需要 `python-telegram-bot>=22.6`。
:::
