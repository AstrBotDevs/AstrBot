# 使用电脑能力

电脑能力（Computer Use）决定 Agent 是否可以在 AstrBot 运行环境中执行代码、访问文件、调用 Shell。

## 模式选择

在 WebUI 中进入：

- `配置 -> 普通配置 -> 使用电脑能力`

核心配置项是 `Computer Use Runtime`：

- `none`：不启用电脑能力，不给 Agent 挂载 Shell、Python、文件系统等工具。
- `local`：在 AstrBot 所在机器上执行，适合需要访问本机文件、命令行工具或本地依赖的场景。
- `sandbox`：在隔离沙盒中执行，适合希望降低本机风险、或让多用户使用自动化能力的场景。

## Local 模式

`local` 模式会把电脑能力挂载到 AstrBot 所在的主机环境。Agent 可以调用本机 Shell、本机 Python，以及本机文件系统工具。

这意味着 Agent 的能力边界接近 AstrBot 进程本身：它能访问什么，取决于 AstrBot 进程的系统权限、运行用户、工作目录和操作系统限制。

### Workspace

在 `local` 模式下，AstrBot 会为每个会话准备一个 workspace：

```text
data/workspaces/{normalized_umo}
```

其中 `{normalized_umo}` 来自当前会话的 `unified_msg_origin`，并会将不适合文件名的字符替换为 `_`。

本地文件工具的相对路径会解析到这个 workspace 下。例如：

```text
notes/todo.txt
```

会被解析为：

```text
data/workspaces/{normalized_umo}/notes/todo.txt
```

本地 Shell 工具执行时，也会把当前工作目录设置为这个 workspace。

> [!NOTE]
> 本地 Python 工具会调用 AstrBot 当前 Python 环境执行代码。编写会读写文件的 Python 代码时，建议使用明确的绝对路径，或先通过文件工具在 workspace 中准备文件。

### 本地工具

`local` 模式主要提供以下工具：

- `Shell`：执行本机 shell 命令。Windows 下使用 `cmd.exe` 语义，Linux/macOS 下使用类 Unix shell 语义。
- `Python`：使用 AstrBot 当前 Python 环境执行 Python 代码。
- `文件读取`：读取 workspace 或允许路径中的文本、图片、表格等文件。
- `文件写入`：写入 UTF-8 文本文件；相对路径默认落在当前 workspace。
- `文件编辑`：按精确字符串替换文件内容。
- `Grep 搜索`：使用 ripgrep 能力搜索文件内容。

`local` 模式不会挂载沙盒上传/下载工具，也不会提供浏览器自动化工具。浏览器能力属于沙盒运行时，需要使用支持 `browser` capability 的沙盒 profile。

本地 Shell 内置了基础危险命令拦截，例如 `rm -rf`、`sudo`、`shutdown`、`reboot`、`kill -9` 等。但这不是完整安全沙箱，不能把它当作安全边界。

### 权限模型

电脑能力还有一个独立开关：

- `需要 AstrBot 管理员权限`

默认情况下这个开关是开启的。

开启后：

- 管理员可以使用 `local` 模式下的 Shell、Python、文件读取、文件写入、文件编辑和 Grep 搜索。
- 非管理员不能使用 Shell 和 Python。
- 非管理员只能在受限目录内使用文件读取、写入、编辑和搜索。插件内置 Skills 只允许读取和搜索，不允许写入或编辑。

非管理员在 `local` 模式下允许访问的目录包括：

- `data/skills`
- `data/plugins/*/skills`（只读，用于插件内置 Skills）
- 当前会话的 `data/workspaces/{normalized_umo}`
- AstrBot 的临时目录
- 系统临时目录中的 `.astrbot`

关闭“需要 AstrBot 管理员权限”后，普通用户在电脑能力工具上的行为会接近管理员。除非你非常清楚风险，否则不建议关闭。

管理员 ID 可在：

- `配置 -> 其他配置 -> 管理员 ID`

中配置。用户可通过 `/sid` 获取自己的 ID。

## Sandbox 模式

`sandbox` 模式会把执行动作放到隔离环境中，而不是直接在 AstrBot 主机上运行。

在沙盒中，Agent 仍然可以使用 Shell、Python、文件系统工具；如果所选沙盒 profile 支持 `browser` capability，还会挂载浏览器自动化工具。

沙盒环境驱动器可在 `配置 -> 普通配置 -> 使用电脑能力` 的沙箱配置中选择。当前常用选项包括：

- `Shipyard Neo`：AstrBot 推荐的远程/独立部署沙盒服务，适合长期运行和多人使用。
- `CUA`：基于 [CUA](https://github.com/trycua/cua) 的本地或云端电脑使用沙盒，可提供桌面截图、鼠标、键盘、Shell、Python 和文件系统能力。

使用 `Shipyard Neo` 时，沙盒 workspace 根目录通常是：

```text
/workspace
```

文件工具一般应传入相对路径，例如：

```text
result.txt
```

而不是：

```text
/workspace/result.txt
```

使用 `CUA` 时，工作目录和可用命令取决于所选 CUA image 与运行方式。Linux CUA 容器通常提供类 Unix Shell；Windows、Android 等非 POSIX 镜像不保证支持 `sh`、`ls`、`rm`、`base64` 等命令，AstrBot 会对部分 shell fallback 操作返回明确错误。

沙盒部署、驱动器选择、CUA 配置、profile、TTL、数据持久化、浏览器能力等内容请参考：[Agent 沙盒环境](/use/astrbot-agent-sandbox)。

> [!NOTE]
> 即使在 `sandbox` 模式下，“需要 AstrBot 管理员权限”仍会影响 Shell、Python、浏览器、上传下载等工具的调用权限。具体权限取决于你的配置。

## Skills

Skills 是给 Agent 使用的“任务说明书”，通常存放在 `data/skills` 下，每个 Skill 都包含一个 `SKILL.md`。

电脑能力和 Skills 的关系可以理解为：

- Skills 告诉 Agent 应该怎么做。
- 电脑能力决定 Agent 能不能执行这些步骤。

例如，一个 Skill 可能要求 Agent 读取文件、运行脚本、生成报告。如果 `Computer Use Runtime` 是 `none`，Agent 可以看到 Skill 的说明，但无法真正调用 Shell 或 Python 完成执行。

在 `local` 模式下，Agent 会读取本地 Skills。
在 `sandbox` 模式下，AstrBot 会尝试把本地 Skills 同步到沙盒中，让 Agent 在沙盒内按 Skill 指令执行。

更多内容请参考：[技能 Skills](/use/skills)。
