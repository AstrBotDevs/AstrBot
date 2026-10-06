# 接入 Sendblue（iMessage 和 SMS）

Sendblue 提供托管号码，AstrBot 通过统一 Webhook 接收私聊文字，并通过 Sendblue API 回复。
此适配器支持文字私聊和主动文字消息，不支持群聊或媒体上传。请先配置 AstrBot 的模型提供商。

## 账号与配置

1. 新的免费代理账号可运行 `npx -y @sendblue/cli@0.10.0 setup --phone +你的个人号码`。
2. 用该手机发送命令显示的验证短信，再运行 `npx -y @sendblue/cli@0.10.0 setup --check`。
   退出码 3 表示仍等待验证。完成后，凭据位于 `~/.sendblue/credentials.json`。
3. 在 AstrBot 管理面板的机器人平台中添加 **Sendblue**，填写唯一 ID 并启用。
4. 将 `apiKey`、`apiSecret`、`assignedNumber` 分别填入 API key ID、API secret 和发送号码。
   `assignedNumber` 是分配的线路号码，不是个人手机号码。
5. 使用 `openssl rand -hex 32` 生成 Webhook 密钥，将个人 E.164 手机号码加入发送者白名单。
   空白名单禁止启动；`*` 明确允许所有发送者。AstrBot 的权限检查仍然生效。
6. 保存配置，复制 Webhook 地址，通过公网 HTTPS 反向代理或隧道将该地址转发到 AstrBot。

## 注册 Webhook 与验证

按照[英文指南的 Webhook 注册步骤](/en/platform/sendblue#register-the-receive-webhook)，
将相同的密钥、线路和回调地址注册到 Sendblue。使用 POST 追加配置，避免替换已有 Webhook。
免费账号的其他联系人还需运行 `npx -y @sendblue/cli@0.10.0 add-contact +联系人号码`，
并让该联系人向分配的线路发送短信；本地白名单不能替代服务商验证。

向线路发送“记住 cobalt”，确认手机收到回复，然后询问刚才的单词并检查会话记录。
未授权号码不应触发模型调用，错误的 `sb-signing-secret` 应返回 HTTP 401。
`QUEUED` 仅表示服务商接受请求，请在真实手机上确认送达。

## 限制

- 仅支持私聊文字；附件以不支持媒体的提示传给模型，不下载附件 URL。
  群消息、发送回声和状态回调被忽略。请关闭文字转图片和 TTS 回复。
- 回调正文限制为 64 KiB，共享事件队列达到 128 条时返回 503。
  HTTP 200 表示进入内存队列，不代表持久化或送达。
- 每个适配器保留最近 4096 个消息标识用于去重；重启或缓存淘汰后可能重复处理。
- 回复按 2000 字符分段，超时 30 秒，不自动重试。遇到失败时先检查 Sendblue，
  避免重复发送已被接受的分段。
- 断开连接时，停用该适配器并仅删除其对应的 Sendblue Webhook。

完整设置、故障排查和服务商参考见[英文指南](/en/platform/sendblue)。
