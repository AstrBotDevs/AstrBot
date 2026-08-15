---
outline: deep
---

# 项目架构

本文描述当前 Xero-Team fork 的运行时结构和代码边界。历史教程或上游实现与本页冲突时，以当前仓库代码为准。

## 事实来源

项目不会把某一篇文档当成唯一真相。修改功能时，应同时核对下面这些来源：

| 内容                    | 事实来源                                                                                      |
| ----------------------- | --------------------------------------------------------------------------------------------- |
| 版本号与 Python 要求    | `pyproject.toml`、`astrbot/__init__.py`、`.python-version`                                    |
| Python 依赖             | `pyproject.toml`、`requirements.txt`、`uv.lock`                                               |
| Dashboard 工具链        | `dashboard/package.json`、`dashboard/pnpm-lock.yaml`                                          |
| 文档工具链              | `docs/package.json`、`docs/pnpm-lock.yaml`                                                    |
| 默认配置与 WebUI 元数据 | `astrbot/core/config/default.py`                                                              |
| HTTP API 契约           | `openspec/openapi-v1.yaml`                                                                    |
| 当前上游同步点          | `upstream-sync.yaml`                                                                          |
| 版本化变更记录          | `changelogs/`；它记录已吸收的版本变更，不等同于 fork 已发布资产；更晚提交尚未纳入最新版本记录 |

当前可复现开发与 CI 基线为 Python 3.14.6、Node.js 26.5.0 和 pnpm 11.21.0；Python 包元数据允许 3.14 及以上版本。

## 启动流程

源码入口和 CLI 入口的前置流程并不相同，但最后都会显式创建 `RuntimeServices` 并交给 `InitialLoader`：

- 根目录 `main.py` 先调用 `runtime_bootstrap.initialize_runtime_bootstrap()` 配置受信任 CA，再导入核心模块、应用启动环境参数并校验 Python 与运行目录。Dashboard 解析优先使用显式 `--webui-dir`，然后依次检查版本匹配的源码树 `dashboard/dist`、运行目录 `data/dist` 和包内置资源。它不访问网络，也不会使用版本失配或不完整的静态资源；没有兼容构建时只停用 WebUI。
- `astrbot` CLI 先解析并锁定 CLI runtime root，要求存在 `.astrbot` 标记。CLI 的 `init` 和 `run` 不下载或更新 Dashboard，也不调用根入口的 `runtime_bootstrap`，因此修改启动安全或资源解析时必须分别检查两条路径。
- 两条路径随后都调用 `create_runtime_services()` 创建配置、数据库、共享偏好、HTML 渲染器、文件 token 服务和依赖安装器等实例，再由 `InitialLoader` 初始化 `AstrBotCoreLifecycle`，并行运行核心任务与 FastAPI Dashboard。
- 初始化中途失败时会调用生命周期清理；停止逻辑必须能处理“只初始化了一部分”的状态并允许重复调用。导入 `astrbot.core` 本身不得创建运行时服务或访问用户数据。

## 运行时所有权

`RuntimeServices` 持有一个 AstrBot 进程共享的基础能力：

- `AstrBotConfig`
- `SQLiteDatabase`
- `SharedPreferences`
- 本地 Playwright `HtmlRenderer`
- `FileTokenService`
- `PipInstaller`
- demo mode 状态

`AstrBotCoreLifecycle` 在这些基础服务之上按依赖顺序创建 Provider、Platform、Conversation、Persona、Memory、Knowledge Base、Cron、Plugin、SubAgent 和 Pipeline 等管理器。需要共享这些能力时，应通过现有所有者注入，不要恢复进程级全局单例。

## 消息处理链

平台适配器将消息规范化为 `AstrMessageEvent`，写入最大长度为 1024 的共享事件队列。`EventBus` 根据消息命中的配置文件选择对应的 `PipelineScheduler`，并在并发信号量保护下执行完整流水线。

流水线顺序由 `astrbot/core/pipeline/stage_order.py` 定义：

1. `WakingCheckStage`
2. `WhitelistCheckStage`
3. `SessionStatusCheckStage`
4. `RateLimitStage`
5. `ContentSafetyCheckStage`
6. `PreProcessStage`
7. `ProcessStage`
8. `ResultDecorateStage`
9. `RespondStage`

`ProcessStage` 负责插件处理与 Agent 调用；`ResultDecorateStage` 处理前缀、分段、TTS、本地文转图、引用等结果装饰；`RespondStage` 统一调用平台发送接口。流水线同时支持普通异步 stage 和用异步生成器实现的洋葱式前后处理，修改时必须保留停止传播和收尾语义。

群聊唤醒规则是显式配置。`platform_settings.group_wake_policy` 分别控制“提及机器人”和“回复机器人”是否唤醒，默认都关闭；`WakingCheckStage` 会把实际原因写入事件的 `wake_reasons`。内置命令是否可用则按 handler 存储在命令数据库中；`disable_builtin_commands` 不迁移、不接受配置写入，也不被 Pipeline 读取。

