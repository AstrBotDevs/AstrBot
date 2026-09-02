# 常见问题

## WebUI 与账号

### 打开 WebUI 显示 404 或空白页

当前 fork 不发布独立的预构建 Dashboard 资源。源码部署需要使用当前 checkout 构建前端并同步到后端静态目录：

```bash
cd dashboard
pnpm install --frozen-lockfile
pnpm build
cd ..
uv run python scripts/sync_dashboard_dist.py
```

然后重启 AstrBot，并用 `Ctrl+Shift+R` / `Ctrl+F5`（macOS 使用 `Cmd+Shift+R`）强制刷新。不要下载上游版本的 Dashboard 覆盖当前 fork；API 和页面可能不匹配。

### 首次登录账号和密码是什么

默认用户名是 `astrbot`。首次启动会生成随机强密码并打印在启动日志中：

```text
➜  Initial username: astrbot
➜  Initial password: <本次启动生成的密码>
➜  Change it after logging in
```

不存在固定的默认密码。使用初始密码登录后应立即修改；不要把包含密码的启动日志公开。

### 忘记 WebUI 密码

在源码 checkout 中执行：

```bash
uv run astrbot run --reset-password
```

也可以使用：

```bash
uv run main.py --reset-password
```

重启过程会生成新密码并打印到日志。不要手工删除 `pbkdf2_password`、`jwt_secret` 或向配置文件写入明文密码。

### 为什么从服务器 IP 无法访问

WebUI 默认只监听 `127.0.0.1:6185`。把浏览器中的 `localhost` 替换为服务器 IP 并不会改变监听地址。

临时允许远程连接：

::: code-group

```bash [Linux / macOS]
ASTRBOT_DASHBOARD_HOST=0.0.0.0 uv run main.py
```

```powershell [Windows PowerShell]
$env:ASTRBOT_DASHBOARD_HOST = '0.0.0.0'
uv run main.py
```

:::

也可以把 `data/cmd_config.json` 中的 `dashboard.host` 改为 `0.0.0.0`。这会监听所有 IPv4 接口，必须同时配置主机防火墙，并优先通过受信任的 HTTPS 反向代理暴露。只有代理会覆盖客户端伪造的转发头时才启用 `dashboard.trust_proxy_headers`。

Docker 发布 `6185` 端口也需要这个监听覆盖，详见 [Docker 部署](./deploy/astrbot/docker)。

## 运行目录与更新

### `data` 目录在哪里

运行根目录默认是启动 AstrBot 时的当前工作目录，运行数据位于 `<root>/data`。源码仓库根目录执行 `uv run main.py` 时通常就是 `AstrBot/data`。

设置 `ASTRBOT_ROOT` 后，数据位于 `$ASTRBOT_ROOT/data`。配置、SQLite 数据库、插件、Skills、知识库、临时文件和备份都可能在这里，升级前应整体备份。步骤见 [备份、恢复与升级演练](./deploy/astrbot/backup)。

当前 fork 不提供独立 Desktop 或 Launcher 部署；外部启动器的目录布局不属于本仓库保证范围。

### 如何更新源码部署

先停止 AstrBot 并备份 `data/`，然后：

```bash
git pull --ff-only
uv sync --locked
cd dashboard
pnpm install --frozen-lockfile
pnpm build
cd ..
uv run python scripts/sync_dashboard_dist.py
```

更新前阅读 `changelogs/` 中跨越的版本和当前未发布提交。不要使用 `uv tool upgrade astrbot` 更新本 fork；PyPI 上的 `astrbot` 是上游包。本 fork 不提供 Dashboard 一键 Core 更新。

### 升级到 4.27.5 后主库无法启动

4.27.5 以当前 SQLModel 表重建主 SQLite schema，不做旧库 `ALTER TABLE` 或数据迁移。`create_all` 只创建缺失表；已有 `data_v4.db` 上的残留列和索引会留在原地。

