# 内置指令

AstrBot 的指令通过插件机制注册。为了保持主程序轻量，当前只有少量基础指令随 AstrBot 主程序内置加载；更多管理类、扩展类指令已经迁移到独立插件中维护。

使用 `/help` 可以查看当前已经启用的指令。

> [!NOTE]
> 1. `/help`、`/set`、`/unset` 默认不会显示在 `/help` 输出的指令清单中，但这些指令仍然可用。
> 2. 如果您修改了唤醒前缀，去掉了默认的 `/`，那么指令也需要使用新的唤醒前缀触发。例如将唤醒前缀改为 `!` 后，应使用 `!help`、`!reset`，而不是 `/help`、`/reset`。

## 主程序内置指令

以下指令由 AstrBot 主程序自带，默认随 AstrBot 加载：

- `/help`：查看当前启用的指令和 AstrBot 版本信息。
- `/sid`：查看当前消息来源信息，包括 UMO、用户 ID、平台 ID、消息类型和会话 ID。常用于配置管理员、白名单或路由规则。
- `/name`：为当前 UMO（统一消息来源，即某个平台上的一个群聊或私聊会话）设置展示别名，让 WebUI 中的会话来源更容易识别。该指令需要管理员权限。
- `/reset`：重置当前会话的 LLM 上下文。
- `/stop`：停止当前会话中正在运行的 Agent 任务。
- `/new`：创建并切换到一个新对话。
- `/stats`：查看当前会话的 Token 用量统计。
- `/provider`：查看或切换 LLM Provider。该指令需要管理员权限。
- `/dashboard_update`：更新 AstrBot WebUI。该指令需要管理员权限。
- `/set`：设置当前会话变量，常用于 Dify、Coze、DashScope 等 Agent 执行器的输入变量。
- `/unset`：移除当前会话变量。

## 核心指令详解

### `/sid`

`/sid` 用于查看当前消息来源信息，主要输出：

- `UMO`：当前消息来源的统一标识。它通常用于白名单、配置文件路由等按会话生效的配置。
- `UID`：当前发送者的用户 ID。它通常用于添加 AstrBot 管理员。
- `Bot ID`：当前机器人所在平台实例的 ID。
- `Message Type`：消息类型，例如私聊或群聊。
- `Session ID`：平台侧会话 ID。

在群聊中，如果开启了 `unique_session`（会话隔离），`/sid` 还会额外提示当前群 ID。这个群 ID 可用于把整个群加入白名单。

常见用途：

- 添加管理员：先发送 `/sid` 获取 `UID`，再在 WebUI 的 `配置 -> 其他配置 -> 管理员 ID` 中添加。
- 配置白名单：使用 `UMO` 或群 ID 控制哪些会话可以使用机器人。
- 配置路由规则：使用 `UMO` 区分不同平台、群聊或私聊来源。

### `/name`

`/name` 用于给当前 UMO 设置一个更容易识别的展示别名。UMO 是 Unified Message Origin 的缩写，可以理解为“统一消息来源”：它用 `平台 ID:消息类型:会话 ID` 的形式标识一个具体的消息来源，例如某个 QQ 群、某个 Telegram 群，或某个平台上的一个私聊会话。

原始 UMO 往往比较长，也不一定能直接看出它对应哪个群或哪个用户。设置 `/name` 后，AstrBot 会在 WebUI 的 UMO 列表、会话来源选择、定时任务投递目标、对话数据等位置优先展示这个别名，帮助管理员更快识别和选择目标会话，降低配置路由规则、Cron 投递目标或会话规则时选错来源的概率。

`/name` 还会记录当前平台可识别的自动名称，例如群聊通常是群名，私聊通常是发送者昵称或发送者 ID。这样即使没有手动设置别名，WebUI 也可以尽量显示一个可读名称。

用法：

- `/name <别名>`：设置或更新当前 UMO 的别名。该指令可以重复使用，后一次设置会覆盖前一次别名。
- `/name`：不带参数时，不会修改别名，只会显示用法、当前 UMO、当前自动名称和已经保存的别名。

名称显示规则：

- 如果同时存在别名和自动名称，优先显示 `别名（自动名称）`。
- 如果只有自动名称，显示自动名称。
- 如果没有别名和自动名称，显示原始 UMO。

`/name` 需要管理员权限。

### `/reset`

`/reset` 用于重置当前会话的 LLM 上下文。

