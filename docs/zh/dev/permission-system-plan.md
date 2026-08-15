# AstrBot 平台无关统一权限系统实现计划

**状态**：已实现（统一授权系统 v1；本文同时作为迁移与运维说明）

**审计基线**：2026-08-13，基于当前 `Xero-Team/AstrBot` 工作树

**目标版本**：当前分支已完成 v1 阶段；固定角色、显式 action/resource/context、Dashboard step-up、审计和控制面均已启用。跨平台 IM elevation 明确不属于 v1。

实现说明：本分支没有存量用户，不执行旧权限迁移，也不保留旧字段清理路径。
Dashboard 配置写入会明确拒绝 `admins_id`、`tool_permissions`、
`disable_builtin_commands`；运行时授权不会读取这些字段。
WebChat/Open API 的 `username` 字段继续兼容，但它是 caller-declared 数据，不是认证主体。

对话导出属于 Dashboard 控制面高风险操作：必须对精确的
`conversation:export` 资源取得一次性的 `data.export_all` step-up 凭证。
Dashboard 导出对话框会在下载前请求该凭证；持有普通 `data` scope 的 API Key
始终会被拒绝。

备份下载是受 `system.manage` 保护的普通 Dashboard API 下载，和其他备份路由
一样必须经过运行时授权服务。前端通过已认证的 Blob 请求下载，不会把 Dashboard
JWT 放入查询参数；API Key 不能访问 `system` scope。

Dashboard Extension Protocol 控制面同样必须经过运行时授权服务：目录和页面
会话要求 `extension.read`，每个已注册 Action 都在插件处理器执行前按其声明的
API scope 授权。Extension API 不会创建独立角色模型，也不存在测试或运行时的
隐式绕过。

插件安装和远程更新同样必须对 `dashboard-api:post-plugin` 取得
`extension.plugin_install` 的一次性 step-up 凭证；核心更新、pip 安装和重启则
分别绑定 `system:core-update`、`system:pip-install`、`system:restart` 资源和
`system.update`、`system.pip_install`、`system.restart` action。API Key 不能调用
这些高风险操作。

## 0. 2026-08-14 验收修订

本次验收修复并强制以下边界：

- 所有新建 session binding 一律保存为版本化 canonical session resource；本分支没有 pre-canonical binding 存量，因此启动时不迁移或合并旧记录。
- 入站会话上下文带有不可变的 `origin_session_resource_id`。默认 `member`、session binding、平台成员事实和会话级工具授权只在该发起会话生效；请求其他会话或命名 `data` 资源默认拒绝。
- `root` 与 `operator` 是 Dashboard 控制面身份，不能因同名主体出现在 IM 消息上下文而成为群管理权限。当前会话的 owner 只可授予/撤销 `session_admin` 或 `member`，不能委派 owner 或修改其他作用域。
- Dashboard 的每一次绑定授予、单条撤销和账户修改都对精确目标资源消费一次性 step-up。批量撤销则把排序后的完整 binding 快照摘要作为资源，单次密码或 TOTP 验证只能消费该集合，不能重放到其他集合或逐条复用。
- 拒绝、高风险决策、step-up 和绑定变更均写脱敏审计；高风险 allow 在有界审计队列已满时 fail closed。绑定变更与 step-up 签发同时写入业务事务，避免安全变更已提交而审计丢失。

`openspec/openapi-v1.yaml` 是 Dashboard 授权接口的完整契约。`docs/public/openapi.json` 刻意只包含 API Key 面向的公开接口，因此不发布 Dashboard-only Authorization 控制面路径。

## 1. 摘要

AstrBot 当前的权限判断主要是 `ADMIN` / `MEMBER` 二元模型。它能覆盖简单的“管理员指令”，但无法表达“某个用户只管理某个群”“Dashboard 控制面身份”“普通用户可以使用模型但不能修改模型凭据”等实际需求。更严重的是，平台适配器和管道都可能写入 `event.role`，而 `AstrMessageEvent.is_admin()` 又把 `role == "admin"` 当成 AstrBot 管理员，存在平台角色与 AstrBot 身份混用的风险。

本文是当前实现和迁移契约。Dashboard step-up、多 Dashboard 账户、API Key principal、插件命名空间和异步审计均已纳入同一运行时授权入口；跨平台一次性 elevation 保留为后续设计，不提供运行时通道。任何迁移都不得扩大现有主体的权限范围，也不得破坏现有 WebChat/Open API 的兼容契约。

本计划将权限收敛到一个平台无关的授权服务：

```text
authorize(subject, action, resource, context) -> decision
```

其中：

- **subject** 是经过规范化的调用主体，例如 IM 用户、Dashboard 会话或 API Key；
- **action** 是稳定的能力标识，例如 `provider.manage`；
- **resource** 是受保护资源，例如 `session:<config-id>/<umo>` 或 `provider:<config-id>/<id>`；
- **context** 保存当前消息、平台角色、认证方式、配置档和提权信息；
- **decision** 至少包含 `allow`、`deny`、`reason`、`requires_step_up` 和审计关联 ID。

角色只表达“主体是谁”，作用域决定“主体在哪些资源上有权”。全局身份和会话身份必须分开：

```text
root/operator                         全局作用域（第一阶段仅预留）
instance_operator                     instance:<config-id> 作用域
session_owner/session_admin/member    session:<config-id>/<umo> 作用域
guest                                 未认证或受限作用域
```

第一版固定内置角色，不提供任意角色继承和角色定义 CRUD；提供主体角色绑定的增删改查、过期和审计，并已提供受 root 保护的 Dashboard 账户 CRUD。跨账户的 root/operator 绑定策略仍受固定角色和最后一个 root 保护约束。

## 2. 当前实现审计

| 位置                                                              | 当前行为                                                                   | 主要问题                                                       | 迁移要求                                                                                  |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `astrbot/core/star/filter/permission.py`                          | 只有 `PermissionType.ADMIN` 和 `PermissionType.MEMBER`                     | 无动作、资源和作用域信息                                       | 替换为动作授权过滤器；移除二元判断作为核心模型                                            |
| `astrbot/core/pipeline/waking_check/stage.py`                     | 历史实现曾根据 `admins_id` 设置 `event.role`                               | 配置档管理员身份依赖消息事件字段                               | 当前实现只挂载规范化 `subject`，由授权服务读取显式绑定                                    |
| `astrbot/core/platform/astr_message_event.py`                     | `is_admin()` 只判断 `event.role == "admin"`                                | 无法区分平台群管理员和 AstrBot operator                        | 改为 `event.authz.require(...)` 或 `event.has_capability(...)`                            |
| `astrbot/core/platform/sources/napcat/napcat_platform_adapter.py` | 将 QQ 的 `sender.role` 直接写入 `event.role`                               | QQ 群管理员可能被当成 AstrBot 管理员                           | 保存到带来源和 TTL 的平台成员事实，禁止写入全局角色字段                                   |
| `astrbot/core/config/default.py`、`commands/admin.py`             | 历史配置曾保存 `admins_id`                                                 | 不能表达会话范围和过期时间；直接升级为全局 operator 会扩大权限 | 当前分支不读取、迁移或清理该字段；配置档级管理员只能通过显式绑定授予                      |
| `builtin_stars/builtin_commands/main.py`                          | Provider、Model、Chat、Persona、Plugin、Admin 等大量命令要求 `ADMIN`       | 管理能力过粗，无法区分当前会话与全局配置                       | 按能力域映射到 `session.*`、`provider.*` 等动作                                           |
| `astrbot/core/tools/function_tool_manager.py`                     | 历史非内置工具默认要求 admin，可由 `tool_permissions` 降为 member          | 配置粒度和统一授权服务不一致                                   | 当前工具声明所需动作并统一调用授权服务                                                    |
| `astrbot/core/tools/computer_tools/*`                             | `computer_use_require_admin` 控制 Computer Use                             | 只支持全局 admin，无法绑定会话/操作者                          | 映射到 `tool.local_exec` 等高风险动作                                                     |
| `astrbot/dashboard/api/auth.py`                                   | Dashboard JWT、Cookie、账户级 TOTP、限流和 API Key scope                   | 高风险操作必须绑定账户和 step-up                               | 使用稳定 `account_id` 与 Dashboard session 主体；账户和 root/operator 绑定由授权 API 管理 |
| `astrbot/dashboard/services/api_key_scopes.py`                    | API Key 使用固定基础 scope                                                 | scope 是接口访问能力，不应直接当作角色                         | 建立 scope 到 action 的显式映射，禁止隐式扩权                                             |
| `astrbot/core/platform/sources/webchat/webchat_adapter.py`        | WebChat `username` 作为 sender 和 session owner；Open API 也公开接受该字段 | 这是现有公开契约，不能把它当认证主体                           | 保留兼容字段，但不赋予 Dashboard 或管理员权限；新接口使用不可伪造的认证主体               |
| Persona/子 Agent 工具选择                                         | 部分路径可能绕过非内置工具权限包装                                         | 模型或插件可能间接获得高风险工具                               | 所有工具执行前再次经过核心授权检查                                                        |

