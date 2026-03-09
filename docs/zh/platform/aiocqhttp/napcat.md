# 使用 NapCat

> [!TIP]
>
> - 本项目严禁用于任何违反法律法规的用途。若您意图将 AstrBot 应用于非法产业或活动，我们**明确反对并拒绝**您使用本项目。
> - AstrBot 通过 `aiocqhttp` 适配器接入 OneBot v11 协议。OneBot v11 协议是一个开放的通信协议，并不代表任何具体的软件或服务。

NapCat 的 GitHub 仓库：[NapCat](https://github.com/NapNeko/NapCatQQ)
NapCat 的文档：[NapCat 文档](https://napcat.napneko.icu/)

NapCat 提供了大量的部署方式，包括 Docker、Windows 一键安装包等等。

## 通过一键脚本部署

推荐采用这种方式部署。

### Windows

看这篇文章：[NapCat.Shell - Win手动启动教程](https://napneko.github.io/guide/boot/Shell#napcat-shell-win%E6%89%8B%E5%8A%A8%E5%90%AF%E5%8A%A8%E6%95%99%E7%A8%8B)

### Linux

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

## 通过 Docker 部署

此教程默认您安装了 Docker。

在终端执行以下命令即可一键部署。

```bash
docker run -d \
-e NAPCAT_GID=$(id -g) \
-e NAPCAT_UID=$(id -u) \
-p 3000:3000 \
-p 3001:3001 \
-p 6099:6099 \
--name napcat \
--restart=always \
mlikiowa/napcat-docker:latest
```

执行成功后，需要查看日志以得到登录二维码和管理面板的 URL。

```bash
docker logs napcat
```

请复制管理面板的 URL，然后在浏览器中打开备用。

然后使用你要登录的账号扫描出现的二维码，即可登录。

如果登录阶段没有出现问题，即成功部署。

## 连接到 AstrBot

## 在 AstrBot 配置 aiocqhttp

1. 进入 AstrBot 的管理面板
2. 点击左边栏 `机器人`
3. 然后在右边的界面中，点击 `+ 创建机器人`
4. 选择 `OneBot v11`

弹出的配置项填写：
- ID(id)：随意填写，仅用于区分不同的消息平台实例。
- 启用(enable): 勾选。
- 反向 WebSocket 主机地址：请填写你的机器的 IP 地址，一般情况下请直接填写 `0.0.0.0`
- 反向 WebSocket 端口：填写一个端口，默认为 `6199`。
- 反向 Websocket Token：只有当 NapCat 网络配置中配置了 token 才需填写。

图例：（最快只需要点击启用，然后保存即可）

<img width="818" height="799" alt="xinjianya" src="https://github.com/user-attachments/assets/813ac338-2fd7-4add-bde4-8b0f6d0bda95" />


点击 `保存`。

### 配置管理员

填写完毕后，进入 `配置文件` 页，点击 `平台配置` 选项卡，找到 `管理员 ID`，填写你的账号号（不是机器人的账号）。

切记点击右下角 `保存`，AstrBot 重启并会应用配置。

### 在 NapCat 中添加 WebSocket 客户端

切换回 NapCat 的管理面板，点击 `网络配置->新建->WebSockets客户端`。

<img width="649" height="751" alt="jiaochenXJY" src="https://github.com/user-attachments/assets/5044f96a-a81f-407a-a3b1-0c518499eda4" />


在新弹出的窗口中：

- 勾选 `启用`。
- `URL` 填写 `ws://宿主机IP:端口/ws`。如 `ws://localhost:6199/ws` 或 `ws://127.0.0.1:6199/ws`。

> [!IMPORTANT]
> 1. 如果采用 Docker 部署并同时把 AstrBot 和 NapCat 两个容器接入了同一网络，`ws://astrbot:6199/ws`（参考本文档的 Docker 脚本）。
> 2. 由于 Docker 网络隔离的原因，不在同一个网络时请使用内网 IP 地址或公网 IP 地址 ***（不安全）*** 进行连接，即 `ws://(内网/公网):6199/ws`。

- 消息格式：`Array`
- 心跳间隔: `5000`
- 重连间隔: `5000`

> [!WARNING]
>
> 1. 切记后面加一个 `/ws`!
> 2. 这里的 IP 不能填为 `0.0.0.0`

点击 `保存`。

前往 AstrBot WebUI `控制台`，如果出现 ` aiocqhttp(OneBot v11) 适配器已连接。` 蓝色的日志，说明连接成功。如果没有，若干秒后出现` aiocqhttp 适配器已被关闭` 则为连接超时（失败），请检查配置是否正确。

## 🎉 大功告成

此时，你的 AstrBot 和 NapCat 应该已经连接成功！使用 `私聊` 的方式对机器人发送 `/help` 以检查是否连接成功。
