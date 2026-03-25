# AstrBot 接入企业微信

AstrBot 支持接入企业微信应用和微信客服。

## 支持的基本消息类型

> 版本 v4.15.0。

| 消息类型 | 是否支持接收 | 是否支持发送 | 备注 |
| --- | --- | --- | --- |
| 文本 | 是 | 是 | |
| 图片 | 是 | 是 | |
| 语音 | 是 | 是 | |
| 视频 | 否 | 是 | |
| 文件 | 否 | 是 | |

主动消息推送：企业微信应用支持，未测试企业微信客服。

## 准备接入

步骤：

1. 进入 AstrBot 的管理面板
2. 点击左边栏 `机器人`
3. 然后在右边的界面中，点击 `+ 创建机器人`
4. 选择 `wecom`

这将弹出一个对话框。接下来，不要关闭页面，转移到下一步。

## 接入方式一：微信客服

> [!NOTE]
>
> 1. 需要 >= v3.5.7
> 2. 以这种方式接入，支持在微信内使用。

1. 进入 [微信客服后台](https://kf.weixin.qq.com/)，使用企业微信扫码登录。

2. **得到客服账号名。** 在 `客服账号` 中创建一个客服账号，记录下名称，填入 AstrBot 配置的 `微信客服账号名` 中（不是账号 ID）。

3. **得到企业 ID。** 在 [企业微信 - 企业信息](https://work.weixin.qq.com/wework_admin/frame#profile) 得到企业 ID（`Corpid`），复制到 AstrBot 配置的 `corpid` 处。

4. **回调服务器验证。** 如果您之前没有使用过微信客服机器人，那么请在 `开发配置` 中点击企业内部接入右侧的 `开始使用` 按钮，您应该会看到回调配置的页面。

![image](https://files.astrbot.app/docs/source/images/wecom/8287fd9fec5823847e6b590dc3f0f545.png)

如果您之前使用过微信客服机器人，那么在 `开发配置` 中直接找到 `回调配置`，点击修改。

点击下方的两个随机获取，得到 `Token` 和 `EncodingAESKey`，复制到 AstrBot 配置的 `token` 和 `encoding_aes_key` 处。请保持 `统一 Webhook 模式 (unified_webhook_mode)` 为开启状态。然后点击保存配置，等待适配器加载完成。

回调 URL 填写：

- 如果开启了 `统一 Webhook 模式`，点击保存之后，AstrBot 将会自动为你生成唯一的 Webhook 回调链接，你可以在日志中或者 WebUI 的机器人页的卡片上找到，将该链接填入回调 URL 处。

![unified_webhook](https://files.astrbot.app/docs/source/images/use/unified-webhook.png)

- 如果没有开启 `统一 Webhook 模式`，填写 `http://你的带公网地址的服务器ip:6195/callback/command`。

> 请注意放行端口。如果开启了统一 Webhook 模式，需要将请求转发到 AstrBot 所在服务器的 `6185` 端口；如果没有开启，则转发到配置指定的端口（默认 `6195`）。

回到微信客服 `回调配置`，点击 `完成`。如果一切无误，将会显示 `已完成`（否则会显示类似 `openapi 回调不通过` 类似的文本）。

1. **获取 Secret。** 之后，在 `开发配置` 中得到 Secret，找到复制到刚刚创建的企业微信适配器，点击编辑，然后修改配置中的 `secret`。然后再次保存配置，等待适配器加载完成。

> [!TIP]
> 根据 [#571](https://github.com/Soulter/AstrBot/issues/571) 的反馈，对于新注册的企业，`corp_id` 可能要注册一段时间后才生效（前后大概过了半个小时）。

然后，打开 `控制台` 页，你应该会看到如下日志：

```txt
请打开以下链接，在微信扫码以获取客服微信 ...
```

![image](https://files.astrbot.app/docs/source/images/wecom/image-13.png)

打开链接，用微信扫码，然后即可打开微信客服聊天页，输入 `help` 测试是否正常连通。

## 接入方式二：企业微信应用

进入 https://work.weixin.qq.com/wework_admin/frame#apps

点击 `我的企业`，查看并得到企业 ID（`Corpid`），复制到 AstrBot 配置的 `corpid` 处。

> [!TIP]
> 根据 [#571](https://github.com/Soulter/AstrBot/issues/571) 的反馈，对于新注册的企业，`corp_id` 可能要注册一段时间后才生效（前后大概过了半个小时）。

![image](https://files.astrbot.app/docs/source/images/wecom/image-5.png)

点击下面的 `自建应用`，然后点击 `创建应用`，填写好应用名称、头像、应用可见范围等信息。

进入应用，查看并得到机器人的 `Secret`，复制到 AstrBot 配置的 `secret` 处。

![image](https://files.astrbot.app/docs/source/images/wecom/image-4.png)

在下方，找到 `接收消息`，点击 `设置 API 接收`，进入 API 接收页面。

![image](https://files.astrbot.app/docs/source/images/wecom/image-6.png)

![image](https://files.astrbot.app/docs/source/images/wecom/image-9.png)

并且点击下方的两个随机获取，得到 `Token` 和 `EncodingAESKey`，复制到 AstrBot 配置的 `token` 和 `encoding_aes_key` 处。建议保持 `统一 Webhook 模式 (unified_webhook_mode)` 为开启状态。

现在应该已经填完 AstrBot 连接到企业微信的所有配置项。点击 AstrBot 配置页右下角保存，等待 AstrBot 重启。

在 URL 处填入回调地址：

- 如果开启了 `统一 Webhook 模式`，点击保存之后，AstrBot 将会自动为你生成唯一的 Webhook 回调链接，你可以在日志中或者 WebUI 的机器人页的卡片上找到，将该链接填入 URL 处。

![unified_webhook](https://files.astrbot.app/docs/source/images/use/unified-webhook.png)

- 如果没有开启 `统一 Webhook 模式`，填入 `http://你的带公网地址的服务器ip:6195/callback/command`。

> 请注意放行端口。如果开启了统一 Webhook 模式，需要将请求转发到 AstrBot 所在服务器的 `6185` 端口；如果没有开启，则转发到配置指定的端口（默认 `6195`）。

接下来配置企业可信 IP。

![image](https://files.astrbot.app/docs/source/images/wecom/image-10.png)

将你的 公网 IP 地址填写到此处，点击确定。


重启成功后，回到API 接收页面，点击下面的保存，看是否能\够保存成功。如果出现 `openapi 请求回调地址不通过` 说明配置有问题，请检查四个配置项是否填写正确。

如果能够保存成功，AstrBot 就已经能够接收信息。

## 测试

在企业微信-工作台中，找到刚刚创建的应用，发送 `/help`，看看 AstrBot 是否能够回复。

![image](https://files.astrbot.app/docs/source/images/wecom/3dc9fa61145ab0dd8f56a10295affec8_720.png)

## 反向代理(自定义 API BASE)

AstrBot 支持自定义企业微信的终结点以适应家庭 ip 没有固定的公网 IP 问题。

只需要将您的自定义地址填入 `api_base_url` 即可。

> 如果您没有公网 ip 当然也可以购买一台服务器，推荐 阿里云 的 99 元/年的服务器。

## 语音输入

为了语音输入，需要你的电脑上安装有 `ffmpeg`。

linux 用户可以使用 `apt install ffmpeg` 安装。

windows 用户可以在 [ffmpeg 官网](https://ffmpeg.org/download.html) 下载安装。

mac 用户可以使用 `brew install ffmpeg` 安装。