当前命令和 Dashboard API 的数量较多，不应为每一条 URL 或命令创建一个角色。稳定的授权边界应由能力域表达，命令和路由只是能力的调用入口。

## 3. 设计目标与非目标

### 3.1 目标

1. 平台无关：核心只依赖规范化主体、UMO/session 资源和平台能力声明，不依赖 QQ、微信等具体 API。
2. 作用域明确：群主/群管理员只影响当前会话；`instance_operator` 只影响对应配置档；root/operator 是预留的全局控制面身份。
3. 最小权限：区分“使用 Provider”和“修改 Provider 凭据”，区分“查看数据”和“导出全部数据”。
4. 统一入口：内置命令、Dashboard、WebChat、API Key、工具和插件都调用同一个授权服务。
5. 可 step-up、可审计：第一阶段使用 Dashboard 密码/TOTP step-up；跨平台一次性提权凭证属于后续阶段。拒绝和高风险操作必须可审计。
6. 无迁移扩权：本分支不从旧 `admins_id`、命令权限或工具权限创建授权绑定。
7. 默认安全：缺少主体、资源或策略时默认拒绝；平台角色无法自动产生 `instance_operator`、global operator 或 root。

### 3.2 非目标

- 第一版不实现任意自定义角色、角色继承、Deny 规则和策略脚本。
- 不把操作系统 root 权限当作 AstrBot 授权的替代品；AstrBot 进程仍必须以最小 OS 权限运行。
- 不把 Dashboard API Key scope、平台角色或插件声明直接视为全局管理员。
- 不在插件中复制一套权限数据库或绕过 AstrBot 核心授权服务。
- 不通过 `session_id` 单独推断用户身份；身份和资源必须分离。

## 4. 核心模型

### 4.1 主体 Subject

主体 ID 必须带命名空间，避免不同平台的同名 ID 冲突：

```text
im:<platform-instance>:<bot-account-id>:<sender-id>
dashboard-session:<session-id>
api-key:<key-id>
plugin:<plugin-id>
agent:<agent-id>
system:<component>
```

实现要求：

- IM 主体由适配器提供平台、机器人账户/配置档和 sender ID，经核心规范化后使用。
- Dashboard 请求同时携带已验证的 JWT session 和稳定的 `dashboard-account:<account_id>` 主体；不得凭用户名推断 root。旧的无账户 claim token 只作迁移期兼容，不能获得新的账户管理权限。
- API Key 主体使用数据库中的 `key_id`，不能使用原始密钥或调用方自报名称。
- `plugin:*` 和 `agent:*` 只能代表执行组件，不能因为组件身份自动获得 root；其最终权限仍受发起请求的用户和工具策略约束。
- 主体显示名、平台昵称和 sender ID 只能用于展示和审计，不能作为唯一授权键。

### 4.2 资源 Resource

第一版资源类型：

```text
instance:<config-id>
session:<config-id>/<umo>
provider:<config-id>/<provider-id>
model:<config-id>/<provider-id>/<model-id>
plugin:<plugin-id>
tool:<tool-id>
data:<namespace>/<id>
identity:<subject-id>
step-up:<request-id>
elevation:<request-id>  # 后续跨平台审批
```

`unified_msg_origin`（UMO）继续作为消息路由、历史和插件兼容的传输标识。授权层不改写现有 UMO 格式，而是使用结构化的 `(config_id, umo)` 资源并生成版本化 canonical string，例如 `session:v1:<encoded-config-id>:<encoded-umo>`。内部 `session_id` 可以作为上下文和索引，但不能脱离平台、机器人账户和配置档单独作为跨平台身份。资源规范化函数必须：

1. 拒绝空值、未解析的外部 URL 和未验证的跨配置档标识；
2. 对同一 `(config_id, UMO)` 产生稳定、可比较的 canonical string；
3. 在审计中同时保存 `config_id`、platform、group/private 类型和原始 session 标识的脱敏摘要；
4. 在跨会话操作中显式要求目标 `session:<config-id>/<umo>`，禁止从消息文本拼接目标资源。

### 4.3 上下文 Context

`AuthContext` 至少包含：

```python
subject
resource
action
config_id
platform
platform_member_role  # owner/admin/member/unknown，仅当前会话声明
message_type  # private/group/webchat/dashboard/api
authenticated  # 是否经过可信认证
source  # im/dashboard/api_key/plugin/system
request_id
step_up_id  # 第一阶段可选；与 Dashboard session 绑定
```

平台角色必须标注来源和可信度。它是会话内的事实输入，不是全局 AstrBot 角色。

### 4.4 决策

```python
class Decision(NamedTuple):
    allowed: bool
    subject: Subject
    action: str
    resource: Resource
    effective_role: str | None
    reason: str
    requires_step_up: bool = False
    audit_id: str | None = None
```

授权顺序固定为：认证主体校验 -> 资源规范化 -> 角色绑定/平台事实解析 -> 动作策略判断 -> step-up/elevation 凭证校验 -> 审计事件。任何一步缺失或异常都按拒绝处理，且不得把内部异常直接返回给用户。普通低风险 allow 不要求同步写 SQLite；拒绝、高风险动作、角色变更、step-up/elevation 和异常必须进入异步审计队列，队列不可用时写入受限的运行时安全日志，写操作仍 fail closed。

## 5. 固定角色和作用域

### 5.1 角色定义

| 角色                | 作用域                      | 语义                                                       | 默认可做的事                                             | 明确不能做的事                                 |
| ------------------- | --------------------------- | ---------------------------------------------------------- | -------------------------------------------------------- | ---------------------------------------------- |
| `root`              | 全局                        | 显式绑定的控制面最高身份；账户 CRUD 受 root + step-up 保护 | 仅在显式配置和 step-up 后执行最高风险动作                | 仍受 OS、平台 Bot Token 和外部服务限制         |
| `operator`          | 全局                        | Dashboard 账户模型的全局运维管理员                         | 全局配置、Provider/平台/插件/数据/系统运维               | 只能显式绑定到有效 Dashboard 账户              |
| `instance_operator` | `instance:<config-id>`      | 显式授予的配置档运维身份                                   | 对应配置档的管理动作                                     | 不能管理其他配置档或全局身份                   |
| `session_owner`     | `session:<config-id>/<umo>` | 当前群的群主、会话所有者或显式绑定的会话负责人             | 当前会话管理、会话内 Provider/模型选择、会话成员角色管理 | 不能修改全局 Provider 凭据、系统升级或全局身份 |
| `session_admin`     | `session:<config-id>/<umo>` | 当前群的平台群管理员或显式绑定的会话管理员                 | 当前会话的有限管理、任务控制、策略允许的提权请求         | 不能默认管理其他会话或授予 operator            |
| `member`            | `session:<config-id>/<umo>` | 普通已识别用户                                             | 普通对话、本人会话数据和被允许的插件动作                 | 不能执行管理动作或发起高风险提权               |
| `guest`             | 会话或无资源                | 未认证、匿名 WebChat、无法验证平台身份的主体               | 仅公开/匿名允许的能力                                    | 默认不能写入配置、读取他人数据或提权           |

