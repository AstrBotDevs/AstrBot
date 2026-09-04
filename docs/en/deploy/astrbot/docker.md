# Deploy AstrBot with Docker

> [!WARNING]
> Docker provides a convenient way to deploy AstrBot on Windows, Mac, and Linux.
>
> This tutorial assumes you have Docker installed in your environment. If not, please refer to the [Docker official documentation](https://docs.docker.com/get-docker/) for installation.

## Deploy with Docker Compose

::: details Deploy AstrBot Only (General Method)

First, clone the AstrBot repository to your local machine:

```bash
git clone https://github.com/AstrBotDevs/AstrBot
cd AstrBot
```

Then, run Compose:

```bash
sudo docker compose up -d
```

> [!TIP]
> If your network environment is in mainland China, the above command will not pull properly. You may need to modify the compose.yml file and replace `image: soulter/astrbot:latest` with `image: m.daocloud.io/docker.io/soulter/astrbot:latest`.
:::

::: details Deploy with Agent Sandbox Environment

Supports native Python code execution, Shell code execution, and other features.

Deployment method:

```bash
git clone https://github.com/AstrBotDevs/AstrBot
cd AstrBot
# Run Shipyard Bay on a dedicated host, then provide its HTTPS endpoint and token.
export SHIPYARD_ENDPOINT=https://shipyard.example.com
export SHIPYARD_ACCESS_TOKEN='<high-entropy-token>'
docker compose -f compose-with-shipyard.yml up -d
```

For configuration and usage details, see the [Agent Sandbox Environment](/en/use/astrbot-agent-sandbox.md) documentation.
:::


## Deploy with Docker

```bash
mkdir astrbot
cd astrbot
sudo docker run -itd -p 127.0.0.1:6185:6185 -e ASTRBOT_DASHBOARD_HOST=0.0.0.0 -e ASTRBOT_DASHBOARD_ACCESS_MODE=container_loopback -v $PWD/data:/AstrBot/data -v /etc/localtime:/etc/localtime:ro -v /etc/timezone:/etc/timezone:ro --name astrbot soulter/astrbot:latest
```

> [!TIP]
> If your network environment is in mainland China, the above command will not pull properly. Please use the following command to pull the image:
>
> ```bash
> sudo docker run -itd -p 127.0.0.1:6185:6185 -e ASTRBOT_DASHBOARD_HOST=0.0.0.0 -e ASTRBOT_DASHBOARD_ACCESS_MODE=container_loopback -v $PWD/data:/AstrBot/data -v /etc/localtime:/etc/localtime:ro -v /etc/timezone:/etc/timezone:ro --name astrbot m.daocloud.io/docker.io/soulter/astrbot:latest
> ```
>
> (Thanks to DaoCloud ❤️)

> No need to add sudo on Windows, same below
> Sync Host Time on Windows (requires WSL2)

```
-v \\wsl.localhost\(your-wsl-os)\etc\timezone:/etc/timezone:ro
-v \\wsl.localhost\(your-wsl-os)\etc\localtime:/etc/localtime:ro
```

View AstrBot logs with the following command:

```bash
sudo docker logs -f astrbot
```


## Deploy via Docker Desktop on Windows

### For Windows CMD

Set `TZ` to the standard IANA time zone format (Region/City). Use `Asia/Shanghai` for China.

```bash
docker run -itd -p 127.0.0.1:6185:6185 -e ASTRBOT_DASHBOARD_HOST=0.0.0.0 -e ASTRBOT_DASHBOARD_ACCESS_MODE=container_loopback -e TZ=Asia/Shanghai -v "%cd%\data:/AstrBot/data" --name astrbot soulter/astrbot:latest
```
> [!TIP]
> If your network environment is in mainland China, the above command will not pull properly. Please use the following command to pull the image:
>
> ```bash
> docker run -itd -p 127.0.0.1:6185:6185 -e ASTRBOT_DASHBOARD_HOST=0.0.0.0 -e ASTRBOT_DASHBOARD_ACCESS_MODE=container_loopback -e TZ=Asia/Shanghai -v "%cd%\data:/AstrBot/data" --name astrbot m.daocloud.io/docker.io/soulter/astrbot:latest
> ```
>
> (Thanks to DaoCloud ❤️)

### For PowerShell

Set `TZ` to the standard IANA time zone format (Region/City). Use `Asia/Shanghai` for China.

```powershell
docker run -itd -p 127.0.0.1:6185:6185 -e ASTRBOT_DASHBOARD_HOST=0.0.0.0 -e ASTRBOT_DASHBOARD_ACCESS_MODE=container_loopback -e TZ=Asia/Shanghai -v "${PWD}\data:/AstrBot/data" --name astrbot soulter/astrbot:latest
```
> [!TIP]
> If your network environment is in mainland China, the above command will not pull properly. Please use the following command to pull the image:
>
> ```powershell
> docker run -itd -p 127.0.0.1:6185:6185 -e ASTRBOT_DASHBOARD_HOST=0.0.0.0 -e ASTRBOT_DASHBOARD_ACCESS_MODE=container_loopback -e TZ=Asia/Shanghai -v "${PWD}\data:/AstrBot/data" --name astrbot m.daocloud.io/docker.io/soulter/astrbot:latest
> ```
>
> (Thanks to DaoCloud ❤️)

## 🎉 All Done

If everything goes well, you will see logs printed by AstrBot.

If there are no errors, you will see a log message similar to `🌈 Dashboard started, accessible at` with several links. Open one of the links to access the AstrBot dashboard.

> [!TIP]
> The default mapping is intentionally limited to `http://localhost:6185`. Use a TLS reverse proxy or the built-in HTTPS configuration for remote access.
>
> New users must use the random password printed in the startup logs to log in for the first time. Use the username shown in the logs (usually `astrbot`) and change the password after first login.
>
> Do not expose ports 6185 or 6199 directly to the Internet. OneBot requires a non-empty token and should use a private network.

Next, you need to deploy any messaging platform to use AstrBot on that platform.
