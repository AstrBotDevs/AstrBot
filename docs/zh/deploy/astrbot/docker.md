# 使用 Docker 部署 AstrBot

每个推送到仓库的 `v*` 标签都会发布一个最小运行时镜像到 GHCR：
`ghcr.io/xero-team/astrbot:<tag>`。正式版本（不含 `-` 的标签）还会更新
`ghcr.io/xero-team/astrbot:latest`。镜像同时提供 `linux/amd64` 和
`linux/arm64`。

## 使用已发布的最小镜像

`minimal` 保留 AstrBot、WebUI 和核心 Shell 工具，但不包含浏览器、文档处理、
媒体、OCR、运行时字体、Node.js 或 Docker CLI 等可选功能。需要这些功能时，请按照
下面的本地构建方式选择功能组；不要把 `latest` 用作可复现部署的版本标识。

将发布的 GHCR package 设为 Public 后，可直接运行指定版本：

```bash
docker run -d --init --name astrbot \\
  -p 127.0.0.1:6185:6185 \\
  -e ASTRBOT_DASHBOARD_HOST=0.0.0.0 \\
  -v astrbot-data:/AstrBot/data \\
  ghcr.io/xero-team/astrbot:v4.27.2
```

首次运行会在日志中写入随机初始密码。使用 `docker logs astrbot` 查看它。对于私有
package，先使用有 `read:packages` 权限的令牌登录 `ghcr.io`。

> [!CAUTION]
> 示例只把管理面板发布到本机回环地址。不要将其直接暴露到公网；如需远程访问，请配置
> 防火墙、HTTPS 反向代理、强密码和 TOTP。

## 从源码构建

需要完整功能、定制运行时功能，或同时运行本仓库文档站点时，请克隆本仓库，并使用根目录
的 `Dockerfile`、`Dockerfile.docs` 和 Compose 文件在本地构建。

## 选择 Compose 文件

仓库提供两条本地构建路径：

- `compose.yml`：运行 AstrBot 和本仓库构建的静态文档站点，适合接入 QQ 官方机器人、Telegram、Discord 等平台，或独立管理其他机器人协议端。
- `compose-with-napcat.yml`：运行 AstrBot、静态文档站点和 NapCat，适合 QQ 个人号；AstrBot 与文档仍由本地源码构建，NapCat 使用所引用的 NapCat 容器镜像。

先克隆仓库：

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
```

## 容器监听与宿主机端口

Compose 部署会显式将容器内的 WebUI 监听地址设为 `0.0.0.0`，否则宿主机无法访问容器端口。宿主机端口默认只绑定到 `127.0.0.1`；需要远程访问时，再显式设置 `ASTRBOT_BIND_ADDRESS` 并配置防火墙或 HTTPS 反向代理。

例如：

```bash
ASTRBOT_BIND_ADDRESS=0.0.0.0 docker compose up -d --build
```

`ASTRBOT_DASHBOARD_HOST` 的优先级高于 `data/cmd_config.json` 中的 `dashboard.host`。

> [!CAUTION]
> `0.0.0.0` 会让 WebUI 监听容器的所有网络接口。不要把管理面板无保护地暴露到公网；至少应限制防火墙来源，并使用反向代理、HTTPS、强密码和 TOTP。

AstrBot 服务按当前部署需求显式使用 `privileged: true`；NapCat 组合还会挂载
`/var/run/docker.sock`。这些设置是所选计算机工具和 Docker 集成所需的，并赋予容器
主机级控制能力。请仅加载可信插件并保护宿主机；静态文档服务仍保持只读、非特权运行。

## 启动 AstrBot 和文档

根 `compose.yml` 会使用根 `Dockerfile` 的 `runtime` 阶段，把当前仓库构建为本地镜像 `astrbot:local`；文档镜像为 `astrbot-docs:local`。根 `Dockerfile` 的 `dev` 阶段保留给开发工具环境：

```bash
docker build --target dev -t astrbot:dev .
```

### 选择运行时功能

`ASTRBOT_FEATURES` 是 Docker **构建参数**，不是容器启动后的运行时环境变量。
Compose 会把它传给 `Dockerfile` 的 `runtime` 阶段；不设置时默认为 `full`，保持完整功能。
修改功能后必须重新构建镜像，已有容器不会自动变化。可以按下面三种方式设置：

一次性设置（只影响本次构建）：

```bash
ASTRBOT_FEATURES=minimal docker compose up -d --build
```

写入项目根目录的 `.env`（之后每次 Compose 构建都会使用）：

```dotenv
ASTRBOT_FEATURES=browser,documents,media,ocr,fonts,node,docker
```

也可以在命令行覆盖 `.env` 中的值：

```bash
ASTRBOT_FEATURES=browser,node,docker docker compose up -d --build
```

NapCat 组合使用同一个参数：

```bash
ASTRBOT_FEATURES=browser,node,docker \
  docker compose -f compose-with-napcat.yml up -d --build