角色优先级只用于展示，不作为跨作用域授权判断。授权必须同时匹配动作、资源和绑定作用域：

```text
root > operator > instance_operator > session_owner > session_admin > member > guest
```

不能只取“用户最高角色”后忽略资源。全局 `operator` 不会隐式继承到 IM 会话；配置档管理员只在对应 `instance:<config_id>` 作用域生效。一个群主在自己的 `(config_id, UMO)` 是 `session_owner`，在另一个群仍按该资源重新解析。

### 5.2 角色来源

角色绑定来源按可信度排序：

1. root/operator 在 Dashboard 中创建的显式绑定；账户管理和绑定变更受 root + step-up 保护；
2. 显式授予的配置档级绑定；
3. 平台适配器在当前群消息中提供的 owner/admin 声明；
4. 会话创建者或平台无法确认时的默认 `member`/`guest`。

平台 owner/admin 声明只允许映射为当前 `(config_id, UMO)` 的 `session_owner`/`session_admin`。如果平台 API 暂时不可用，不能保留上一次的高权限声明而无限期使用；应使用短 TTL 缓存并在过期后降级。

## 6. 稳定能力域

能力命名采用 `domain.verb`，必要时在资源中携带对象 ID。第一版建议固定以下能力：

| 能力                         | 说明                                                                | 默认允许角色                                                           | 高风险/提权              |
| ---------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------- | ------------------------ |
| `session.read`               | 查看当前会话 ID、状态、有限历史和统计                               | member 及以上（仅本人/当前会话）                                       | 否                       |
| `session.manage`             | 重置、停止任务、改名、创建/删除会话、修改会话变量                   | session_admin 及以上；本人资源可按策略开放 member                      | 否/部分                  |
| `session.assign`             | 为当前或其他会话指定 Provider、模型、Persona 或策略                 | session_owner、instance_operator、operator、root                       | 是，跨会话时必须提权     |
| `provider.use`               | 使用已允许的 Provider、模型、STT/TTS                                | member（仅调用）或 session_admin，按配置                               | 否                       |
| `provider.manage`            | 新增、修改、删除 Provider 和模型（不含凭据）                        | instance_operator、operator、root                                      | 否                       |
| `provider.credentials.write` | 新增、替换或删除 Provider 凭据                                      | instance_operator、operator、root                                      | 是                       |
| `platform.manage`            | 修改平台连接、Bot、Webhook 和平台级动作                             | instance_operator、operator、root                                      | 是                       |
| `agent.manage`               | Persona、SubAgent、Cron、主动消息和 Agent 编排                      | session_owner（当前会话）、instance_operator、operator、root           | 部分                     |
| `extension.manage`           | 插件启停/删除、MCP、Skill、工具目录和权限                           | instance_operator、operator、root                                      | 部分                     |
| `data.manage`                | 知识库、Memory、文件、跨用户历史、备份和导出                        | 资源所有者可读写本人数据；instance_operator/operator/root 按作用域管理 | 全量导出/删除是高风险    |
| `system.manage`              | 更新、pip 安装、重启、诊断、日志和运行时设置                        | root；部分只读给 instance_operator/operator                            | 更新、pip、重启必须提权  |
| `identity.manage`            | 角色绑定、后续 operator 管理、step-up/elevation 策略和 API Key 管理 | instance_operator 管理配置档低级绑定；后续 root/operator 管理全局身份  | 敏感身份变更必须 step-up |

以下高风险动作必须单独标记，不能仅因拥有上层能力而静默放行：

```text
identity.operator.write
identity.root.write
extension.plugin_install
tool.mcp_write
system.update
system.restart
system.pip_install
tool.local_exec
tool.file_write
data.export_all
provider.credentials.write
```

能力判断应支持资源约束，例如 `provider.use` 可以允许用户在当前会话使用一个白名单模型，但不允许读取 Provider API Key；`data.manage` 可以允许用户删除自己的 Memory，但不允许读取其他用户的原始记录。

## 7. 现有命令映射

内置命令迁移时不再直接使用 `PermissionType.ADMIN`，而是为 handler 声明稳定能力。建议映射如下：

| 现有命令/命令组                                   | 新动作                                        | 默认范围                                                                  |
| ------------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------------------- |
| `/session info`                                   | `session.read`                                | 当前 `(config_id, UMO)`                                                   |
| `/session name`                                   | `session.manage`                              | 当前 `(config_id, UMO)`；session_admin+                                   |
| `/conversation reset/create/switch/rename/delete` | `session.manage`                              | 当前用户拥有或当前 `(config_id, UMO)`；删除他人会话需更高角色             |
| `/conversation create-for`                        | `session.assign` + `session.manage`           | 目标 `(config_id, UMO)`；instance_operator 或明确的 session_owner         |
| `/task stop`                                      | `session.manage`                              | 当前 `(config_id, UMO)`；默认允许发起者停止自己的任务                     |
| `/provider list`、`/model list`                   | `provider.use` 或 `provider.read`             | 当前配置档；凭据永不返回                                                  |
| `/provider set ...`、`/model set`                 | `provider.use`；跨会话时追加 `session.assign` | 当前 `(config_id, UMO)`                                                   |
| `/chat status/enable/disable`                     | `session.manage`                              | 当前 `(config_id, UMO)`                                                   |
| `/admin list`                                     | `identity.manage`（只读）                     | 当前配置档身份列表；instance_operator 可读，写操作另行限制                |
| `/admin grant/revoke`                             | `identity.manage`                             | 管理当前配置档的 session 绑定；root/operator 绑定只能由受保护的控制面管理 |
| `/persona *`                                      | `agent.manage`                                | 当前 `(config_id, UMO)` 或显式 Persona 资源                               |
| `/plugin list/show`                               | `extension.manage`（只读）或 `extension.read` | 可按安装信息脱敏开放                                                      |
| `/plugin enable/disable`                          | `extension.manage`                            | 配置档插件或显式插件资源                                                  |
| `/plugin install`                                 | `extension.plugin_install`                    | instance_operator 或控制面身份 + Dashboard step-up                        |
| `/variable set/unset`                             | `session.manage`                              | 当前 `(config_id, UMO)`                                                   |

命令权限配置数据库可以继续作为“命令到动作”的来源，但最终执行必须调用授权服务。迁移完成后，命令配置不应再产生一个绕过资源检查的全局 `admin` 分支。

## 8. Dashboard、WebChat 和 API Key

### 8.1 Dashboard 登录

- Dashboard JWT session 解析为 `DashboardPrincipal(username, sid, jti, account_id, auth_strength, issued_at)`；业务代码不能凭 `username == "astrbot"` 推断 root。
- Dashboard 控制面身份来自受保护的账户表和角色绑定；账户 CRUD 由 root 权限和 step-up 保护。
- Dashboard 驱动的 WebChat 请求保留控制面认证主体与 caller-declared username 两个字段，不能把后者当成普通 IM 身份或授权依据。
- 需要 step-up 的操作要求最近一次 TOTP/密码重新验证，不能只依赖仍未过期的长时 JWT。

### 8.2 WebChat

- WebChat 继续使用现有 `webchat!<username>!<conversation-id>` 会话编码；授权资源另行包装为 `(config_id, umo)`，不直接修改历史和路由数据。
- 现有 WebChat/Open API 的 `username` 请求字段在兼容版本中继续存在，但仅作为 caller-declared identity；不能把它当作 JWT/API Key 的认证主体，也不能凭它获得管理员权限。
- Dashboard 支持多个账户；匿名 WebChat 为 `guest`，已认证请求同时保留 `dashboard-session:<sid>` 和 `dashboard-account:<account_id>` 两个主体层次。
- WebChat 内的提权批准应在同一已认证 Dashboard 会话或专用私聊会话完成，不能通过公开群消息确认。
- 项目、会话、文件等现有 owner 校验保留，但改为授权服务的资源检查，避免“项目 owner 校验”和“系统权限校验”产生冲突。