### 指令解析子系统

指令参数由 `astrbot/core/command/` 下的 Orbit Command Syntax 子系统处理。`catalog.py` 为已启用指令、指令组和各级别名建立不可变最长匹配索引；`lexer.py` 实现不执行 expansion 或 operator 的确定性 POSIX word 子集；`schema.py` 在 handler 注册期编译签名；`binder.py` 负责位置参数、option、默认值和类型转换；`engine.py` 统一执行 resolve、lex 和 bind。

插件管理器按 Pipeline 配置显式拥有 `CommandCatalogStore`。插件加载、卸载、重载、启禁，以及 Dashboard 中的指令启禁、重命名和别名修改都会构建新 snapshot 并原子替换引用。`WakingCheckStage` 的消息热路径只读取 snapshot：先完成 wake prefix 移除和最长指令头匹配，命中后只 lex 一次，再按 `handler_full_name` 分别绑定所有匹配 handler。完全未知根指令不会进入 Orbit，因此带 `$`、URL 或不完整引号的普通 LLM prompt 不会被指令解析器拦截。

核心结构化诊断只保存稳定错误码、Unicode code-point span、参数和 hint code；zh-CN/en-US 文本及源码 caret 在展示边界渲染。插件公开入口是 `astrbot.api.command` 以及 `astrbot.api.event.filter` 中的 `option`、`GreedyStr`，内部 catalog、engine 和 handler metadata 不属于插件 API。

## Agent、工具与 Skills

核心 Agent 运行时位于 `astrbot/core/agent/`，主 Agent 的请求组装位于 `astrbot/core/astr_main_agent.py`。Provider 抽象位于 `astrbot/core/provider/`；OpenAI、Anthropic、Gemini 等具体实现位于 `provider/sources/`，并通过 `provider_modules.py` 延迟注册。Dify、Coze、DashScope 和 DeerFlow 属于 `astrbot/core/agent/runners/` 下的外部 Agent Runner，不是普通模型 Provider。

工具来源包括内置工具、插件工具和 MCP 工具。MCP 仅支持 stdio 与 Streamable HTTP；远程 HTTP 默认拒绝 localhost、私网、链路本地和保留地址，只有在可信配置中显式设置 `allow_private_network` 才会放开。

Skills 可来自 `data/skills`、插件 `skills/`、沙盒和当前会话 workspace。工作区 Skill 是请求级资源，默认路径为 `data/workspaces/{normalized_umo}/skills/`。

SubAgent 通过 `transfer_to_*` handoff 工具挂载到主 Agent。启用编排后，主 Agent 默认保留自身工具；只有启用“去重重复工具”时，才会移除与已启用 SubAgent 重叠的工具。

Tool Loop 每完成一次模型调用都会发出 `agent_stats`，包括工具调用前的中间模型轮次；WebChat 将它作为带请求身份的协议事件转发，而不是只在整个 Agent 结束时汇总一次。

## 插件边界

插件称为 Star。内置插件位于 `astrbot/builtin_stars/`，用户插件位于 `<runtime-root>/data/plugins/`。

插件和内置 Star 应使用 `astrbot.api` 提供的 SDK，不应直接依赖具体平台或 Provider source。共享核心只有注册/发现所有者（例如 `astrbot/core/platform/discovery.py` 和 Provider 模块注册表）可以有意导入具体 source；普通共享模块不能绕过这些所有者。`tests/unit/test_import_boundaries.py` 会检查关键绝对导入路径，但不能代替对相对导入和注册所有权的代码审查：

- `astrbot/api/` 不得依赖 Dashboard 或具体 source。
- 共享 `astrbot/core/` 只有注册/发现所有者可以直接导入具体平台或 Provider source。
- `astrbot/builtin_stars/` 不得直接导入具体 source。

插件持久化小数据应使用 Star KV API；在 `Star` 实例中通过 `self.context.storage.data_directory()` 获取 `data/plugin_data/<plugin>` 目录，而不是把文件写到插件源码目录。

插件 Dashboard 页面使用 Extension Protocol v1：metadata 同时声明 `requires.dashboard_extension: 1` 与 `dashboard`，静态资源由带摘要的 `assets.v1.json` 完整列举，Python Action 只能在 `initialize()` 中通过 `astrbot.api.dashboard` 注册。页面运行在只有 `allow-scripts` 的 sandbox iframe 中，特权操作必须经过宿主管理的结构化 Action；不支持旧 Page metadata、任意 HTTP proxy 或直接读取 Dashboard 认证状态。具体契约见[插件 Dashboard 扩展开发指南](/dev/star/plugin-dashboard-extension)。

## Dashboard 与 HTTP API

