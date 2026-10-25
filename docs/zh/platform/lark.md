# 接入飞书

## 支持的基本消息类型

> 版本 v4.16.0。

| 消息类型 | 是否支持接收 | 是否支持发送 | 备注 |
| --- | --- | --- | --- |
| 文本 | 是 | 是 | |
| 图片 | 是 | 是 | |
| 语音 | 是 | 是 | 接收时转为 wav，发送时转为 opus |
| 视频 | 是 | 是 | 发送时转为 mp4 |
| 文件 | 是 | 是 | |

接收引用（回复）消息时，AstrBot 会解析被引用消息中的文本、图片、视频、文件等内容。

群聊中，机器人会响应 @ 机器人、@ 全体成员（未禁用时）、引用机器人消息以及以唤醒前缀（例如 `/`）开头的消息。

主动消息推送：支持。

流式输出：支持。需要在飞书开发者后台为应用开通 `创建与更新卡片(cardkit:card:write)` 权限。

飞书客户端版本需 >= 7.20。低版本客户端将只显示标题和升级提示。

## 创建机器人

飞书（Lark）支持两种创建方式：在 AstrBot 中扫码一键创建，或在飞书开发者后台手动创建企业自建应用。

### 方式一：扫码一键创建

需要 AstrBot 版本 >= v4.25.0。

进入 AstrBot 管理面板，点击左边栏 `机器人`，然后点击 `创建机器人`，选择 `lark(飞书)`。

在 `选择创建方式` 中选择 `扫码一键创建`，按需选择国内版或海外版，然后使用手机飞书扫描页面中的二维码并确认。创建成功后，AstrBot 会自动写入该应用的 `app_id`、`app_secret` 和域名配置。

> [!IMPORTANT]
> 群聊中，飞书默认只会把 @ 机器人的消息推送给 AstrBot。如果你希望机器人接收群聊中的所有消息，需要前往飞书开发者后台为应用开通 `im:message.group_msg` 权限。
>
> 可以将下面链接中的 `<APP_ID>` 替换为你的飞书应用 App ID 后打开，一键进入权限开通页：
>
> App ID 获取方式：回到 AstrBot 的 `机器人` 页，选中刚刚创建的飞书机器人，在 `接入设置` 中查看 `app_id`。
>
> ```text
> https://open.feishu.cn/app/<APP_ID>/auth?q=contact:contact.base:readonly,contact:user.base:readonly,im:message,im:message.p2p_msg:readonly,im:message.group_at_msg:readonly,im:message.group_msg,im:message:send_as_bot,im:resource,cardkit:card:write&op_from=openapi&token_type=tenant
> ```

扫码创建完成后，建议继续检查后文的事件订阅、权限、版本发布和拉入群组步骤。

### 方式二：手动创建