### 8.3 API Key

现有 API Key scope 继续作为调用面能力，但必须显式映射到动作：

| 现有 scope                     | 新动作映射（示例）                                                     |
| ------------------------------ | ---------------------------------------------------------------------- |
| `provider`                     | `provider.use`、有限 `provider.read`                                   |
| `config`                       | `platform.manage`、`provider.manage` 的非凭据读取部分                  |
| `chat`                         | `session.read`、`session.manage` 的 API 允许部分                       |
| `persona`                      | `agent.manage` 的 Persona 子集                                         |
| `plugin`、`mcp`、`skill`       | `extension.manage` 对应读取/管理子集；安装和 MCP 写入另需高风险 action |
| `kb`、`memory`、`data`、`file` | `data.manage` 对应资源范围                                             |

旧 scope 不应直接转换为 `operator` 角色。API Key 的资源范围、来源账户和过期时间必须进入 `AuthContext`；历史 `NULL` scope 按当前已有语义保留，但新增敏感动作不能因为历史 key 而自动获得。Open API 的 `username` 只是 caller-declared 字段，不应被误标为 API Key 的认证主体。

## 9. 平台角色归一化

适配器接口新增或统一以下字段：

```python
event.subject
event.resource
event.platform_member_role  # owner/admin/member/unknown，仅当前消息事实
event.platform_role_source  # adapter/api/cache/none
event.platform_role_expires_at
```

规则：

1. `event.role` 不再作为 AstrBot 全局权限字段；迁移期间发现写入必须报诊断日志。
2. NapCat、OneBot、Discord、Telegram、Lark、DingTalk 等能提供群角色的平台，将角色作为带来源和 TTL 的 `PlatformMembershipFact`，只在当前 `(config_id, UMO)` 解析为 session 角色。
3. 不能提供稳定群角色的平台统一为 `member` 或 `unknown`，不猜测群主身份。
4. 私聊没有群主/群管理员角色；会话创建者是否为 `session_owner` 必须由明确的会话策略决定，不能从 sender ID 自动推断全局身份。
5. 平台返回的字符串、数字和枚举值都先经过适配器级白名单归一化，未知值降级为 `unknown`。
6. 角色事实缓存必须按平台实例、机器人账户、群 UMO 和用户主体分区，并设置过期时间；不能把 QQ 群角色缓存用于微信或其他群，也不能把过期事实写成永久 role binding。

## 10. Step-up 与后续提权协议

v1 只实现 Dashboard 控制面的短时 step-up（重新验证密码/TOTP）和高风险动作拒绝审计，不实现跨平台 IM 审批。IM 私聊审批、控制面通知和一次性 nonce 属于后续设计，当前运行时不生成或接受 elevation 凭证。`requires_step_up` 表示“需要 Dashboard step-up”。

第一阶段的 step-up 是一次性、短时、绑定 Dashboard session、动作、资源和上下文摘要的操作凭证，不是把用户永久加入管理员列表。第一阶段记录 `step-up_id`、新鲜度、验证方式和消费状态。以下字段仅作为后续设计记录，不属于 v1 持久化模型：

```text
request_id
subject_id
requested_action
resource_id
requested_from
approval_channel
nonce_hash
created_at / expires_at
status: pending/approved/denied/expired/consumed/cancelled
approved_at / consumed_at
request_context_digest
```

### 10.1 后续 elevation 发起策略

- `member` 和 `guest` 默认不能发起高风险提权请求；命令提供者可选择静默失败或返回通用的“无权限”提示，但两种结果都必须审计。
- `session_admin` 可以请求当前 `(config_id, UMO)` 内允许的会话管理动作。
- `session_owner` 可以请求当前 `(config_id, UMO)` 的会话级高风险动作。
- `instance_operator` 只能请求对应配置档内允许的动作。
- 后续的 `operator` 可以请求全局运维动作，但不能通过自助提权获得 root 或授予自己 operator。
- 后续的 `root` 可直接执行，或作为审批者批准其他主体。

后续阶段的 `elevation.request`、`elevation.approve`、`elevation.execute` 分开鉴权。审批者的有效角色必须覆盖目标动作和资源；不能因为审批者“能看见请求”就能批准请求。第一阶段只记录 step-up 事件，不提供 IM 审批者。

### 10.2 第一阶段 step-up 流程

1. 第一阶段仅允许 Dashboard 控制面提交需要 step-up 的动作；IM、插件和 Agent 遇到高风险动作直接拒绝并审计。
2. Dashboard step-up 返回短 TTL（建议 5 分钟）的、绑定 session/action/resource/context digest 的一次性凭证；v1 不生成 IM 可执行 nonce。
3. 服务端重新验证密码或 TOTP，并检查最近验证时间、Dashboard session、动作、资源和上下文摘要。
4. step-up 凭证只能消费一次；动作、资源、session 或上下文变化均拒绝并审计。

### 10.3 后续跨平台 elevation 流程（未实现）

后续阶段才发送通知卡片、批准请求、原子消费 nonce 并执行跨平台 elevation。该流程必须满足本节末尾的私聊能力约束，不能在第一阶段实现半套 IM 审批。

### 10.4 不支持私聊的平台（后续设计）

平台无关设计不能假设每个平台都有机器人私聊能力：

- 首选该平台的私聊；
- 没有私聊能力时，转为同一已认证 Dashboard/WebChat 控制面的待审批通知；
- 如果平台既没有私聊也没有可信控制面，提权请求必须失败，不允许在公开群里发送可执行 nonce；
- 审批通知不能包含可直接泄露的 API Key、文件路径或完整会话历史。

## 11. 插件和工具接口

### 11.1 插件鉴权 API

插件只声明自己的业务动作，动作名必须使用插件命名空间：

```text
plugin:<plugin-id>:<action>
```

插件通过 AstrBot API 调用授权服务：

```python
decision = await context.authz.authorize(
    subject=event.subject,
    action="plugin:example:publish",
    resource=authz.session_resource(
        config_id=event.get_extra("config_id"),
        umo=event.unified_msg_origin,
    ),
    context=event.auth_context,
)
if not decision.allowed:
    if decision.requires_step_up:
        # Dashboard routes must complete the step-up flow before retrying.
        return
    return
```

核心负责主体/资源规范化、授权、提权和审计。插件可以选择未授权时静默或显式响应，但不能自行修改角色绑定、伪造 subject、复用其他事件的授权上下文或直接访问权限表。

插件元数据建议声明：动作 ID、描述、默认风险级别、所需资源类型和是否允许提权。未声明的插件写操作默认拒绝，避免插件安装后获得隐式能力。

### 11.2 工具和 Agent

- 每个 Function Tool 注册 `required_actions` 和资源解析器；执行入口再次调用授权服务，不能只在模型选择工具时检查一次。
- Shell、Python、本地文件写入、浏览器控制、上传/下载、MCP 写操作分别映射到高风险动作，不再由单一 `computer_use_require_admin` 开关决定全部行为。
- Persona/子 Agent 的工具白名单是附加约束，不是授权替代品；最终权限为“用户授权 ∩ Persona 工具策略 ∩ 工具自身策略”。
- Agent handoff 传递原始主体、资源和取消上下文；子 Agent 不能把自己的身份升级为调用者 root。

## 12. 持久化模型

建议在现有 SQLite 数据库中新增独立表，表名可按项目数据库命名规范调整。第一阶段只需要角色绑定、平台事实和高风险审计；提权表在跨平台审批立项时再加入：

### 12.1 `auth_role_bindings`

