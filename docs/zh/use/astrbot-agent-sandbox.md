# Agent 沙盒环境

## 这是什么？

AstrBot 内置 AI 支持让 Agent 通过执行代码、读写文件等方式访问电脑环境。这在 AstrBot 内置 AI 中称为 “使用电脑能力”。

目前，“使用电脑能力” 支持两种运行环境：

- 本机环境：让 AstrBot Agent 在 AstrBot **所在的本机环境**中**直接**执行代码和文件操作，**直接**访问本机环境内的文件和命令。利用 macOS 的 `Seatbelt` 或 Linux 的 `bubblewrap(bwrap)` 技术，可以在本机环境中为 AstrBot Agent 提供**受限的文件访问和执行能力**，以保护本机环境的安全性，限制机器人的不同用户使用 AstrBot Agent 时的文件访问范围和联网权限，获得一定的安全性保证。
- 第三方沙箱环境：让 AstrBot Agent 在**独立的环境**中执行代码和文件操作，避免直接访问宿主机或 AstrBot 容器内的文件和命令。由于是独立环境，因此可以直接限制机器人的不同用户使用 AstrBot Agent 时的文件访问范围和联网权限，获得更高的安全性保证。由于是独立的环境，第三方沙箱环境通常也需要额外部署和配置，并对机器性能有更高要求。

您可以在 `配置文件 -> AI -> 能力 -> 使用电脑能力` 中选择 “运行环境” 为 “本机环境” 或者 “第三方沙箱环境”。