Dashboard 后端是 FastAPI 应用，使用 Hypercorn 运行。普通 JSON 路由位于 `astrbot/dashboard/api/`，领域操作位于 `astrbot/dashboard/services/`，请求模型集中在 `astrbot/dashboard/schemas.py`。

普通 JSON API 使用 `status` / `message` / `data` envelope，常见状态为 `ok`、`error`，部分显式场景也会返回 `warning`。文件下载、SSE、Webhook、静态资源和其他协议原生响应应使用相应的 FastAPI/Starlette response，不应强制包成 JSON。

所有 `/api/v1` 路由由 `astrbot/dashboard/api/router.py` 汇总。源规范是 `openspec/openapi-v1.yaml`；Dashboard 的 Hey API 客户端和文档站的 `public/openapi.json` 都由它生成，禁止手工修改生成客户端。

Live Chat WebSocket 允许同一连接并发运行多个请求，以唯一 `message_id` 关联任务、响应和 interrupt。follow-up 捕获、`run_started` 与每轮 `agent_stats` 都必须保留原请求身份；不能用 session 级 busy 标志把协议退回单请求串行模型。

## 持久化一致性

`AstrBotConfig.save_config_async()` 在离开事件循环前深拷贝稳定快照，并使用单调递增 revision 提交；较旧但完成较晚的写入不能覆盖较新的配置。异步调用方应使用该接口，保留临时文件、`fsync` 和原子替换语义，不要自行用 `to_thread(save_config)` 拼装并发保存。

知识库上传会跨越媒体文件、文档 metadata、分块存储和 FAISS 向量。向量形状与维度必须在本地写入前校验；metadata 提交前任一步骤失败，都要对已经写入的各存储执行补偿清理，不能让 API 报错后仍留下可检索的半成品文档。

## 运行目录

源码目录和运行时根目录不是同一个概念。运行时根目录默认是当前工作目录，可由 `ASTRBOT_ROOT` 覆盖；Desktop 包使用用户目录下的专用根目录。

常见可变数据位于 `<runtime-root>/data/`：

- `cmd_config.json` 与 `config/`
- `data_v4.db`
- `plugins/` 与 `plugin_data/`
- `skills/` 与 `workspaces/`
- `knowledge_base/`
- `t2i_templates/`
- `backups/`、`temp/`、`webchat/`

`astrbot.core.utils.astrbot_path` 中的运行目录 helper 当前返回字符串；新核心代码做路径运算时应在调用边界包装成 `Path(...)`。不要把这条规则套到已经返回 `Path` 的 CLI helper 或插件存储能力的 `data_directory()`。

## 网络与安全默认值

- WebUI 和内置 Webhook/反向 WebSocket 服务默认只监听 loopback。远程访问必须显式配置监听地址，并配合防火墙、TLS 或可信反向代理。
- `dashboard.trust_proxy_headers` 默认关闭；只有确认前置代理会覆盖客户端提交的转发头时才应开启。
- 下载路径必须验证 TLS，不允许通过 `ssl=False` 或 `verify=False` 静默降级。
- 不可信 XML 使用 `defusedxml` 解析。
- Dashboard 动态 HTML 必须经过 DOMPurify；前端 lint 默认禁止未审计的 `v-html`。
- 面向用户或日志输出的 Agent 异常需要经过敏感信息脱敏。

## 修改位置速查

| 变更类型          | 主要位置                                             | 同步检查                                                    |
| ----------------- | ---------------------------------------------------- | ----------------------------------------------------------- |
| 新消息平台        | `astrbot/core/platform/sources/`                     | discovery、配置元数据、平台文档、发送/清理测试              |
| 新模型 Provider   | `astrbot/core/provider/sources/`                     | `provider_modules.py`、配置元数据、Provider 测试            |
| 新 Agent Runner   | `astrbot/core/agent/runners/`                        | Provider 配置、Runner 文档、工具/流式行为                   |
| Pipeline/唤醒行为 | `astrbot/core/pipeline/`                             | stage 顺序、wake reason、停止传播、流式测试                 |
| 指令语法与绑定    | `astrbot/core/command/`、`astrbot/core/star/filter/` | lexer/binder property tests、catalog 生命周期、原生平台同步 |
| Dashboard API     | `astrbot/dashboard/api/`、`services/`、`schemas.py`  | OpenAPI、生成客户端、前后端测试                             |
| Live Chat 协议    | `live_chat_service.py`、`webchat/`                   | request identity、并发、interrupt、前端状态测试             |
| 插件 SDK/页面协议 | `astrbot/api/`、`astrbot/core/star/`                 | import boundary、插件指南、Vitest、Playwright               |
| 配置持久化        | `astrbot/core/config/`                               | 默认值/metadata、revision、并发保存测试                     |
| 知识库写入        | `knowledge_base/`、`db/vec_db/`                      | 多存储回滚、失败注入、残留文件与可检索性                    |
| NapCat 事件模型   | `scripts/napcat/`                                    | 运行 `make napcat-check`，不要手改 generated model          |
