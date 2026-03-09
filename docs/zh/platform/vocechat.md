# 接入 VoceChat

> [!TIP]
> AstrBot 未自带这个适配器，需要安装 [astrbot_plugin_vocechat](https://github.com/HikariFroya/astrbot_plugin_vocechat) 插件。该插件由 [HikariFroya](https://github.com/HikariFroya) 开发 ❤️。
> **如果您觉得有帮助，请支持开发者，给该仓库点一个 Star。**

> [!WARNING]
> 这个适配器目前不由 AstrBot 官方维护，因此稳定性未知。

## 部署 VoceChat

VoceChat 是一个开源的支持多平台、搭建简单的即时通讯平台。

请在 [VoceChat 官方网站](https://voce.chat/zh-CN)查看部署方式。

## 安装 astrbot_plugin_vocechat 插件

进入 AstrBot 仪表盘的插件市场，搜索 `astrbot_plugin_vocechat`，点击安装。

![image](https://files.astrbot.app/docs/source/images/vocechat/image.png)

安装完成后，前往 `机器人` → `+ 创建机器人` → 选择 VoceChat（若选项缺失，尝试重启 AstrBot 或检查插件安装状态）。

在弹出的配置对话框中点击 `启用`。

## 配置

- **`vocechat_server_url` (必填)**: 您的 VoceChat 服务器的完整 URL 地址。例如: `http://localhost:3009` 或 `https://your.vocechat.domain`。请确保末尾没有 `/`。
- **`api_key` (必填)**: 您在 VoceChat 后台为该机器人账号生成的 API Key。
- **`webhook_path` (建议保留默认或自定义)**: AstrBot 用于接收 VoceChat 推送消息的 Webhook 路径。例如: `/vocechat_webhook`。您需要在 VoceChat 机器人设置中填写的 Webhook URL 将是 `http://<你的AstrBot可访问地址>:<webhook_port><webhook_path>`。
- **`webhook_listen_host` (通常为 `0.0.0.0`)**: AstrBot Webhook 服务器监听的IP地址。`0.0.0.0` 表示监听所有可用的网络接口。
- **`webhook_port` (必填)**: AstrBot Webhook 服务器监听的端口号。例如: `8080`。请确保此端口未被其他应用占用，并且如果您的 AstrBot 服务器在防火墙后，此端口需要被允许访问。
- **`get_user_nickname_from_api` (布尔值, 默认: `true`)**: 是否尝试通过 VoceChat API 获取用户昵称。如果为 `false`，将使用 `VoceChatUser_UID` 作为默认昵称。
- **`send_plain_as_markdown` (布尔值, 默认: `false`)**: 如果为 `true`，发送纯文本消息时会使用 Markdown 格式（可能会影响部分纯文本的显示，但能更好地支持一些特殊字符）。通常建议保持 `false`，除非有特定需求。
- **`default_bot_self_uid` (必填)**: 您要连接的这个 VoceChat 机器人账号在 VoceChat 中的用户 ID (UID)。

全部配置好后，点击右下角的保存按钮。然后前往 VoceChat 中测试。

## 问题提交

如有疑问，请提交 issue 至[插件仓库](https://github.com/HikariFroya/astrbot_plugin_vocechat/issues) 以及 [AstrBot 仓库](https://github.com/AstrBotDevs/AstrBot/issues/new?template=bug-report.yml)。

**如果您觉得有帮助，请支持开发者，给 [astrbot_plugin_vocechat](https://github.com/HikariFroya/astrbot_plugin_vocechat) 仓库点一个 Star。**