前往 [开发者后台](https://open.feishu.cn/app) ，创建企业自建应用。

![创建企业自建应用](https://files.astrbot.app/docs/source/images/lark/image.png)

添加应用能力——机器人。

![添加应用能力](https://files.astrbot.app/docs/source/images/lark/image-1.png)

点击凭证与基础信息，获取 app_id 和 app_secret。

![获取 app_id 和 app_secret](https://files.astrbot.app/docs/source/images/lark/image-4.png)

## 配置 AstrBot

1. 进入 AstrBot 的管理面板
2. 点击左边栏 `机器人`
3. 点击机器人列表上方的 `创建机器人`
4. 选择 `lark(飞书)`
5. 如果使用扫码一键创建，选择 `扫码一键创建` 并完成扫码；如果使用自己创建的企业自建应用，选择 `手动创建`

弹出的配置项填写：

- ID(id)：随意填写，用于区分不同的消息平台实例。
- 启用(enable): 勾选。
- app_id: 获取的 app_id
- app_secret: 获取的 app_secret

对于 domain，如果您使用国内版飞书，保持默认即可；如果您正在用国际版飞书，请设置为 `https://open.larksuite.com`；如果您使用企业自部署飞书，请填写您的飞书实例的域名。

对于订阅方式，`socket` 代表使用「长连接」订阅方式，`webhook` 代表「将事件发送至开发者服务器」的订阅方式，后者需要您拥有公网服务器。一般来说使用 `socket` 即可，国内版和国际版飞书均支持长连接；如果您使用企业自部署飞书且长连接不可用，请选择 `webhook`。相应地，接下来的配置也会有所不同。

如果您选择了 `webhook` 方式，选择了之后，前往飞书的开发者后台，点击事件与回调，点击加密策略，填写 Encrypt Key。这不是必须的，AstrBot 十分注重你的数据安全，所以请务必填写。填写后将 `Encrypt Key` 和 `Verification Token` 复制到 AstrBot 配置中对应的 `Encrypt Key`（`lark_encrypt_key`）和 `Verification Token`（`lark_verification_token`）字段。

点击 `保存`。

## 设置回调和权限

对于上面选择的订阅方式，接下来的步骤有所不同，请你根据实际选择的方式，跳转到对应的章节。

### `socket` 长连接方式

接下来，点击事件与回调，使用长连接接收事件，点击保存。**如果上一步没有成功启动，那么这里将无法保存。**

![设置事件与回调](https://files.astrbot.app/docs/source/images/lark/image-6.png)

### `webhook` 将事件发送至开发者服务器方式

> [!TIP]
> 为了更好地使用这种方式，请先参考 [统一 Webhook 模式](/use/unified-webhook.html) 做好相关配置。

点击 `保存` 后，在 `机器人` 页选中刚创建的机器人，点击 `查看 Webhook 链接`，复制回调 URL。

接下来，回到飞书的事件与回调页，点击「事件配置」，选择「将事件发送至开发者服务器」，将“请求地址”填写为刚刚复制的回调 URL，点击保存。如果一切无误将不会报错。

### 设置事件

上一步事件配置完成后，点击添加事件，消息与群组，下拉找到 `接收消息`，添加。

![添加事件](https://files.astrbot.app/docs/source/images/lark/image-7.png)

点击开通以下权限。

![开通权限](https://files.astrbot.app/docs/source/images/lark/image-8.png)

再点击上面的`保存`按钮。

接下来，点击权限管理，点击开通权限，输入 `im:message,im:message:send_as_bot`。添加筛选到的权限。

再次输入 `im:resource` 开通上传、下载图片和文件等资源的权限。

开通 `contact:contact.base:readonly` 和 `contact:user.base:readonly`，用于读取私聊发送者的显示名。

如果需要在群聊里使用，请额外开通 `im:message.group_at_msg:readonly` 和 `im:message.group_msg` 权限。

> [!TIP]
> 扫码一键创建的应用默认只能收到被 @ 的群聊消息。如果要接收群聊中的所有消息，请确认已经开通 `im:message.group_msg`。你也可以使用上文提供的权限开通链接快速进入对应页面。

如果需要使用流式输出，请额外开通 `创建与更新卡片(cardkit:card:write)` 权限。

最终开通的权限如下图：

![最终开通的权限](https://files.astrbot.app/docs/source/images/lark/image-11.png)

## 创建版本

创建版本。

![创建版本](https://files.astrbot.app/docs/source/images/lark/image-2.png)

填写版本号，更新说明，可见范围后点击保存，确认发布。

## 拉入机器人到群组

进入飞书 APP（网页版飞书无法添加机器人），点进群聊，点击右上角按钮->群机器人->添加机器人。

搜索刚刚创建的机器人的名字。比如教程创建了 `AstrBot` 机器人：

![添加机器人](https://files.astrbot.app/docs/source/images/lark/image-9.png)

## 🎉 大功告成

在群内 @ 机器人并发送一个 `/help` 指令，机器人将做出响应。

![成功](https://files.astrbot.app/docs/source/images/lark/image-13.png)
