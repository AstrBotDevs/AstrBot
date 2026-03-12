# Using NapCat

> [!TIP]
>
> - Please control usage frequency appropriately. Sending messages too frequently may be identified as abnormal behavior, increasing the risk of triggering risk control mechanisms.
> - This project is strictly prohibited from being used for any purpose that violates laws and regulations. If you intend to use AstrBot for illegal industries or activities, we **explicitly oppose and refuse** your use of this project.
> - AstrBot connects to the OneBot v11 protocol through the `aiocqhttp` adapter. OneBot v11 protocol is an open communication protocol and does not represent any specific software or service.

NapCat's GitHub Repository: [NapCat](https://github.com/NapNeko/NapCatQQ)
NapCat's Documentation: [NapCat Documentation](https://napcat.napneko.icu/)

NapCat provides multiple deployment methods, including Docker, Windows one-click installation packages, and more.

## Deploy via One-Click Script

This deployment method is recommended.

### Windows

Refer to this article: [NapCat.Shell - Windows Manual Start Tutorial](https://napneko.github.io/guide/boot/Shell#napcat-shell-win%E6%89%8B%E5%8A%A8%E5%90%AF%E5%8A%A8%E6%95%99%E7%A8%8B)

### Linux

Refer to this article: [NapCat.Installer - Linux One-Click Script (Supports Ubuntu 20+/Debian 10+/Centos9)](https://napneko.github.io/guide/boot/Shell#napcat-installer-linux%E4%B8%80%E9%94%AE%E4%BD%BF%E7%94%A8%E8%84%9A%E6%9C%AC-%E6%94%AF%E6%8C%81ubuntu-20-debian-10-centos9)

> [!TIP]
> **Where to open Napcat WebUI**:
> The WebUI link will be displayed in napcat's logs.
>
> If napcat is deployed via Linux command line one-click deployment: `docker log <account>`.
>
> For Docker-deployed NapCat: `docker logs napcat`.

## Deploy via Docker Compose

> [!TIP]
> If deploying with Docker Compose, no configuration is needed on the NapCat side. Just log in via NapCat WebUI (running on port 6099) or `docker logs napcat`, enable the aiocqhttp adapter on the AstrBot side to connect, and you can directly implement normal receiving and sending of `voice data` and `file data`.

1. Download or copy the content of [astrbot.yml](https://github.com/NapNeko/NapCat-Docker/blob/main/compose/astrbot.yml)
2. Rename the downloaded file to `astrbot.yml`
3. Modify `astrbot.yml`, change `#- "6199:6199` to `- "6199:6199"`, remove the flag of "#"
4. Execute in the directory where the `astrbot.yml` file is located:

```bash
NAPCAT_UID=$(id -u) NAPCAT_GID=$(id -g) docker compose -f ./astrbot.yml up -d
```

## Deploy via Docker

> [!TIP]
> If deploying with Docker, you will not be able to properly receive `voice data` and `file data`. This means voice-to-text and sandbox file input functions will not be available. You can receive text messages, image messages, and other types of messages.

This tutorial assumes you have Docker installed.

Execute the following command in the terminal for one-click deployment.

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

After successful execution, you need to check the logs to get the login QR code and the management panel URL.

```bash
docker logs napcat
```

Please copy the management panel URL and open it in your browser.

Then use the account you want to log in with to scan the QR code that appears.

If there are no issues during the login stage, deployment is successful.

## Connect to AstrBot

## Configure aiocqhttp in AstrBot

1. Enter AstrBot's management panel
2. Click `Bots` in the left sidebar
3. Then in the interface on the right, click `+ Create Bot`
4. Select `OneBot v11`

Fill in the configuration items that appear:
- ID(id): Fill in arbitrarily, only used to distinguish different messaging platform instances.
- Enable: Check this.
- Reverse WebSocket Host Address: Please fill in your machine's IP address, generally fill in `0.0.0.0` directly
- Reverse WebSocket Port: Fill in a port, default is `6199`.
- Reverse Websocket Token: Only needs to be filled when a token is configured in NapCat's network settings.

Example image: (At the fastest, just check Enable, then save)

<img width="818" height="799" alt="xinjianya" src="https://github.com/user-attachments/assets/813ac338-2fd7-4add-bde4-8b0f6d0bda95" />


Click `Save`.

### Configure Administrator

After filling in, go to the `Configuration File` page, click the `Platform Configuration` tab, find `Administrator ID`, and fill in your account number (not the bot's account number).

Remember to click `Save` in the lower right corner, AstrBot will restart and apply the configuration.

### Add WebSocket Client in NapCat

Switch back to NapCat's management panel, click `Network Configuration->New->WebSockets Client`.

<img width="649" height="751" alt="jiaochenXJY" src="https://github.com/user-attachments/assets/5044f96a-a81f-407a-a3b1-0c518499eda4" />


In the newly opened window:

- Check `Enable`.
- For local deployment, fill in `URL` with `ws://HostIP:Port/ws`. For example, `ws://localhost:6199/ws` or `ws://127.0.0.1:6199/ws`.

> [!IMPORTANT]
> 1. If deploying with Docker and both AstrBot and NapCat containers are connected to the same network, use `ws://astrbot:6199/ws` (refer to the Docker script in this documentation).
> 2. For cross-host or public network deployment, do not expose plain `ws://`. Put AstrBot behind an HTTPS/TLS reverse proxy and connect with `wss://your-domain/ws` instead.

- Message Format: `Array`
- Heartbeat Interval: `5000`
- Reconnection Interval: `5000`

> [!WARNING]
>
> 1. Remember to add `/ws` at the end!
> 2. The IP here cannot be `0.0.0.0`

Click `Save`.

Go to AstrBot WebUI `Console`, if you see the blue log ` aiocqhttp(OneBot v11) adapter connected.`, it means the connection is successful. If not, and after several seconds ` aiocqhttp adapter has been closed` appears, it indicates connection timeout (failed), please check if the configuration is correct.

## 🎉 All Done

At this point, your AstrBot and NapCat should be successfully connected! Use `private message` to send `/help` to the bot to check if the connection is successful.
