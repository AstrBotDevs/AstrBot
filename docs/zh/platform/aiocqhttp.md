# 接入 OneBot v11 协议实现

OneBot 是一个**聊天机器人应用接口标准**，旨在统一不同聊天平台上的机器人应用开发接口。

AstrBot 支持接入所有适配了 OneBotv11 反向 Websockets（AstrBot 做服务器端）的机器人协议端。

下文给出一些常见的 OneBot v11 协议实现端项目。

- [NapCat](https://github.com/NapNeko/NapCatQQ) (连接到 QQ)
- [OneDisc](https://github.com/ITCraftDevelopmentTeam/OneDisc) (连接到 Discord)
- [Tele-KiraLink](https://github.com/Echomirix/Tele-KiraLink) (连接到 Telegram)

请参阅对应的协议实现端项目的部署文档。

对于 Napcat 项目，请参考下文的 `附录：部署 Napcat`

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

## 附录：部署 Napcat

### 通过一键启动脚本部署

推荐采用这种方式部署。

#### Windows

看这篇文章：[NapCat.Shell - Win手动启动教程](https://napneko.github.io/guide/boot/Shell#napcat-shell-win%E6%89%8B%E5%8A%A8%E5%90%AF%E5%8A%A8%E6%95%99%E7%A8%8B)

#### Linux

看这篇文章：[NapCat.Installer - Linux一键使用脚本(支持Ubuntu 20+/Debian 10+/Centos9)](https://napneko.github.io/guide/boot/Shell#napcat-installer-linux%E4%B8%80%E9%94%AE%E4%BD%BF%E7%94%A8%E8%84%9A%E6%9C%AC-%E6%94%AF%E6%8C%81ubuntu-20-debian-10-centos9)

> [!TIP]
> **Napcat WebUI 在哪打开**：
> 在 napcat 的日志里会显示 WebUI 链接。
>
> 如果是 linux 命令行一键部署的napcat：`docker log <账号>`。
>
> Docker部署的 NapCat：`docker logs napcat`。

## 通过 Docker Compose 部署

1. 下载或复制 [astrbot.yml](https://github.com/NapNeko/NapCat-Docker/blob/main/compose/astrbot.yml) 内容
2. 将刚刚下载的文件重命名为 `astrbot.yml`
3. 编辑 `astrbot.yml`，将 `# - "6199:6199"` 修改为 `- "6199:6199"`，移除开头的 `#`
4. 在 `astrbot.yml` 文件所在目录执行:

```bash
NAPCAT_UID=$(id -u) NAPCAT_GID=$(id -g) docker compose -f ./astrbot.yml up -d
```

部署完毕之后，可以去 Napcat 的 WebUI（默认端口 6099）中新增 OneBot 连接实例：点击`网络配置->新建->WebSockets客户端`，在新弹出的窗口中：勾选`启用`，
URL 填写 `ws://宿主机IP:端口/ws`。如 `ws://127.0.0.1:6199/ws`。如果采用上面的 Docker Compose 部署，可以填写 `ws://astrbot:6199/ws`（参考本文档的 Docker 脚本）。心跳间隔和重连间隔可以改为 `1000`(1 秒)。点击保存，然后去 AstrBot WebUI 的控制台中检查是否连接成功，出现 `aiocqhttp(OneBot v11) 适配器已连接` 日志即代表成功。

如果您对部署、网络配置不了解，请千万不要在公网暴露 Napcat 的端口。