对于 AstrBot 内置 Agent Runner，它会：

- 停止当前会话中正在运行的任务。
- 清空当前对话的上下文消息。
- 通知长期记忆会话清理当前上下文状态。

对于第三方 Agent Runner，例如 `dify`、`coze`、`dashscope`、`deerflow`，它会：

- 停止当前会话中正在运行的任务。
- 删除当前会话保存的第三方会话 ID，让下一轮对话重新开始。

权限说明：

- 私聊中默认普通用户可使用。
- 群聊开启会话隔离时，默认普通用户可使用。
- 群聊未开启会话隔离时，默认需要管理员权限。
- 如果管理员修改过指令权限配置，则以实际配置为准。

### `/stop`

`/stop` 用于停止当前会话中正在运行的 Agent 任务。

它不会清空对话历史，也不会创建新对话。它只对当前会话正在执行的任务发出停止请求。

对于内置 Agent Runner，`/stop` 会请求 Agent Runner 停止当前任务。  
对于第三方 Agent Runner，例如 `dify`、`coze`、`dashscope`、`deerflow`，`/stop` 会直接停止当前会话中登记的运行任务。

如果当前会话没有正在运行的任务，AstrBot 会提示当前会话没有运行中的任务。

### `/stats`

`/stats` 用于查看当前会话的 Token 用量统计。

它从数据库中查询当前对话的所有 Provider 调用记录，汇总并展示：

- 总 Token 用量（输入 Token + 输出 Token）。
- 输入 Token（缓存命中），即被提供商缓存并跳过计费的输入 Token。
- 输入 Token（其他），即未被缓存、正常计费的输入 Token。
- 输出 Token，即模型生成的输出 Token。

如果当前不在任何对话中，AstrBot 会提示先使用 `/new` 创建对话。

### `/provider`

`/provider` 用于查看或切换当前 UMO 使用的 Provider（LLM / TTS / STT）。

**查看 Provider 列表：**

不带参数时，`/provider` 会列出所有已配置的 Provider，按 LLM、TTS、STT 分类展示。每个 Provider 旁会显示：

- 序号，用于后续切换。
- Provider ID 和当前使用的模型（LLM 类型）。
- 可达性标记：`✅` 表示连接正常，`❌` 表示连接失败（附带错误码）。
- 当前正在使用的 Provider 末尾会标注 `(当前使用)`。

> [!NOTE]
> 可达性检测需要在 WebUI 的 `配置 -> 普通配置 -> AI 配置` 中，展开底部的「更多配置」，开启「提供商可达性检测」后才会生效。关闭后不显示可达性标记，列表加载更快。

**切换 Provider：**

使用 `/provider <序号>` 可以将当前会话的 LLM Provider 切换为列表中对应序号的 Provider。

- `/provider <序号>`：切换到指定序号的 LLM Provider。
- `/provider tts <序号>`：切换到指定序号的 TTS Provider。
- `/provider stt <序号>`：切换到指定序号的 STT Provider。

该指令需要管理员权限。

## 内置指令扩展

除上述基础指令外，其他原本随主程序提供的内置指令已经迁移到独立插件：

- [builtin_commands_extension](https://github.com/AstrBotDevs/builtin_commands_extension)

可直接在插件市场搜索安装。

该插件提供插件管理、Provider 管理、模型切换、Persona 管理、对话列表管理等扩展指令，例如：

- `/plugin`：查看、启用、停用或安装插件。
- `/op`、`/deop`：添加或移除管理员。
- `/provider`：查看或切换 LLM Provider。
- `/model`：查看或切换模型。
- `/history`：查看当前对话历史。
- `/ls`：查看对话列表。
- `/groupnew`：为指定群聊创建新对话。
- `/switch`：切换到指定对话。
- `/rename`：重命名当前对话。
- `/del`：删除当前对话。
- `/persona`：查看或切换 Persona。
- `/llm`：开启或关闭 LLM 聊天功能。

如果你需要这些扩展指令，请安装或启用 `builtin_commands_extension` 插件。

## 权限说明

部分指令需要 AstrBot 管理员权限，例如 `/dashboard_update`、`/name`、`/op`、`/deop`、`/provider`、`/model`、`/persona` 等。

可以通过 `/sid` 获取用户 ID，然后在 WebUI 的 `配置 -> 其他配置 -> 管理员 ID` 中添加管理员。
