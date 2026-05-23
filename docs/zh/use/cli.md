# CLI 指令

AstrBot CLI 用于初始化实例、启动 AstrBot、安装后台服务、查看日志、修改常用配置和管理插件。

如果你使用 `uv` 安装：

```bash
uv tool install astrbot --python 3.12
```

`uv` 会生成 `astrbot` 可执行文件，并把它放到 `PATH` 中。可以用下面的命令确认路径：

::: code-group

```bash [Linux / macOS]
which astrbot
```

```powershell [Windows]
where.exe astrbot
```

:::

> [!TIP]
> 下面的命令都需要在 AstrBot 工作目录中执行，除非命令提供了 `--workdir` 选项。

## 快速开始

第一次部署时先初始化目录，再启动 AstrBot：

```bash
astrbot init
astrbot run
```

`astrbot init` 会在当前目录创建 AstrBot 所需的数据目录和配置文件。初始化完成后，后续启动只需要执行 `astrbot run`。

## 顶层指令

| 指令 | 用途 |
| --- | --- |
| `astrbot init` | 初始化当前目录为 AstrBot 工作目录。 |
| `astrbot run` | 在前台启动 AstrBot。 |
| `astrbot service` | 安装和管理 AstrBot 后台服务。 |
| `astrbot config` | 查看或修改常用配置项。 |
| `astrbot password` | 交互式修改 WebUI 登录密码。 |
| `astrbot plugin` | 创建、安装、更新、删除或搜索插件。 |
| `astrbot help` | 查看 CLI 帮助。 |
| `astrbot --version` | 查看 AstrBot CLI 版本。 |

`conf` 和 `plug` 是兼容别名，仍然可用：

```bash
astrbot conf get
astrbot plug list
```

推荐在新文档和脚本中使用 `config` 和 `plugin`。

## 启动 AstrBot

```bash
astrbot run
```

常用选项：

| 选项 | 用途 |
| --- | --- |
| `-p, --port <PORT>` | 指定 WebUI 端口。 |
| `-r, --reload` | 启用插件自动重载，适合插件开发调试。 |
| `--reset-password` | 启动时重置 WebUI 初始密码，并在启动日志中打印新的初始密码。 |

示例：

```bash
astrbot run --port 6185
astrbot run --reload
astrbot run --reset-password
```

## 后台服务

`astrbot service` 可以把 AstrBot 安装为用户级后台服务，适合长期运行。

不同系统会使用对应的服务管理机制：

| 系统 | 服务管理器 |
| --- | --- |
| Linux | `systemd --user` |
| macOS | LaunchAgent |

> [!NOTE]
> Windows 暂不支持 `astrbot service`。请使用 `astrbot run` 前台启动，或使用其他进程管理工具。

### 安装服务

```bash
astrbot service install --now
```

该命令默认使用当前 `PATH` 中的 `astrbot` 可执行文件，并把当前目录作为 AstrBot 工作目录。`--now` 表示安装后立即启动或重启服务。

常用选项：

| 选项 | 用途 |
| --- | --- |
| `--name <NAME>` | 指定服务名，默认 `astrbot`。 |
| `--workdir <DIR>` | 指定 AstrBot 工作目录。 |
| `--executable <PATH>` | 指定 `astrbot` 可执行文件路径。 |
| `--force` | 覆盖已有服务定义。 |
| `--now` | 安装后立即启动或重启服务。 |

如果 `astrbot` 不在 `PATH` 中，可以显式指定可执行文件：

```bash
astrbot service install --workdir /path/to/astrbot-root --executable /path/to/astrbot --now
```

### 管理服务

```bash
astrbot service start
astrbot service stop
astrbot service restart
astrbot service uninstall
```

这些命令都支持 `--name <NAME>`，用于管理非默认服务名：

```bash
astrbot service restart --name astrbot-test
```

卸载服务时，如果不希望交互确认，可以使用：

```bash
astrbot service uninstall --force
```

### 查看服务状态

```bash
astrbot service status
```

状态输出会包含：

- 整体健康状态。
- 当前系统和服务管理器。
- 服务是否已安装、是否启用、当前运行状态。
- AstrBot 工作目录。
- Dashboard 端口。
- WebUI URL 和是否可访问。

