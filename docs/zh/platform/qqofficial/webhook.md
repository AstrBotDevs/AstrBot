# 通过 QQ官方机器人 接入 QQ (Webhook)

> [!WARNING]
>
> 1. 截至目前，QQ 官方机器人需要设置 IP 白名单。
> 2. Webhook 模式需要一台带公网 IP 的服务器、域名和 HTTPS 访问能力。
> 3. 支持群聊、私聊、频道聊天、频道私聊。

## 支持的基本消息类型

> 版本 v4.19.6。

| 消息类型 | 是否支持接收 | 是否支持发送 | 备注 |
| --- | --- | --- | --- |
| 文本 | 是 | 是 | |
| 图片 | 是 | 是 | |
| 语音 | 是 | 是 | |
| 视频 | 是 | 是 | |
| 文件 | 是 | 是 | |

主动消息推送：支持。

## 在 AstrBot 中扫码一键创建 QQ 机器人（推荐）

### 配置流程

1. 进入 AstrBot 的 WebUI，点击左边栏 `机器人`，然后点击 `+ 创建机器人`。
2. 选择 `QQ 官方机器人（Webhook）`。
3. 在 `选择创建方式` 中选择 `扫码一键创建`，点击开始创建后，用手机 QQ 扫描页面中的二维码。
4. 扫码确认后，点击 `保存`。
5. 根据服务器环境配置域名 DNS 解析和反向代理，将 HTTPS 请求转发到 AstrBot 所在服务器的 `6185` 端口。
6. 回到 QQ 开放平台的机器人管理页，在 `开发 -> 回调配置` 中填写 AstrBot 生成的 Webhook 回调地址。
7. 在回调事件中勾选需要接收的事件。如果需要接收群聊全量消息，请确保勾选群事件 `GROUP_MESSAGE_CREATE`。
8. 保存回调配置后，重启 AstrBot。

> [!TIP]
> 使用 `统一 Webhook 模式` 时，AstrBot 会自动生成唯一的 Webhook 回调链接。你可以在日志中，或者 WebUI 的机器人卡片上找到该链接。

![unified_webhook](https://files.astrbot.app/docs/source/images/use/unified-webhook.png)

### 在群聊中使用

#### 添加到群聊

进入创建的 QQ 机器人的资料页（手机QQ -> 联系人 -> 机器人页签），在下方可以找到 “添加到群聊”。目前只能添加到自己为群主的群聊。

#### 设置机器人可获取的群聊消息范围和主动发言

在手机 QQ 的群聊设置中打开机器人设置，推荐将 `机器人可获取的群聊消息范围` 设置为 `获取群内全部消息`，并开启 `机器人主动在群聊内发言`。

这样机器人可以接收群聊全量消息，也可以在群聊中主动推送消息，例如定时任务推送、插件主动通知等。

Webhook 模式还需要在 QQ 开放平台的回调配置中勾选群事件 `GROUP_MESSAGE_CREATE`，否则 AstrBot 无法收到群聊全量消息事件。

![QQ 官方机器人推荐群聊配置](/qqofficial-group-recommended-config.png)

## 手动申请 QQ 机器人（不推荐）

### 申请一个机器人

首先，打开 [QQ官方机器人](https://q.qq.com) 并登录。

然后，点击创建机器人，填写名称、简介、头像等信息。然后点击下一步、提交审核。等待安全校验通过后，创建成功。

点击创建好的机器人，然后你将会被导航到机器人的管理页面。如下图所示：

![image](https://files.astrbot.app/docs/source/images/qqofficial/image.png)

### 允许机器人加入频道/群/私聊

点击`沙箱配置`，这允许你立即设置一个沙箱频道/QQ群/QQ私聊，用于拉入机器人（需要小于等于20个人）。

然后你将会看到 QQ 群配置、消息列表配置和 QQ 频道配置。根据你的需求来选择QQ群、允许私聊的QQ号、QQ频道。

![image](https://files.astrbot.app/docs/source/images/qqofficial/image-1.png)

### 获取 appid、secret

添加机器人到你想用的地方后。

点击 `开发->开发设置`，找到 appid、secret。复制并保存它们。

如果你使用 AstrBot WebUI 的 `扫码一键创建`，这一步可以跳过。扫码绑定成功后，AstrBot 会自动填入 `appid` 和 `secret`。

### 添加 IP 白名单

点击 `开发->开发设置`，找到 IP 白名单。添加你的服务器 IP 地址。

![image](https://files.astrbot.app/docs/source/images/qqofficial/image-3.png)

> [!TIP]
> 如果你不知道你的服务器 IP 地址，可以在终端中输入 `curl ifconfig.me` 来获取。或者登录 [ip138.com](https://ip138.com/) 查看。
>
> 如果你在没有公网 IP 的环境下，你看到的 IP 是运营商 NAT 的 IP，这个 IP 根据你的运营商的情况可能会随时变化。如有必要，可以配置代理。

### 在 AstrBot 配置

1. 进入 AstrBot 的管理面板
2. 点击左边栏 `机器人`
3. 然后在右边的界面中，点击 `+ 创建机器人`
4. 选择 `QQ 官方机器人（Webhook）`

推荐使用 `扫码一键创建`：

1. 在 `选择创建方式` 中选择 `扫码一键创建`。
2. 点击开始创建，用手机 QQ 扫描二维码并确认。
3. 等待页面显示绑定成功。AstrBot 会自动填入 `appid` 和 `secret`。
4. 保持 `统一 Webhook 模式` 开启，根据需要调整 `ID` 等配置，然后点击 `保存`。

如果扫码不可用，也可以选择 `手动创建`。弹出的配置项填写：

- ID(id)：随意填写，用于区分不同的消息平台实例。
- 启用(enable): 勾选。
- appid: QQ 官方机器人中获取的 appid。
- secret: QQ 官方机器人中获取的 secret。
- 统一 Webhook 模式 (unified_webhook_mode): 保持开启。

点击 `保存`。

### 配置反向代理

保存之后，请根据你的服务器环境，配置域名 DNS 解析和反向代理，将请求转发到 AstrBot 所在服务器的 `6185` 端口（如果没有开启统一 Webhook 模式，将请求转发到上一步配置指定的端口）。

Webhook 回调地址必须可以被 QQ 开放平台公网访问，并且需要使用 HTTPS。

### 设置回调地址和事件

在 `开发 -> 回调配置` 处，配置回调地址。

上一步点击保存之后，AstrBot 将会自动为你生成唯一的 Webhook 回调链接，你可以在日志中或者 WebUI 的机器人页的卡片上找到。

将请求地址填写为该地址。

填写好之后，添加事件。需要接收群聊全量消息时，请勾选群事件 `GROUP_MESSAGE_CREATE`；同时按需勾选单聊事件、频道事件等。

![image](https://files.astrbot.app/docs/source/images/webhook/image.png)

输入完成后，将光标挪出输入框，将会发送一次验证请求。如果没问题，右边的确定配置按钮将可点击，点击即可。

接着重启 AstrBot。

## 附录：如何配置反向代理

如果你还没有相关经验，这里推荐使用 Caddy 作为反向代理的工具，请参考：

1. 安装 Caddy: <https://caddy2.dengxiaolong.com/docs/install>
2. 设置反向代理: <https://caddy2.dengxiaolong.com/docs/quick-starts/reverse-proxy>

Caddy 将自动为您申请 TLS 证书，以达到接入 Webhook 的目的。
