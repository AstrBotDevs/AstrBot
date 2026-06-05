# Agent 沙盒环境 ⛵️

> [!TIP]
> 此功能目前处于技术预览阶段，可能会存在一些 Bug。如果您遇到了问题，请在 [GitHub](https://github.com/AstrBotDevs/AstrBot/issues) 上提交 issue。

从 `v4.12.0` 开始，AstrBot 引入了 Agent 沙盒环境，用来替代之前的代码执行器功能。它让 Agent 在隔离环境里运行 Shell、Python、文件操作或桌面自动化任务，不必直接碰 AstrBot 主机。

如果你是从旧配置迁移过来的，先看清楚配置是怎么对应的。现在沙盒运行时已经拆成独立插件，AstrBot Core 只负责调度、复用、占用和清理；你需要做的是：先装驱动插件，再把 `Computer Use Runtime`、`沙盒驱动` 和驱动自己的参数填好。

![](https://files.astrbot.app/docs/source/images/astrbot-agent-sandbox/image.png)

## 安装与启用沙盒环境

### 先看这 3 个配置

1. `Computer Use Runtime` 设为 `sandbox`。
2. 在 `沙盒驱动` 里选择 `Shipyard Neo`、`BoxLite`、`Shipyard` 或 `CUA`。
3. 按所选驱动补齐对应配置，比如 `Shipyard Neo API Endpoint`、`Shipyard Neo Access Token`、`CUA Image`、`CUA Sandbox TTL`。

这几个驱动现在都以独立插件的形式提供，所以顺序一定是：先装插件，再回到 WebUI 配置。

当前可用的沙盒驱动包括：

- [`Shipyard Neo`](https://github.com/AstrBotDevs/astrbot_sandbox_shipyard_neo)（推荐，适合长期运行和多人使用）
- [`BoxLite`](https://github.com/AstrBotDevs/astrbot_sandbox_boxlite)（轻量本地沙盒，适合只需要 Shell、Python 和文件操作的场景）
- [`Shipyard`](https://github.com/AstrBotDevs/astrbot_sandbox_shipyard)（旧方案，仍可继续使用）
- [`CUA`](https://github.com/AstrBotDevs/astrbot_sandbox_cua)（本地或云端电脑使用沙盒，适合需要桌面操作的场景）

如果你只是想先跑通沙盒，建议这样选：

- 需要稳定的 Shell、Python、文件系统和 Skills 同步：优先选 `Shipyard Neo`。
- 只想要轻量本地执行环境：选 `BoxLite`。
- 需要截图、鼠标、键盘这类桌面操作：选 `CUA`。
- 还在用旧部署：继续用 `Shipyard`，但新环境不建议再从它开始。

安装示例：

```bash
git clone https://github.com/AstrBotDevs/astrbot_sandbox_shipyard_neo.git data/plugins/astrbot_sandbox_shipyard_neo
git clone https://github.com/AstrBotDevs/astrbot_sandbox_boxlite.git data/plugins/astrbot_sandbox_boxlite
git clone https://github.com/AstrBotDevs/astrbot_sandbox_shipyard.git data/plugins/astrbot_sandbox_shipyard
git clone https://github.com/AstrBotDevs/astrbot_sandbox_cua.git data/plugins/astrbot_sandbox_cua
```

安装完成后，重启 AstrBot，或者在插件管理页重新加载插件。

然后打开 AstrBot 控制台，在“AI 配置” -> “Agent Computer Use”中选择：

- `Computer Use Runtime` = `sandbox`
- `沙盒驱动` = `Shipyard Neo`、`BoxLite`、`Shipyard` 或 `CUA`

其中，`Shipyard Neo` 是当前推荐的默认驱动。它由 Bay、Ship、Gull 三部分组成：

- **Bay**：控制面 API，负责创建和管理沙盒
- **Ship**：负责 Python / Shell / 文件系统能力
- **Gull**：负责浏览器自动化能力

对于 `Shipyard Neo`，工作区根目录固定为 `/workspace`。在 AstrBot 中调用文件系统工具时，请传入**相对于工作区根目录**的路径，例如 `reports/result.txt`，不要写成 `/workspace/reports/result.txt`。

> [!TIP]
> `Shipyard Neo` 的浏览器能力不是所有 profile 都支持。只有 profile 带有 `browser` capability 时，AstrBot 才会挂载浏览器相关工具。一个常见示例是 `browser-python`。

## 托管沙盒、占用和保留策略

启用沙盒后，你可以在 WebUI 的“沙盒管理”页面看到 AstrBot 管理的沙盒。这里有几个容易混淆的词：

- **托管沙盒**：AstrBot 记录并管理的沙盒。它可能来自 `Shipyard Neo`、`BoxLite`、`CUA` 或旧版 `Shipyard`。
- **默认沙盒**：某个驱动下优先复用的沙盒。Agent 没有明确指定时，会优先尝试复用它。
- **占用**：某个会话正在控制这个沙盒。占用期间，其他会话不能直接抢用，除非管理员或配置允许接管。
- **占用租约**：占用的有效时间。默认 600 秒。Agent 可以调用续租工具延长它；续租后，后续普通工具调用不会把更长的租约缩短。
- **临时沙盒**：释放后可以按空闲时间或过期时间自动清理。
- **持久沙盒**：环境会保留，适合准备好依赖后反复使用。它仍然会有“占用”状态，只是释放后不会因为临时清理策略被删掉。

排障时可以先看这两项：

- `最后使用`：最近一次由 Agent 占用、续租或切换到这个沙盒的时间。
- `占用到期时间`：当前会话控制权的到期时间。它和驱动自己的 TTL 不是一回事。

驱动 TTL 通常表示沙盒实例本身最多保留多久；占用租约只表示当前会话还能控制它多久。比如 CUA 的 `CUA Sandbox TTL` 管的是 CUA 实例生命周期，而 AstrBot 的 `沙盒占用超时` 管的是会话占用时间。

## CUA 驱动

`CUA` 面向电脑使用（Computer Use）场景。它可以通过统一的 Python SDK 创建 Linux、macOS、Windows、Android 等不同类型的沙盒，并提供 Shell、截图、鼠标、键盘和文件系统等接口。

在 AstrBot 中选择 `CUA` 驱动后，Agent 可以在 CUA 沙盒中使用：

- Shell 工具
- Python 工具
- 文件读取、写入、编辑和搜索工具
- 截图工具
- 鼠标点击工具
- 键盘输入工具
- 沙盒文件上传与下载工具

> [!NOTE]
> CUA 是可选驱动，AstrBot 默认不会强制安装它。如果你选择了 `CUA`，但当前 Python 环境里没有安装 `cua` 包，启动沙盒时会提示缺少依赖。

### 先安装 CUA 插件

在配置 `CUA` 之前，请先把插件安装到 AstrBot 的插件目录：

```bash
git clone https://github.com/AstrBotDevs/astrbot_sandbox_cua.git data/plugins/astrbot_sandbox_cua
```

然后重启 AstrBot，或者在插件管理页重新加载插件。

### 安装 CUA 依赖

如果你是通过源码或虚拟环境运行 AstrBot，请在 AstrBot 使用的 Python 环境里安装 CUA：

```bash
pip install cua
```

如果你使用 `uv` 管理 AstrBot 环境，可以在 AstrBot 项目目录中执行：

```bash
uv pip install cua
```

CUA 还依赖具体的运行方式：

- 本地 Linux 容器通常需要 Docker 可用。
- 本地 Linux/Windows VM 通常需要 QEMU 或 CUA 对应的本地运行时。
- macOS VM 通常依赖 CUA/Lume 相关运行时。
- 云端 CUA 需要可用的 CUA API Key。

具体的宿主机要求、镜像支持情况，以及本地运行时的安装方式，请参考 [CUA 官方文档](https://cua.ai/docs)。

### 在 AstrBot 中配置 CUA

打开 WebUI：

- `配置 -> 普通配置 -> 使用电脑能力`

然后设置：

- `Computer Use Runtime` = `sandbox`
- `沙盒驱动` = `CUA`

CUA 相关配置项包括：

- `CUA Image`：要启动的 CUA 镜像。常见值为 `linux`、`macos`、`windows`、`android`。默认 `linux`。
- `CUA OS Type`：镜像的操作系统类型。默认 `linux`。它会影响 AstrBot 对 POSIX Shell fallback 的判断。
- `CUA Sandbox TTL`：沙盒生命周期，单位为秒。默认 `3600`。
- `CUA Telemetry Enabled`：是否启用 CUA 侧遥测。默认关闭。
- `CUA Local Runtime`：是否使用本地运行时。默认开启。关闭后会按 CUA SDK 的云端方式创建沙盒。
- `CUA API Key`：云端 CUA 所需的 API Key。仅在使用云端运行时时填写。

一个最小的本地 Linux 容器配置通常是：

```text
Computer Use Runtime = sandbox
沙盒驱动 = CUA
CUA Image = linux
CUA OS Type = linux
CUA Local Runtime = true
CUA Sandbox TTL = 3600
```

如果使用云端 CUA，可以改成：

```text
Computer Use Runtime = sandbox
沙盒驱动 = CUA
CUA Image = linux
CUA OS Type = linux
CUA Local Runtime = false
CUA API Key = <your-cua-api-key>
```

> [!WARNING]
> 不要把 CUA API Key 写进公开日志、截图或 issue。AstrBot 的运行日志不会输出这个字段，但部署平台、Shell 历史和容器环境变量仍然需要你自己保护好。

### 使用 CUA 时的注意事项

- `linux` 镜像通常适合 Shell、Python、文件系统和桌面自动化测试。
- 非 POSIX 镜像（如 `windows`、`android`）不一定支持 `sh`、`cat`、`ls`、`rm`、`base64` 等命令。AstrBot 对依赖这些命令的 fallback 操作会返回明确错误。
- 如果你需要在 CUA 沙盒里打开浏览器或 GUI 程序，通常应通过 Shell 后台执行，例如显式传入 `background=true`，避免命令阻塞后续工具调用。
- 直接把沙盒内的文件路径发给用户通常不可行。应优先使用 AstrBot 的沙盒下载工具，把文件下载到 AstrBot 临时目录后再发送。
- CUA 与 Shipyard Neo 的 workspace 语义不同。Shipyard Neo 固定使用 `/workspace`；CUA 的工作目录和文件路径取决于镜像与运行时。

### 何时选择 CUA

建议在以下场景选择 `CUA`：

- 需要桌面截图、鼠标点击、键盘输入等 GUI 自动化能力。
- 需要测试不同 OS 镜像中的行为，例如 Linux、Windows、Android。
- 已经在本机或云端部署好 CUA 运行环境。

如果你只是需要稳定的 Python/Shell/文件系统沙盒，而且不需要桌面 GUI 操作，通常优先选择 `Shipyard Neo`。它和 AstrBot 的 workspace、Skills 同步，以及长期运行模式更匹配。

## 性能要求

AstrBot 给每个沙盒环境限制最高 1 CPU 和 512 MB 内存。

建议宿主机至少有 2 个 CPU 和 4 GB 内存，并开启 Swap。这样同时跑多个沙盒时更稳。

## 推荐：使用 Shipyard Neo

### 单独部署 Shipyard Neo（推荐）

在 AstrBot 侧配置 `Shipyard Neo` 之前，请先安装对应插件：

```bash
git clone https://github.com/AstrBotDevs/astrbot_sandbox_shipyard_neo.git data/plugins/astrbot_sandbox_shipyard_neo
```

如果你准备长期使用 `Shipyard Neo`，更推荐将它**单独部署在一台资源更充足的机器上**，例如 homelab、局域网服务器，或独立云主机，然后再让 AstrBot 远程接入 Bay。

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
- 在 AstrBot 控制台中选择 `Shipyard Neo` 驱动
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
# 这种模式下，沙盒容器不需要向宿主机暴露端口。
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

  # 创建新沙盒时是否拉取镜像。
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

    # 是否将沙盒容器端口暴露到宿主机。
    # 生产环境建议关闭，以减少攻击面。
    publish_ports: false
    host_port: null

cargo:
  # Cargo 在 Bay 侧的存储根路径
  root_path: "/var/lib/bay/cargos"
  # 默认工作区大小限制（MB）
  default_size_limit_mb: 1024
  # Cargo 挂载到沙盒内的路径。AstrBot/Neo 的工作区根目录就是这里。
  mount_path: "/workspace"

security:
  # 必改项：设置一个强随机密钥，例如 openssl rand -hex 32
  api_key: "CHANGE-ME"
  # 是否允许匿名访问。生产环境建议 false。
  allow_anonymous: false

# 容器代理环境变量注入。
# 启用后，Bay 会把 HTTP(S)_PROXY 和 NO_PROXY 注入到沙盒容器。
proxy:
  enabled: false
  # http_proxy: "http://proxy.example.com:7890"
  # https_proxy: "http://proxy.example.com:7890"
  # no_proxy: "my-internal.service"

# Warm Pool：预热一批待命沙盒，减少冷启动延迟。
# 当用户创建沙盒时，Bay 会优先尝试领取一个已预热实例。
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

AstrBot 会按请求的 `session_id` 缓存沙盒 booter。在主 Agent 默认流程下，这个 `session_id` 通常等于消息会话标识 `unified_msg_origin`。因此，同一消息会话的后续请求通常会复用同一个 Neo 沙盒；如果沙盒失效，AstrBot 会自动重建。

关于 TTL 与数据持久化的更详细说明，请参考下文的“关于 `Shipyard Neo Sandbox TTL`”与“关于沙盒环境的数据持久化”小节。

## BoxLite 驱动

`BoxLite` 是一个更轻量的本地沙盒驱动，适合只需要 Shell、Python 和文件操作的场景，不提供浏览器或 GUI 专用工具。

### 安装 BoxLite 插件

在配置 `BoxLite` 之前，请先把插件安装到 AstrBot 的插件目录，并保留 `Shipyard` 插件源码在同一目录树下：

```bash
git clone https://github.com/AstrBotDevs/astrbot_sandbox_boxlite.git data/plugins/astrbot_sandbox_boxlite
git clone https://github.com/AstrBotDevs/astrbot_sandbox_shipyard.git data/plugins/astrbot_sandbox_shipyard
```

然后重启 AstrBot，或者在插件管理页重新加载插件。

### 在 AstrBot 中配置 BoxLite

打开 WebUI：

- `配置 -> 普通配置 -> 使用电脑能力`

然后设置：

- `Computer Use Runtime` = `sandbox`
- `沙盒驱动` = `BoxLite`

`BoxLite` 当前没有额外的驱动级配置项，启用插件后即可使用。

然后重启 AstrBot，或在插件管理页重新加载插件。

## 旧方案：Shipyard

以下内容是旧版 `Shipyard` 驱动的部署与配置说明，保留给仍在使用旧部署方案的用户参考。

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
2. 在 `沙盒驱动` 中选择 `Shipyard Neo` 或 `Shipyard`
3. 根据驱动填写对应配置项
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
  - 如果留空，AstrBot 会优先尝试选择能力更完整、且优先带有 `browser` capability 的 profile，失败时再回退到 `python-default`
- `Shipyard Neo Sandbox TTL`
  - 沙盒生命周期上限，默认值为 3600 秒（1 小时）

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

- TTL 表示沙盒生命周期上限
- profile 还会定义一个独立的空闲超时（`idle_timeout`）
- AstrBot 发起能力调用时，通常会刷新空闲超时，而不是直接延长 TTL
- `keepalive` 只会延长空闲超时，不会自动启动新的 session，也不会延长 TTL

换句话说，TTL 更像“这个沙盒最多能活多久”，空闲超时更像“这个沙盒多久没人用就可以收掉”。两者不是一回事，排障时最好分开看。

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
