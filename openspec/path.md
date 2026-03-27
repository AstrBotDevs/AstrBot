# 路径规范

## 概述

AstrBot 遵循 [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html)，定义标准化的目录结构。

**跨平台支持**：
- **Linux/macOS 桌面**：遵循 XDG 规范
- **Linux 服务器**：使用 `/var/lib/astrbot`（systemd 服务场景）
- **Windows**：不遵循 XDG，使用 `%APPDATA%` / `%LOCALAPPDATA%` / `%USERPROFILE%`

> 相关: [config.md](config.md)（配置规范）, [env.md](env.md)（环境变量）
- **BSD/Unix**：遵循 XDG 规范

## Linux 服务器场景

### 为什么使用 /var/lib/astrbot

| 原因 | 说明 |
|------|------|
| **FHS 合规** | `/var/lib` 用于存储可变的状态信息，符合文件系统层次结构标准 |
| **systemd 服务** | 服务以系统用户运行，无用户目录访问权限 |
| **系统级目录** | 所有用户共享，适合守护进程部署 |
| **持久化** | `/var` 分区通常有足够空间存储数据 |

**场景说明**：
- systemd 服务以 `astrbot` 系统用户运行
- 系统用户没有 `~/.local/share` 等用户目录
- 必须使用系统级目录 `/var/lib/astrbot`

### Linux 服务器路径

| 类型 | 路径 | 说明 |
|------|------|------|
| 配置 | `/var/lib/astrbot/config/` | 配置文件 |
| 数据 | `/var/lib/astrbot/` | 主数据目录 |
| 缓存 | `/var/cache/astrbot/` | 临时文件 |
| 状态 | `/var/lib/astrbot/state/` | 会话状态 |
| 日志 | `/var/log/astrbot/` | 日志文件 |
| 运行时 | `/run/astrbot/` | PID 文件、socket |

**目录结构**：

```
/var/lib/astrbot/
├── config/                    # 配置文件
│   └── mcp_servers.json        # MCP 服务器配置
├── data/                      # 插件、skills 等
│   ├── plugins/
│   ├── plugin_data/
│   ├── skills/
│   ├── knowledge_base/
│   ├── backups/
│   └── webchat/
├── state/                     # 会话状态
│   └── sessions/
└── .env                       # 环境变量

/var/cache/astrbot/
├── temp/                      # 临时文件
└── t2i_templates/             # 文转图模板

/run/astrbot/                  # 运行时文件
├── astrbot.sock               # Unix Socket
└── pid                        # PID 文件
```

### MCP 服务器配置

MCP 服务器配置位于 `config/mcp_servers.json`：

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
      "env": {}
    },
    "http-server": {
      "url": "http://localhost:3000/mcp",
      "transport": "sse"
    }
  }
}
```

**配置字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `command` | string | 启动命令（stdio 传输） |
| `args` | array | 命令参数 |
| `env` | object | 环境变量 |
| `url` | string | 服务器 URL（HTTP 传输） |
| `transport` | string | 传输类型：`stdio` / `sse` / `streamable_http` |

## 平台差异

| 平台 | 配置目录 | 数据目录 | 缓存目录 | 运行时目录 |
|------|----------|----------|----------|------------|
| Linux 桌面 | `$XDG_CONFIG_HOME/astrbot/` | `$XDG_DATA_HOME/astrbot/` | `$XDG_CACHE_HOME/astrbot/` | `$XDG_RUNTIME_DIR/astrbot/` |
| Linux 服务器 | `/var/lib/astrbot/config/` | `/var/lib/astrbot/` | `/var/cache/astrbot/` | `/run/astrbot/` |
| macOS | `$XDG_CONFIG_HOME/astrbot/` | `$XDG_DATA_HOME/astrbot/` | `$XDG_CACHE_HOME/astrbot/` | `$XDG_RUNTIME_DIR/astrbot/` |
| Windows | `%APPDATA%/AstrBot/` | `%LOCALAPPDATA%/AstrBot/` | `%TEMP%/AstrBot/` | `%LOCALAPPDATA%/AstrBot/runtime/` |

## XDG 基础变量（Linux/macOS）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `XDG_CONFIG_HOME` | `~/.config` | 用户配置文件目录 |
| `XDG_DATA_HOME` | `~/.local/share` | 用户数据目录 |
| `XDG_CACHE_HOME` | `~/.cache` | 用户缓存目录 |
| `XDG_STATE_HOME` | `~/.local/state` | 用户状态目录 |
| `XDG_RUNTIME_DIR` | `/run/user/<UID>` | 运行时目录 |

## AstrBot 目录结构

```
$XDG_DATA_HOME/astrbot/
├── data/                      # 应用数据
│   ├── plugins/              # 插件目录
│   ├── plugin_data/          # 插件数据
│   ├── skills/               # Skills 目录
│   ├── knowledge_base/       # 知识库
│   ├── backups/              # 备份
│   └── webchat/              # WebChat 数据
├── cache/                     # 缓存
│   ├── temp/                 # 临时文件
│   └── t2i_templates/        # 文转图模板
└── state/                     # 状态
    └── sessions/              # 会话状态

