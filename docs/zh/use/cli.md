# CLI 指令

AstrBot CLI 用于初始化运行目录、启动 AstrBot、修改常用配置和管理插件。当前 fork 不发布独立 PyPI 包，因此本页假设你已经按[源码部署](/deploy/astrbot/cli)完成 `uv sync`，并在仓库根目录执行命令。

下文表格用 `astrbot` 表示命令名；在源码 checkout 中请使用完整前缀：

```bash
uv run astrbot --help
```

## 顶层指令

| 指令                      | 用途                                       |
| ------------------------- | ------------------------------------------ |
| `astrbot init`            | 将当前目录初始化为 CLI runtime root。      |
| `astrbot run`             | 在前台启动 AstrBot。                       |
| `astrbot install-browser` | 安装本地文转图所需的 Playwright Chromium。 |
| `astrbot conf`            | 查看或修改常用配置项。                     |
| `astrbot password`        | 交互式修改 WebUI 登录密码。                |
| `astrbot plug`            | 创建、安装、更新、删除或搜索插件。         |
| `astrbot help`            | 查看 CLI 帮助。                            |
| `astrbot --version`       | 查看 CLI 版本。                            |

## 初始化与启动

CLI 模式第一次运行时：

```bash
uv run astrbot init
uv run astrbot run
```

`init` 会创建 `.astrbot` 标记、`data/` 子目录并检查 Dashboard。`astrbot init --yes`（或 `-y`）仅跳过首次安装目录确认，不会跳过文件锁、初始密码设置或其他后续确认。直接使用 `uv run main.py` 的源码启动流程不要求这个标记。

`run` 常用选项：

| 选项                | 用途                                 |
| ------------------- | ------------------------------------ |
| `-p, --port <PORT>` | 临时覆盖 WebUI 端口。                |
| `-r, --reload`      | 启用插件自动重载。                   |
| `--reset-password`  | 启动时重置随机初始密码并打印到日志。 |

```bash
uv run astrbot run --port 6185
uv run astrbot run --reload
uv run astrbot run --reset-password
```

CLI 没有远程监听快捷参数。远程访问仍需设置 `dashboard.host` 或 `ASTRBOT_DASHBOARD_HOST`，详见 [WebUI](/use/webui)。

源码入口也支持密码重置：

```bash
uv run main.py --reset-password
```

## 本地文转图浏览器

启用 T2I 或插件 HTML 渲染前执行一次：

```bash
uv run astrbot install-browser
```

该命令调用当前 Python 环境中的 Playwright 安装 Chromium。它不会启动 AstrBot。

## 配置

```bash
uv run astrbot conf get
uv run astrbot conf get dashboard.port
uv run astrbot conf set dashboard.port 6185
```

CLI 支持的常用键包括 `timezone`、`log_level`、`dashboard.port`、`dashboard.username`、`dashboard.password` 和 `callback_api_base`。修改密码时会把 PBKDF2 哈希写入 `pbkdf2_password`，并清空遗留的 `password` 字段。不要手工生成 MD5 值。

也可以使用专门的交互式命令：

```bash
uv run astrbot password
uv run astrbot password --username admin
```

## 插件

```bash
uv run astrbot plug list
uv run astrbot plug list --all
uv run astrbot plug search <QUERY>
uv run astrbot plug install <MARKET_NAME>
uv run astrbot plug update [NAME]
uv run astrbot plug remove <NAME>
uv run astrbot plug new <NAME>
```

### 从本地目录安装

v4.26.3 之后，CLI 支持直接复制本地插件目录：

```bash
uv run astrbot plug install ../my-plugin
```

插件目录必须包含 `metadata.yaml`，其中 `name` 必须是合法的单目录名，并且目标 `data/plugins/<name>` 不得已存在。

开发时可以使用 editable 模式创建目录链接，使源目录修改立即可见：

```bash
uv run astrbot plug install --editable ../my-plugin
# 等价短选项
uv run astrbot plug install -e ../my-plugin
```

editable 模式依赖操作系统的符号链接能力和权限；发布或迁移实例时不要把这个链接当成完整插件副本。

### 代理

市场安装或更新可以传入 GitHub **URL 前缀镜像**。该值必须是已校验的公开 HTTPS origin，不是普通 HTTP 正向代理：

```bash
uv run astrbot plug install example-plugin --proxy https://gh-proxy.example.com
uv run astrbot plug update --proxy https://gh-proxy.example.com
```

## 帮助

```bash
uv run astrbot help
uv run astrbot help run
uv run astrbot plug --help
uv run astrbot --version
```
