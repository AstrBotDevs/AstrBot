
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


主动消息推送：支持。

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

请确保你的网络环境可以访问 Telegram。你可能需要使用 `配置页->其他配置->HTTP 代理` 来设置代理。

## 流式输出

Telegram 平台支持流式输出。需要在「AI 配置」->「其他配置」中开启「流式输出」开关。

### 私聊流式输出

在私聊中，AstrBot 使用 Telegram Bot API v9.3 新增的 `sendMessageDraft` API 实现流式输出。这种方式会在私聊界面展示一个「正在输入」的草稿预览动画，体验更接近「打字机」效果，且避免了传统方案的消息闪烁、推送通知干扰和 API 编辑频率限制等问题。

### 群聊流式输出

在群聊中，由于 `sendMessageDraft` API 仅支持私聊，AstrBot 会自动回退到传统的 `send_message` + `edit_message_text` 方案。

:::warning
`sendMessageDraft` 功能需要 `python-telegram-bot>=22.6`。
:::
