# 接入飞书

## 支持的基本消息类型

> 版本 v4.15.0。

| 消息类型 | 是否支持接收 | 是否支持发送 | 备注 |
| --- | --- | --- | --- |
| 文本 | 是 | 是 | |
| 图片 | 是 | 是 | |
| 语音 | 否 | 是 | |
| 视频 | 否 | 是 | |
| 文件 | 否 | 是 | |

主动消息推送：支持。

流式输出：支持。需要在飞书开发者后台为应用开通 `创建与更新卡片(cardkit:card:write)` 权限。

飞书客户端版本需 >= 7.20。低版本客户端将只显示标题和升级提示。

## 创建机器人

前往 [开发者后台](https://open.feishu.cn/app) ，创建企业自建应用。

![创建企业自建应用](https://files.astrbot.app/docs/source/images/lark/image.png)

添加应用能力——机器人。

![添加应用能力](https://files.astrbot.app/docs/source/images/lark/image-1.png)

点击凭证与基础信息，获取 app_id 和 app_secret。

![获取 app_id 和 app_secret](https://files.astrbot.app/docs/source/images/lark/image-4.png)

## 配置 AstrBot

1. 进入 AstrBot 的管理面板
2. 点击左边栏 `机器人`
3. 然后在右边的界面中，点击 `+ 创建机器人` 
4. 选择 `lark(飞书)`

弹出的配置项填写：

- ID(id)：随意填写，用于区分不同的消息平台实例。
- 启用(enable): 勾选。
- app_id: 获取的 app_id
- app_secret: 获取的 app_secret
- 飞书机器人的名字

对于 domain，如果您使用国内版飞书，保持默认即可；如果您正在用国际版飞书，请设置为 `https://open.larksuite.com`；如果您使用企业自部署飞书，请填写您的飞书实例的域名。

对于订阅方式，`socket` 代表使用「长连接」订阅方式，`webhook` 代表「将事件发送至开发者服务器」的订阅方式，后者需要您拥有公网服务器。一般来说使用 `socket` 即可，如果您使用国际版飞书或者企业自部署飞书，请选择 `webhook`。相应地，接下来的配置也会有所不同。

如果您选择了 `webhook` 方式，选择了之后，前往飞书的开发者后台，点击事件与回调，点击加密策略，填写 Encrypt Key。这不是必须的，AstrBot 十分注重你的数据安全，所以请务必填写。填写后复制 `Encrypt Key` 和 `Verification Token` 到 AstrBot 配置的 `encrypt_key` 和 `verification_token` 处。

点击 `保存`。

## 设置回调和权限

对于上面选择的订阅方式，接下来的步骤有所不同，请你根据实际选择的方式，跳转到对应的章节。

### `socket` 长连接方式

接下来，点击事件与回调，使用长连接接收事件，点击保存。**如果上一步没有成功启动，那么这里将无法保存。**

![设置事件与回调](https://files.astrbot.app/docs/source/images/lark/image-6.png)

### `webhook` 将事件发送至开发者服务器方式

> [!TIP]
> 为了更好地使用这种方式，请先参考 [统一 Webhook 模式](/use/unified-webhook.html) 做好相关配置。

在点击 `保存` 后，机器人卡片会显示「查看 Webhook 链接」，点击查看，复制回调 URL。

![](https://files.astrbot.app/docs/source/images/lark/webhook.png)

接下来，回到飞书的事件与回调页，点击「事件配置」，选择「将事件发送至开发者服务器」，将“请求地址”填写为刚刚复制的回调 URL，点击保存。如果一切无误将不会报错。

### 设置事件

上一步事件配置完成后，点击添加事件，消息与群组，下拉找到 `接收消息`，添加。

![添加事件](https://files.astrbot.app/docs/source/images/lark/image-7.png)

点击开通以下权限。

![开通权限](https://files.astrbot.app/docs/source/images/lark/image-8.png)

再点击上面的`保存`按钮。

接下来，点击权限管理，点击开通权限，输入 `im:message,im:message:send_as_bot`。添加筛选到的权限。

再次输入 `im:resource:upload,im:resource` 开通上传图片相关的权限。

如果需要在群聊里使用，请额外开通 `im:message.group_at_msg:readonly` 和 `im:message.group_msg` 权限。

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

在群内发送一个 `/help` 指令，机器人将做出响应。

![成功](https://files.astrbot.app/docs/source/images/lark/image-13.png)
