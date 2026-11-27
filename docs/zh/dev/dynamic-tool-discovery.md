# 动态工具发现设计

## 现状和目标

AstrBot 的本地 Agent 由 `build_main_agent` 组装工具集。Persona、会话插件配置、内置能力开关和请求钩子共同决定本次运行有哪些候选工具。插件和已连接的 MCP Server 通过 `FunctionToolManager` 注册工具。内置工具按功能配置加入同一个 `ToolSet`。Provider 将 `ToolSet` 序列化为各自的 Function Calling 格式，`ToolLoopAgentRunner` 将结果交给执行器，再把工具结果追加到后续模型请求。

`full` 每轮发送完整 Schema。`skills_like` 第一次请求发送全量名称和描述，再为模型选中的工具请求参数。两者都要求模型扫过全量清单。MCP 客户端已经会在连接时调用 `tools/list`，并能通过现有执行路径发起 `tools/call`。当前工具管理器在启动和停止 Server 时更新注册表，尚未将远端工具列表变更通知作为实时目录来源。

## 参考实现

| 技术 | 机制 | 对 AstrBot 的意义 |
| --- | --- | --- |
| Anthropic Tool Search | `defer_loading` 加 BM25 或正则搜索，结果以工具引用展开 | 验证延迟加载模式。服务端延迟加载及缓存机制依赖支持该功能的 Anthropic 接口 |
| OpenAI Tool Search | Responses 支持托管搜索和客户端搜索。后者由应用返回工具定义 | 客户端检索适合已有本地注册表和权限规则的应用。协议依赖支持该功能的模型与接口 |
| Hermes Tool Search | 用固定的搜索、描述和调用函数代理低频工具 | 递进披露可建立在常规 Function Calling 上，不必在发现工具时改写顶层定义 |
| MCP Tools | `tools/list` 发现元数据，`tools/call` 执行，协议支持列表变更通知 | MCP 提供工具来源和调用协议。AstrBot 负责把工具目录提供给模型 |

- [Anthropic Tool Search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- [OpenAI Tool Search](https://developers.openai.com/api/docs/guides/tools-tool-search)
- [Hermes Tool Search](https://hermes-agent.nousresearch.com/docs/user-guide/features/tool-search)
- [MCP Tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)

## 技术方案

在内置 Agent 执行器的工具模式 `agent.config.misc.tool_schema_mode` 中加入 `dynamic`，默认使用 `full`。内置 SubAgent 和定时或后台任务唤醒读取会话配置。插件直接使用 `Context.tool_loop_agent` 时可显式传入 `tool_schema_mode="dynamic"`。

1. Runner 在 Agent 启动钩子之后，从本次运行的 `ToolSet` 获取候选。真实工具留在服务端；Provider 请求顶层只携带固定的 `astrbot_search_tools`、`astrbot_describe_tool` 和 `astrbot_call_tool`。
2. `astrbot_search_tools` 按名称和描述的词项匹配排序，支持中文词片段，每次返回最多三个新候选的名称和简介。`astrbot_describe_tool` 返回指定工具的完整 Schema；知道确切名称时可直接查看，无需先搜索。
3. `astrbot_call_tool` 只接受此前模型响应中已描述、当前仍可用的工具。Runner 以真实工具名执行、触发钩子并记录事件；Provider 的历史保留外层函数名和调用 ID。Schema 和搜索结果作为工具消息追加，不改写顶层定义。新的 Agent 运行重置描述状态。
4. 动态工具集和显式传给旧版 SubAgent 的已注册工具统一保留权限包装。注册状态、运行范围与执行权限在调用时独立确认。JSON Schema 支持本地引用，不拉取外部引用；含正则的 Schema 在有输入大小和时间限制的子进程中验证，避免阻塞事件循环。
5. Provider 继续用常规 Function Calling。它只能检查固定入口的参数，真实工具参数由 AstrBot 验证。当前不接入特定 Provider 的原生增量协议，远端 Agent 执行器自行管理工具。

自动化测试比对多轮顶层定义的序列化结果，以及未压缩消息是否只追加、不改写。该方案不需要更改外部 API 或存储结构。

## 取舍

词项搜索不需要额外模型、凭据或索引服务。工具名与描述的质量会影响召回，跨语言任务可用工具常用的英文关键词重试。搜索和查看定义各占一次模型请求。目录很大且每次只使用少量工具时适合按需加载；工具很少或每次均须使用时可选 `full`。

发现工具本身不破坏顶层工具定义的缓存前缀，实际命中仍取决于 Provider、模型、上下文压缩等因素。当前排序是词项重叠计分，不是 BM25，也不理解同义词。重复查询可继续查看剩余匹配项。应使用包含近义工具和混合语言的目录评估召回，再决定是否引入 BM25 或混合检索。

禁用、卸载或替换已注册工具，或从本次运行的工具集中移除对象时，后续搜索和调用会跳过失效对象；不会中断已经开始的调用。启动钩子之后新增或重新注册的对象在下一次运行进入候选集。后续可在工具描述质量和真实模型评估支持的情况下引入语义排序，也可在 MCP 注册表实现列表变更订阅后复用该来源。

同一运行中，查看过的定义作为工具结果保留在消息历史里，因此频繁查看不同 Schema 仍会增加上下文长度。若切换模型或发生上下文压缩，不能保证缓存命中。

## 验证结果

使用脚本化 Provider 执行三个任务，分别查找 GitHub Pull Request、日历事件和中文闹钟设置。每个目录包含三个目标工具，其余为实验用库存工具。所有工具使用含三个属性的参数 Schema。以 `o200k_base` 对紧凑 JSON 编码，首轮只计工具定义，整任务累加各轮的消息和工具定义。数值未计服务端封装、缓存或输出 Token。

| 目录工具数 | Full 首轮 Schema | Dynamic 首轮 Schema | Full 平均整任务输入 | Dynamic 平均整任务输入 |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 8,393 | 189 | 16,905 | 1,803 |
| 500 | 41,993 | 189 | 84,105 | 1,803 |
| 1,000 | 83,993 | 189 | 168,105 | 1,803 |

三种目录规模中，动态搜索均将目标排在第一位（3/3）。两种模式均完成三个脚本任务。Full 每个任务用两轮，Dynamic 完整执行搜索、描述和调用时用四轮。目标和查询词由脚本预设，因此这些结果验证词项召回和执行闭环。没有用真实 Provider 测量模型选择准确率、任务完成率、缓存读写、延迟或计费。

自动化回归覆盖流式与非流式请求、内置工具、插件、MCP、多轮加载、空目录与无匹配、运行状态重置、Provider 回退、Persona 与插件筛选、同批调用拒绝、参数校验以及运行中工具失效。
