# 使用 Docker 部署 AstrBot

> [!WARNING]
> 通过 Docker 可以方便地将 AstrBot 部署到 Windows, Mac, Linux 上。
>
> 以下教程默认您的环境已安装 Docker。如果没有安装，请参考 [Docker 官方文档](https://docs.docker.com/get-docker/) 进行安装。

## 通过 Docker Compose 部署

::: details 只部署 AstrBot（通用方式）

首先，需要 Clone AstrBot 仓库到本地：

```bash
git clone https://github.com/AstrBotDevs/AstrBot
cd AstrBot
```

然后，运行 Compose：

```bash
sudo docker compose up -d
```

> [!TIP]
> 如果您的网络环境在中国大陆境内，上述命令将无法正常拉取。您可能需要修改 compose.yml 文件，将其中的 `image: soulter/astrbot:latest` 替换为 `image: m.daocloud.io/docker.io/soulter/astrbot:latest`。
:::

::: details 带 Agent 沙盒环境的部署

支持原生的 Python 代码执行、Shell 代码执行等功能。

部署方式如下：

```bash
git clone https://github.com/AstrBotDevs/AstrBot
cd AstrBot
# 修改 compose-with-shipyard.yml 文件中的环境变量配置，例如 Shipyard 的 access token 等
docker compose -f compose-with-shipyard.yml up -d
docker pull soulter/shipyard-ship:latest
```

配置和使用详见 [Agent 沙盒环境](/use/astrbot-agent-sandbox.md) 文档。
:::

::: details 和 NapCat 一起部署

如果您想对接 NapCat，使用这种方式可以同时部署 AstrBot 和 NapCat。

```bash
mkdir astrbot
cd astrbot
wget https://raw.githubusercontent.com/NapNeko/NapCat-Docker/main/compose/astrbot.yml
sudo docker compose -f astrbot.yml up -d
```

:::


## 通过 Docker 部署

```bash
mkdir astrbot
cd astrbot
sudo docker run -itd -p 6185:6185 -p 6199:6199 -v $PWD/data:/AstrBot/data -v /etc/localtime:/etc/localtime:ro -v /etc/timezone:/etc/timezone:ro --name astrbot soulter/astrbot:latest
```

> [!TIP]
> 如果您的网络环境在中国大陆境内，上述命令将无法正常拉取。请使用以下命令拉取镜像：
>
> ```bash
> sudo docker run -itd -p 6185:6185 -p 6199:6199 -v $PWD/data:/AstrBot/data -v /etc/localtime:/etc/localtime:ro -v /etc/timezone:/etc/timezone:ro --name astrbot m.daocloud.io/docker.io/soulter/astrbot:latest
> ```
>
> (感谢 DaoCloud ❤️)
>
> Windows 下不需要加 sudo，下同
>
Windows 同步 Host Time（需要WSL2）

```
-v \\wsl.localhost\(your-wsl-os)\etc\timezone:/etc/timezone:ro
-v \\wsl.localhost\(your-wsl-os)\etc\localtime:/etc/localtime:ro
```

通过以下命令查看 AstrBot 的日志：

```bash
sudo docker logs -f astrbot
```

## 🎉 大功告成

如果一切顺利，你会看到 AstrBot 打印出的日志。

如果没有报错，你会看到一条日志显示类似 `🌈 管理面板已启动，可访问` 并附带了几条链接。打开其中一个链接即可访问 AstrBot 管理面板。

> [!TIP]
> 由于 Docker 隔离了网络环境，所以不能使用 `localhost` 访问管理面板。
>
> 默认用户名和密码是 `astrbot` 和 `astrbot`。
>
> 如果部署在云服务器上，需要在相应厂商控制台里放行对应端口。

接下来，你需要部署任何一个消息平台，才能够实现在消息平台上使用 AstrBot。