```text
binding_id           主键
subject_id           规范化主体 ID
role                 root/operator/instance_operator/session_owner/session_admin/member/guest
scope_type           global/session/instance/resource
scope_id             例如 config-id 或 UMO
config_id            配置档隔离键，可为空
source               explicit/migrated/default
expires_at           可为空；平台角色建议必须有 TTL
created_by           创建者主体
created_at / updated_at
revoked_at / revoked_by
    metadata_json        绑定备注、迁移版本和来源摘要
```

约束：同一主体在同一作用域只能有一个有效绑定；`root`/`operator` 只能绑定到有效的 Dashboard 账户；平台事实不能写入 role binding，也不能写入 global scope。

### 12.2 `auth_platform_membership_facts`

保存平台适配器提供的短期 owner/admin/member 事实，不等同于显式 role binding：

```text
fact_id, subject_id, config_id, platform_instance, umo,
platform_role, source, observed_at, expires_at, metadata_json
```

过期事实不得参与授权，也不得自动写入 global 或 instance role binding。

### 12.3 `auth_elevation_requests`（历史兼容表；v1 运行时不创建请求）

保存上一节的请求字段和 nonce 哈希。对 `(status, expires_at)`、`subject_id`、`resource_id` 建索引；批准和消费使用事务和条件更新，防止并发重放。

### 12.4 `auth_audit_log`

字段至少包括：

```text
audit_id, timestamp, request_id, subject_id, effective_role,
source, platform, config_id, action, resource_id,
decision, reason, step_up_id,
outcome, latency_ms, metadata_json
```

日志中不得保存原始 JWT、API Key、nonce、Provider 凭据、完整消息内容或未经脱敏的异常 URL。默认保留 90 天，提供后续控制面身份配置的保留周期和脱敏导出；删除/清理动作本身也要写审计。

### 12.5 `auth_policy_overrides`（第二阶段可选）

仅用于固定能力在特定配置档/会话的 allow-list，例如允许 member 使用某个 Provider。第一版优先使用结构化字段，不支持任意 Python/表达式策略。

## 13. 角色绑定管理和 Dashboard UI

### 13.1 CRUD 范围

固定角色不做定义 CRUD：

```text
root/operator/session_owner/session_admin/member/guest
```

提供的是以下绑定 CRUD：

- 查看主体、角色、作用域、来源、过期时间和最近审计；
- 授予、修改、撤销和设置过期时间；
- 按主体、平台、UMO、角色和状态过滤；
- 批量撤销必须二次确认并要求 step-up；
- instance_operator 只能管理其配置档内允许的 `session_owner`、`session_admin`、`member`，不能写 global/root/operator；
- root/operator 的绑定仍不能由 instance_operator 修改；Dashboard 账户创建、停用和绑定管理由 root 权限与 step-up 保护，并保留最后一个 root 保护；
- 平台自动角色显示为只读事实，不允许 Dashboard 直接修改其来源。

第一版不提供“创建角色”“编辑角色继承”或“自定义拒绝规则”；账户 CRUD 不是角色定义 CRUD，已作为受 root 保护的控制面能力提供。后续若需要自定义角色或更复杂的多账户策略，应先补齐策略验证、冲突解析、迁移和离线审计，再单独立项。

### 13.2 页面和 API

新增 Dashboard 页面/接口建议按领域划分：

```text
/api/v1/authorization/role-bindings
/api/v1/authorization/audit
```

普通 JSON 接口继续使用现有 `status/message/data` envelope；导出文件、SSE 和 WebSocket 保持各自协议。所有写接口统一使用 `require_dashboard_session_principal`，并在服务层再次调用授权服务，不能只依赖路由装饰器。

## 14. 迁移方案

### 阶段 A：只读审计和数据导入（历史计划；本分支不执行旧权限导入）

1. 新增授权模型、主体/资源规范化和审计表。
2. 本分支不读取、迁移或清理旧 `admins_id`，也不会将其转换为任何角色绑定。
3. 为 Dashboard 账户建立受保护的控制面 principal 映射，不根据用户名猜测 root；首次部署时创建稳定 `account_id` 和 bootstrap root。
4. 读取旧 `event.role` 时同时记录冲突诊断，NapCat 等适配器改为填充 `platform_member_role` 和 `auth_platform_membership_facts`；平台事实不写入 role binding。
5. 授权服务以 observe-only 模式计算新决策并与旧 `is_admin()` 结果对比，发现放行差异时写审计和告警。

### 阶段 B：核心管道和内置命令

1. 在 `AstrMessageEvent` 中加入规范化 subject、resource 和 auth context。
2. 新增动作过滤器并逐步替换 `PermissionTypeFilter`，例如 `@filter.permission("session.manage")`；旧过滤器在迁移期只作为适配层，不得作为新的授权入口。
3. 按本计划的命令映射更新 builtin commands 和 command catalog。
4. 将 Admin grant/revoke 改为角色绑定操作，并加入目标角色和作用域校验。
5. 删除核心路径对 `event.role == "admin"` 的依赖；旧二元枚举不再作为长期兼容层保留。

### 阶段 C：工具、Persona、Agent 和插件

1. 工具动作策略直接来自声明和显式授权；不读取或导入 `tool_permissions`。
2. 为 Computer Use、Shell、Python、文件、浏览器和 MCP 工具添加执行前授权检查。
3. 修复 Persona/子 Agent 选择绕过工具权限包装的路径，增加“模型选择工具”和“实际执行工具”两处测试。
4. 发布插件 API 和动作声明；在开发模式对旧插件权限声明给出明确诊断，完成迁移后不再自动授予 admin。

### 阶段 D：Dashboard、WebChat 和 API Key

1. 将 JWT session、API Key 和 WebChat 请求统一解析为 `AuthContext`。
2. 建立旧 API scope 到新动作的显式映射；高风险动作不由 API Key scope 直接授予。
3. 兼容接口继续接受请求体 `username`，但将其标为 caller-declared identity；它不产生管理员身份。新接口从认证主体派生 username。
4. 实现 Dashboard 账户可见的角色绑定（以 instance/session 为主）、账户管理和高风险审计页面/API；跨平台提权不属于本阶段。

### 阶段 E：提权和强制执行

1. 后续阶段才实现私聊/控制面通知、nonce 哈希、TTL、原子批准/消费和重放防护。
2. 当前阶段将高风险动作切换为“直接允许、Dashboard step-up 或拒绝”，禁止全局 `admin` 兜底。
3. 所有拒绝和提权失败统一进入审计；命令/插件仅控制用户提示形式。
4. 关闭 observe-only 后，移除旧 `event.role` 核心判定；旧配置字段不保留为运行时兼容开关。

## 15. 测试计划

### 15.1 单元测试

- 主体和 `(config_id, UMO)` 规范化：跨平台同 ID 不冲突，空值和伪造资源拒绝，现有 UMO 编码保持兼容。
- 角色解析：instance 与会话作用域隔离，过期绑定/平台事实降级，平台 owner/admin 不生成 instance_operator 或 global operator。
- 动作策略：provider.use/provider.manage、session.assign 和 identity.manage 的边界。
- 角色变更：instance_operator 不能写 global/root/operator；账户停用和 root 绑定变更必须保留最后一个可用 root。
- step-up：密码/TOTP 新鲜度、动作/资源绑定、过期和重复使用。
- 审计：拒绝、高风险动作、异常和静默失败生成脱敏记录；低风险 allow 不要求同步落库。

### 15.2 管道和平台集成测试

- NapCat 群主/群管理员在当前群有对应 session 角色，但在另一群不能执行同一管理动作。
- 没有平台角色字段的 QQ 官方、微信、Slack、WebChat 等适配器默认为 member/guest，不误升权。
- 私聊、群聊、WebChat、API Key 的 `message_type` 和 resource 互不串用。
- UMO、`session_id`、配置档切换时不会访问其他配置档的数据；canonical resource 始终包含 `config_id`。

### 15.3 Dashboard 和 WebChat 测试

