# Agent 沙盒环境 ⛵️

> [!TIP]
> 此功能目前处于技术预览阶段，可能会存在一些 Bug。如果您遇到了问题，请在 [GitHub](https://github.com/AstrBotDevs/AstrBot/issues) 上提交 issue。

在 `v4.12.0` 版本及之后，AstrBot 引入了 Agent 沙盒环境，以替代之前的代码执行器功能。沙盒环境给 Agent 提供了更安全、更灵活的代码执行和自动化操作能力。

![](https://files.astrbot.app/docs/source/images/astrbot-agent-sandbox/image.png)

## 启用沙盒环境

目前，AstrBot 的沙盒环境驱动器支持：

- `Shipyard Neo`（当前推荐）
- `Shipyard`（旧方案，仍可继续使用）

在当前版本的 AstrBot 控制台中，可在“AI 配置” -> “Agent Computer Use”中选择：

- `Computer Use Runtime` = `sandbox`
- `沙箱环境驱动器` = `Shipyard Neo` 或 `Shipyard`

其中，`Shipyard Neo` 是当前默认驱动器。它由 Bay、Ship、Gull 三部分组成：

- **Bay**：控制面 API，负责创建和管理 sandbox
- **Ship**：负责 Python / Shell / 文件系统能力
- **Gull**：负责浏览器自动化能力

对于 `Shipyard Neo`，工作区根目录固定为 `/workspace`。在 AstrBot 中调用文件系统工具时，应当传入**相对于工作区根目录**的路径，例如 `reports/result.txt`，而不是 `/workspace/reports/result.txt`。

> [!TIP]
> `Shipyard Neo` 下浏览器能力并不是所有 profile 都有。只有 profile 支持 `browser` capability 时，AstrBot 才会挂载浏览器相关工具。典型 profile 如 `browser-python`。

## 性能要求

AstrBot 给每个沙盒环境限制最高 1 CPU 和 512 MB 内存。

我们建议您的宿主机至少有 2 个 CPU 和 4 GB 内存，并开启 Swap，以保证多个沙盒环境实例可以稳定运行。

## 推荐：使用 Shipyard Neo

### 单独部署 Shipyard Neo（推荐）

如果您准备长期使用 `Shipyard Neo`，更推荐将它**单独部署在一台资源更充足的机器上**，例如您的 homelab、局域网服务器，或独立云主机，然后再让 AstrBot 远程接入 Bay。

原因是：`Shipyard Neo` 在启用浏览器能力时需要运行较重的浏览器运行时。对于资源紧张的云服务器，把 AstrBot 和 `Shipyard Neo` 部署在同一台机器上，通常会让 CPU 和内存压力都比较大，稳定性和体验都不理想。

大致步骤如下：

```bash
git clone https://github.com/AstrBotDevs/shipyard-neo
cd shipyard-neo/deploy/docker
# 修改 config.yaml 中的关键配置，例如 security.api_key
docker compose up -d
```

部署完成后：

- Bay 默认监听在 `http://<your-host>:8114`
- 在 AstrBot 控制台中选择 `Shipyard Neo` 驱动器
- `Shipyard Neo API Endpoint` 填写对应地址，例如 `http://<your-host>:8114`
- `Shipyard Neo Access Token` 填写 Bay API Key；如果 AstrBot 能访问 Bay 的 `credentials.json`，也可以留空让 AstrBot 自动发现

### 参考：`config.yaml` 完整示例（附说明）

如果您准备自行调整 `Shipyard Neo` 的部署参数，可以直接参考下面这份基于 [`deploy/docker/config.yaml`](https://github.com/AstrBotDevs/shipyard-neo/blob/main/deploy/docker/config.yaml) 整理的完整示例。它保留了默认结构，并额外加上了中文注释，便于理解每个配置项的用途。

> [!TIP]
> 其中最少需要修改的是 `security.api_key`。如果不清楚其他参数的作用，建议先保持默认值，仅按需调整 profile、资源限制和 warm pool 配置。

```yaml
# Bay Production Config - Docker Compose (container_network mode)
#
# Bay 运行在 Docker 容器中，并通过共享 Docker 网络与 Ship/Gull 容器通信。
# 这种模式下，sandbox 容器不需要向宿主机暴露端口。
#
# 部署前至少需要修改：
#   1. security.api_key  —— 设置强随机密钥

server:
  # Bay API 监听地址
  host: "0.0.0.0"
  # Bay API 监听端口
  port: 8114

database:
  # 单机部署默认使用 SQLite。
  # 如果要做多实例 / 高可用，可改用 PostgreSQL，例如：
  # url: "postgresql+asyncpg://user:pass@db-host:5432/bay"
  url: "sqlite+aiosqlite:///./data/bay.db"
  echo: false

driver:
  # 当前默认使用 Docker 驱动
  type: docker

  # 创建新 sandbox 时是否拉取镜像。
  # 生产环境通常建议 always，以便拿到最新镜像。
  image_pull_policy: always

  docker:
    # Docker Socket 地址
    socket: "unix:///var/run/docker.sock"

    # Bay 在容器内运行，Ship/Gull 也在容器内运行时，
    # 推荐使用 container_network 通过容器网络直接通信。
    connect_mode: container_network

    # 共享网络名，必须与 docker-compose.yaml 中的网络一致
    network: "bay-network"

    # 是否将 sandbox 容器端口暴露到宿主机。
    # 生产环境建议关闭，以减少攻击面。
    publish_ports: false
    host_port: null

cargo:
  # Cargo 在 Bay 侧的存储根路径
  root_path: "/var/lib/bay/cargos"
  # 默认工作区大小限制（MB）
  default_size_limit_mb: 1024
  # Cargo 挂载到 sandbox 内的路径。AstrBot/Neo 的工作区根目录就是这里。
  mount_path: "/workspace"

security:
  # 必改项：设置一个强随机密钥，例如 openssl rand -hex 32
  api_key: "CHANGE-ME"
  # 是否允许匿名访问。生产环境建议 false。
  allow_anonymous: false

# 容器代理环境变量注入。
# 启用后，Bay 会把 HTTP(S)_PROXY 和 NO_PROXY 注入到 sandbox 容器。
proxy:
  enabled: false
  # http_proxy: "http://proxy.example.com:7890"
  # https_proxy: "http://proxy.example.com:7890"
  # no_proxy: "my-internal.service"

# Warm Pool：预热一批待命 sandbox，减少冷启动延迟。
# 当用户创建 sandbox 时，Bay 会优先尝试领取一个已预热实例。
warm_pool:
  enabled: true
  # 预热队列 worker 数量
  warmup_queue_workers: 2
  # 预热队列最大长度
  warmup_queue_max_size: 256
  # 队列满时的丢弃策略
  warmup_queue_drop_policy: "drop_newest"
  # 超过这个阈值时便于运维告警
  warmup_queue_drop_alert_threshold: 50
  # 预热池维护扫描周期（秒）
  interval_seconds: 30
  # Bay 启动时是否立即运行预热逻辑
  run_on_startup: true

profiles:
  # ── 标准 Python 沙箱 ────────────────────────
  - id: python-default
    description: "Standard Python sandbox with filesystem and shell access"
    image: "ghcr.io/astrbotdevs/shipyard-neo-ship:latest"
    runtime_type: ship
    runtime_port: 8123
    resources:
      cpus: 1.0
      memory: "1g"
    capabilities:
      - filesystem  # 包含 upload/download
      - shell
      - python
    # 空闲超时（秒）
    idle_timeout: 1800
    # 保持 1 个预热实例
    warm_pool_size: 1
    env: {}
    # 可选：profile 级代理覆盖
    # proxy:
    #   enabled: false

  # ── 数据科学沙箱（更多资源） ──────────
  - id: python-data
    description: "Data science sandbox with extra CPU and memory"
    image: "ghcr.io/astrbotdevs/shipyard-neo-ship:latest"
    runtime_type: ship
    runtime_port: 8123
    resources:
      cpus: 2.0
      memory: "4g"
    capabilities:
      - filesystem  # 包含 upload/download
      - shell
      - python
    idle_timeout: 1800
    warm_pool_size: 1
    env: {}

  # ── 浏览器 + Python 多容器沙箱 ───────
  - id: browser-python
    description: "Browser automation with Python backend"
    containers:
      - name: ship
        image: "ghcr.io/astrbotdevs/shipyard-neo-ship:latest"
        runtime_type: ship
        runtime_port: 8123
        resources:
          cpus: 1.0
          memory: "1g"
        capabilities:
          - python
          - shell
          - filesystem  # 包含 upload/download
        # 这些能力优先由 ship 容器提供
        primary_for:
          - filesystem
          - python
          - shell
        env: {}
      - name: browser
        image: "ghcr.io/astrbotdevs/shipyard-neo-gull:latest"
        runtime_type: gull
        runtime_port: 8115
        resources:
          cpus: 1.0
          memory: "2g"
        capabilities:
          - browser
        env: {}
    idle_timeout: 1800
    warm_pool_size: 1

gc:
  # 生产环境建议启用自动 GC
  enabled: true
  run_on_startup: true
  # GC 扫描周期（秒）
  interval_seconds: 300

  # 多实例部署时必须保证唯一
  instance_id: "bay-prod"

  idle_session:
    enabled: true
  expired_sandbox:
    enabled: true
  orphan_cargo:
    enabled: true
  orphan_container:
    # 建议在生产环境开启，用于清理遗留容器
    enabled: true
```

通常可以按下面的思路理解和修改：

- **最小必改项**：`security.api_key`
- **最常改项**：`profiles` 里的资源限制、`warm_pool_size`、`idle_timeout`
- **需要浏览器能力时**：使用或调整 `browser-python` profile
- **希望减少冷启动时间时**：保留 `warm_pool.enabled: true`，并适当提高常用 profile 的 `warm_pool_size`
- **资源较紧张时**：可先把 `warm_pool_size` 改小，甚至关闭 `warm_pool`
- **如果需要代理访问外网**：配置顶层 `proxy`，或按 profile 单独覆盖

### 关于 Shipyard Neo 的复用与持久化

`Shipyard Neo` 中有几个重要概念：

- **Sandbox**：对外稳定可见的资源单元
- **Session**：实际运行中的容器会话，可被停止或重建
- **Cargo**：持久化工作区卷，挂载到 `/workspace`

对 AstrBot 而言，当前会按请求的 `session_id` 维度缓存沙箱 booter；在主 Agent 默认流程下，这个 `session_id` 通常等于消息会话标识 `unified_msg_origin`。因此，同一消息会话的后续请求通常会继续复用同一个 Neo sandbox；如果沙箱失效，则会自动重建。

关于 TTL 与数据持久化的更详细说明，请参考下文的“关于 `Shipyard Neo Sandbox TTL`”与“关于沙盒环境的数据持久化”小节。

## 旧方案：Shipyard

以下内容为旧版 `Shipyard` 驱动器的部署与配置说明，仍然保留，供兼容旧部署方案时参考。

### 使用 Docker Compose 部署 AstrBot 和 Shipyard

如果您还没有部署 AstrBot，或者想更换为我们推荐的带沙盒环境的部署方式，推荐使用 Docker Compose 来部署 AstrBot，代码如下：

```bash
git clone https://github.com/AstrBotDevs/AstrBot
cd AstrBot
# 修改 compose-with-shipyard.yml 文件中的环境变量配置，例如 Shipyard 的 access token 等
docker compose -f compose-with-shipyard.yml up -d
docker pull soulter/shipyard-ship:latest
```

这会启动一个包含 AstrBot 主程序和沙盒环境的 Docker Compose 服务。

### 单独部署 Shipyard

如果您已经部署了 AstrBot，但没有部署沙盒环境，可以单独部署 Shipyard。

代码如下：

```bash
mkdir astrbot-shipyard
cd astrbot-shipyard
wget https://raw.githubusercontent.com/AstrBotDevs/shipyard/refs/heads/main/pkgs/bay/docker-compose.yml -O docker-compose.yml
# 修改 compose-with-shipyard.yml 文件中的环境变量配置，例如 Shipyard 的 access token 等
docker compose -f docker-compose.yml up -d
docker pull soulter/shipyard-ship:latest
```

部署成功后，上述命令会启动一个 Shipyard 服务，默认监听在 `http://<your-host>:8156`。

> [!TIP]
> 如果您使用 Docker 部署 AstrBot，您也可以修改上面的 Compose 文件，将 Shipyard 的网络与 AstrBot 放在同一个 Docker 网络中，这样就不需要暴露 Shipyard 的端口到宿主机。

## 配置 AstrBot 使用沙盒环境

> [!TIP]
> 请确保您的 AstrBot 版本在 `v4.12.0` 及之后。

在 AstrBot 控制台，进入 “AI 配置” -> “Agent Computer Use”。

1. 将 `Computer Use Runtime` 设为 `sandbox`
2. 在 `沙箱环境驱动器` 中选择 `Shipyard Neo` 或 `Shipyard`
3. 根据驱动器填写对应配置项
4. 点击右下角“保存”

### 配置 Shipyard Neo

如果您选择的是 `Shipyard Neo`，主要配置项如下：

- `Shipyard Neo API Endpoint`
  - 联合部署时可填写 `http://bay:8114`
  - 单独部署时填写实际地址，例如 `http://<your-host>:8114`
- `Shipyard Neo Access Token`
  - 填写 Bay API Key
  - 如果是官方联合部署，且 AstrBot 能访问 Bay 的 `credentials.json`，可以留空自动发现
- `Shipyard Neo Profile`
  - 例如 `python-default`、`browser-python`
  - 如果未手动指定，AstrBot 会优先尝试选择能力更完整、且优先带有 `browser` capability 的 profile，失败时再回退到 `python-default`
- `Shipyard Neo Sandbox TTL`
  - sandbox 生命周期上限，默认值为 3600 秒（1 小时）

### 配置 Shipyard（旧方案）

如果您选择的是旧版 `Shipyard`，配置项如下：

- `Shipyard API Endpoint`
  - 如果您使用上述 Docker Compose 部署方式，填写 `http://shipyard:8156` 即可
  - 如果您是单独部署的 Shipyard，请填写对应地址，例如 `http://<your-host>:8156`
- `Shipyard Access Token`
  - 请填写部署 Shipyard 时配置的访问令牌
- `Shipyard Ship 存活时间(秒)`
  - 定义每个沙箱环境实例的存活时间，默认值为 3600 秒（1 小时）
- `Shipyard Ship 会话复用上限`
  - 定义每个沙箱环境实例可以复用的最大会话数，默认值为 10

## 关于 `Shipyard Neo Sandbox TTL`

在 `Shipyard Neo` 中：

- TTL 表示 sandbox 生命周期上限
- profile 还会定义一个独立的空闲超时（`idle_timeout`）
- AstrBot 发起能力调用时，通常会刷新空闲超时，而不是直接延长 TTL
- `keepalive` 只会延长空闲超时，不会自动启动新的 session，也不会延长 TTL

## 关于 `Shipyard Ship 存活时间(秒)`

以下说明仅适用于旧版 `Shipyard`：

沙箱环境实例的存活时间定义了每个实例在被销毁之前可以存在的最长时间，这个时间的设置需要根据您的使用场景以及资源来决定。

- 新的会话加入已有的沙箱环境实例时，该实例会自动延长存活时间到这个会话请求的 TTL。
- 当对沙箱环境实例执行操作后，该实例会自动延长存活时间到当前时间加上 TTL。

## 关于沙盒环境的数据持久化

### Shipyard Neo

`Shipyard Neo` 的工作区根目录固定为 `/workspace`。

其持久化由 Cargo 提供：

- 文件系统数据保存在 Cargo 中，并挂载到 `/workspace`
- 即使底层 Session 被停止或重建，Cargo 中的数据通常仍可保留
- 对于带浏览器能力的 profile，浏览器状态也可能会一起持久化，例如 `/workspace/.browser/profile/`

### Shipyard（旧方案）

Shipyard 会给每个会话分配一个工作目录，在 `/home/<会话唯一 ID>` 目录下。

Shipyard 会自动将沙盒环境中的 /home 目录挂载到宿主机的 `${PWD}/data/shipyard/ship_mnt_data` 目录下，当沙盒环境实例被销毁后，如果某个会话继续请求调用沙箱，Shipyard 会重新创建一个新的沙盒环境实例，并将之前持久化的数据重新挂载进去，保证数据的连续性。

## 其他同类社区插件

### luosheng520qaq/astrobot_plugin_code_executor

如果您资源有限，不希望使用沙盒环境来执行代码，可以尝试 luosheng520qaq 开发的 [astrobot_plugin_code_executor](https://github.com/luosheng520qaq/astrobot_plugin_code_executor) 插件。该插件会直接在宿主机上执行代码。插件已经尽力提升安全性，但仍需留意代码安全性问题。