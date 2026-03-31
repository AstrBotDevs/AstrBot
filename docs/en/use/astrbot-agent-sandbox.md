# Agent Sandbox Environment ⛵️

> [!TIP]
> This feature is currently in technical preview and may have some bugs. If you encounter any issues, please submit an issue on [GitHub](https://github.com/AstrBotDevs/AstrBot/issues).

Starting from version `v4.12.0`, AstrBot introduced the Agent sandbox environment to replace the previous code executor functionality. The sandbox environment provides Agents with safer and more flexible code execution and automation capabilities.

![](https://files.astrbot.app/docs/source/images/astrbot-agent-sandbox/image.png)

## Enabling the Sandbox Environment

AstrBot currently supports the following sandbox drivers:

- `Shipyard Neo` (recommended)
- `Shipyard` (legacy option, still supported)

In the current AstrBot console, go to **AI Settings** -> **Agent Computer Use** and select:

- `Computer Use Runtime` = `sandbox`
- `Sandbox Driver` = `Shipyard Neo` or `Shipyard`

`Shipyard Neo` is now the default driver. It consists of Bay, Ship, and Gull:

- **Bay**: the control-plane API responsible for creating and managing sandboxes
- **Ship**: provides Python / Shell / filesystem capabilities
- **Gull**: provides browser automation capabilities

For `Shipyard Neo`, the workspace root is fixed at `/workspace`. When using filesystem tools in AstrBot, you should pass **paths relative to the workspace root**, for example `reports/result.txt`, not `/workspace/reports/result.txt`.

> [!TIP]
> Browser capability is not available in every `Shipyard Neo` profile. AstrBot only mounts browser-related tools when the selected profile supports the `browser` capability. A typical example is `browser-python`.

## Performance Requirements

AstrBot limits each sandbox instance to at most 1 CPU and 512 MB of memory.

We recommend that your host machine have at least 2 CPUs, 4 GB of memory, and swap enabled, so multiple sandbox instances can run more reliably.

## Recommended: Use Shipyard Neo

### Deploy Shipyard Neo Separately (Recommended)

If you plan to use `Shipyard Neo` for the long term, it is generally better to **deploy it separately on a machine with more resources**, such as your homelab, a LAN server, or a dedicated cloud host, and then let AstrBot connect to Bay remotely.

The reason is that `Shipyard Neo` can become fairly resource-heavy when browser capability is enabled, because it needs to run a full browser runtime. On resource-constrained cloud servers, deploying AstrBot and `Shipyard Neo` on the same machine usually puts significant pressure on CPU and memory, which can negatively affect both stability and overall experience.

A basic deployment flow looks like this:

```bash
git clone https://github.com/AstrBotDevs/shipyard-neo
cd shipyard-neo/deploy/docker
# Modify the key settings in config.yaml, such as security.api_key
docker compose up -d
```

After deployment:

- Bay listens on `http://<your-host>:8114` by default
- In the AstrBot console, choose the `Shipyard Neo` driver
- Set `Shipyard Neo API Endpoint` to the corresponding address, for example `http://<your-host>:8114`
- Set `Shipyard Neo Access Token` to the Bay API key; if AstrBot can access Bay's `credentials.json`, you may also leave it empty and let AstrBot auto-discover it

### Reference: Full `config.yaml` Example (with Notes)

If you want to customize the deployment parameters of `Shipyard Neo`, you can refer to the complete example below, adapted from [`deploy/docker/config.yaml`](https://github.com/AstrBotDevs/shipyard-neo/blob/main/deploy/docker/config.yaml). It keeps the default structure and adds explanatory notes to make each option easier to understand.

> [!TIP]
> The minimum required change is `security.api_key`. If you are not sure what the other options do, it is usually best to keep the defaults first and only adjust profiles, resource limits, and warm pool settings as needed.

```yaml
# Bay Production Config - Docker Compose (container_network mode)
#
# Bay runs inside Docker and communicates with Ship/Gull containers
# through a shared Docker network.
# In this mode, sandbox containers do not need to expose ports to the host.
#
# At minimum, update:
#   1. security.api_key  — set a strong random secret

server:
  # Bay API listen address
  host: "0.0.0.0"
  # Bay API listen port
  port: 8114

database:
  # SQLite is the default for single-node deployment.
  # For multi-instance / HA deployments, you can switch to PostgreSQL, for example:
  # url: "postgresql+asyncpg://user:pass@db-host:5432/bay"
  url: "sqlite+aiosqlite:///./data/bay.db"
  echo: false

driver:
  # Docker is the default driver
  type: docker

  # Whether to pull images when creating new sandboxes.
  # In production, always is usually recommended so you get the latest images.
  image_pull_policy: always

  docker:
    # Docker Socket endpoint
    socket: "unix:///var/run/docker.sock"

    # When Bay, Ship, and Gull all run in containers,
    # container_network is recommended for direct container-network communication.
    connect_mode: container_network

    # Shared network name; must match the network in docker-compose.yaml
    network: "bay-network"

    # Whether to expose sandbox container ports to the host.
    # Disabling this is generally recommended in production.
    publish_ports: false
    host_port: null

cargo:
  # Cargo storage root path on the Bay side
  root_path: "/var/lib/bay/cargos"
  # Default workspace size limit (MB)
  default_size_limit_mb: 1024
  # Path mounted inside the sandbox. This is AstrBot/Neo's workspace root.
  mount_path: "/workspace"

security:
  # Required: set a strong random secret, for example openssl rand -hex 32
  api_key: "CHANGE-ME"
  # Whether anonymous access is allowed. false is recommended for production.
  allow_anonymous: false

# Proxy environment variable injection for containers.
# When enabled, Bay injects HTTP(S)_PROXY and NO_PROXY into sandbox containers.
proxy:
  enabled: false
  # http_proxy: "http://proxy.example.com:7890"
  # https_proxy: "http://proxy.example.com:7890"
  # no_proxy: "my-internal.service"

# Warm Pool: keep standby sandboxes pre-warmed to reduce cold-start latency.
# When a user creates a sandbox, Bay will first try to claim a pre-warmed instance.
warm_pool:
  enabled: true
  # Number of warmup queue workers
  warmup_queue_workers: 2
  # Maximum warmup queue size
  warmup_queue_max_size: 256
  # Policy when the queue is full
  warmup_queue_drop_policy: "drop_newest"
  # Useful threshold for operational alerts
  warmup_queue_drop_alert_threshold: 50
  # Warm pool maintenance interval (seconds)
  interval_seconds: 30
  # Whether to start warm-pool maintenance when Bay starts
  run_on_startup: true

profiles:
  # ── Standard Python sandbox ────────────────────────
  - id: python-default
    description: "Standard Python sandbox with filesystem and shell access"
    image: "ghcr.io/astrbotdevs/shipyard-neo-ship:latest"
    runtime_type: ship
    runtime_port: 8123
    resources:
      cpus: 1.0
      memory: "1g"
    capabilities:
      - filesystem  # includes upload/download
      - shell
      - python
    # Idle timeout (seconds)
    idle_timeout: 1800
    # Keep 1 warm instance ready
    warm_pool_size: 1
    env: {}
    # Optional profile-level proxy override
    # proxy:
    #   enabled: false

  # ── Data-science sandbox (more resources) ──────────
  - id: python-data
    description: "Data science sandbox with extra CPU and memory"
    image: "ghcr.io/astrbotdevs/shipyard-neo-ship:latest"
    runtime_type: ship
    runtime_port: 8123
    resources:
      cpus: 2.0
      memory: "4g"
    capabilities:
      - filesystem  # includes upload/download
      - shell
      - python
    idle_timeout: 1800
    warm_pool_size: 1
    env: {}

  # ── Browser + Python multi-container sandbox ───────
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
          - filesystem  # includes upload/download
        # These capabilities are primarily handled by the ship container
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
  # Automatic GC is recommended in production
  enabled: true
  run_on_startup: true
  # GC interval (seconds)
  interval_seconds: 300

  # Must be unique in multi-instance deployments
  instance_id: "bay-prod"

  idle_session:
    enabled: true
  expired_sandbox:
    enabled: true
  orphan_cargo:
    enabled: true
  orphan_container:
    # Recommended in production to clean up leaked containers
    enabled: true
```

A practical way to think about this file:

- **Minimum required change**: `security.api_key`
- **Most commonly adjusted options**: resource limits, `warm_pool_size`, and `idle_timeout` under `profiles`
- **If you need browser capability**: use or customize the `browser-python` profile
- **If you want to reduce cold-start time**: keep `warm_pool.enabled: true` and increase `warm_pool_size` for frequently used profiles
- **If resources are limited**: reduce `warm_pool_size`, or even disable `warm_pool`
- **If outbound proxy access is needed**: configure the top-level `proxy`, or override it per profile

### About Shipyard Neo Reuse and Persistence

`Shipyard Neo` has several important concepts:

- **Sandbox**: the stable, externally visible resource unit
- **Session**: the actual running container session, which may be stopped or rebuilt
- **Cargo**: the persistent workspace volume mounted at `/workspace`

From AstrBot's perspective, the current implementation caches the sandbox booter by request `session_id`; in the default main-agent flow, this `session_id` usually equals the message-session identifier `unified_msg_origin`. As a result, follow-up requests from the same message session will usually continue using the same Neo sandbox; if the sandbox becomes unavailable, it will be rebuilt automatically.

For more detailed explanations of TTL and persistence behavior, see the later sections on “`Shipyard Neo Sandbox TTL`” and “Data Persistence in the Sandbox Environment”.

## Legacy Option: Shipyard

The following content describes the older `Shipyard` driver. It is kept for compatibility with existing legacy deployments.

### Deploying AstrBot and Shipyard with Docker Compose

If you have not deployed AstrBot yet, or want to use the older recommended deployment method with sandbox support, you can still deploy AstrBot with Docker Compose using the following commands:

```bash
git clone https://github.com/AstrBotDevs/AstrBot
cd AstrBot
# Modify the environment variables in compose-with-shipyard.yml, such as the Shipyard access token
docker compose -f compose-with-shipyard.yml up -d
docker pull soulter/shipyard-ship:latest
```

This starts a Docker Compose stack containing the AstrBot main program and the sandbox environment.

### Deploying Shipyard Separately

If AstrBot is already deployed but the sandbox environment is not, you can deploy Shipyard separately.

```bash
mkdir astrbot-shipyard
cd astrbot-shipyard
wget https://raw.githubusercontent.com/AstrBotDevs/shipyard/refs/heads/main/pkgs/bay/docker-compose.yml -O docker-compose.yml
# Modify the environment variables in docker-compose.yml, such as the Shipyard access token
docker compose -f docker-compose.yml up -d
docker pull soulter/shipyard-ship:latest
```

After successful deployment, Shipyard listens on `http://<your-host>:8156` by default.

> [!TIP]
> If you deploy AstrBot with Docker, you can also place Shipyard on the same Docker network as AstrBot so you do not need to expose Shipyard's port to the host.

## Configuring AstrBot to Use the Sandbox Environment

> [!TIP]
> Please make sure your AstrBot version is `v4.12.0` or later.

In the AstrBot console, go to **AI Settings** -> **Agent Computer Use**.

1. Set `Computer Use Runtime` to `sandbox`
2. Select `Shipyard Neo` or `Shipyard` as the sandbox driver
3. Fill in the corresponding configuration values for the selected driver
4. Click **Save**

### Configuring Shipyard Neo

If you choose `Shipyard Neo`, the main configuration items are:

- `Shipyard Neo API Endpoint`
  - For a separated deployment, use the actual address, such as `http://<your-host>:8114`
- `Shipyard Neo Access Token`
  - Fill in the Bay API key
  - If AstrBot can access Bay's `credentials.json`, you may leave it empty and let AstrBot auto-discover it
- `Shipyard Neo Profile`
  - For example `python-default` or `browser-python`
  - If not explicitly specified, AstrBot will try to choose a profile with richer capabilities, preferring one that includes the `browser` capability, and fall back to `python-default` if needed
- `Shipyard Neo Sandbox TTL`
  - The upper lifetime limit of the sandbox, defaulting to 3600 seconds (1 hour)

### Configuring Shipyard (Legacy)

If you choose the legacy `Shipyard` driver, the relevant configuration items are:

- `Shipyard API Endpoint`
  - If you use the Docker Compose deployment above, set it to `http://shipyard:8156`
  - If Shipyard is deployed separately, use the corresponding address, such as `http://<your-host>:8156`
- `Shipyard Access Token`
  - Fill in the access token you configured when deploying Shipyard
- `Shipyard Ship Lifetime (seconds)`
  - Defines the lifetime of each sandbox instance, default 3600 seconds (1 hour)
- `Shipyard Ship Session Reuse Limit`
  - Defines the maximum number of sessions that can reuse the same sandbox instance, default 10

## About `Shipyard Neo Sandbox TTL`

In `Shipyard Neo`:

- TTL represents the upper lifetime bound of the sandbox
- The selected profile also defines a separate idle timeout (`idle_timeout`)
- Capability calls from AstrBot usually refresh the idle timeout, rather than directly extending the TTL
- `keepalive` only extends the idle timeout; it does not automatically start a new session and does not extend the TTL

## About `Shipyard Ship Lifetime (seconds)`

The following explanation applies only to the legacy `Shipyard` driver:

The lifetime of a sandbox instance defines the maximum amount of time that instance can exist before being destroyed. This value should be chosen according to your use case and available resources.

- When a new session joins an existing sandbox instance, the instance automatically extends its lifetime to the TTL requested by that session
- When an operation is performed on a sandbox instance, the instance automatically extends its lifetime to the current time plus TTL

## About Data Persistence in the Sandbox Environment

### Shipyard Neo

The workspace root of `Shipyard Neo` is fixed at `/workspace`.

Persistence is provided by Cargo:

- Filesystem data is stored in Cargo and mounted at `/workspace`
- Even if the underlying Session is stopped or rebuilt, the data in Cargo is usually retained
- For profiles with browser capability, browser state may also be persisted together, for example under `/workspace/.browser/profile/`

### Shipyard (Legacy)

Shipyard allocates a working directory for each session under `/home/<unique session ID>`.

Shipyard automatically mounts the `/home` directory from the sandbox environment to `${PWD}/data/shipyard/ship_mnt_data` on the host. When a sandbox instance is destroyed and a session later requests the sandbox again, Shipyard recreates a new instance and remounts the previously persisted data to preserve continuity.

## Other Community Plugins

### luosheng520qaq/astrobot_plugin_code_executor

If your resources are limited and you do not want to use the sandbox environment for code execution, you can try the [astrobot_plugin_code_executor](https://github.com/luosheng520qaq/astrobot_plugin_code_executor) plugin developed by luosheng520qaq. This plugin executes code directly on the host machine. It tries to improve safety as much as possible, but you should still pay close attention to code-execution security.