- Dashboard 控制面按显式账户绑定和 step-up 执行高风险动作；instance_operator 受配置档作用域限制。
- JWT、Cookie、TOTP、API Key scope 与 action 映射正确；无 scope 不因历史 key 获得新敏感能力。
- 兼容 WebChat/Open API 的 `username` 只能作为 caller-declared identity，不产生管理员身份；新接口主体来自认证会话。
- 角色绑定和审计 API 使用标准 response envelope，未授权返回 401/403 且不泄露策略细节。

### 15.4 插件和工具测试

- 插件只能使用自己的命名空间动作，不能伪造其他插件或系统主体。
- Function Tool 在直接调用、Agent 中间调用、Persona 选择和重试路径都执行授权。
- Shell/Python/文件/MCP 的高风险动作在 member、session_admin、operator、root 下分别符合预期。

### 15.5 安全回归和性质测试

- 任意平台群角色输入都不能产生 global operator/root。
- 任意未认证主体都不能读取他人数据或执行系统动作。
- 任意后续 elevation token 不能跨 subject、action、resource、配置档或过期时间重放；第一阶段 step-up 不能跨 Dashboard session 复用。
- 并发角色撤销和请求消费后，旧决策不能继续执行写操作。

## 16. 风险、兼容性和回滚

| 风险                                                | 缓解措施                                                                                                        |
| --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| 平台角色与 AstrBot 角色再次混用                     | 类型和字段分离；适配器契约测试；禁止 `event.role` 写全局角色                                                    |
| UMO 不稳定或跨配置档串用                            | 保留现有 UMO；授权资源使用 `(config_id, umo)` 和版本化 canonicalizer；拒绝未解析目标                            |
| instance_operator 或兼容 `username` 自助提权为 root | 只有现有 root 可在 step-up 后管理 root/operator；目标角色写入策略硬编码；兼容 `username` 不具备提权语义         |
| 后续提权消息被转发/重放                             | nonce 只存哈希；短 TTL；绑定 subject/action/resource/context digest；原子消费。第一阶段只使用 Dashboard step-up |
| 插件或 Agent 绕过授权                               | SDK 入口和工具执行入口双重检查；插件不能访问内部表                                                              |
| 旧命令/配置行为变化                                 | 明确记录旧字段不迁移、不清理；不创建旧权限快照或运行时兼容路径                                                  |
| API Key 历史 scope 意外扩权                         | scope 到 action 显式映射；新增敏感动作默认不继承历史 wildcard                                                   |
| 授权服务故障导致误放行或审计阻塞                    | 写操作 fail closed；低风险 allow 不同步落库；拒绝和高风险事件进入有界异步队列，队列满时使用受限安全日志         |

数据库迁移采用新增表和可回滚索引；本分支不导入或恢复旧 `admins_id` 快照。提权和审计表即使应用回滚也应保留，避免失去安全事件记录。

## 17. 验收标准

实现完成必须满足：

1. 代码库中不再以 `event.role == "admin"` 作为授权依据；旧权限字段不被运行时读取。
2. 所有内置管理命令、Dashboard 写接口、工具执行和插件动作都能定位到一个 action 和 resource。
3. QQ 群主/群管理员在当前 `(config_id, UMO)` 可按短 TTL 平台事实获得 session 角色，在其他群或其他配置档不会获得同等角色。
4. Dashboard 控制面主体来自已验证 session；兼容 WebChat username 不等于认证主体，不能仅凭 username 获得 root 或 operator。
5. `provider.use` 与 `provider.manage` 分离，Provider 凭据不会返回给 member/session_admin。
6. instance_operator 只能作用于对应配置档；不存在通过旧配置自动生成任何 operator/root 的路径。
7. 第一阶段高风险 Dashboard 操作必须 step-up；跨平台私聊提权不属于第一阶段，后续实现也不得在公开群发送可执行凭证。
8. 角色绑定、step-up、拒绝、高风险动作和失败尝试都有可检索的脱敏审计记录；低风险 allow 可以异步采样或不落库。
9. 插件和 Agent 无法绕过核心授权服务，工具直接执行和间接执行结果一致。
10. 单元、平台集成、Dashboard/WebChat、插件/工具和安全回归测试全部通过。

## 18. 推荐实施顺序（开发任务拆分）

1. `authz` 核心包：Subject、结构化 Resource、AuthContext、Decision、固定角色、策略表和有界审计接口。
2. 身份事实迁移：拆分平台成员事实与 AstrBot 角色，修复 NapCat 冲突；不改写现有 UMO。
3. 数据库迁移：角色绑定、平台事实和高风险审计表及索引；不导入旧 `admins_id`。
4. 管道和命令：动作过滤器、builtin command 映射、Admin 命令迁移；旧过滤器仅保留适配层。
5. 工具和 Agent：统一执行前检查，补齐 Computer Use、MCP、Persona/子 Agent 路径。
6. Dashboard/API Key/WebChat：principal 统一、scope 映射、兼容 username 的无提权兼容接口、instance/session 管理接口和页面。
7. 插件 SDK：动作声明、`context.authz` 和迁移诊断；插件不能伪造认证主体。
8. Dashboard step-up：密码/TOTP 新鲜度、一次性操作上下文和高风险审计。
9. 后续单独立项：跨平台提权通道和任意策略扩展。

每个任务都必须同时提交对应的单元/集成测试；涉及 Dashboard 路由时同步更新 `openspec/openapi-v1.yaml`、生成客户端和公开 OpenAPI 文档。

## 19. 统一权限系统 v2 设计提案（未实现）

### 19.1 定位、范围与非目标

v2 是在当前 v1 授权入口、资源规范化、step-up、脱敏审计和
fail-closed 行为上的增量设计，不是立即替换运行时的完整授权引擎。当前实现的
事实来源仍是 AuthorizationService.authorize()、ACTIONS、高风险动作表以及
现有 Dashboard/API/插件契约；本节不会把提案描述成已实现功能。

目标是让授权能表达“谁通过什么关系访问哪个对象”，同时把 API Key、插件、Agent
和工具的附加限制显式化：

```text
关系（subject -> relation -> resource）
  + 有限的上下文条件（ABAC）
  + API Key 的显式 capability
  + root/operator 仅用于 Dashboard 控制面；会话角色仍受资源作用域约束
```

不在本期做以下事情：

- 不引入 OpenFGA、Zanzibar、Cedar 等外部策略服务；
- 不提供用户可编辑的任意 deny DSL、递归关系查询或脚本化策略；
- 不把平台昵称、WebChat username、群号或裸 session_id 当作身份；
- 不通过兼容 shim 继续读取旧字段；如有存量数据，使用一次性迁移或阻断升级；
- 不返回 Provider 密钥。凭据只允许安全地写入、替换或删除，读取接口必须脱敏。

单实例、本地 SQLite、插件和 Dashboard 是当前部署形态。只有在多实例共享授权域、
关系规模或一致性需求明显超出本地实现时，才重新评估外部 FGA 服务。

### 19.2 与当前实现的契合度审计

当前代码已经提供适合 v2 演进的边界：

- authorize(subject, action, resource, context) 是单一授权入口；
- Subject、Resource、AuthContext 已区分认证身份、来源、配置档和原始会话；
- ACTIONS 是动作注册表，插件动作使用命名空间；
- 平台成员事实具有来源和 TTL，Dashboard 高风险操作使用一次性 step-up；
- API Key 仍以历史 scope 映射动作，且 NULL 和显式 * 具有历史语义；
- 高风险 allow 依赖审计写入，授权异常默认拒绝。

因此 v2 应保留入口和安全不变量，只替换“按最高角色放行”的内部策略。原方案中
改名为 tool.local.exec、新增 provider.credentials.read、把 operator 绑定到
instance、以及直接删除所有 v1 数据的写法均不契合当前契约。

