# 接入 Matrix

> [!TIP]
> 该平台适配器由社区([stevessr](https://github.com/stevessr)) 维护。如果您觉得有帮助，请支持开发者，给该仓库点一个 Star。❤️

## 部署 Matrix 服务器

Matrix 是一个 IM 协议，有着丰富的服务端实现。

请在 [Matrix Server](https://matrix.org/ecosystem/servers/)查看可用的服务端。



## 支持的基本消息类型


| 消息类型     | 是否支持接收 | 是否支持发送 | 备注                                           |
| ------------ | ------------ | ------------ | ---------------------------------------------- |
| 文本         | 是           | 是           |                                                |
| 图片*        | 是           | 是           |                                                |
| 语音*        | 是           | 是           |                                                |
| 视频*        | 是           | 是           |                                                |
| 文件*        | 是           | 是           |                                                |
| 投票         | 是           | 否           |                                                |
*: 会持久化到本地，插件会按配置清理，在发送前会进行上传操作，超过服务器允许大小的上传将会失败

## 安装 astrbot_plugin_matrix_adapter 插件

进入 AstrBot WebUI 的插件市场，搜索 `astrbot_plugin_matrix_adapter`，点击安装。

安装完成后，前往 机器人（旧版本为 `消息平台`） → 新增适配器 → 选择 Matrix（若选项缺失，尝试重启 AstrBot 或检查插件安装状态）。

在弹出的配置对话框中点击 `启用`。

## 配置

- **`matrix_homeserver` (必填)`**: 你的 matrix 服务器实例的完整URL地址,支持域名委托自动探测。例如官方实例`https://matrix.org`
- **`matrix_user_id`**: 你的 matrix 完整用户名。如 `@username:homeserver.com`
- **`matrix_auth_method` (必填)** : 你的登陆方式，可选`password`,`token`,`oauth2`,`qr`推荐使用`password`或`oauth2/qr`模式 (oauth2/qr 模式下请确保用于认证/扫码的设备回调可以访问到 astrbot 配置的公开地址)

更多请参考该仓库的 [README.md](https://github.com/stevessr/astrbot_plugin_matrix_adapter?tab=readme-ov-file#astrbot-matrix-adapter-%E6%8F%92%E4%BB%B6) 进行配置。

## 问题提交

如有疑问，请提交 issue 至[插件仓库](https://github.com/stevessr/astrbot_plugin_matrix_adapter/issues)。
