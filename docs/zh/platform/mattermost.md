# 接入 Mattermost

Mattermost 适配器通过 Bot Token 和 WebSocket 连接到 Mattermost 服务器。完成下面两部分配置后，AstrBot 就可以在 Mattermost 频道和私聊中收发消息。

## 创建 AstrBot Mattermost 平台适配器

进入 `机器人` 页面，点击 `+ 创建机器人`，选择 `Mattermost`。

在配置页中先打开 `启用`，然后填写以下字段：

- `Mattermost URL`：你的 Mattermost 服务地址，例如 `https://chat.example.com`
- `Mattermost Bot Token`：在 Mattermost 中创建 Bot 账户后生成的访问令牌
- `Mattermost 重连延迟`：WebSocket 断开后的重连等待时间，默认 `5`

填写完成后点击保存。

## 部署 Mattermost

如果你还没有 Mattermost 服务，建议直接使用 Mattermost 官方提供的 Docker Compose 仓库：

- 官方文档：https://docs.mattermost.com/deployment-guide/server/containers/install-docker.html
- 官方仓库：https://github.com/mattermost/docker

官方当前推荐的快速部署步骤如下：

```bash
git clone https://github.com/mattermost/docker
cd docker
cp env.example .env
```

然后至少修改 `.env` 中的：

- `DOMAIN`
- `MATTERMOST_IMAGE_TAG`
- 建议补充 `MM_SUPPORTSETTINGS_SUPPORTEMAIL`

接着创建数据目录并设置权限：

```bash
mkdir -p ./volumes/app/mattermost/{config,data,logs,plugins,client/plugins,bleve-indexes}
sudo chown -R 2000:2000 ./volumes/app/mattermost
```

启动方式二选一：

不使用内置 NGINX：

```bash
docker compose -f docker-compose.yml -f docker-compose.without-nginx.yml up -d
```

使用内置 NGINX：

```bash
docker compose -f docker-compose.yml -f docker-compose.nginx.yml up -d
```

访问地址：

- 不使用 NGINX：`http://你的域名:8065`
- 使用 NGINX：`https://你的域名`

> [!TIP]
> Mattermost 官方当前说明中，Docker 生产支持仅限 Linux。macOS 和 Windows 更适合开发或测试用途。

## 在 Mattermost 中创建 Bot

### 1. 开启 Bot 账户创建

进入 Mattermost 的系统控制台：

`System Console > Integrations > Bot Accounts`

开启 `Enable Bot Account Creation`。

### 2. 创建 Bot 账户

进入：

`Product menu(左上角的图标) > Integrations > Bot Accounts`

点击 `Add Bot Account`，填写：

- `Username`
- `Display Name`
- `Description`

创建完成后复制生成的 Bot Token。这个 Token 只会展示一次，随后填写到 AstrBot 的 `Mattermost Bot Token` 中。

### 3. 将 Bot 加入频道

把刚创建的 Bot 添加到你准备让 AstrBot 工作的频道中，否则机器人无法在该频道正常收发消息。

## Mattermost URL 如何填写

`Mattermost URL` 填 Mattermost 的外部访问地址，不要带结尾斜杠。例如：

```text
https://chat.example.com
```

如果你当前只是在本机测试，也可以填写：

```text
http://127.0.0.1:8065
```

如果 AstrBot 和 Mattermost 都在 Docker 中运行，请优先填写 AstrBot 容器可访问到的地址，例如同一 Docker 网络中的服务名地址。

## 启动并验证

保存 AstrBot 平台适配器配置后：

1. 确保 AstrBot 日志中没有出现 Mattermost 认证失败或 WebSocket 连接失败。
2. 在 Mattermost 中向 Bot 所在频道发送消息，或直接给 Bot 发私聊。
3. 如果 AstrBot 正常回复，说明接入成功。

## 常见问题

### 提示 Token 无效

通常是以下原因：

- 复制的不是 Bot Token
- Token 复制时带了空格
- Bot 账户被删除或重新生成了 Token

### 连接成功但收不到频道消息

优先检查：

- Bot 是否已经加入目标频道
- Mattermost URL 是否填写为 AstrBot 实际可访问的地址
- Mattermost 反向代理是否正确转发了 WebSocket 请求

### 本机部署能打开页面，但 AstrBot 连接不到

如果 AstrBot 运行在容器里，而 Mattermost URL 填的是 `localhost` 或 `127.0.0.1`，那么 AstrBot 实际连接到的是它自己的容器，而不是 Mattermost。此时应改为 Docker 网络内可访问的地址。