```

可用的功能组如下：

- `browser`：Chromium 及其系统依赖。
- `documents`：Pandoc、Poppler、TeX 及相关字体。
- `media`：FFmpeg、ImageMagick、Ghostscript 和编解码库。
- `ocr`：Tesseract 以及英文、简体中文语言数据。
- `fonts`：运行时字体和 fontconfig。
- `node`：供 MCP 启动器使用的 Node.js、npm、npx、pnpm。
- `docker`：Docker CLI 和 Compose 插件。

注意：`node` 不是 WebUI 正常运行所必需的。Dashboard 会在 Dockerfile 的
`builder` 阶段用 Node.js 构建，生成的静态文件会复制进 `runtime` 镜像；运行时由
AstrBot 的 Python/FastAPI 服务直接提供。因此 `minimal` 仍然包含并可以访问 WebUI，
只有需要运行 Node.js MCP 启动器或其他 Node.js 工具时才加入 `node`。

例如：

```bash
docker compose config
```

上面的命令可以检查 Compose 最终传入的 `ASTRBOT_FEATURES` 构建参数。
`minimal` 保留 Python 应用和核心 Shell 工具；需要某项可选集成时再显式加入对应功能。
构建阶段仍会保留生成 Dashboard 和文档所需的工具链；这些开关影响最终运行镜像。

```bash
docker compose up -d --build
docker compose logs -f astrbot docs
```

默认挂载和端口为：

- `./data` -> `/AstrBot/data`：配置、数据库、插件等运行时数据。
- `127.0.0.1:6185:6185`：AstrBot WebUI。
- `127.0.0.1:6199:6199`：可选的 OneBot v11 反向 WebSocket 入口。
- `127.0.0.1:6186:8080`：本仓库构建的文档站点，可通过 `http://localhost:6186` 访问。

文档是独立的只读静态服务，不读取 `data/`，也不复用 WebUI 的登录状态。仅在需要对外提供文档时才发布 `6186`，并按部署环境使用防火墙或 HTTPS 反向代理保护该端口。

发布 `6199` 并不会自动让 OneBot 入口监听外部接口。仅当 OneBot 客户端位于 AstrBot 容器之外时，才把该平台的 `ws_reverse_host` 改为 `0.0.0.0`；同时配置 `ws_reverse_token`，并限制端口的网络访问范围。

## 同时启动 AstrBot 和 NapCat

当前文件还为 NapCat 设置了 `MODE=astrbot`。该模式会在 NapCat 每次启动时写入一个连接 `ws://astrbot:6199/ws` 的**反向** WebSocket 客户端。如果要使用 AstrBot 当前推荐的独立 `NapCat` 平台，请先将它改成：

```yaml
- MODE=ws
```

`MODE=ws` 会让 NapCat 启动监听 `0.0.0.0:3001` 的 OneBot v11 正向 WebSocket 服务。然后启动：

```bash
docker compose -f compose-with-napcat.yml up -d --build
docker compose -f compose-with-napcat.yml logs -f astrbot docs napcat
```

Linux 上可让 NapCat 使用当前宿主用户的 UID/GID，以减少挂载目录权限问题：

```bash
NAPCAT_UID=$(id -u) NAPCAT_GID=$(id -g) \
  docker compose -f compose-with-napcat.yml up -d --build
```

该 Compose 默认发布（宿主机仅绑定环回地址）：

- `6185`：AstrBot WebUI。
- `6186`：本仓库构建的文档站点。
- `6099`：NapCat WebUI。

并持久化：

- `./data`
- `./napcat/config`
- `./ntqq`

AstrBot 与 NapCat 位于同一个 Docker 网络。使用 `MODE=ws` 时，请在 AstrBot 中创建独立的 `NapCat` 平台，将 `ws_url` 填为 `ws://napcat:3001`；如果 NapCat 的正向 WebSocket 配置了 token，两端必须填写同一个值。此路径不需要向宿主机发布 QQ WebSocket 端口。

> [!NOTE]
> NapCat 的 `MODE` 是启动模板选择器，会在每次启动时重写 `onebot11.json`，模板中的 token 为空。如果需要自定义并持久化 token，可先用 `MODE=ws` 启动一次生成配置，再从 Compose 删除 `MODE`，然后在 NapCat WebUI 中设置 token；配置会保存在 `./napcat/config`。

如果保留 Compose 原有的 `MODE=astrbot`，则不要创建独立 `NapCat` 平台。请创建 `OneBot v11` 平台，将 `ws_reverse_host` 设为 `0.0.0.0`，端口保持 `6199`。`6199` 只需在内部 Docker 网络可达，不需要发布到宿主机。如需鉴权，同样要在第一次生成配置后从 Compose 删除 `MODE`，再在 NapCat 与 AstrBot 两端设置相同 token。

## 首次登录和更新

首次启动时，AstrBot 会在日志中打印 WebUI 地址和随机初始密码，默认用户名为 `astrbot`。登录后请立即修改密码。

更新时先备份 `data/`，再拉取代码并重新构建所用服务：

```bash
git pull --ff-only
docker compose up -d --build
```

NapCat 组合部署则使用：

```bash
git pull --ff-only
docker compose -f compose-with-napcat.yml up -d --build
```
