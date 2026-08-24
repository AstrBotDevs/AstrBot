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
- `astrbot` CLI 先解析并锁定 CLI runtime root，要求存在 `.astrbot` 标记。`astrbot/cli/__main__.py` 与 `astrbot run` 都会调用 `runtime_bootstrap.initialize_runtime_bootstrap()` 安装受信任 CA。CLI 的 `init` 和 `run` 不下载、不更新 Dashboard，也没有 `main.py` 的 `--webui-dir`。因此修改启动安全、runtime root 或 Dashboard 静态资源解析时，仍必须分别检查 `main.py` 与 CLI 两条路径。
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

主 SQLite 库以 SQLModel 表为 schema 真源，访问口是域存储协议，`SQLiteDatabase` 只是组合实现。细节见下文[主 SQLite 库](#主-sqlite-库)。知识库 SQLite 与 FAISS 文档库仍独立于主库。

## 主 SQLite 库

主库文件是 runtime root 下的 `data/data_v4.db`。SQLModel 表是 schema 的唯一真源：表、列、普通唯一约束和普通索引都写在模型上。访问口是 `astrbot/core/db/protocols.py` 中的域存储协议；`SQLiteDatabase` 用 mixin 组合这些协议，调用方仍导入该类。本 fork 不引入 Alembic、sqlc 或主库 `.sql` schema。

`create_runtime_services()` 构造 `SQLiteDatabase(DB_PATH)`。生命周期会显式调用 `db.initialize()`；`get_db()` 保留懒初始化兜底。显式初始化、第一次 `get_db()` 和并发初始化共用同一把锁，schema 工作只执行一次。

### 布局

```text
astrbot/core/db/
  __init__.py              # BaseDatabase 与引擎生命周期
  protocols.py             # 域协议与组合协议
  schema.py                # registry + create_all + PRAGMA
  sqlite.py                # SQLiteDatabase 门面
  po/
    __init__.py            # 再导出 table=True 的模型
    registry.py            # 显式导入全部表模型
    mixins.py              # TimestampMixin
    ...                    # 按域拆分的表模块
  stores/
    session.py             # 会话与事务作用域助手
    ...                    # 每个域协议一个 mixin
```

`po/__init__.py` 再导出表模型，只是包入口。新代码可以写 `from astrbot.core.db.po.memory import MemoryFact`；`from astrbot.core.db.po import MemoryFact` 仍有效。模型注册由 `po.registry.import_all_models()` 显式完成，不能依赖业务模块碰巧导入。`schema.py` 必须先调用它，再执行 `SQLModel.metadata.create_all`。`tests/unit/db/test_schema.py` 用源码内固定的 `EXPECTED_TABLE_NAMES`（当前 35 张表）对照初始化后的数据库表名；registry 漏登时测试必须失败。

`initialize()` 只做：

1. `import_all_models()`
2. `SQLModel.metadata.create_all`
3. WAL / `busy_timeout` / `synchronous` / `cache_size` / `temp_store` / `mmap_size` / `optimize`

它不探测 `PRAGMA table_info`，也不执行 `ALTER TABLE`。`create_all` 只创建缺失表，不会给已有表加列。schema 变更后需要空库重建：停进程，删除 `data/data_v4.db*`，再启动。测试继续使用临时库。将来若确实需要 SQLite 的 `WHERE` 索引，必须把 `Index(..., sqlite_where=...)` 声明在模型上，让 `create_all` 在空库上创建。

Mixin 只通过 `self.get_db()` 拿会话，不直接持有 engine，也不互相导入对方的查询函数。跨域写入由 composite store 或 application/domain service 持有一个事务边界。

### 协议与表

| 协议                   | 表                                                                                                                                                                               | store 模块                        |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| `StatisticsStore`      | `platform_stats`、`provider_stats`                                                                                                                                               | `stores/statistics.py`            |
| `PersonaRuntimeStore`  | `persona_session_states`、expression/jargon/behavior                                                                                                                             | `stores/persona_runtime.py`       |
| `MemoryStore`          | fact/profile/episode/scope policy/tuning task/operation log                                                                                                                      | `stores/memory.py`                |
| `ConversationStore`    | `conversations`；只读 session projection 会 join `preferences`、`personas`                                                                                                       | `stores/conversations.py`         |
| `MessageHistoryStore`  | `platform_message_history`                                                                                                                                                       | `stores/message_history.py`       |
| `WebChatThreadStore`   | `webchat_threads`                                                                                                                                                                | `stores/webchat.py`               |
| `AttachmentStore`      | `attachments`                                                                                                                                                                    | `stores/attachments.py`           |
| `ApiKeyStore`          | `api_keys` + 派生 `auth_capabilities`                                                                                                                                            | `stores/api_keys.py`（同一事务）  |
| `PersonaStore`         | `personas`、`persona_folders`                                                                                                                                                    | `stores/personas.py`              |
| `PreferenceStore`      | `preferences`                                                                                                                                                                    | `stores/preferences.py`           |
| `CommandStore`         | `command_configs`、`command_conflicts`                                                                                                                                           | `stores/commands.py`              |
| `CronStore`            | `cron_jobs`                                                                                                                                                                      | `stores/cron.py`                  |
| `PlatformSessionStore` | `platform_sessions`                                                                                                                                                              | `stores/sessions.py`              |
| `UmoAliasStore`        | `umo_aliases`                                                                                                                                                                    | `stores/aliases.py`               |
| `ChatProjectStore`     | `chatui_projects`、`session_project_relations`                                                                                                                                   | `stores/projects.py`              |
| （无 SQLite 方法）     | `dashboard_accounts`、`auth_role_bindings`、`auth_platform_membership_facts`、`auth_step_up_credentials`、`auth_policy_overrides`、`auth_audit_log`、`dashboard_trusted_devices` | `po/auth.py` 仅建表；授权服务操作 |

组合协议（`ChatStore`、`DashboardStore`、`PluginRuntimeStore` 等）不增加新方法。`tests/unit/db/test_protocols.py` 要求每个公开协程都挂在域协议上。

`get_session_conversations()` 由 `ConversationStore` 所有。它是明确记录的跨域只读例外，会 join `Preference`、`ConversationV2` 和 `Persona`；不要为此新增 projection 协议。

`platform_message_history` 的 `role`、`is_group` 和 `ix_platform_message_history_scope_order` 只存在于模型上，没有“缺列则补”的路径。

### 运行时 DTO

`Conversation` 与 `Personality` 不是表：

- `Conversation` 位于 `astrbot/core/conversation_models.py`，是会话、平台和 agent 共用的中性运行时契约。
- `Personality` 位于 `astrbot/core/persona_runtime/models.py`，与 persona runtime 契约归属一致。

插件 SDK 仍从 `astrbot.api.provider` 导出 `Personality`。`astrbot.core.db.po` 不再导出这两个名字，也不为旧导入提供垫片。

### 授权持久化

角色绑定和 capability 是当前状态表：同一规范化作用域只保留一行，撤销或过期后重新授权执行 revive/upsert；完整变更历史写入 `AuthAuditLog`。

- 角色绑定的全局作用域使用 `GLOBAL_SCOPE_ID`（`__global__`），唯一键为 `(subject_id, scope_type, scope_id, config_id)`，不包含 `role`。
- capability 的“适用于所有配置”使用 `ANY_CONFIG_SCOPE_ID`（`__any_config__`）；具体配置仍保存真实 config id。唯一键为 `(subject_id, action, resource_type, resource_id, config_id)`。
- 领域对象可以用 `None` 表达“未指定”，进入数据库前必须归一化为非空 scope key。不要依赖 SQLite 把多个 `NULL` 当作互不相等。
- `ApiKeyStore` 是 capability 的唯一写入者和事务所有者；`create_api_key()` / `revoke_api_key()` 与派生 capability 必须在同一事务中完成。`AuthorizationService.grant_capability()` 委托 `upsert_capability()`，不得直接 `session.add(AuthCapability(...))`。
- 角色绑定、平台事实、step-up 和审计仍由授权服务通过 `DatabaseSessionStore.get_db()` 操作，不进入 `SQLiteDatabase` 的域方法。

### 测试

测试按协议分文件，位于 `tests/unit/db/`。`test_schema.py` 只锁 schema 契约：35 张表、`platform_message_history` 列与索引、授权唯一约束、WAL/`busy_timeout` 以及幂等初始化。授权行为断言放在 `tests/unit/test_authorization_service.py` 和 `tests/unit/db/test_api_key_store.py`。`tests/conftest.py` 的 `temp_db` 仍是 `SQLiteDatabase`。

## 消息处理链

平台适配器将消息规范化为 `AstrMessageEvent`，写入最大长度为 1024 的共享事件队列。`EventBus` 根据消息命中的配置文件选择对应的 `PipelineScheduler`，并在并发信号量保护下执行完整流水线。

流水线顺序由 `astrbot/core/pipeline/stage_order.py` 定义：

1. `WakingCheckStage`
2. `WhitelistCheckStage`
3. `SessionStatusCheckStage`
4. `RateLimitStage`
5. `ContentSafetyCheckStage`
6. `PreProcessStage`
7. `GroupMessageHistoryStage`
8. `ProcessStage`
9. `ResultDecorateStage`
10. `RespondStage`

`GroupMessageHistoryStage` 在插件处理前持久化非 WebChat 的入站群消息，供 `GetGroupMessageHistoryTool` 使用；私聊和 WebChat 会跳过。`ProcessStage` 负责插件处理与 Agent 调用；`ResultDecorateStage` 处理前缀、分段、TTS、本地文转图、引用等结果装饰；`RespondStage` 统一调用平台发送接口。流水线同时支持普通异步 stage 和用异步生成器实现的洋葱式前后处理，修改时必须保留停止传播和收尾语义。`SessionStatusCheckStage` 在会话关闭时停止事件，但放行已激活的 `/bot status` 和 `/bot enable`，以便从聊天重新打开会话。

群聊唤醒规则是显式配置。`platform_settings.group_wake_policy` 分别控制“提及机器人”和“回复机器人”是否唤醒，默认都关闭；`WakingCheckStage` 会把实际原因写入事件的 `wake_reasons`。内置命令是否可用则按 handler 存储在命令数据库中；`disable_builtin_commands` 不迁移、不接受配置写入，也不被 Pipeline 读取。指令配置以 `command_id`（`{plugin}:{original path}`，空格换成点）为稳定标识；同步时按 `handler_full_name` 再按 `command_id` 认领活 handler，认领失败的行删除。`alter_cmd` 只读取 `command_id` 键，不从 Python 方法名或历史短名迁移。内置指令在 `resolution_strategy` 不是 `manual_rename` 时忽略库中的名字和别名覆盖。未使用的 `keep_original_alias` 列在独立事务中删除，失败不影响启动。

`platform_settings.group_sender_concurrency` 是实验性开关，默认关闭。启用且未开 `unique_session` 时，群聊 LLM 锁可按发送者拆分，不同群友可并行生成；整轮出站仍按群 UMO 排队，本轮强制非流式。对话历史在 `AssistantHistoryCommitter` 内合并并发完整轮次，不复活已截断历史。私聊、WebChat、live、定时任务和主动回复保持原 UMO 串行。

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

## 统一授权系统

命令、Dashboard、WebChat、API Key、工具和插件都进入同一个运行时入口：

```text
authorize(subject, action, resource, context) -> Decision
```

实现位于 `astrbot/core/auth/`。`AuthorizationService` 按固定动作注册表、关系绑定和有限父资源解析放行；未知动作、缺失主体/资源/上下文、策略异常和高风险审计队列满载都 fail closed。`event.role` 不再作为授权依据，`event.is_admin()` 恒为 `False`。运行时不读取 `admins_id`、`tool_permissions`、`disable_builtin_commands`；Dashboard 配置写入会拒绝这些字段。本 fork 不执行旧权限迁移。

跨平台 IM elevation 没有运行时通道。

### 主体、资源和上下文

主体必须带命名空间，例如：

```text
im:<platform-instance>:<bot-account-id>:<sender-id>
dashboard-account:<account-id>
dashboard-session:<session-id>
api-key:<key-id>
plugin:<plugin-id>
agent:<agent-id>
system:<component>
guest:<id>
```

`dashboard-account` 是稳定的控制面主体；`dashboard-session` 只表示当前已认证会话。`plugin:*` 和 `agent:*` 是执行组件，不会自动继承调用者的 `root`/`operator`。显示名、平台昵称、WebChat `username` 和调用方自报 ID 不能作为授权键。`username` 仍是 WebChat/Open API 的兼容字段，属于 caller-declared 数据。

会话资源使用版本化 canonical string `session:v1:<encoded-config-id>:<encoded-umo>`，不改写现有 UMO 路由。入站上下文带有不可变的 `origin_session_resource_id`；默认 `member`、session binding、平台成员事实和会话级工具授权只在该发起会话生效。请求其他会话或命名 `data` 资源默认拒绝。

### 固定角色与关系

角色只表达“主体是谁”，作用域决定“在哪些资源上有权”。当前关系表把 `session_owner`/`session_admin` 解释为 `owner`/`admin`；`viewer`、`editor`、`executor`、`caller` 仍是预留关系。

| 角色                | 作用域                      | 语义                                                       |
| ------------------- | --------------------------- | ---------------------------------------------------------- |
| `root`              | 全局                        | Dashboard 控制面最高身份；账户 CRUD 受 root + step-up 保护 |
| `operator`          | 全局                        | Dashboard 全局运维                                         |
| `instance_operator` | `instance:<config-id>`      | 单个配置档运维                                             |
| `session_owner`     | `session:<config-id>/<umo>` | 当前会话负责人；平台群主只映射到当前会话                   |
| `session_admin`     | `session:<config-id>/<umo>` | 当前会话有限管理                                           |
| `member`            | `session:<config-id>/<umo>` | 普通已识别用户                                             |
| `guest`             | 会话或无资源                | 未认证或匿名 WebChat                                       |

`root` 与 `operator` 只能绑定有效 Dashboard 账户，不能因同名主体出现在 IM 消息中成为群管理权限。当前会话 owner 只可授予/撤销本会话的 `session_admin` 或 `member`，不能委派 owner。平台 owner/admin 事实带 TTL，过期后降级，且从不写入 global/instance binding。

### 稳定动作

动作使用 `domain.verb`。内置命令通过 `@filter.permission("session.manage")` 声明能力，最终仍调用 `authorize()`。高风险动作不能从父动作静默继承。

| 动作                                                      | 默认允许角色                                   | 高风险             |
| --------------------------------------------------------- | ---------------------------------------------- | ------------------ |
| `session.read`                                            | member 及以上（当前会话）                      | 否                 |
| `session.manage`                                          | session_admin 及以上                           | 否                 |
| `session.assign`                                          | session_owner 及以上                           | 跨会话时需更高角色 |
| `provider.use` / `provider.read`                          | member 及以上                                  | 否；凭据永不返回   |
| `provider.manage`                                         | instance_operator 及以上                       | 否                 |
| `provider.credentials.write`                              | instance_operator 及以上                       | 是                 |
| `platform.manage`                                         | instance_operator 及以上                       | 是                 |
| `agent.manage`                                            | session_owner 及以上                           | 部分               |
| `extension.read` / `extension.manage`                     | member / instance_operator 及以上              | 部分               |
| `extension.plugin_install`                                | instance_operator 及以上 + Dashboard step-up   | 是                 |
| `data.manage` / `data.export_all`                         | 资源所有者 / instance_operator 及以上          | 全量导出是高风险   |
| `system.manage`                                           | root；部分只读给 operator                      | 否                 |
| `system.update` / `system.restart` / `system.pip_install` | root + step-up                                 | 是                 |
| `identity.manage`                                         | session_owner 及以上（作用域受限）             | 是                 |
| `identity.operator.write` / `identity.root.write`         | root + step-up                                 | 是                 |
| `dashboard.account.manage`                                | root + step-up                                 | 是                 |
| `filesystem.read` / `filesystem.write`                    | operator、root                                 | 否                 |
| `filesystem.manage`                                       | root + step-up                                 | 是                 |
| `tool.file_read` / `tool.mcp_read`                        | member 及以上                                  | 否                 |
| `tool.local_exec` 等实例工具                              | instance_operator 及以上；WebChat 另需 step-up | 是                 |

插件自定义动作必须使用 `plugin:<plugin-id>:<action>` 命名空间，并通过 `self.context.authz.authorize()` 再次调用核心授权。未声明的插件写操作默认拒绝。工具最终权限是“用户授权 ∩ Persona 工具策略 ∩ 工具自身策略”；子 Agent handoff 不能提升调用者。

### Step-up、审计与 API Key

全局高风险操作只接受 Dashboard 控制面的一次性密码/TOTP step-up，凭证绑定 account、Dashboard `sid`、action、资源和上下文摘要，TTL 不超过 5 分钟，只能原子消费一次。Dashboard 驱动的 WebChat 使用独立的 `/authorization/webchat-step-up`，只覆盖六个实例级工具：`tool.local_exec`、`tool.python_exec`、`tool.file_write`、`tool.browser_control`、`tool.mcp_write`、`tool.computer_use`。Live Voice 不复用该 proof。

拒绝、高风险 allow、step-up 和绑定变更写脱敏审计。高风险 allow 在有界审计队列已满时 fail closed；绑定变更与 step-up 签发在同一业务事务中落库。

API Key 只认显式 capability，运行时不再把 `*` 或 `NULL` scope 扩权。历史 `NULL` 按冻结的 `DEFAULT_API_KEY_SCOPES` 解释，但高风险动作对 API Key 一律拒绝。API Key 不能访问 `system` scope，也不能进入数据文件管理器。capability 写入由 `ApiKeyStore.upsert_capability()` 独占，作用域键在持久化前归一化为非空 sentinel。完整 Dashboard 授权契约在 `openspec/openapi-v1.yaml`；公开 `docs/public/openapi.json` 只包含 API Key 面向路径。授权表的当前状态与审计分离见[主 SQLite 库](#主-sqlite-库)。

平台成员事实只从入站载荷归一化：NapCat/aiocqhttp 使用群消息 `sender.role`；Discord 使用消息上的 `guild.owner_id` 与 `administrator`；Telegram 仅在已带 `status` 时映射；Misskey 仅在房间 owner 匹配时映射。Lark、DingTalk、Kook、Slack、Mattermost、Satori 保持 `member`/`unknown`。QQ 官方、微信公众号、企业微信、个微、Line 和 WebChat 不从平台事实提升。

使用说明见 [WebUI](/use/webui#账户与权限)。插件过滤器示例见[接收消息事件](/dev/star/guides/listen-message-event#权限与动作)。

## Dashboard 与 HTTP API

Dashboard 后端是 FastAPI 应用，使用 Hypercorn 运行。普通 JSON 路由位于 `astrbot/dashboard/api/`，领域操作位于 `astrbot/dashboard/services/`，请求模型集中在 `astrbot/dashboard/schemas.py`。

普通 JSON API 使用 `status` / `message` / `data` envelope，常见状态为 `ok`、`error`，部分显式场景也会返回 `warning`。文件下载、SSE、Webhook、静态资源和其他协议原生响应应使用相应的 FastAPI/Starlette response，不应强制包成 JSON。

所有 `/api/v1` 路由由 `astrbot/dashboard/api/router.py` 汇总。源规范是 `openspec/openapi-v1.yaml`；Dashboard 的 Hey API 客户端和文档站的 `public/openapi.json` 都由它生成，禁止手工修改生成客户端。

Live Chat WebSocket 允许同一连接并发运行多个请求，以唯一 `message_id` 关联任务、响应和 interrupt。follow-up 捕获、`run_started` 与每轮 `agent_stats` 都必须保留原请求身份；不能用 session 级 busy 标志把协议退回单请求串行模型。

### 数据文件管理器

Dashboard 在 `/data` 提供原生运行时 `data/` 文件管理器，不是 iframe 嵌入的 IDE，也不提供终端、代码执行、Git、LSP 或任意宿主机路径访问。实现位于：

- `astrbot/dashboard/api/data_files.py`
- `astrbot/dashboard/services/data_file_service.py`
- `dashboard/src/views/DataFilesPage.vue`

路由使用独立的 `Data Files` OpenAPI tag，不加入 `PUBLIC_OPEN_API_TAGS`。认证复用 `require_dashboard_session_principal`；API Key 一律 403。授权动作为 `filesystem.read`、`filesystem.write` 和 `filesystem.manage`，集合资源是 `Resource.named("filesystem", "collection")`，单路径使用 `object_resource("filesystem", relative_path)`。

`DataFileService` 通过 `get_astrbot_data_path()` 解析根目录。用户路径只接受相对 `data/` 的片段：拒绝绝对路径、空片段、`.`/`..`、控制字符和 Windows 保留名；符号链接只显示元数据，不遍历逃出根目录的目标。分类路径前缀优先于扩展名：`plugins/` 默认只读，需 `filesystem.manage` + step-up 才可写；`plugin_data/` 按普通数据目录处理；`dist/`、`site-packages/`、活跃数据库及其 WAL/SHM 硬只读。root Dashboard session 可以读取 `cmd_config.json` 和 `config/` 原文；`operator` 不能借文件读取绕过 Config API 脱敏。托管配置保存必须走解析、验证、既有配置服务持久化和关联 reload，不能直接写字节。

已实现目录树、元数据、UTF-8 文本读写、创建/重命名/移动/删除、上传下载、二进制预览和递归文件名搜索。文本上限 1 MiB，目录首屏 200 项，单文件上传 32 MiB，单次上传请求 64 MiB。搜索只匹配 basename 和相对路径，最多 100 项，inode 预算 5000，超时 3 秒。读写使用 SHA-256 etag 和同目录临时文件原子替换；冲突返回 409。隐藏文件会显示。demo mode 只读。审计只记录相对路径摘要，不记录文件内容。

使用说明见 [WebUI](/use/webui#数据文件)。

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

| 变更类型          | 主要位置                                                     | 同步检查                                                    |
| ----------------- | ------------------------------------------------------------ | ----------------------------------------------------------- |
| 新消息平台        | `astrbot/core/platform/sources/`                             | discovery、配置元数据、平台文档、发送/清理测试              |
| 新模型 Provider   | `astrbot/core/provider/sources/`                             | `provider_modules.py`、配置元数据、Provider 测试            |
| 新 Agent Runner   | `astrbot/core/agent/runners/`                                | Provider 配置、Runner 文档、工具/流式行为                   |
| Pipeline/唤醒行为 | `astrbot/core/pipeline/`                                     | stage 顺序、wake reason、停止传播、流式测试                 |
| 指令语法与绑定    | `astrbot/core/command/`、`astrbot/core/star/filter/`         | lexer/binder property tests、catalog 生命周期、原生平台同步 |
| Dashboard API     | `astrbot/dashboard/api/`、`services/`、`schemas.py`          | OpenAPI、生成客户端、前后端测试                             |
| 授权策略/绑定     | `astrbot/core/auth/`                                         | 动作注册表、step-up、平台事实、审计、插件 `context.authz`   |
| 数据文件管理器    | `data_files.py`、`data_file_service.py`、`DataFilesPage.vue` | 路径穿越、符号链接、etag、step-up、OpenAPI tag 白名单       |
| Live Chat 协议    | `live_chat_service.py`、`webchat/`                           | request identity、并发、interrupt、前端状态测试             |
| 插件 SDK/页面协议 | `astrbot/api/`、`astrbot/core/star/`                         | import boundary、插件指南、Vitest、Playwright               |
| 配置持久化        | `astrbot/core/config/`                                       | 默认值/metadata、revision、并发保存测试                     |
| 主 SQLite 库      | `astrbot/core/db/`                                           | 域协议、SQLModel 表、schema 初始化、`tests/unit/db/`        |
| 知识库写入        | `knowledge_base/`、`db/vec_db/`                              | 多存储回滚、失败注入、残留文件与可检索性                    |
| NapCat 事件模型   | `scripts/napcat/`                                            | 运行 `make napcat-check`，不要手改 generated model          |