$XDG_CONFIG_HOME/astrbot/
├── .env                      # 环境变量
├── config.yaml               # 主配置文件
└── mcp_servers.json          # MCP 服务器配置
```

## 路径映射

### 配置目录 (`XDG_CONFIG_HOME/astrbot/`)

| 路径 | 说明 | 环境变量 |
|------|------|----------|
| `$XDG_CONFIG_HOME/astrbot/` | AstrBot 配置根目录 | `ASTRBOT_CONFIG_DIR` |
| `$XDG_CONFIG_HOME/astrbot/.env` | 环境变量文件 | - |
| `$XDG_CONFIG_HOME/astrbot/config.yaml` | 主配置文件 | - |

### 数据目录 (`XDG_DATA_HOME/astrbot/`)

| 路径 | 说明 | 环境变量 |
|------|------|----------|
| `$XDG_DATA_HOME/astrbot/` | AstrBot 数据根目录 | `ASTRBOT_DATA_DIR` |
| `$XDG_DATA_HOME/astrbot/plugins/` | 插件目录 | `ASTRBOT_PLUGIN_DIR` |
| `$XDG_DATA_HOME/astrbot/plugin_data/` | 插件数据 | `ASTRBOT_PLUGIN_DATA_DIR` |
| `$XDG_DATA_HOME/astrbot/skills/` | Skills 目录 | `ASTRBOT_SKILLS_DIR` |
| `$XDG_DATA_HOME/astrbot/knowledge_base/` | 知识库 | `ASTRBOT_KB_DIR` |
| `$XDG_DATA_HOME/astrbot/backups/` | 备份目录 | `ASTRBOT_BACKUPS_DIR` |
| `$XDG_DATA_HOME/astrbot/webchat/` | WebChat 数据 | `ASTRBOT_WEBCHAT_DIR` |

### 缓存目录 (`XDG_CACHE_HOME/astrbot/`)

| 路径 | 说明 | 环境变量 |
|------|------|----------|
| `$XDG_CACHE_HOME/astrbot/` | AstrBot 缓存根目录 | `ASTRBOT_CACHE_DIR` |
| `$XDG_CACHE_HOME/astrbot/temp/` | 临时文件 | `ASTRBOT_TEMP_DIR` |
| `$XDG_CACHE_HOME/astrbot/t2i_templates/` | 文转图模板 | - |

### 状态目录 (`XDG_STATE_HOME/astrbot/`)

| 路径 | 说明 | 环境变量 |
|------|------|----------|
| `$XDG_STATE_HOME/astrbot/` | AstrBot 状态根目录 | `ASTRBOT_STATE_DIR` |
| `$XDG_STATE_HOME/astrbot/sessions/` | 会话状态 | - |

### 运行时目录

| 路径 | 说明 | 环境变量 |
|------|------|----------|
| `/run/user/<UID>/astrbot/` | 运行时目录 | `ASTRBOT_RUNTIME_DIR` |

### 项目目录

| 路径 | 说明 | 备注 |
|------|------|------|
| `<source_root>/` | 源码目录 | 固定，指向 astrbot 包位置 |
| `<source_root>/dashboard/dist/` | 前端资源 | 固定 |

## 环境变量覆盖

### 根目录覆盖

| 变量 | 说明 | 优先级 |
|------|------|--------|
| `ASTRBOT_ROOT` | 覆盖整个 AstrBot 数据根目录 | 最高 |
| `ASTRBOT_DATA_DIR` | 覆盖数据目录 | 次高 |
| `ASTRBOT_CONFIG_DIR` | 覆盖配置目录 | 次高 |

### 子目录覆盖

| 变量 | 说明 |
|------|------|
| `ASTRBOT_PLUGIN_DIR` | 插件目录 |
| `ASTRBOT_PLUGIN_DATA_DIR` | 插件数据目录 |
| `ASTRBOT_SKILLS_DIR` | Skills 目录 |
| `ASTRBOT_KB_DIR` | 知识库目录 |
| `ASTRBOT_BACKUPS_DIR` | 备份目录 |
| `ASTRBOT_WEBCHAT_DIR` | WebChat 目录 |
| `ASTRBOT_TEMP_DIR` | 临时文件目录 |
| `ASTRBOT_CACHE_DIR` | 缓存根目录 |
| `ASTRBOT_STATE_DIR` | 状态根目录 |
| `ASTRBOT_RUNTIME_DIR` | 运行时目录 |

### 覆盖优先级

```
ASTRBOT_ROOT > ASTRBOT_DATA_DIR > 子目录变量
```

## 目录用途

| 目录 | 内容 | 是否持久化 |
|------|------|-----------|
| `config/` | 配置文件、.env | 是 |
| `plugins/` | 插件代码 | 是 |
| `plugin_data/` | 插件运行时数据 | 是 |
| `skills/` | Skills 配置 | 是 |
| `knowledge_base/` | 知识库文件 | 是 |
| `backups/` | 备份文件 | 是 |
| `webchat/` | WebChat 数据 | 是 |
| `temp/` | 临时文件 | 否（可清理） |
| `t2i_templates/` | 文转图模板缓存 | 否（可清理） |
| `sessions/` | 会话状态 | 是 |

## 兼容性别名

以下路径函数保留用于向后兼容：

```python
# 旧路径 → 新路径
get_astrbot_root()        → $XDG_DATA_HOME/astrbot/
get_astrbot_data_path()   → $XDG_DATA_HOME/astrbot/
get_astrbot_config_path() → $XDG_CONFIG_HOME/astrbot/
get_astrbot_plugin_path() → $XDG_DATA_HOME/astrbot/plugins/
get_astrbot_plugin_data_path() → $XDG_DATA_HOME/astrbot/plugin_data/
get_astrbot_skills_path() → $XDG_DATA_HOME/astrbot/skills/
get_astrbot_knowledge_base_path() → $XDG_DATA_HOME/astrbot/knowledge_base/
get_astrbot_backups_path() → $XDG_DATA_HOME/astrbot/backups/
get_astrbot_webchat_path() → $XDG_DATA_HOME/astrbot/webchat/
get_astrbot_temp_path() → $XDG_CACHE_HOME/astrbot/temp/
get_astrbot_t2i_templates_path() → $XDG_CACHE_HOME/astrbot/t2i_templates/
```

## 目录创建

AstrBot 启动时自动创建以下目录（如不存在）：

```
$XDG_CONFIG_HOME/astrbot/
$XDG_DATA_HOME/astrbot/
$XDG_DATA_HOME/astrbot/plugins/
$XDG_DATA_HOME/astrbot/plugin_data/
$XDG_DATA_HOME/astrbot/skills/
$XDG_DATA_HOME/astrbot/knowledge_base/
$XDG_DATA_HOME/astrbot/backups/
$XDG_DATA_HOME/astrbot/webchat/
$XDG_CACHE_HOME/astrbot/
$XDG_CACHE_HOME/astrbot/temp/
$XDG_CACHE_HOME/astrbot/t2i_templates/
$XDG_STATE_HOME/astrbot/
$XDG_STATE_HOME/astrbot/sessions/
```

## 多实例支持

通过 `ASTRBOT_INSTANCE_NAME` 支持多实例：

```
$XDG_DATA_HOME/astrbot/<instance_name>/
├── data/
├── cache/
└── state/
```

## 路径规范总结

### Linux 服务器（systemd 部署）

| 类型 | 路径 |
|------|------|
| 配置 | `/var/lib/astrbot/config/` |
| 数据 | `/var/lib/astrbot/` |
| 缓存 | `/var/cache/astrbot/` |
| 状态 | `/var/lib/astrbot/state/` |
| 运行时 | `/run/astrbot/` |

### Linux/macOS 桌面

| 类型 | XDG 路径 |
|------|----------|
| 配置 | `$XDG_CONFIG_HOME/astrbot/` |
| 数据 | `$XDG_DATA_HOME/astrbot/` |
| 缓存 | `$XDG_CACHE_HOME/astrbot/` |
| 状态 | `$XDG_STATE_HOME/astrbot/` |

### Windows

| 类型 | Windows 路径 |
|------|--------------|
| 配置 | `%APPDATA%/AstrBot/` |
| 数据 | `%LOCALAPPDATA%/AstrBot/` |
| 缓存 | `%TEMP%/AstrBot/` |

## 环境变量

所有平台统一使用 `ASTRBOT_*` 环境变量覆盖默认路径，优先级最高。

## 与 Claude Code 目录对比

Claude Code 使用 `~/.claude/` 作为根目录，**不遵循 XDG 规范**：

```
~/.claude/                          # Claude Code 根目录
├── backups/                        # 备份
├── cache/                          # 缓存
├── downloads/                       # 下载
├── file-history/                   # 文件历史
├── paste-cache/                    # 粘贴缓存
├── plans/                          # 计划
├── plugins/                        # 插件
├── projects/                       # 项目会话
├── session-env/                    # 会话环境
├── sessions/                       # 会话
├── shell-snapshots/                # Shell 快照
├── skills/                         # Skills
├── tasks/                          # 任务
├── teams/                          # 团队
├── history.jsonl                   # 对话历史
├── settings.json                   # 设置
└── settings.local.json             # 本地设置
```

### 关键差异

| 维度 | Claude Code | AstrBot |
|------|-------------|---------|
| 规范 | 非标准（固定 `~/.claude/`） | XDG 规范 |
| 配置 | 根目录直接放配置文件 | 分离到 `$XDG_CONFIG_HOME/` |
| 缓存 | 根目录下 `cache/` | `$XDG_CACHE_HOME/` |
| 数据 | 根目录直接放数据文件 | 分离到 `$XDG_DATA_HOME/` |
| 会话 | `sessions/`, `session-env/` | `$XDG_STATE_HOME/` |
| 项目 | `projects/` | 内嵌在数据目录 |

### 设计哲学

- **Claude Code**：简单直接，所有内容在 `~/.claude/` 下
- **AstrBot**：遵循 XDG，数据分类清晰（配置/数据/缓存/状态分离）

## 已知限制

- Windows 平台**不遵循** XDG 规范，使用 Windows 标准路径
- 桌面客户端（packaged desktop runtime）使用 `~/.astrbot/` 作为数据根目录

> 相关: [config.md](config.md)（配置规范）, [env.md](env.md)（环境变量）
