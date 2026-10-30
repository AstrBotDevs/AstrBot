# 接入 QQ 官方机器人平台

QQ 官方机器人平台是腾讯官方提供的一个机器人接入平台，允许开发者通过官方接口将机器人接入 QQ 群聊和个人聊天中。

目前主要通过 Webhook 方式接入。

- [Webhook 方式](/platform/qqofficial/webhook)
- [Websockets 方式](/platform/qqofficial/websockets)

## 默认消息格式

在 WebUI 的 `机器人` 页面打开 QQ 官方机器人的配置，找到 **默认使用 Markdown**（原名 **主动消息使用 Markdown**）。此设置同时适用于 WebSocket 和 Webhook 的普通 AI 回复、插件回复以及主动消息。

- 开启时，未指定格式的消息默认使用 Markdown；关闭时，默认发送纯文本。
- 插件通过 `MessageChain.use_markdown(True)` 或 `MessageChain.use_markdown(False)` 显式指定格式时，消息级设置优先；`None` 跟随平台配置。
- C2C 回复选择纯文本时，流式生成的内容会在回复结束或工具调用前累积后普通发送；选择 Markdown 时继续使用原有流式发送。
- 图片、语音、视频和文件仍使用各自的富媒体发送方式。

配置键仍为 `use_markdown`，默认值仍为 `true`，无需迁移旧配置。**已有配置将此项设为 `false` 时，升级后普通回复也会改为纯文本**，不再仅影响主动消息。
