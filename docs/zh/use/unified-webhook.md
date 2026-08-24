# 统一 Webhook 模式

统一 Webhook 模式让多个平台适配器共用 AstrBot Dashboard 的 FastAPI 服务和端口 `6185`。每个平台实例会获得独立的回调路径：

```text
/api/v1/webhooks/platforms/<webhook_uuid>
```

这样通常只需要为一个域名和一个 HTTPS 入口配置反向代理，不必为每个机器人开放单独的回调端口。

## 当前支持的平台

当前代码中支持统一 Webhook 的平台类型只有：

| 平台                       | 使用条件                                     |
| -------------------------- | -------------------------------------------- |
| QQ 官方机器人              | 创建 `QQ 官方机器人（Webhook）` 平台。       |
| 微信公众平台               | 开启 `unified_webhook_mode`。                |
| 企业微信（应用和微信客服） | 开启 `unified_webhook_mode`。                |
| 企业微信智能机器人         | 连接模式必须是 `webhook`；长连接不接收回调。 |
| Slack                      | 连接模式必须是 `webhook`。                   |
| 飞书/Lark                  | 连接模式必须是 `webhook`。                   |
| LINE                       | 适配器固定使用统一 Webhook。                 |

其他平台即使也使用 HTTP，也不会因为手动添加同名配置项而自动接入该入口。

## 1. 准备公网入口

1. 准备域名，例如 `astrbot.example.com`，并将 DNS 指向你的服务器或负载均衡器。
2. 配置有效的 HTTPS 证书。
3. 将外部请求反向代理到 AstrBot 的 `6185` 端口。回调路由需要同时允许 `GET` 和 `POST`。

如果反向代理和 AstrBot 位于同一主机，代理可以连接默认的 `127.0.0.1:6185`。如果 AstrBot 位于另一个容器，则还必须让 WebUI 监听对应网络接口；参见 [Docker 部署](/deploy/astrbot/docker) 或 [源码部署](/deploy/astrbot/cli)。只发布端口但保留容器内的环回监听无法工作。

> [!CAUTION]
> 统一 Webhook 与管理面板共用 `6185`。请限制管理页面的公网访问，使用强密码和 TOTP，并在反向代理或防火墙中实施适当的访问控制。

## 2. 设置公开基地址

在 AstrBot WebUI 中进入 `设置` -> `常规`，填写 `对外可达的回调接口地址`（配置键 `callback_api_base`）：

```text
https://astrbot.example.com
```

该值是外部服务实际访问 AstrBot 的公开基地址。它只用于生成和展示回调/文件 URL，不会自动配置 DNS、TLS、端口映射或反向代理。请不要在末尾填写某个平台的 `/api/v1/webhooks/...` 路径。

系统配置会自动保存；如果页面提示需要重启，请在继续创建平台前重启 AstrBot。

## 3. 创建平台并复制回调 URL

1. 在 `机器人` 中创建或编辑上表中的平台。
2. 对有开关的平台启用 `unified_webhook_mode`；Slack、Lark、企业微信智能机器人还要选择 Webhook 连接模式。
3. 保存平台。AstrBot 会自动生成并持久化 `webhook_uuid`。
4. 从机器人卡片的 `查看 Webhook URL` 或 AstrBot 日志复制完整地址，例如：

   ```text
   https://astrbot.example.com/api/v1/webhooks/platforms/0123456789abcdef
   ```

5. 将完整地址填入对应平台后台的事件回调 URL，并按该平台文档完成签名、Token、加密密钥和事件订阅配置。

不要手工复用另一个机器人实例的 `webhook_uuid`。同一平台的多个实例也应各自使用生成的 URL。

## 故障排查

- 回调 URL 显示 `http(s)://<your-astrbot-domain>`：尚未正确填写 `callback_api_base`，或平台尚未重新加载配置。
- 外部请求超时：检查 DNS、证书、反向代理、云安全组和防火墙；容器还要检查 WebUI 监听地址。
- 返回 404：确认代理没有丢失 `/api/v1/webhooks/platforms/<uuid>` 路径，且 UUID 来自当前平台实例。
- 企业微信智能机器人返回长连接模式不接受回调：把连接模式切换为 `webhook`，或者继续使用推荐的长连接而不要配置入站 URL。
- 平台验证签名失败：统一入口只负责路由，请继续核对该平台自己的 Secret、Token、EncodingAESKey 或签名密钥。
