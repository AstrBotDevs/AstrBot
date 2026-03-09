# AstrBot 接入微信公众平台

AstrBot 支持接入微信公众平台（版本 >= v3.5.8），并以微信公众号的形式接入，届时，您可以直接在微信公众号聊天界面中与 AstrBot 进行交互。

## 准备接入

步骤：

1. 进入 AstrBot 的管理面板
2. 点击左边栏 `机器人`
3. 然后在右边的界面中，点击 `+ 创建机器人`
4. 选择 `weixin_official_account(微信公众平台)`

这将弹出一个对话框。接下来，不要关闭页面，转移到下一步。

## 创建/登入微信公众平台

进入[微信公众平台](https://mp.weixin.qq.com/)，如果您需要接入现有的公众号请直接登录即可，如果没有，请点击立即注册然后选择 `公众号` 并填写相关信息注册。

> [!NOTE]
> 新注册的公众号需要花费 1-2 天审核，期间不能使用。

## 设置回调服务

点击 `设置与开发` -> `开发接口管理`。界面如下：

![开发接口管理](https://files.astrbot.app/docs/source/images/weixin-official-account/image.png)

记录开发者 ID(AppID) 和开发者密码(AppSecret)，分别填入 AstrBot 配置的 `appid` 和 `secret` 处。

找到 IP白名单，点击查看，然后添加你的公网 IP 地址。如果有多个公网 IP 地址，换行分隔。

找到下方的服务器配置，然后点击修改配置。


`Token` 由自己填写，请随意填写一个字符串，长度 3-32 位。并同样填入 AstrBot 配置的 `token` 处（一定要相同）。

`EncodingAESKey` 请点击随机生成，然后复制到 AstrBot 配置的 `encoding_aes_key` 处。

建议保持 `统一 Webhook 模式 (unified_webhook_mode)` 为开启状态。

现在应该已经填完 AstrBot 连接到微信公众平台的所有配置项。点击 AstrBot 配置页右下角保存，等待 AstrBot 重启。

`URL` 填写：

- 如果开启了 `统一 Webhook 模式`，点击保存之后，AstrBot 将会自动为你生成唯一的 Webhook 回调链接，你可以在日志中或者 WebUI 的机器人页的卡片上找到，将该链接填入 URL 处。

![unified_webhook](https://files.astrbot.app/docs/source/images/use/unified-webhook.png)

- 如果没有开启 `统一 Webhook 模式`，请填入 `http://你的域名/callback/command`。

> 注意⚠️：仅支持 80 或者 443 端口。您可能需要购买域名，然后反向代理流量到 AstrBot 所在服务器的 `6185` 端口（如果开启了统一 Webhook 模式）或 `6194` 端口（如果没有开启统一 Webhook 模式），或者将端口改成 80 端口（注意服务器需要没有软件在占用 80 端口）。

消息加解密方式请选中 `安全模式`。

等待片刻，点击 `提交`。如果一切无误，会显示 `提交成功`。

## 测试

点击左下角你的账号头像，点击账号详情，找到 `二维码`，扫码进入到公众号聊天界面，发送 `help`，看看 AstrBot 是否能够回复。

如果可以回复，说明接入成功。

> [!NOTE]
> 如果没有回复，并且控制台报错 `ip xxxxx not in whitelist`，说明你没有添加公网 IP 地址到微信公众平台的 IP 白名单中。如果确认添加了，那请等待若干分钟以让微信服务器更新。

## 反向代理(自定义 API BASE)

AstrBot 支持自定义企业微信的终结点以适应家庭 ip 没有固定的公网 IP 问题。

只需要将您的自定义地址填入 `api_base_url` 即可。

> 如果您没有公网 ip 当然也可以购买一台服务器，推荐 阿里云 的 99 元/年的服务器。

## 语音输入

为了语音输入，需要你的电脑上安装有 `ffmpeg`。

linux 用户可以使用 `apt install ffmpeg` 安装。

windows 用户可以在 [ffmpeg 官网](https://ffmpeg.org/download.html) 下载安装。

mac 用户可以使用 `brew install ffmpeg` 安装。