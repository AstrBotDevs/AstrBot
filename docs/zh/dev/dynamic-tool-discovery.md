# 动态工具发现设计

## 现状和目标

AstrBot 的本地 Agent 由 `build_main_agent` 组装工具集。Persona、会话插件配置、内置能力开关和请求钩子共同决定本次运行有哪些候选工具。插件和已连接的 MCP Server 通过 `FunctionToolManager` 注册工具。内置工具按功能配置加入同一个 `ToolSet`。Provider 将 `ToolSet` 序列化为各自的 Function Calling 格式，`ToolLoopAgentRunner` 将结果交给执行器，再把工具结果追加到后续模型请求。

`full` 每轮发送完整 Schema。`skills_like` 第一次请求发送全量名称和描述，再为模型选中的工具请求参数。两者都要求模型扫过全量清单。MCP 客户端已经会在连接时调用 `tools/list`，并能通过现有执行路径发起 `tools/call`。当前工具管理器在启动和停止 Server 时更新注册表，尚未将远端工具列表变更通知作为实时目录来源。

## 参考实现

| 技术 | 机制 | 对 AstrBot 的意义 |
| --- | --- | --- |
| Anthropic Tool Search | `defer_loading` 加 BM25 或正则搜索，结果以工具引用展开 | 验证延迟加载模式。服务端延迟加载及缓存机制依赖支持该功能的 Anthropic 接口 |
| OpenAI Tool Search | Responses 支持托管搜索和客户端搜索。后者由应用返回工具定义 | 客户端检索适合已有本地注册表和权限规则的应用。协议依赖支持该功能的模型与接口 |
| MCP Tools | `tools/list` 发现元数据，`tools/call` 执行，协议支持列表变更通知 | MCP 提供工具来源和调用协议。AstrBot 负责把工具目录提供给模型 |

- [Anthropic Tool Search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- [OpenAI Tool Search](https://developers.openai.com/api/docs/guides/tools-tool-search)
- [MCP Tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)

## 技术方案

在内置 Agent 执行器的工具模式 `agent.config.misc.tool_schema_mode` 中加入 `dynamic`，默认使用 `full`。内置 SubAgent 和定时或后台任务唤醒读取会话配置。插件直接使用 `Context.tool_loop_agent` 时可显式传入 `tool_schema_mode="dynamic"`。

1. Runner 从已完成请求筛选的 `ToolSet` 获取本次运行的候选。候选在服务端保留，初始模型请求只携带搜索工具。
2. 模型用自然语言描述所需能力。Runner 按名称和描述的词项匹配排序，支持中文词片段。每次最多加载三个匹配项，并在搜索结果中返回工具名。Provider 在下一轮请求中提供这些工具的完整描述和参数 Schema。
3. 模型获得真实的 Function Calling 定义，再按现有执行流程调用工具。搜索在后续轮次仍然可用。工具集随候选被发现而扩充，新的 Agent 运行重新开始搜索。
4. 运行时按实际发给模型的工具集接受调用。即便模型猜到候选名称，也需要先在先前的搜索轮次获得它。工具的可用性和调用参数在执行前校验。插件、MCP 和内置工具沿用各自的权限检查，搜索结果本身只表示工具匹配。JSON Schema 支持本地引用，验证时禁止拉取外部引用。
5. OpenAI Chat Completions、OpenAI Responses、Anthropic Messages、Gemini 等实现继续使用已有的工具序列化。动态变化发生在两次常规 Function Calling 请求之间。模型必须支持 Function Calling，远端 Agent 执行器自行管理工具。

实现与验证按三段推进。首先在 Runner 中验证首轮只提供搜索、多轮注入及工具结果回传。其次验证 Persona 和插件筛选、工具失效、参数与权限限制及 Provider 回退。最后检查 WebUI 配置路径、静态模式回归，并测量大目录下的工具 Schema 开销。实现使用现有 Python 依赖和 pytest，不需要更改外部 API 或存储结构。

## 取舍

词项搜索不需要额外模型、凭据或索引服务。工具名与描述的质量会影响召回，跨语言任务可用工具生态常见的英文关键词重试。搜索本身占用一次模型轮次，工具集合变化可能影响 Provider 的提示缓存。大型目录适合按需加载，工具很少或每次均须使用时可选 `full`。

延迟加载与客户端检索符合现有厂商方案的设计思路，但此处是常规 Function Calling 兼容层，不使用厂商原生的工具引用、缓存保持或命名空间协议。当前排序是词项重叠计分，不是 BM25，也不理解同义词；同样的查询会重复返回同样的三个可用结果。应使用包含近义工具和混合语言的目录评估召回，再决定是否引入 BM25 或混合检索。

禁用、卸载或替换已注册工具时，运行中会跳过失效对象。运行开始后新增或重新注册的对象在下一次运行进入候选集。后续可在工具描述质量和真实模型评估支持的情况下引入语义排序，也可在 MCP 注册表实现列表变更订阅后复用该来源。

同一运行中，后续请求继续携带已加载且可用的定义。每次搜索的三个匹配项是单次上限，运行累计加载量由实际搜索决定。多次查找不同能力时，Token 收益会随工具集扩张而减少。

## 验证结果

使用脚本化 Provider 执行三个任务，分别查找 GitHub Pull Request、日历事件和中文闹钟设置。每个目录包含三个目标工具，其余为实验用库存工具。所有工具使用含三个属性的参数 Schema。以 `o200k_base` 对紧凑 JSON 编码，首轮只计工具定义，整任务累加各轮的消息和工具定义。数值未计服务端封装、缓存或输出 Token。

| 目录工具数 | Full 首轮 Schema | Dynamic 首轮 Schema | Full 平均整任务输入 | Dynamic 平均整任务输入 |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 8,393 | 104 | 16,905 | 967 |
| 500 | 41,993 | 104 | 84,105 | 967 |
| 1,000 | 83,993 | 104 | 168,105 | 967 |

三种目录规模中，动态搜索均将目标排在第一位（3/3）。每种模式的脚本均选择了预设的三个目标工具并完成三个任务。Full 每个任务用两轮，Dynamic 用三轮。目标和查询词由脚本预设，因此这些结果验证词项召回和执行闭环。真实模型的工具选择准确率、任务完成率和计费需单独测量。

自动化回归覆盖流式与非流式请求、内置工具、插件、MCP、多轮加载、空目录与无匹配、运行状态重置、Provider 回退、Persona 与插件筛选、同批调用拒绝、参数校验以及运行中工具失效。
