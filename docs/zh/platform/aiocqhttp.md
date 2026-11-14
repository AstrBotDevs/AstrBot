# 接入 OneBot v11 协议实现

> [!TIP]
> 如果您打算将 AstrBot 接入 QQ，推荐使用 [QQ 官方机器人（WebSockets）](/platform/qqofficial/websockets)，由 QQ 官方推出，更稳定，支持一键扫码登录。

OneBot 是一个**聊天机器人应用接口标准**，旨在统一不同聊天平台上的机器人应用开发接口。

AstrBot 支持接入所有适配了 OneBotv11 反向 Websockets（AstrBot 做服务器端）的机器人协议端。

下文给出一些常见的 OneBot v11 协议实现端项目。

- [OneDisc](https://github.com/ITCraftDevelopmentTeam/OneDisc) (连接到 Discord)
- [Tele-KiraLink](https://github.com/Echomirix/Tele-KiraLink) (连接到 Telegram)

请参阅对应的协议实现端项目的部署文档。

> [!WARNING]
> NapCat 已停止维护，官方仓库不再提供程序与部署文档，原有一键脚本、Docker 镜像与 Kubernetes 清单均已失效。如仍需在 QQ 个人号上使用 OneBot v11，请自行评估其他 OneBot v11 实现端的可用性与安全性；AstrBot 不对第三方实现端的可用性作保证。

## 1. 配置 OneBot v11

1. 进入 AstrBot 的 WebUI
2. 点击左边栏 `机器人`
3. 点击机器人列表上方的 `创建机器人`
4. 选择 `OneBot v11`

在出现的表单中，填写：

- ID(id)：随意填写，仅用于区分不同的消息平台实例。
- 启用(enable): 勾选。
- 反向 WebSocket 主机地址：请填写你的机器的 IP 地址，一般情况下请直接填写 `0.0.0.0`
- 反向 WebSocket 端口：填写一个端口，默认为 `6199`。
- 反向 Websocket Token：只有当协议实现端的网络配置中启用了 token 时才需填写。

点击 `保存`。

## 2. 配置协议实现端

请参阅对应的协议实现端项目的部署文档。

一些注意点：

1. 协议实现端需要支持 `反向 WebSocket` 实现，及 AstrBot 端作为服务端，实现端作为客户端。
2. `反向 WebSocket` 的 URL 为 `ws(s)://<your-host>:6199/ws`。

## 3. 验证

前往 AstrBot WebUI 的 `数据与日志` -> `日志`，如果出现 ` aiocqhttp(OneBot v11) 适配器已连接。` 蓝色的日志，说明连接成功。如果没有，若干秒后出现` aiocqhttp 适配器已被关闭` 则为连接超时（失败），请检查配置是否正确。
