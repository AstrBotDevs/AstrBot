# 接入企业微信智能机器人平台

企业微信智能机器人是企业微信官方推出的 AI 友好的机器人平台，可在单聊或群聊（企业微信内部群）中直接使用，并且支持流式传输。

## 支持的基本消息类型

> 版本 v4.15.0。

| 消息类型 | 是否支持接收 | 是否支持发送 | 备注 |
| --- | --- | --- | --- |
| 文本 | 是 | 是 | |
| 图片 | 是 | 是 | 仅限配置了消息推送 Webhook URL。|
| 语音 | 否 | 是 | 仅限配置了消息推送 Webhook URL。|
| 视频 | 否 | 是 | 仅限配置了消息推送 Webhook URL。|
| 文件 | 否 | 是 | 仅限配置了消息推送 Webhook URL。|

主动消息推送：支持，但需要配置消息推送 Webhook URL。

## 配置智能机器人

1. 登录到[企业微信后台](https://work.weixin.qq.com/wework_admin)。

2. 在左侧导航栏中，点击 `管理工具`，找到 `智能机器人`，点击进入，然后点击创建机器人。

![管理工具-智能机器人](https://files.astrbot.app/docs/source/images/wecom_ai_bot/image-1.png)

3. 在创建智能机器人页面下方找到并点击 `API模式创建`。填写机器人名称、头像等基本信息。Token、EncodingAESKey 请点击 `随机获取` 按钮生成。生成之后，先不要点击创建，接下来将配置 AstrBot。

![创建智能机器人账号](https://files.astrbot.app/docs/source/images/wecom_ai_bot/image.png)

## 配置 AstrBot

1. 进入 AstrBot 的管理面板，点击左侧栏 `消息平台`，然后在右侧的界面中，点击 `+ 新增适配器`，选择 `企业微信智能机器人`，进入配置页面。

![新增适配器](https://files.astrbot.app/docs/source/images/wecom_ai_bot/image-2.png)

2. 在弹出的配置项中将 `企业微信智能机器人的名字`、`token`、`encoding_aes_key` 从上一步创建智能机器人时填写的值复制粘贴到对应的输入框中。ID 可以随意填写，用于区分不同的消息平台实例。`port` 默认为 `6198`，可以根据需要修改，但请确保该端口未被占用。请保持 `统一 Webhook 模式 (unified_webhook_mode)` 为开启状态。点击 `保存`。

3. 回到企业微信智能机器人创建页面，填写 `URL`：

   - 如果开启了 `统一 Webhook 模式`，点击保存之后，AstrBot 将会自动为你生成唯一的 Webhook 回调链接，你可以在日志中或者 WebUI 的机器人页的卡片上找到，将该链接填入 `URL` 处。

   ![unified_webhook](https://files.astrbot.app/docs/source/images/use/unified-webhook.png)

   - 如果没有开启 `统一 Webhook 模式`，填写 `http://IP:port/webhook/wecom-ai-bot`，其中 `IP` 替换为你的 AstrBot 服务器的公网 IP 地址，`port` 替换为上一步填写的端口号。

> 建议有能力的用户自行配置域名和反向代理，将请求转发到 AstrBot 所在服务器的 `6185` 端口（如果开启了统一 Webhook 模式）或配置指定的端口（如果没有开启统一 Webhook 模式），并使用 HTTPS 协议。如果没有域名，也可以使用 [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/)。

4. 点击 `创建` 按钮，如果一切无误，将进入智能机器人详情页面。如果报错 `服务没有正确响应，请确认后重试`，请检查 AstrBot 的配置、服务器防火墙端口放行规则等。

![创建智能机器人详情页面](https://files.astrbot.app/docs/source/images/wecom_ai_bot/image-3.png)

5. [可选，推荐] 配置企业微信消息推送 Webhook URL。默认情况下，企业微信智能机器人只能在用户主动发送消息时被动回复消息。如果希望实现机器人主动消息推送功能，可以配置企业微信的消息推送 Webhook URL。只需要在企业微信内部群中，点击群设置 -消息推送，创建一个推送机器人，然后将下方生成的 Webhook URL 填入配置中即可。要求 AstrBot 版本不低于 v4.15.0。企业微信智能机器人之支持图片和文本消息类型，如果配置了该选项，在发送其他类型消息（如视频、音频、文件）时，AstrBot 将会调用消息推送的接口去发送消息。**强烈建议配置该选项以获得更完整的消息类型支持。**

6. [可选，推荐] 企业微信智能机器人只支持对用户的一个消息回复最多一个消息气泡。如果您希望机器人发送更复杂的消息（例如连续发送多条消息、包含图片或文件的消息等），您可打开 「仅使用 Webhook 发送消息」。这将仅使用 Webhook 方式发送消息，绕过企业微信智能机器人的回复限制。**如果您不需要类似企业微信智能机器人那样的打字机效果，强烈建议您打开此选项。**此选项需要您配置第 5 步中的消息推送 Webhook URL。

## 使用智能机器人

### 将机器人添加到群聊

在企业微信客户端的企业内部群中，点击添加成员，点击智能机器人，找到刚刚创建的智能机器人，点击添加即可。

![点击添加成员](https://files.astrbot.app/docs/source/images/wecom_ai_bot/image-4.png)

![添加成功](https://files.astrbot.app/docs/source/images/wecom_ai_bot/image-5.png)

### 使用机器人

在单聊或群聊中，直接发送消息即可与机器人进行对话。

如果您需要类似实时打字机的效果，请确保在 AstrBot 中开启了 `流式回复` 功能。

![流式回复](https://files.astrbot.app/docs/source/images/wecom_ai_bot/image-6.png)

## 帮助与支持

如您在配置或使用过程中遇到问题，或需要其他企业支持服务，可发送邮件至 [community@astrbot.app](mailto://community@astrbot.app)。
