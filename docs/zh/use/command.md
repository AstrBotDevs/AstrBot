# 内置指令

AstrBot 的指令通过插件机制注册。内置指令统一采用“单数名词根命令 + 完整动词子命令 + 长选项”的 CLI 命名方式，例如 `/plugin list`、`/conversation create` 和 `/provider set llm 1`。

使用 `/help` 查看当前已经启用的根指令；使用 `/help --image` 或 `/help -i` 请求图片版帮助。如果修改了唤醒前缀，所有示例中的 `/` 也要替换为实际前缀。

## Orbit 指令参数语法

AstrBot 使用 **Orbit Command Syntax** 解析已注册指令的参数。Orbit 不是 shell，也不会执行 shell。只有消息命中完整指令名、指令组或别名后才会严格解析参数；完全未知的根指令仍可进入普通插件过滤器或 LLM。

Orbit 支持确定性的 POSIX quoting 和 escaping 子集：

- 只有 ASCII 空格和 Tab 分隔参数。
- 单引号内所有字符都是字面值。
- 双引号内的反斜杠只转义 `$`、反引号、反斜杠、双引号和换行；其他反斜杠会原样保留。
- 未引用的反斜杠转义下一个字符；反斜杠加换行会执行 line continuation。
- 相邻的引用和未引用片段属于同一个参数，例如 `ab"cd"'ef'` 得到 `abcdef`。
- `""` 和 `''` 都会产生一个空参数。Unicode 原样保留，指令匹配区分大小写。

Orbit 不执行变量、命令、算术或波浪号展开，也不执行 glob、重定向、管道、列表或子 shell。任何未转义且不在单引号内的 `$` 或反引号，以及未引用的词首 `~`、`*`、`?`、`[`、`|`、`&`、`;`、`<`、`>`、`(`、`)`、词首 `#` 和换行都会返回结构化语法错误。

需要把这些字符作为普通数据传入时，请引用或转义：

```text
/session name '$HOME'
/session name "a|b"
/session name \*.txt
/session name "C:\Users\bot"
/session name '^user#[0-9]+$'
/plugin install 'https://example.com?a=1&b=2#readme'
```

已声明的 option 可以位于位置参数前后，支持 `--name=value`。`--` 会终止 option 解析，例如 `/session name -- -x` 会把 `-x` 当作普通参数。`-1` 等负数可以直接用于数值位置参数。

## 指令列表

### 帮助

- `/help`：显示当前启用的根指令和版本信息。
- `/help --image` 或 `/help -i`：生成图片版帮助。

### 会话信息

- `/session info`：显示 UMO、用户 ID、平台 ID、消息类型和会话 ID。
- `/session name`：显示当前自动名称和已保存别名，需要管理员权限。
- `/session name <名称>`：设置当前 UMO 的展示别名，需要管理员权限。名称由 `GreedyStr` 接收，可以包含空格。

使用 `/session info` 得到的用户 ID 可以通过 `/admin grant` 授予当前会话范围的管理员绑定。群聊开启 `unique_session` 时，该指令也会显示可用于白名单的群 ID。

### 对话

- `/conversation create`：创建并切换到新对话。
- `/conversation reset`：清空当前对话上下文，同时清理对应的第三方 Agent Runner 会话状态。
- `/conversation stats`：显示当前对话的输入、缓存输入和输出 Token 统计。
- `/conversation history [--page N|-p N]`：显示当前对话历史。
- `/conversation list [--page N|-p N]`：列出对话。
- `/conversation switch <序号>`：切换到列表中的对话。
- `/conversation rename <新标题>`：重命名当前对话，标题可以包含空格。
- `/conversation delete`：删除当前对话。
- `/conversation create-for <会话 ID>`：为指定群会话创建新对话，需要管理员权限。

`reset` 和 `delete` 在未开启群聊会话隔离时可能要求管理员权限；Dashboard 中的指令权限配置优先于默认行为。

### 运行任务

- `/task stop`：停止当前会话中正在运行的 Agent 或第三方 Agent Runner 任务，不删除历史。

### Provider 与模型

- `/provider list`：列出 LLM、TTS 和 STT Provider，以及当前选中项和可达性状态。
- `/provider set llm <序号>`：切换 LLM Provider。
- `/provider set tts <序号>`：切换 TTS Provider。
- `/provider set stt <序号>`：切换 STT Provider。
- `/model list`：列出当前 LLM Provider 可用模型。
- `/model set <名称或序号>`：切换模型；名称也可以解析到其他已配置 Provider。

这些指令需要管理员权限。

### 会话变量

- `/variable set <键> <值>`：设置 Agent Runner 输入变量。
- `/variable unset <键>`：删除输入变量。

### LLM 聊天状态

- `/chat status`：显示当前会话是否启用 LLM 聊天。
- `/chat enable`：启用当前会话的 LLM 聊天。
- `/chat disable`：停用当前会话的 LLM 聊天。

这些指令需要管理员权限。`enable` 和 `disable` 都是幂等操作。

### 管理员

- `/admin list`：列出当前配置中生效的管理员用户 ID。
- `/admin grant <用户 ID>`：授予 AstrBot 管理员权限。
- `/admin revoke <用户 ID>`：撤销 AstrBot 管理员权限。

三个子指令都需要管理员权限。

### Persona

- `/persona status`：显示默认 Persona 和当前对话实际使用的 Persona。
- `/persona list`：列出 Persona。
- `/persona show <persona_id>`：显示 Persona 的系统提示词。
- `/persona set <persona_id>`：为当前对话选择 Persona。
- `/persona unset`：让当前对话显式不使用 Persona。

Persona 子指令需要管理员权限。仅输入 `/persona` 会显示子指令树。

### 插件

- `/plugin list`：列出已加载插件。
- `/plugin show <插件名>`：显示插件版本、作者和已注册指令。
- `/plugin enable <插件名>`：启用插件，需要管理员权限。
- `/plugin disable <插件名>`：停用插件，需要管理员权限。
- `/plugin install <仓库 URL>`：安装插件，需要管理员权限。

插件加载、卸载、重载或启禁后，AstrBot 会立即重建指令 catalog，并刷新已启用的 Telegram/Discord 原生命令入口。
