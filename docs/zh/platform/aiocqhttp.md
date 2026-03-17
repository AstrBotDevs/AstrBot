# 接入 OneBot v11 协议实现

OneBot 是一个聊天机器人应用接口标准，旨在统一不同聊天平台上的机器人应用开发接口，使开发者只需编写一次业务逻辑代码即可应用到多种机器人平台。

AstrBot 支持接入所有适配了 OneBotv11 反向 Websockets（AstrBot 做服务器端）的机器人协议端。

下文给出一些常见的 OneBot v11 协议实现端项目。

- [NapCat](https://github.com/NapNeko/NapCatQQ)
- [OneDisc](https://github.com/ITCraftDevelopmentTeam/OneDisc)
- [Tele-KiraLink](https://github.com/Echomirix/Tele-KiraLink)

请参阅对应的协议实现端项目的部署文档。

## 1. 配置 OneBot v11

1. 进入 AstrBot 的 WebUI
2. 点击左边栏 `机器人`
3. 然后在右边的界面中，点击 `+ 创建机器人`
4. 选择 `OneBot v11`

在出现的表单中，填写：

- ID(id)：随意填写，仅用于区分不同的消息平台实例。
- 启用(enable): 勾选。
- 反向 WebSocket 主机地址：请填写你的机器的 IP 地址，一般情况下请直接填写 `0.0.0.0`
- 反向 WebSocket 端口：填写一个端口，默认为 `6199`。
- 反向 Websocket Token：只有当 NapCat 网络配置中配置了 token 才需填写。

点击 `保存`。

## 2. 配置协议实现端

请参阅对应的协议实现端项目的部署文档。

一些注意点：

1. 协议实现端需要支持 `反向 WebSocket` 实现，及 AstrBot 端作为服务端，实现端作为客户端。
2. `反向 WebSocket` 的 URL 为 `ws(s)://<your-host>:6199/ws`。

## 3. 验证

前往 AstrBot WebUI `控制台`，如果出现 ` aiocqhttp(OneBot v11) 适配器已连接。` 蓝色的日志，说明连接成功。如果没有，若干秒后出现` aiocqhttp 适配器已被关闭` 则为连接超时（失败），请检查配置是否正确。