停进程并备份 `data/` 后，删除 runtime root 下的 `data/data_v4.db`、`data/data_v4.db-wal` 和 `data/data_v4.db-shm`，再启动。会话、长期记忆、授权绑定和 API Key 等主库记录不会从旧文件迁出。`data/knowledge_base/` 不受这次切库影响。架构说明见[项目架构](/dev/architecture#主-sqlite-库)。

## Agent、权限与输出

### 群聊中机器人不回复

为避免群消息泛滥，普通消息需要满足配置档的 `llm_access.group` 策略（默认是 `prefix`，`llm_access.prefixes` 默认值为 `["/"]`）。如需把“回复机器人”作为额外触发条件，请启用 `llm_access.reply_to_bot`。同时检查：

- 当前配置档是否绑定到该消息会话；
- 平台和 Provider 是否启用；
- 白名单、管理员绕过和限流；
- `ignore_at_all`、机器人自身消息过滤及平台权限。

### 管理员指令提示无权限

群聊仍需要通过 Dashboard [权限页面](/use/webui#账户与权限)或 `/admin grant` 授予当前会话的 `session_admin`。这不是全局 operator。私聊对端已经是当前会话的 `session_owner`，无需预先绑定 `session_admin` 即可 `/conversation reset`。配置档可能按平台、群或私聊分别绑定，修改默认配置档不一定影响当前会话。使用 `/session info` 可查看当前用户 ID。

### 以前的 `/plugin ls`、`/reset` 等指令无效

内置指令已改为完整 CLI 路径，例如 `/plugin list`、`/conversation reset`。旧短名不是别名，不会匹配。用 `/help` 查看当前启用的声明名；Dashboard 里手动重命名过的名字仍然有效。详见[内置指令](/use/command)。

### 如何使用电脑能力

在 **配置 → Agent Computer Use** 中选择：

- `local`：直接操作 AstrBot 主机，只适合可信环境；
- `sandbox`：使用配置的 Shipyard Neo 或 CUA 沙箱；
- `none`：关闭，默认值。

电脑能力现在按工具动作经过统一授权服务检查（例如 `tool.computer_use`、`tool.local_exec` 和 `tool.file_write`）。已认证 Dashboard 驱动的 WebChat 在当前 session/config 内，经 WebChat 一次性 step-up 后可使用实例级高风险工具；全局控制面仍 Dashboard-only，匿名 WebChat、IM、插件、Agent 和 API Key 不会继承 Dashboard 角色。沙箱只提供运行隔离，不会改变授权策略。详见 [使用电脑能力](./use/computer) 和 [Agent 沙箱](./use/astrbot-agent-sandbox)。

### T2I 中文乱码

在当前启用的本地 T2I 模板 CSS 中配置已安装的中文字体，例如：

```css
font-family: 'Maple Mono', 'Noto Sans CJK SC', sans-serif;
```

可参考 [Maple Mono](https://github.com/subframe7536/maple-font)。容器内也必须实际安装对应字体。

### Provider 返回空内容

依次检查：

1. API Key 权限、余额和限额；
2. API Base 与模型 ID 是否完全匹配；
3. 模型是否支持当前图片、工具调用或 reasoning 格式；
4. 代理、DNS、TLS 和请求超时；
5. Provider 测试结果和服务端原始错误；
6. fallback 模型是否来自真正独立的端点。

不要用关闭 TLS 验证的方式“修复”连接。必要时重置会话或降低历史轮数，并参考 [上下文压缩](./use/context-compress)。

### 市场插件安装后加载失败

Dashboard 默认市场源是上游 `cloud.astrbot.app` 市场 JSON（失败后回退到 `AstrBotDevs/AstrBot_Plugins_Collection`），不是本 fork 的官方市场。本分支要求 Python 3.14+，且不提供旧插件 API 或旧 Dashboard 页面兼容。安装前核对该插件的 `astrbot_version` 和 `requires.dashboard_extension`。失败时用 URL 安装已知兼容的插件，或查看插件加载错误，不要假定上游市场插件能在本分支运行。详见 [插件](/use/plugin) 和 [插件开发指南](/dev/star/plugin-new)。

### 如何关闭长期记忆

当前源码会在运行时无条件初始化长期记忆，并在本地 Agent 对话完成后排队写回；WebUI 和配置档没有按用户或按配置档关闭的开关。处理敏感数据前先阅读 [长期记忆](/use/long-term-memory)。不要把 WebUI 软删除当成数据擦除。

## 插件

### 插件安装失败

GitHub 网络不可用时，可以配置出站 HTTP 代理，或下载可信插件压缩包后从 WebUI 上传。不要安装来源不明的压缩包；插件在 AstrBot 进程中运行，拥有其 Python 权限。

### 安装后出现 `No module named 'xxx'`

常见原因是网络错误、插件缺少 `requirements.txt`，或依赖不支持 Python 3.14。先查看安装日志和插件 README。源码开发环境中可以在 checkout 内用 `uv` 安装和调试；生产环境不要用全局 `pip` 混入不受管理的依赖。

如果插件声明缺失，应向插件作者报告，而不是长期手工维护无法复现的依赖状态。

## NapCat / OneBot v11

### 推荐的新部署：NapCat 正向 WebSocket

使用独立 **NapCat** 平台适配器，让 AstrBot 主动连接 NapCat：

1. NapCat 启动正向 WebSocket 服务，容器镜像使用 `MODE=ws` 时默认监听 `0.0.0.0:3001`。
2. AstrBot 的 NapCat 平台地址填写：
   - 同一 Docker 网络：`ws://napcat:3001`；
   - 同一主机、非容器：`ws://127.0.0.1:3001`；
   - 跨主机：使用 NapCat 主机的受保护地址，并配置防火墙和 token。
3. `127.0.0.1` 在容器内只代表当前容器，不能指向另一个容器。

先从 AstrBot 容器检查 DNS、TCP 端口和 NapCat 日志。`0.0.0.0` 是服务端绑定地址，不能写成客户端连接目标。

### 什么时候使用 6199 反向 WebSocket

`6199/ws` 属于通用 **OneBot v11（aiocqhttp）** 反向 WebSocket 路径，不是独立 NapCat 适配器的推荐连接方式。

保留 `MODE=astrbot` 的旧 compose 组合时，NapCat 会连接 `ws://astrbot:6199/ws`；AstrBot 必须使用 OneBot v11 平台，并在跨容器时把 `ws_reverse_host` 绑定为 `0.0.0.0`。两端都在同一主机进程时才可使用 loopback。

不要同时配置同一个 NapCat 实例的正向和反向路径，否则可能产生重复事件。完整说明见 [NapCat](./platform/napcat) 与 [OneBot v11](./platform/aiocqhttp)。
