# 接入 LINE

## 支持的基本消息类型

> 版本 v4.17.0。

| 消息类型 | 是否支持接收 | 是否支持发送 | 备注 |
| --- | --- | --- | --- |
| 文本 | 是 | 是 | |
| 图片 | 是 | 是 | |
| 语音 | 是 | 是 | |
| 视频 | 是 | 是 | |
| 文件 | 是 | 是 | |
| 贴纸 | 是 | 否 | |

主动消息推送：支持。

## 创建 LINE Messaging API Channel

1. 打开 [LINE Developers Console](https://developers.line.biz/console/)
2. 创建或选择一个 Provider
3. 创建一个 `Messaging API` Channel （不是 `LINE Login` Channel）
4. 在 `Messaging API` 页面中，完成机器人初始化

## 获取凭据

你需要以下配置项：

- `channel_secret`
- `channel_access_token`

获取方式：

1. 进入对应 Channel 的设置页面
2. 在 `Basic settings` 获取 `Channel secret`
3. 在 `Messaging API` 页面签发 `Channel access token`

![](https://files.astrbot.app/docs/source/images/line/7ecee0a9102f191245330f8408eb0493.png)

## 配置 AstrBot

1. 进入 AstrBot 管理面板
2. 点击左侧 `机器人`
3. 点击 `+ 创建机器人`
4. 选择 `line`

填写配置：

- `ID(id)`：自定义，区分多个平台实例
- `启用(enable)`：勾选
- `LINE Channel Access Token`：填入 `channel_access_token`
- `LINE Channel Secret`：填入 `channel_secret`

点击保存。

## 配置回调地址（统一 Webhook）

LINE 适配器仅支持 AstrBot 统一 Webhook 模式。

保存后，在机器人卡片里点击「查看 Webhook 链接」，复制 URL。

然后到 LINE Developers Console：

1. 打开 `Messaging API` 页面
2. 在 `Webhook settings` 中粘贴 `Webhook URL`
3. 点击 `Verify`
4. 打开 `Use webhook`

> [!TIP]
> 如果你的 AstrBot 不在公网，请先配置好可公网访问的域名与反向代理，确保 LINE 可以访问该 Webhook URL。

## 测试

1. 用 LINE 添加该官方账号为好友（通过二维码即可添加）
2. 给机器人发送一条消息（例如 `hi`）
3. 若能收到回复，即接入成功

如果要在群内使用，请先将该官方账号拉入群组后再测试。