**评审结论**：建议采纳本节的有限关系 + 结构化上下文 + 显式 capability 方案，
但按增量路线落地。它能解决当前 v1 的对象级作用域、API Key 资源边界和工具/Agent
调用链问题，又不会把单实例 SQLite 项目提前变成外部策略服务。v2 的首要交付物应是
action/resource/policy registry、对象级查询过滤和迁移预检；关系推理、可编辑策略和
跨平台 elevation 都必须排在这些契约之后。

### 19.3 主体和可信上下文

主体继续使用现有命名空间：

```text
dashboard-account:<account-id>
dashboard-session:<session-id>
im:<platform-instance>:<bot-account-id>:<sender-id>
api-key:<key-id>
plugin:<plugin-id>
agent:<agent-id>
system:<component>
guest:<id>
```

规则如下：

1. dashboard-account 是稳定的 Dashboard 关系主体；dashboard-session 只表示当前
   已认证会话，不能单独产生永久授权。
2. plugin 和 agent 是执行组件，不会自动继承调用者的 root/operator 权限。子 Agent
   必须携带原始调用主体和调用链，handoff 不能提升权限。
3. IM 主体必须由适配器根据平台实例、Bot 账户和发送者 ID 构造。显示名、昵称、
   username 和调用方自报的主体 ID 永远不可信。
4. AuthContext.source、config_id、origin_session_resource_id、认证强度和平台事实
   由受信任入口填充；缺失或不一致时拒绝，而不是猜测。

### 19.4 Canonical Resource：先固定边界，再做关系推理

资源 ID 由服务端规范化生成，调用方只能引用已存在的对象。v2 的最小资源图为：

```text
global
└── instance:<config-id>
    ├── session:<config-id>:<platform-instance>:<bot-account-id>:<umo>
    │   ├── conversation:<session-resource>:<conversation-id>
    │   └── memory:<session-resource>:<memory-id>
    ├── provider:<config-id>:<provider-id>
    ├── knowledge-base:<config-id>:<kb-id>
    │   └── knowledge-base-document:<kb-id>:<document-id>
    └── file:<config-id>:<owner-kind>:<owner-id>:<file-id>
```

其中：

- session 必须同时包含 config_id、platform_instance、bot_account_id 和规范化
  UMO；不得用裸 session_id 作为跨平台身份；
- conversation、memory、文件和知识库文档必须携带可验证的父资源或配置档；
- provider.credentials.write 的资源必须是具体 Provider 或其所属 instance，不能
  用一个全局 provider 字符串代替；
- 父子关系只提供候选范围，不自动授予权限。每条继承关系必须在固定策略表中明确
  声明，且最多向上解析一层；禁止递归、循环和调用方自定义父路径；
- 查询服务必须先根据授权主体过滤对象，再序列化响应。只授权 collection endpoint
  而不做行级过滤是不合格的对象级授权。

当前 v1 canonical session 编码保持不变。v2 可以新增独立的 session:v2 编码，但必须提供一次性数据库迁移：对每条现存 v1 session
binding 由可信平台元数据补全字段。若无法无歧义补全，升级预检必须停止并要求管理员
导出、确认或重建绑定；“本分支没有存量用户”不能替代迁移预检。

### 19.5 有限关系模型，而不是可编程 ReBAC

关系 tuple 的内部表达为：

```text
subject --relation--> resource
```

关系 registry 只允许固定集合：root、operator、instance_operator、owner、admin、
member、guest、viewer、editor、executor、caller。与当前 `Role` 的迁移映射为
`session_owner -> owner`、`session_admin -> admin`；平台事实中的 owner/admin/member
仍是带来源和 TTL 的短期事实，不是全局关系绑定。`viewer`、`editor`、`executor`、
`caller` 先作为受约束的预留关系，只有对应 action/resource 策略和数据模型落地后
才能启用。root 和 operator 只能绑定 Dashboard account 的 global 关系；
instance_operator 绑定 instance；平台 owner/admin/member 不能产生 global 或 instance
控制面权限。

每个 (action, resource_type) 在代码中登记：

- 可匹配的 relation；
- 允许的父资源和最大深度（v2 固定为 0 或 1）；
- 必需的 context 属性（来源、配置档、原始 session、认证强度）；
- 风险级别和是否要求 step-up。

关系数据优先复用当前的 `auth_role_bindings`：将现有 `role` 按固定关系语义解释，
通过一次 schema 迁移补足 relation/source/expiry 所需字段；只有在确认现有表无法
承载关系元数据时才改名为 `auth_relationships`，不得让两套表长期并存。关系表必须
有 (subject_id, resource_type, resource_id, relation, revoked_at) 索引、唯一有效约束、
过期清理和来源字段。授权结果保留 matched_relations、relation_sources 和可审计的
拒绝原因，不再把单一 effective_role 当作决策依据。

示例：

```text
dashboard-account:a --root---------------> global
dashboard-account:b --operator-----------> global
dashboard-account:c --instance_operator--> instance:default
im:napcat:bot:42 --owner---------------> session:default:...
im:napcat:bot:99 --admin---------------> session:default:...
session:default:... --owner-------------> conversation:...
```

### 19.6 决策流程和适用约束

保留现有接口：

```text
authorize(subject, action, resource, context) -> Decision
```

决策顺序固定为：

1. 验证 subject 与 context 的绑定；
2. 规范化并验证 resource、配置档和原始 session；
3. 验证 action registry（未知动作默认拒绝）；
4. 解析直接关系和最多一层父关系；
5. 检查来源、TTL、同配置和其他 ABAC 条件；
6. 仅在 `source == api_key` 且主体类型为 `api-key` 时检查 API Key capability；
7. 按风险策略检查 Dashboard step-up；
8. 写入必要的脱敏审计并返回 Decision。

授权成立必须同时满足：

```text
authenticated
AND known_action
AND valid_resource
AND (relationship_grant OR api_key_capability_grant)
AND applicable_context_constraints_pass
AND applicable_capability_constraints_pass
AND step_up_passed
```

对于 API Key，显式 capability 本身就是 grant，不要求额外伪造一个 role binding；
它必须精确匹配 action、resource、配置档和有效期，并且不能覆盖高风险动作。对于
其他主体，`relationship_grant` 来自固定关系和有限父资源解析。

“适用”是关键边界：API Key capability 只约束 API Key；插件声明只约束
`plugin:<id>:<action>` 自有动作；Persona 工具白名单只约束该 Persona 发起的工具
调用；IM 的原始 session 约束只约束 IM 来源。未适用的约束视为 true，不能把普通
Dashboard/IM 用户与不存在的 API Key 或插件声明求交而误拒绝。

Agent/工具调用必须保留原始调用主体、执行组件和完整调用链。核心授权检查与直接
工具执行、Agent 间接执行、MCP 调用使用同一 action/resource 结果；插件声明是必要
条件，不是提升调用者权限的通道。Dashboard Extension 的 `required_scope` 仍先映射
到现有 API scope/action；它与插件自有的 `plugin:<plugin-id>:<action>` 动作命名空间
是两条不同的声明路径，不能混用。

### 19.7 Action Registry 兼容策略

v2 不擅自改名。以下现有动作继续作为 canonical 名称：session.read、session.manage、
session.assign、provider.read、provider.use、provider.manage、
provider.credentials.write、platform.read、platform.manage、agent.manage、
extension.read、extension.manage、extension.plugin_install、data.manage、
data.export_all、system.manage、system.update、system.restart、system.pip_install、
identity.read、identity.manage、identity.operator.write、identity.root.write、
tool.local_exec、tool.python_exec、tool.file_read、tool.file_write、
tool.browser_control、tool.mcp_read、tool.mcp_write、tool.computer_use 和
`dashboard.account.manage`。插件动作继续使用 `plugin:<plugin-id>:<action>` 命名空间并
经过声明校验。

细分 data.manage 或工具动作只有在对应服务、路由和测试同时落地时才新增。新增动作
必须登记资源类型、关系、风险、来源和迁移映射；旧动作不能通过字符串别名长期共存。
特别注意：

