# 从源码部署 AstrBot

> [!IMPORTANT]
> 当前 fork 不发布独立 PyPI 包或预构建 Dashboard Release。要运行与本仓库一致的后端和 WebUI，需要从当前 checkout 安装依赖并本地构建 Dashboard。

## 前置条件

- Git
- `uv`
- Node.js 26.5.0
- pnpm 11.21.0

Python 包要求为 3.14+；仓库的 `.python-version` 固定为 3.14.6，`uv` 可以在本机缺少该版本时按配置自动下载。

## 克隆仓库

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
```

默认分支跟踪当前开发状态。部署前请先阅读最新 `changelogs/`，并自行选择要固定的 commit；当前 fork 尚未建立可依赖的发布 tag 序列。

## 安装后端依赖

```bash
uv sync --locked
```

`--locked` 会拒绝在安装时静默改写 `uv.lock`，确保使用仓库已经审核的依赖解析结果。

## 构建当前 Dashboard

```bash
cd dashboard
pnpm install --frozen-lockfile
pnpm build
cd ..
uv run python scripts/sync_dashboard_dist.py
```

不要跳过这一步。`astrbot init`、`astrbot run` 和根启动入口都不会下载 Dashboard；上游静态资源与当前 fork 的 FastAPI 路由和前端功能不兼容。

## 可选：安装本地文转图浏览器

只有启用本地文转图或插件 HTML 渲染时才需要执行一次：

```bash
uv run astrbot install-browser
```

## 启动

```bash
uv run main.py
```

依赖已同步后，可以用下面的命令跳过每次启动前的依赖检查：

```bash
uv run --no-sync main.py
```

首次启动会创建 `data/`、生成随机 WebUI 初始密码，并在日志中打印登录信息。默认用户名为 `astrbot`，WebUI 仅监听 `127.0.0.1:6185`。

## 远程访问

只把浏览器地址中的 `localhost` 换成服务器 IP 并不会开放服务。默认 loopback 监听是安全措施；需要远程访问时，必须显式修改 `data/cmd_config.json`：

```json
{
  "dashboard": {
    "host": "0.0.0.0",
    "port": 6185
  }
}
```

也可以在启动进程时临时覆盖：

::: code-group

```bash [Linux / macOS]
ASTRBOT_DASHBOARD_HOST=0.0.0.0 uv run main.py
```

```powershell [Windows PowerShell]
$env:ASTRBOT_DASHBOARD_HOST = '0.0.0.0'
uv run main.py
```

:::

`0.0.0.0` 会监听所有 IPv4 网卡。请同时配置主机防火墙，并优先通过带 HTTPS 的可信反向代理对外提供服务。只有当前置代理会覆盖客户端提交的 `X-Forwarded-For`/`X-Real-IP` 时，才开启 `dashboard.trust_proxy_headers`。

## 更新 checkout

先停止 AstrBot，再执行：

```bash
git pull --ff-only
uv sync --locked
cd dashboard
pnpm install --frozen-lockfile
pnpm build
cd ..
uv run python scripts/sync_dashboard_dist.py
```

更新前备份 `data/`，并阅读跨越版本的 changelog。不要使用 `uv tool upgrade astrbot` 更新此 fork；该命令对应上游 PyPI 包。
