# 统一 Webhook 模式

在 v4.8.0 版本开始，AstrBot 支持统一 Webhook 模式 (unified_webhook_mode)。开启该模式后，所有支持该模式的平台适配器都将使用同一个 Webhook 回调接口，从而简化了反向代理和域名配置，不再需要给每一个机器人适配器单独配置端口、域名和反向代理。

支持统一 Webhook 模式的平台适配器包括：

- Slack Webhook 模式
- 微信公众平台
- 企业微信客服机器人
- 企业微信智能机器人
- 微信客服机器人
- QQ 官方机器人 Webhook 模式
- ...

## 如何使用统一 Webhook 模式

1. 拥有一个域名（如 example.com）和公网 IP 服务器
2. 配置 DNS 解析（如 astrbot.example.com）
3. 配置反向代理，将域名的 80 或 443 端口请求转发到 AstrBot 的 WebUI 端口（默认为 6185）
4. 前往 AstrBot `配置文件` 页，点击 `系统`，将 `对外可达的回调接口地址` 为配置的 URL 地址。（如 https://astrbot.example.com），点击保存，等待重启。


在之后配置各个平台适配器时，选择开启 `统一 Webhook 模式 (unified_webhook_mode)`。

> [!TIP]
> 如果您正在尝试更新 v4.8.0 之前配置的机器人适配器，你可能无法看到 `统一 Webhook 模式 (unified_webhook_mode)` 选项。请重新创建一个新的适配器实例，即可看到该选项。

![unified_webhook](https://files.astrbot.app/docs/source/images/use/unified-webhook-config.png)

开启该模式后，AstrBot 会为你生成一个唯一的 Webhook 回调链接，你只需要将该链接填写到各个平台的回调地址处即可。

![unified_webhook](https://files.astrbot.app/docs/source/images/use/unified-webhook.png)