- 不新增 provider.credentials.read；任何 Provider 读取响应都必须脱敏；
- 文档和代码使用 tool.file_write，不是未注册的 tool.file.write；
- provider.credentials.write、extension.plugin_install、data.export_all、
  tool.local_exec、tool.python_exec、tool.file_write、tool.browser_control、
  tool.mcp_write、tool.computer_use、identity.manage、dashboard.account.manage、
  系统更新/重启/安装等高风险动作保持独立授权，不能从父动作静默继承。

### 19.8 典型策略和入口矩阵

| 入口/资源                        | 允许的关系或条件                                                          | 必须额外满足                                     |
| -------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------ |
| 当前 IM session                  | owner/admin/member；instance operator 或 global operator/root             | resource == origin_session_resource_id           |
| session 下的 conversation/memory | 该 session 的 owner/admin/member；instance operator；global operator/root | 服务层按对象过滤                                 |
| Provider 配置/凭据               | instance operator、operator、root                                         | 仅 Dashboard；凭据写入需 step-up，读取脱敏       |
| 插件目录与插件 Action            | extension 相关关系；插件自有 Action 需声明                                | Action 仍调用核心 authorize                      |
| API Key 请求                     | 该 key 的显式 action/resource capability（不依赖角色绑定）                | 高风险 action 一律拒绝                           |
| Agent/Computer/MCP/本地工具      | 原始调用者对目标 resource 的 action 授权                                  | Persona/插件声明/风险规则仅在适用时叠加          |
| 导出、下载、更新、重启           | 明确的高风险 action                                                       | Dashboard step-up；IM、插件、Agent、API Key 拒绝 |

列表、搜索、批量导出和下载都必须在 service/query 层执行对象级过滤；禁止先取全量
数据再在 Dashboard 或插件层隐藏。批量变更的 step-up 必须绑定排序后的完整资源集合，
防止拆分重放。

### 19.9 持久化与 API Key 迁移

关系存储建议：

```text
auth_role_bindings（沿用现有表；role 按 relation 解释）
binding_id, subject_id, role/relation, scope_type, scope_id,
config_id, source, expires_at, created_by, created_at,
revoked_at, revoked_by, metadata_json
```

如确实需要独立的资源关系表，必须提供从 `auth_role_bindings` 到新表的一次性、可审计
迁移，并删除旧读取路径；不得同时读取两张表。API Key 则新增显式能力表：

```text
auth_capabilities:
capability_id, subject_id, action, resource_type, resource_id,
config_id, expires_at, created_by, revoked_at
```

约束包括固定 relation/action registry、canonical resource 校验、来源 TTL、撤销时间、
唯一有效记录和必要索引。平台事实仍保留完整隔离键：
subject_id + config_id + platform_instance + bot_account_id + umo，不能只按
subject_id + config_id + umo 查询。

API Key 从 scope 迁移为显式 capability：

```json
{
  "capabilities": [
    {
      "action": "session.read",
      "resource": "session:v2:..."
    },
    {
      "action": "provider.use",
      "resource": "instance:default"
    }
  ],
  "expires_at": "..."
}
```

`NULL` scope 在当前代码中不是 wildcard，而是固定的历史默认 scope 集合；显式 `*`
才是另一种历史 wildcard。二者都不能在 v2 继续产生扩权语义，但迁移处理不同：

1. 预检并统计所有 role binding、policy override、v1 resource 和 API Key；
2. `NULL` 按代码中冻结的 `DEFAULT_API_KEY_SCOPES` 展开为有限 action 集合；由于旧
   scope 没有对象级边界，只有能确定配置档/资源范围的记录才自动生成 capability，
   其余记录要求管理员重新签发；
3. 显式 `*` 和冲突记录标记为需重建并禁用，而不是扩大权限；不得把 wildcard 当作
   普通 capability 迁移；
4. 迁移在事务中写入审计，完成后删除旧字段读取路径；
5. 若管理员选择不迁移 API Key，明确要求全部重建并在升级说明中列出影响。

这不是运行时兼容层；迁移脚本或升级预检完成后，核心只读取 v2 schema。

### 19.10 WebChat、Dashboard 与 Step-up

WebChat 的 username 仍可作为协议兼容字段，但永远不等于认证主体。匿名请求使用
guest；Dashboard 驱动的 WebChat 同时传递已认证 account/session 上下文，修改
username 不能改变权限。

v2.0 只保留 Dashboard step-up：

- 高风险 Dashboard 操作要求新鲜密码或 TOTP；
- step-up 绑定 subject、Dashboard session、action、精确 resource、config、source
  和 policy version，短 TTL、单次消费、原子更新；
- IM 仅保留当前 origin session 内受限的成员管理例外；不得借此操作其他会话、
  instance 或 global identity；
- 插件、Agent、MCP 和 API Key 不能直接执行高风险动作；
- 不在公开群发送可执行凭证。

跨平台提权作为独立 v2.1 设计，必须分离 request/approve/execute，并要求审批者同时
拥有目标 action 和 resource 的授权；在协议、审计和回滚方案落地前不实现。

### 19.11 实施与发布闸门

1. **契约冻结**：整理当前 ACTIONS、高风险表、插件 action 和 API scope 映射，生成
   action/resource/risk 矩阵。
2. **关系内核**：引入 RelationshipTuple 和有限策略 registry，保留 authorize()，
   先以 shadow decision 对比 v1，不改变放行结果。
3. **资源与存储**：补全 session v2 canonical 资源、父资源解析、关系表索引和一次性
   迁移预检。
4. **能力迁移**：实现 API Key capability，拒绝 wildcard/未界定资源，完成旧 key
   重建或事务迁移。
5. **入口覆盖**：逐一覆盖 Dashboard JSON、WebSocket、SSE、下载、插件、Agent、
   MCP、Computer Tool 和本地工具，并在 query/service 层过滤对象。
6. **切换与清理**：shadow 矩阵无差异后切换决策，将仍需保留的结构化 policy
   override 显式迁移到新 registry；删除旧 scope/字段读取代码，不保留长期 shim。
7. **发布闸门**：迁移预检、授权矩阵、越权回归、step-up 重放、审计队列满载、
   并发撤销和跨配置/跨平台测试全部通过；否则阻断升级。

### 19.12 验收标准

1. 每次授权都能定位 subject、action、resource、来源、匹配关系和 context。
2. 授权不依赖单一 effective_role，关系策略最多解析一层且无循环。
3. session 资源不可由裸 session ID 构造；不同配置、平台实例和 Bot 账户隔离。
4. 未知 action/resource、缺失 context、策略异常和审计不可用均 fail closed。
5. provider.credentials.read、tool.file.write 等未注册/越界动作不会被文档或运行时
   接受；Provider 凭据永不返回。
6. API Key 只有显式 action/resource capability，运行时没有 wildcard 或 NULL 扩权，
   也没有隐式 operator 权限。
7. 列表、搜索、导出、下载和批量写入均执行对象级授权。
8. 插件、Agent、MCP、Computer Tool 和本地工具不能绕过核心授权或提升调用者。
9. 高风险 Dashboard 操作需要精确、一次性 step-up；IM/插件/Agent/API Key 被拒绝。
10. 关系变更、step-up、拒绝和高风险 allow 都有脱敏、可查询审计。
11. Dashboard、WebSocket、SSE、下载、插件和工具入口均有授权矩阵测试。
12. 迁移前置检查能识别无法安全映射的数据，并阻断不完整升级。

### 19.13 参考原则（已核对，2026-08-15）

- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)：
  认证与授权分离、默认拒绝、最小权限、每次请求检查、对象级授权和授权回归测试；
- [NIST SP 800-162](https://csrc.nist.gov/pubs/sp/800/162/upd2/final)：ABAC 评估主体、对象、
  操作和环境属性及其策略关系；
- [OpenFGA Authorization Concepts](https://openfga.dev/docs/concepts)：用
  object-relation-user tuple 表达关系，但本项目只采纳其表达方式，不引入外部服务或
  无限递归模型。