如果选择“本机环境”，AstrBot 会尝试在本机环境中启用隔离能力。隔离能力的可用性取决于操作系统、内核、账户权限和系统安全策略等因素。请参见下文的 [本机环境](#local-environment) 章节。

如果选择“第三方沙箱环境”，还需要选择对应的“沙箱环境驱动器”，并填写连接地址、访问令牌等配置。相见下文的 [第三方沙箱环境](#third-party-sandbox-environment) 章节。

## 本机环境 {#local-environment}

在 `配置文件 -> AI -> 能力 -> 使用电脑能力` 中，将“运行环境”设为“本机环境”（`local`）。

本质上，AstrBot 会通过提供给 Agent 一系列工具（Shell、Python、文件工具等）来让 Agent 访问本机环境。

> [!NOTE]
> 如果您通过 Docker 运行 AstrBot，此处的“本机环境”指的是 AstrBot Docker 容器内的 Linux 环境，而不是宿主机的环境。Docker 容器内的文件访问范围和联网权限仍然受限于 Docker 容器的配置。

具体的权限支持按普通成员和管理员分别设置，以矩阵的形式展示，见下图。

![本地权限策略矩阵](./images/config-local-permissions-zh.png)

当勾选 “允许执行代码” 时，AstrBot 会为 Agent 提供 `astrbot_execute_shell` 和 `astrbot_execute_python` 两个工具，以让 Agent 在本机环境中执行 Shell 和 Python 代码。

当勾选 “允许联网” 时，AstrBot 会让 Agent 在执行 Shell/Python 时可以访问网络；否则，Agent 执行 Shell/Python 时会被限制网络访问。

> [!TIP]
> 这里的 “允许联网” 不是指 [网页搜索](/use/websearch) 的搜索功能，而是指 Agent 在执行 Shell/Python 时是否可以通过类似 `curl`, `wget` 等工具访问网络。

对于 “文件访问范围”，分为 “关闭”、“工作区” 和 “整个环境” 三种：

- **关闭**：Agent 无法访问任何文件，文件工具不可用。
- **工作区**：Agent 只能访问对应用户会话（按 UMO 来划分）的以下目录：
  - 工作区目录（在 `data/workspaces/<umo>/` 下）【**读写**】
  - AstrBot 的临时目录（`data/temp/`）【**读写**】
  - 系统临时目录（`<系统临时目录>/.astrbot/`）【**读写**】
  - AstrBot 提供给 Agent 的的技能（Skills）目录 (`data/skills/`) 【普通成员**只读**，管理员**读写**】
  - AstrBot 插件提供的技能（Skills）目录 (`data/plugins/<插件名>/skills/`) 【**只读**】
  - AstrBot 内置插件提供的技能（Skills）目录 (`<AstrBot 运行安装目录>/builtin_stars/<插件名>/skills/`) 【**只读**】
- **整个环境**：Agent 可以访问本机环境内的**所有文件**，文件工具可以在整个环境中操作。

AstrBot 为 Agent 提供的文件工具包括 `astrbot_file_read_tool`, `astrbot_file_write_tool`, `astrbot_file_edit_tool` 和 `astrbot_grep_tool`，分别对应文件的读取、写入、编辑和搜索功能。Agent 可以通过这些工具访问本机环境内的文件。

以下是上述权限矩阵的一些逻辑上的限制：

- 当不勾选 “允许执行代码” 时，无法勾选 “允许联网”，因为**联网权限只在执行代码时生效**。
- 当“文件访问范围”选择“关闭”时，无法勾选 “允许执行代码” 和 “允许联网”，因为**执行代码和联网权限都需要文件访问权限**。

如果您的环境**未满足本机隔离的要求**（如 Windows 系统暂不支持本地隔离、Linux 系统未安装 bubblewrap、macOS 系统未安装 Seatbelt 等），您会看到界面上没有显示 “允许联网” 选项，并且只能配置以下权限组合：

- 文件访问范围：关闭，允许执行代码：否
- 文件访问范围：工作区，允许执行代码：否
- 文件访问范围：整个环境，允许执行代码：否
- 文件访问范围：整个环境，允许执行代码：是

如果您发现您的环境未满足本机隔离的要求，您可以根据您的系统和环境参考下方的文档阅读，了解如何安装和配置。

### macOS 用户 {#local-macos}

Seatbelt 是 macOS 的内置沙箱机制。AstrBot 在 macOS 上使用 `/usr/bin/sandbox-exec` 来调用 Seatbelt，从而限制 Agent 的文件访问范围和联网权限。macOS 通常自带 `/usr/bin/sandbox-exec`。

1. 在运行 AstrBot 的 Mac 上，确认系统工具存在：

   ```bash
   ls -l /usr/bin/sandbox-exec
   ```

2. 检查系统是否允许启动该工具：

   ```bash
   /usr/bin/sandbox-exec -p '(version 1) (allow default)' /usr/bin/true
   ```

   退出码为 `0` 表示这个简单检查通过；AstrBot 启动时还会用实际的工作区限制再检查一次。

如果系统没有提供该工具，或当前系统策略不允许使用，可以改为使用[第三方沙箱环境](#third-party-sandbox-environment)。

如果 AstrBot 运行在 Mac 上的 Docker 容器中，请使用下面的 [Docker 用户](#local-docker)步骤。宿主机上的 Seatbelt 不会直接用于 Linux 容器内的进程。

### Linux 用户 {#local-linux}

[bubblewrap](https://github.com/containers/bubblewrap) 是 Linux 上的用户空间沙箱工具。

检查是否安装 bubblewrap 并且可用：

```bash
command -v bwrap
bwrap --unshare-all --ro-bind / / --proc /proc --dev /dev /bin/sh -c 'echo "AstrBot is good to go!"'
```

如果正常输出 `AstrBot is good to go!`，说明 bubblewrap 安装成功且可用。

如果没有安装 bubblewrap，可以按发行版安装：

::: code-group

```bash [Debian / Ubuntu]
sudo apt update
sudo apt install bubblewrap
```

```bash [Fedora]
sudo dnf install bubblewrap
```

```bash [Arch Linux]
sudo pacman -S bubblewrap
```

:::

如果启动失败：

- **找不到 `bwrap`**：检查是否装在运行 AstrBot 的同一环境，以及进程启动时的 `PATH`。
- **`Operation not permitted` 或用户命名空间错误**：检查用户命名空间限制、AppArmor 和其他系统安全策略。可通过 `sysctl user.max_user_namespaces` 查看命名空间数量上限，通过 `sudo journalctl -k` 查看相关内核日志。
- **AppArmor 拒绝**：按发行版要求为实际运行环境设置允许创建用户命名空间的策略。不要仅为通过检查而关闭整台机器的安全策略。
- **容器部署**：继续阅读 [Docker 用户](#local-docker)，宿主机安装 `bwrap` 不能替代容器内安装。

修复后重启 AstrBot。是否能使用工作区执行和联网控制，以 AstrBot 的启动检查结果为准，如果发现权限矩阵中出现了 `允许联网` 选项则说明本地隔离已成功启用。

### Docker 用户 {#local-docker}

AstrBot 的 Docker 镜像本质上是一个 Linux 容器。

Docker 已提供容器级的隔离。在容器内，AstrBot 默认只能访问容器内的文件和挂载的卷，无法访问宿主机的文件系统。容器内的网络访问也受 Docker 网络配置限制。本地隔离是在容器内通过 bubblewrap 进一步限制**工作区文件访问和执行时联网**。如果只需要访问容器内和挂载的文件，可以继续使用“整个环境”。无需为了使用所有电脑能力而强制开启容器内的 bwrap。

安装 bwrap 只是其中一步。在 Docker 容器中启用本地隔离能力的步骤**相对复杂**，**默认 Docker 部署不一定能启动它**，因为容器还受到宿主机的用户命名空间配置、seccomp、AppArmor 和容器权限限制。因此，如果需要隔离执行，建议使用 [第三方沙箱环境](#third-party-sandbox-environment)。如果仍需要在 Docker 容器中启用本地隔离，请自行参考网络上的资源，给容器配置 `seccomp` 等安全策略，允许容器内的 bwrap 创建用户命名空间。

### Windows 用户 {#local-windows}

目前 Windows 系统暂不支持本机隔离能力。您可以选择使用 [第三方沙箱环境](#third-party-sandbox-environment)。

## 第三方沙箱环境 {#third-party-sandbox-environment}

第三方沙箱环境是 AstrBot 提供的一种可选能力。它可以让 Agent 在**独立的环境**中执行代码和文件操作，避免直接访问宿主机或 AstrBot 容器内的文件和命令。目前支持的第三方沙箱环境驱动器包括：

- **Shipyard Neo**：目前推荐使用的沙箱环境驱动器。它由 Bay、Ship、Gull 三部分组成，分别负责控制面 API、Python/Shell/文件系统能力和浏览器自动化能力。
- **CUA**：面向电脑使用（Computer Use）的沙盒运行时。它可以直接创建一个 Linux、macOS、Windows、Android 等不同类型的沙盒，并暴露 Shell、截图、鼠标、键盘、文件系统等接口。
- **Shipyard**：旧版沙箱环境驱动器，仍然保留，供兼容旧部署方案时参考。它由 Bay、Ship 两部分组成，分别负责控制面 API 和 Python/Shell/文件系统能力。

> [!TIP]
> 第三方沙箱能力仍处于技术预览阶段。遇到问题可在 [GitHub](https://github.com/AstrBotDevs/AstrBot/issues) 提交 issue。

<span id="配置-astrbot-使用沙盒环境"></span>

### 启用沙盒环境 {#启用沙盒环境}

1. 在 `配置文件 -> AI -> 能力 -> 使用电脑能力` 中，将“运行环境”设为“第三方沙箱环境”（`sandbox`）。
2. 选择“沙箱环境驱动器”：Shipyard Neo、Shipyard 或 CUA。
3. **按下面对应驱动器的说明部署服务**，填写连接地址、令牌或镜像等配置。
4. 点击页面右下角“保存”按钮，再测试是否可用。

### 性能要求 {#性能要求}

资源限制由驱动器及 profile 配置决定，不同方案不使用统一的 CPU 和内存上限。建议宿主机至少有 4 个 CPU 和 8 GB 内存。实际使用情况很大程度上取决于机器人的用户数、用户的使用频率和使用场景。

<span id="推荐-使用-shipyard-neo"></span>

### Shipyard Neo {#shipyard-neo}

其中，`Shipyard Neo` 是当前默认驱动器。它由 Bay、Ship、Gull 三部分组成：

- **Bay**：控制面 API，负责创建和管理 sandbox
- **Ship**：负责 Python / Shell / 文件系统能力
- **Gull**：负责浏览器自动化能力

对于 `Shipyard Neo`，工作区根目录固定为 `/workspace`。在 AstrBot 中调用文件系统工具时，应当传入**相对于工作区根目录**的路径，例如 `reports/result.txt`，而不是 `/workspace/reports/result.txt`。

> [!TIP]
> `Shipyard Neo` 下浏览器能力并不是所有 profile 都有。只有 profile 支持 `browser` capability 时，AstrBot 才会挂载浏览器相关工具。典型 profile 如 `browser-python`。

#### 单独部署 Shipyard Neo

如果您准备长期使用 `Shipyard Neo`，更推荐将它**单独部署在一台资源更充足的机器上**，例如您的 homelab、局域网服务器，或独立云主机，然后再让 AstrBot 远程接入 Bay。

原因是：`Shipyard Neo` 在启用浏览器能力时需要运行较重的浏览器运行时。**对于资源紧张的云服务器**，把 AstrBot 和 `Shipyard Neo` 部署在同一台机器上，通常会让 CPU 和内存压力都比较大，稳定性和体验都不理想。

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

#### 参考：`config.yaml` 完整示例（附说明）

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

#### 关于 Shipyard Neo 的复用与持久化

`Shipyard Neo` 中有几个重要概念：

- **Sandbox**：对外稳定可见的资源单元
- **Session**：实际运行中的容器会话，可被停止或重建
- **Cargo**：持久化工作区卷，挂载到 `/workspace`

对 AstrBot 而言，当前会按请求的 `session_id` 维度缓存沙箱 booter；在主 Agent 默认流程下，这个 `session_id` 通常等于消息会话标识 `unified_msg_origin`。因此，同一消息会话的后续请求通常会继续复用同一个 Neo sandbox；如果沙箱失效，则会自动重建。

关于 TTL 与数据持久化的更详细说明，请参考下文的“关于 `Shipyard Neo Sandbox TTL`”与“关于沙盒环境的数据持久化”小节。

#### 配置 Shipyard Neo

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
  - sandbox 生命周期上限，默认值为 3600 秒（1 小时）

#### 关于 `Shipyard Neo Sandbox TTL`

在 `Shipyard Neo` 中：

- TTL 表示 sandbox 生命周期上限
- profile 还会定义一个独立的空闲超时（`idle_timeout`）
- AstrBot 发起能力调用时，通常会刷新空闲超时，而不是直接延长 TTL
- `keepalive` 只会延长空闲超时，不会自动启动新的 session，也不会延长 TTL

<span id="关于沙盒环境的数据持久化"></span>

#### 数据持久化 {#shipyard-neo-persistence}

`Shipyard Neo` 的工作区根目录固定为 `/workspace`。

其持久化由 Cargo 提供：

- 文件系统数据保存在 Cargo 中，并挂载到 `/workspace`
- 即使底层 Session 被停止或重建，Cargo 中的数据通常仍可保留
- 对于带浏览器能力的 profile，浏览器状态也可能会一起持久化，例如 `/workspace/.browser/profile/`

### CUA {#cua}

[CUA](https://github.com/trycua/cua) 是一个面向电脑使用（Computer Use）的沙盒运行时。

Agent 可以在 CUA sandbox 中使用多种能力，请见下表：

| 能力 | 为 Agent 提供的工具名称 | 用途 |
| --- | --- | --- |
| Shell 执行 | `astrbot_execute_shell` | 执行命令、启动程序 |
| Python 执行 | `astrbot_execute_ipython` | 执行 Python 代码 |
| 文件读取 | `astrbot_file_read_tool` | 读取文件 |
| 文件写入 | `astrbot_file_write_tool` | 创建或覆盖文件 |
| 文件编辑 | `astrbot_file_edit_tool` | 替换文件中的指定文本 |
| 文件搜索 | `astrbot_grep_tool` | 按模式搜索文件内容 |
| 文件上传 | `astrbot_upload_file` | 将 AstrBot 所在环境的文件上传到沙箱 |
| 文件下载 | `astrbot_download_file` | 从沙箱下载文件，可发送给用户 |
| 桌面截图 | `astrbot_cua_screenshot` | 获取截图，供模型查看或发送给用户 |
| 鼠标点击 | `astrbot_cua_mouse_click` | 按坐标点击，支持指定鼠标按键 |
| 键盘输入 | `astrbot_cua_keyboard_type` | 向当前焦点输入文本 |

> [!WARNING]
> CUA 是可选运行时，AstrBot 默认安装不会强制安装它。如果您选择了 `CUA` 但当前 AstrBot 的 Python 环境没有安装 `cua` 包，启动沙盒时会提示安装缺失。

#### 何时选择 CUA

建议在以下场景选择 `CUA`：

- 需要桌面截图、鼠标点击、键盘输入等 GUI 自动化能力。
- 需要测试不同 OS 镜像中的行为，例如 Linux、Windows、Android。
- 已经在本机或云端部署好 CUA 运行环境。

如果只是需要稳定的 Python/Shell/文件系统沙盒，且不需要桌面 GUI 操作，通常优先选择 `Shipyard Neo`。它与 AstrBot 的 workspace、Skills 同步和长期运行模式更贴合。

#### 安装 CUA 依赖

您可以在 WebUI 的 “数据与日志” 页的 “日志” 中点击 “安装 Pip 库” 按钮，输入 `cua` 以安装 CUA 依赖。也可以按照下面的方式在 AstrBot 的 Python 环境中安装 CUA。

- 如果您通过源码或虚拟环境运行 AstrBot，请在 AstrBot 使用的 Python 环境中安装 CUA：

  ```bash
  pip install cua
  ```

- 如果您使用 `uv` 管理 AstrBot 环境，可在 AstrBot 项目目录中执行：

  ```bash
  uv pip install cua
  ```

CUA 本身还依赖具体运行方式：

- 本地 Linux 容器通常需要 Docker 可用。
- 本地 Linux/Windows VM 通常需要 QEMU 或 CUA 对应的本地运行时。
- macOS VM 通常依赖 CUA/Lume 相关运行时。
- 云端 CUA 需要可用的 CUA API Key。

具体宿主机要求、镜像支持情况和本地运行时安装方式，请参考 [CUA 官方文档](https://cua.ai/docs)。

#### 在 AstrBot 中配置 CUA

进入 WebUI：

- `配置文件 -> AI -> 能力 -> 使用电脑能力`

然后设置：

- `运行环境`：`sandbox`
- `沙箱环境驱动器`：`CUA`

CUA 相关配置项包括：

- `CUA Image`：要启动的 CUA 镜像。常见值为 `linux`、`macos`、`windows`、`android`。默认 `linux`。
- `CUA OS Type`：镜像的操作系统类型。默认 `linux`。它会影响 AstrBot 对 POSIX Shell fallback 的判断。
- `CUA Sandbox TTL`：沙盒生命周期，单位为秒。默认 `3600`。
- `CUA Telemetry Enabled`：是否启用 CUA 侧遥测。默认关闭。
- `CUA Local Runtime`：是否使用本地运行时。默认开启。关闭后会按 CUA SDK 的云端方式创建沙盒。
- `CUA API Key`：云端 CUA 所需的 API Key。仅在使用云端运行时时填写。

一个最小本地 Linux 容器配置通常是：

```text
Computer Use Runtime = sandbox
沙箱环境驱动器 = CUA
CUA Image = linux
CUA OS Type = linux
CUA Local Runtime = true
CUA Sandbox TTL = 3600
```

如果使用云端 CUA，可改为：

```text
Computer Use Runtime = sandbox
沙箱环境驱动器 = CUA
CUA Image = linux
CUA OS Type = linux
CUA Local Runtime = false
CUA API Key = <your-cua-api-key>
```

> [!WARNING]
> 不要把 CUA API Key 写入公开日志、截图或 issue。

#### 使用 CUA 时的注意事项

- `linux` 镜像通常适合 Shell、Python、文件系统和桌面自动化测试。
- 非 POSIX 镜像（如 `windows`、`android`）不一定支持 `sh`、`cat`、`ls`、`rm`、`base64` 等命令。AstrBot 对需要这些命令的 fallback 操作会返回明确错误。
- 如果需要在 CUA sandbox 中打开浏览器或 GUI 程序，通常应使用 Shell 后台执行，例如显式传入 `background=true`，避免命令阻塞后续工具调用。
- 直接把 sandbox 内的文件路径发送给用户通常不可行。应优先使用 AstrBot 的沙盒下载工具，将文件下载到 AstrBot 临时目录后再发送。
- CUA 与 Shipyard Neo 的 workspace 语义不同。Shipyard Neo 固定使用 `/workspace`；CUA 的工作目录和文件路径取决于镜像与运行时。

<span id="旧方案-shipyard"></span>

### Shipyard（旧方案） {#shipyard}

以下内容为旧版 `Shipyard` 驱动器的部署与配置说明，仍然保留，供兼容旧部署方案时参考。

#### 使用 Docker Compose 部署 AstrBot 和 Shipyard

如果您还没有部署 AstrBot，或者想更换为我们推荐的带沙盒环境的部署方式，推荐使用 Docker Compose 来部署 AstrBot，代码如下：

```bash
git clone https://github.com/AstrBotDevs/AstrBot
cd AstrBot
# 修改 compose-with-shipyard.yml 文件中的环境变量配置，例如 Shipyard 的 access token 等
docker compose -f compose-with-shipyard.yml up -d
docker pull soulter/shipyard-ship:latest
```

这会启动一个包含 AstrBot 主程序和沙盒环境的 Docker Compose 服务。

#### 单独部署 Shipyard

如果您已经部署了 AstrBot，但没有部署沙盒环境，可以单独部署 Shipyard。

代码如下：

```bash
mkdir astrbot-shipyard
cd astrbot-shipyard
wget https://raw.githubusercontent.com/AstrBotDevs/shipyard/refs/heads/main/pkgs/bay/docker-compose.yml -O docker-compose.yml
# Update the access token in docker-compose.yml
docker compose -f docker-compose.yml up -d
docker pull soulter/shipyard-ship:latest
```

部署成功后，上述命令会启动一个 Shipyard 服务，默认监听在 `http://<your-host>:8156`。

> [!TIP]
> 如果您使用 Docker 部署 AstrBot，您也可以修改上面的 Compose 文件，将 Shipyard 的网络与 AstrBot 放在同一个 Docker 网络中，这样就不需要暴露 Shipyard 的端口到宿主机。

#### 配置 Shipyard（旧方案）

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

#### 关于 `Shipyard Ship 存活时间(秒)`

以下说明仅适用于旧版 `Shipyard`：

沙箱环境实例的存活时间定义了每个实例在被销毁之前可以存在的最长时间，这个时间的设置需要根据您的使用场景以及资源来决定。

- 新的会话加入已有的沙箱环境实例时，该实例会自动延长存活时间到这个会话请求的 TTL。
- 当对沙箱环境实例执行操作后，该实例会自动延长存活时间到当前时间加上 TTL。

#### 数据持久化 {#shipyard-persistence}

Shipyard 会给每个会话分配一个工作目录，在 `/home/<会话唯一 ID>` 目录下。

Shipyard 会自动将沙盒环境中的 /home 目录挂载到宿主机的 `${PWD}/data/shipyard/ship_mnt_data` 目录下，当沙盒环境实例被销毁后，如果某个会话继续请求调用沙箱，Shipyard 会重新创建一个新的沙盒环境实例，并将之前持久化的数据重新挂载进去，保证数据的连续性。
