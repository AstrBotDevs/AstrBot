# 接入企业微信智能机器人

企业微信智能机器人可用于企业内部单聊和群聊，并支持流式回复。AstrBot 提供两种连接模式：

- **长连接（默认、推荐）**：AstrBot 主动连接企业微信，不需要公网 IP、域名或入站 Webhook。
- **Webhook 回调**：企业微信主动请求 AstrBot，需要公网可达的 HTTPS 地址。

新建 `企业微信智能机器人` 平台时，当前模板默认选择 `long_connection`。除非企业网络或现有配置要求 Webhook，否则优先使用长连接。

## 消息能力

| 消息类型 | 接收 | 发送 | 说明                                   |
| -------- | ---- | ---- | -------------------------------------- |
| 文本     | 是   | 是   | 支持流式回复。                         |
| 图片     | 是   | 是   | 发送图片需要配置消息推送 Webhook URL。 |
| 语音     | 否   | 是   | 发送语音需要配置消息推送 Webhook URL。 |
| 视频     | 否   | 是   | 发送视频需要配置消息推送 Webhook URL。 |
| 文件     | 否   | 是   | 发送文件需要配置消息推送 Webhook URL。 |

主动消息推送也需要配置消息推送 Webhook URL。这里的“消息推送 Webhook”是 AstrBot 向企业微信群机器人发消息的**出站**地址，与企业微信向 AstrBot 推送事件的入站回调不是同一个概念。

## 方式一：长连接（推荐）

### 1. 在企业微信创建机器人

1. 登录[企业微信管理后台](https://work.weixin.qq.com/wework_admin)。
2. 进入 `管理工具` -> `智能机器人`，创建 API 模式机器人。
3. 在机器人的长连接配置中取得 `BotID` 和 `Secret`。请像密码一样保管 Secret。

企业微信后台的具体文字可能随版本变化；需要的是长连接凭证，而不是 Webhook 回调模式使用的 Token 和 EncodingAESKey。

### 2. 在 AstrBot 创建平台

1. 打开 AstrBot WebUI，进入 `机器人`。
2. 点击 `+ 创建机器人`，选择 `企业微信智能机器人`。
3. 保持连接模式为 `长连接`（`long_connection`）。
4. 填写：
   - `wecom_ai_bot_name`：与企业微信中的机器人名称一致。
   - `wecomaibot_ws_bot_id`：企业微信提供的 BotID。
   - `wecomaibot_ws_secret`：企业微信提供的 Secret。
5. 保存平台配置。

`wecomaibot_ws_url` 默认为 `wss://openws.work.weixin.qq.com`，心跳间隔默认为 30 秒，通常无需修改。

长连接模式不启动本地回调服务器，也不使用 `unified_webhook_mode`、Token、EncodingAESKey 或回调端口。AstrBot 所在网络只需能够主动访问企业微信的 WebSocket 服务。

### 3. 验证

在 AstrBot `控制台` 中确认出现长连接启动/连接日志，然后在企业微信中向机器人发送消息。若无法连接，重点检查 BotID、Secret、服务器出站网络、代理和 TLS 检查，而不是检查入站端口。

## 方式二：Webhook 回调

只有明确需要回调方式时才使用本节。

### 1. 准备公网回调入口

1. 为 AstrBot 准备公网可达的 HTTPS 域名。
2. 将反向代理转发到 AstrBot WebUI 端口 `6185`。
3. 在 WebUI 的 `设置` -> `常规` 中填写 `对外可达的回调接口地址`，例如 `https://astrbot.example.com`。

如果 AstrBot 运行在 Docker 中，还必须让 WebUI 监听容器网络接口；参见 [Docker 部署](/deploy/astrbot/docker)。不要只发布端口而保留 `127.0.0.1` 监听。

### 2. 配置企业微信和 AstrBot

1. 在企业微信管理后台创建 API 模式智能机器人，选择 Webhook/回调连接方式，并生成 Token 和 EncodingAESKey。
2. 在 AstrBot 创建 `企业微信智能机器人`，将连接模式改为 `webhook`。
3. 填写机器人名称、`wecomaibot_token` 和 `wecomaibot_encoding_aes_key`，并保持 `unified_webhook_mode` 开启。
4. 保存后，从 AstrBot 日志或 WebUI 机器人卡片复制为该实例生成的唯一回调 URL。
5. 将该 URL 填入企业微信机器人的回调地址并完成验证。

![统一 Webhook 回调地址](https://files.astrbot.app/docs/source/images/use/unified-webhook.png)

统一 Webhook 模式复用 AstrBot 的 `6185` 端口，不需要单独开放 `6198`。

如果关闭统一 Webhook，适配器才会启动独立服务器，路径为 `/webhook/wecom-ai-bot`，默认端口为 `6198`，默认监听地址为 `127.0.0.1`。远程回调时还必须把 `callback_server_host` 改为 `0.0.0.0` 或指定可达接口，并单独保护、转发该端口；通常不建议这样部署。

## 可选：配置消息推送 Webhook

企业微信智能机器人的直接回复能力受消息类型和回复窗口限制。若需要图片、语音、视频、文件、连续多条消息或主动推送：

1. 在企业微信内部群的群设置中创建“消息推送”机器人。
2. 将生成的 URL 填入 AstrBot 的 `msg_push_webhook_url`。
3. 如果希望所有回复都经该地址发送，启用 `only_use_webhook_url_to_send`。

该 URL 包含敏感 key，不要写入日志、截图或公开配置。它可以同时配合长连接和入站 Webhook 模式使用。

## 使用机器人

在企业微信内部群中通过 `添加成员` -> `智能机器人` 添加已创建的机器人，也可以直接进入单聊。需要打字机效果时，请在 AstrBot 中启用流式回复。