常用选项：

| 选项 | 用途 |
| --- | --- |
| `--name <NAME>` | 指定服务名，默认 `astrbot`。 |
| `--workdir <DIR>` | 指定 AstrBot 工作目录，用于读取端口配置。 |
| `--timeout <SECONDS>` | 指定 WebUI 健康检查超时时间，默认 2 秒。 |

示例：

```bash
astrbot service status --timeout 5
```

## 日志

AstrBot CLI 中有两类日志：

| 类型 | 命令 | 说明 |
| --- | --- | --- |
| 服务日志 | `astrbot service logs` | 查看服务管理器捕获的控制台输出。 |
| 应用日志文件 | `astrbot service logs --source app` | 查看 `data/logs/astrbot.log`，需要先启用文件日志。 |

### 查看服务日志

```bash
astrbot service logs
astrbot service logs -n 100
astrbot service logs -f
```

常用选项：

| 选项 | 用途 |
| --- | --- |
| `--name <NAME>` | 指定服务名。 |
| `-n, --lines <N>` | 显示最近 N 行，默认 200。 |
| `-f, --follow` | 持续跟随日志输出。 |
| `--include-stderr` | 在 macOS 上同时显示 stderr 日志。 |

macOS 下，`astrbot service logs` 默认只显示标准输出日志，也就是 `.out.log`。如果需要同时查看错误输出，再加 `--include-stderr`。

### 启用应用日志文件

`data/logs/astrbot.log` 默认不会写入。需要先启用应用日志文件，然后重启 AstrBot：

```bash
astrbot service logs enable
astrbot service restart
astrbot service logs --source app
```

查看应用日志文件配置：

```bash
astrbot service logs status
```

关闭应用日志文件：

```bash
astrbot service logs disable
astrbot service restart
```

自定义应用日志文件路径：

```bash
astrbot service logs enable --path logs/astrbot.log
```

相对路径会以 AstrBot 数据目录为基准解析。

## 配置

`astrbot config` 用于查看和修改常用配置项。

```bash
astrbot config get
astrbot config get dashboard.port
astrbot config set dashboard.port 6185
```

支持的配置项：

| 配置项 | 说明 |
| --- | --- |
| `timezone` | 时区，例如 `Asia/Shanghai`。 |
| `log_level` | 日志等级：`DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`。 |
| `dashboard.port` | WebUI 端口。 |
| `dashboard.username` | WebUI 用户名。 |
| `dashboard.password` | WebUI 密码。 |
| `callback_api_base` | 回调 API 基础地址，需要以 `http://` 或 `https://` 开头。 |

修改密码时会自动写入新版密码哈希：

```bash
astrbot config set dashboard.password "new-password"
```

也可以使用专门的交互式密码指令：

```bash
astrbot password
astrbot password --username admin
```

## 插件

`astrbot plugin` 用于管理 `data/plugins` 下的插件。

| 指令 | 用途 |
| --- | --- |
| `astrbot plugin list` | 查看已安装插件。 |
| `astrbot plugin list --all` | 同时显示未安装插件。 |
| `astrbot plugin search <QUERY>` | 搜索插件。 |
| `astrbot plugin install <NAME>` | 安装插件。 |
| `astrbot plugin update [NAME]` | 更新指定插件；不传名称时更新所有可更新插件。 |
| `astrbot plugin remove <NAME>` | 删除已安装插件。 |
| `astrbot plugin new <NAME>` | 基于模板创建新插件。 |

安装或更新插件时可以使用 GitHub 代理：

```bash
astrbot plugin install example-plugin --proxy https://gh-proxy.example.com/
astrbot plugin update --proxy https://gh-proxy.example.com/
```

创建新插件会交互式询问作者、描述、版本和仓库地址：

```bash
astrbot plugin new my-plugin
```

## 帮助

查看全部 CLI 帮助：

```bash
astrbot help
```

查看指定指令帮助：

```bash
astrbot help service
astrbot service --help
astrbot service logs --help
```

查看版本：

```bash
astrbot --version
```
