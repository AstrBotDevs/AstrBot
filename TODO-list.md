# SDK Parity TODO List

目标：让新 `astrbot_sdk` 在能力上可以完整替代 legacy 插件系统。

说明：
- 只列出 SDK 插件开发者真正需要调用的 API
- 不包含 Core 内部实现细节
- **状态标记**：✅ 已实现 | 🔄 部分实现 | ❌ 未实现 | ⚠️ Core端未支持

---

## 📊 覆盖率总览

| 模块 | 总计 | ✅ | 🔄 | ❌ | ⚠️ | 覆盖率 |
| --- | --- | --- | --- | --- | --- | --- |
| LLM Client | 8 | 8 | 0 | 0 | 0 | 100% |
| DB Client (KV) | 7 | 6 | 0 | 0 | 1 | 93% |
| Platform Client | 6 | 5 | 1 | 0 | 0 | 100% |
| Metadata Client | 4 | 4 | 0 | 0 | 0 | 100% |
| Memory Client | 8 | 8 | 0 | 0 | 0 | 100% |
| HTTP Client | 3 | 3 | 0 | 0 | 0 | 100% |
| MessageEvent | 40 | 38 | 0 | 2 | 0 | 95% |
| 装饰器/触发器 | 17 | 13 | 0 | 2 | 2 | 76% |
| 事件类型 | 14 | 14 | 0 | 0 | 0 | 100% |
| 消息组件 | 22 | 10 | 0 | 12 | 0 | 45% |
| Legacy Context | 27 | 22 | 0 | 5 | 0 | 81% |
| 工具方法 | 6 | 4 | 0 | 2 | 0 | 67% |
| 会话控制 | 5 | 5 | 0 | 0 | 0 | 100% |
| 过滤器 | 5 | 5 | 0 | 0 | 0 | 100% |
| 高级管理器 | 12 | 12 | 0 | 0 | 0 | 100% |
| Provider管理 | 11 | 11 | 0 | 0 | 0 | 100% |
| Provider实体 | 9 | 6 | 1 | 2 | 0 | 72% |
| TTS/STT/Embedding | 8 | 8 | 0 | 0 | 0 | 100% |
| Platform实体 | 12 | 7 | 1 | 4 | 0 | 62% |
| Agent运行器 | 7 | 1 | 0 | 6 | 0 | 14% |
| Handler注册表 | 5 | 2 | 0 | 3 | 0 | 40% |
| SDK扩展能力 | 19 | 8 | 0 | 11 | 0 | 47% |
| 其他系统能力 | 52 | 7 | 0 | 44 | 1 | 14% |
| **Star基类扩展** | **7** | **7** | **0** | **0** | **0** | **100%** |
| **命令参数类型** | **8** | **8** | **0** | **0** | **0** | **100%** |
| **过滤器组合** | **5** | **5** | **0** | **0** | **0** | **100%** |
| **StarTools工具集** | **10** | **10** | **0** | **0** | **0** | **100%** |
| **会话级管理** | **6** | **6** | **0** | **0** | **0** | **100%** |
| **命令组系统** | **9** | **9** | **0** | **0** | **0** | **100%** |
| **消息类型过滤** | **7** | **7** | **0** | **0** | **0** | **100%** |
| **PluginKVStoreMixin** | **5** | **5** | **0** | **0** | **0** | **100%** |
| **StarMetadata字段** | **2** | **2** | **0** | **0** | **0** | **100%** |
| **总计** | **334** | **重算中** | **-** | **-** | **-** | **以正文为准** |

> 注：覆盖率 = `(已实现 + 部分实现 × 0.5) / 总计`，⚠️ 表示SDK已定义但Core端未实现
> 
> 说明：顶部模块统计存在**分类重叠**（例如 `Provider 管理` 与 `P1.3`、`StarTools` 与 `P0.7/P1.4`、`其他系统能力` 与 `P1.5` 不是互斥维度），因此不再维护单一“总覆盖率”数字；请以各模块表格和 P0/P1/P2 正文状态为准。
>
> **2026-03-16 更新说明**：
> - **P1.4 已完成**：Star 兼容层与开发工具全部实现
> - StarTools 工具集从 0% → 100%（10项全部完成）
> - PluginKVStoreMixin 从 0% → 100%（5项全部完成）
> - StarMetadata 字段从 0% → 100%（2项全部完成）
> - Platform Client 从 58% → 100%（新增 send_message/send_message_by_id）
> - SDK 扩展能力从 32% → 47%（新增动态 LLM Tool 注册/注销）
> - 总覆盖率从 50% → 56%（+6%）
>
> **2026-03-15 更新说明**：
> - 消息组件总数从 13 修正为 22（包含所有平台特定组件）
> - MessageEvent 总数从 41 修正为 40（移除重复计数）
> - Platform实体总数从 6 修正为 12（包含所有方法）
> - 新增 Handler注册表 模块（5项）
> - @session_waiter 装饰器已实现，装饰器覆盖率提升
> - MessageSession.from_str() 已实现，Provider实体覆盖率提升
>
> **2026-03-17 校对说明**：
> - 已按当前代码实现修正文档中一批过时状态，尤其是 `MessageEvent` 结果控制、Provider 管理、TTS/STT/Embedding、Platform facade、RegistryClient、群组管理与 Legacy 入口
> - 顶部模块统计已同步校正关键模块，整体总计保留为“重算中”，本轮以正文和优先级章节为准

---

## 更新记录

### 2026-03-16 P0.6-P0.7 平台与会话能力及Legacy入口完成
- **P0.6 平台与会话能力已完成 ✅**：
  - **PlatformClient 扩展** - `send_by_id()`, `send_by_session()`, `get_members()`
  - **群组管理** - `get_group()`, 群成员列表获取
  - **会话级插件管理** - `SessionPluginManager`, `is_plugin_enabled_for_session()`, `filter_handlers_by_session()`
  - **会话级服务开关** - `SessionServiceManager`, `is_llm_enabled_for_session()`, `set_llm_status_for_session()`, `is_tts_enabled_for_session()`, `set_tts_status_for_session()`
- **P0.7 Legacy Context 与开发者入口已完成 ✅**：
  - **动态命令注册** - `register_commands()`，仅在 `astrbot_loaded`/`platform_loaded` 事件中可用
  - **后台任务注册** - `register_task()`，支持异常捕获和日志记录
  - **平台兼容层** - `get_platform()`, `get_platform_inst()`, 返回 `PlatformCompatFacade`
  - **PlatformCompatFacade** - 封装平台实例，提供 `send()`, `send_by_id()`, `send_by_session()` 主动发送能力
- **覆盖率更新**：
  - 工具方法：67% → 100%
  - Platform实体：0% → 17%
  - Agent运行器：0% → 100%
  - SDK扩展能力：11% → 32%
  - 会话级管理：0% → 100%
  - 总覆盖率：47% → 50%


### 2026-03-16 P0.3 路由功能完成
- **P0.3 命令、过滤器与调度已全部完成 ✅**：
  - **命令组系统** - `CommandGroup` 类支持嵌套组、别名笛卡尔积展开、命令树打印
  - **过滤器系统** - `PlatformFilter`, `MessageTypeFilter`, `CustomFilter` 及组合 (`all_of`, `any_of`)
  - **命令参数类型解析** - 自动解析 `int`, `float`, `bool`, `Optional[T]`, `GreedyStr`
  - **调度触发器** - `@on_schedule(cron=...)` 和 `@on_schedule(interval_seconds=N)` Core 端完整支持
  - **ScheduleContext** - 调度上下文注入到 handler
- **新增文件**：
  - `astrbot_sdk/commands.py` - CommandGroup 实现
  - `astrbot_sdk/filters.py` - 过滤器系统实现
  - `astrbot_sdk/schedule.py` - ScheduleContext 定义
  - `astrbot_sdk/types.py` - GreedyStr 类型
- **Core 端桥接更新**：
  - `plugin_bridge.py` - 调度触发器注册/注销、`_request_plugin_ids` 映射
  - `trigger_converter.py` - 过滤器匹配逻辑
  - `cron/manager.py` - 支持 `interval_seconds` 间隔调度
- **覆盖率更新**：
  - 过滤器：0% → 100%
  - 命令参数类型：12% → 100%
  - 过滤器组合：0% → 100%
  - 命令组系统：0% → 100%
  - 消息类型过滤：0% → 100%
  - 装饰器/触发器：53% → 76%
  - 总覆盖率：32% → 43%

### 2026-03-16 P0.5 LLM、工具与 Provider 查询完成
- **P0.5 LLM、工具与 Provider 使用能力已完成 ✅**：
  - **Provider 查询** - `get_using_provider()`, `get_current_chat_provider_id()`, `get_all_providers()`, `get_all_tts_providers()`, `get_all_stt_providers()`, `get_all_embedding_providers()`, `get_using_tts_provider()`, `get_using_stt_provider()`
  - **LLM 工具管理** - `get_llm_tool_manager()`, `activate_llm_tool()`, `deactivate_llm_tool()`, `add_llm_tools()`
  - **LLM 工具注册** - `@register_llm_tool()`，支持静态注册与运行时动态增加
  - **Agent 注册与最小闭环** - `@register_agent()`, `BaseAgentRunner`, `tool_loop_agent()`
  - **Provider/Tool 实体** - `ProviderType`, `ProviderMeta`, `ProviderRequest`, `ToolCallsResult`, `RerankResult`, `LLMToolSpec`
- **新增文件**：
  - `astrbot_sdk/llm/entities.py`
  - `astrbot_sdk/llm/providers.py`
  - `astrbot_sdk/llm/tools.py`
  - `astrbot_sdk/llm/agents.py`
  - `data/sdk_plugins/sdk_demo_agent_tools/`
- **边界说明**：
  - `tool_loop_agent()` 始终复用 Core `ToolLoopAgentRunner`
  - SDK 工具 callable 只保留在 worker 本地注册表，Core 只持有元数据和激活状态
  - `@register_agent()` 在 P0.5 仅提供注册与 metadata，不提供独立 `await agent.run()` 调用入口

### 2026-03-15 全面覆盖率审计
- **覆盖率表格修正**：
  - 消息组件总数从 13 修正为 22（包含所有平台特定组件）
  - MessageEvent 总数从 41 修正为 40（移除重复计数）
  - Platform实体总数从 6 修正为 12（包含所有方法）
  - 新增 Handler注册表 模块（5项）
  - 总计从 282 修正为 334
- **状态更新**：
  - `@session_waiter` 装饰器：❌ → ✅ 已实现
  - `SessionWaiter` 类：🔄 → ✅ 已实现（通过 SessionWaiterManager）
  - `MessageSession.from_str()`：❌ → ✅ 已实现
  - LLM Client 所有方法已实现：覆盖率 64% → 100%
  - MessageEvent 覆盖率：56% → 83%
  - 装饰器覆盖率：41% → 53%
  - 会话控制覆盖率：90% → 100%
  - 总覆盖率：28% → 32%

### 2026-03-15 路由机制验证
- **P0.0 基础核心能力路由验证**：
  - 确认消息分发流程：旧插件 (`StarRequestSubStage`) → SDK 插件 (`SdkPluginBridge.dispatch_message()`)
  - 确认隔离级别：旧插件同进程直接调用 `Context`，SDK 插件独立 Worker 进程通过 `CoreCapabilityBridge` 协议调用
  - 为每个 P0.0 能力点添加了旧插件 vs SDK 插件的 API 对照

### 2025-03-15 更新
- 新增 Star基类扩展方法对比（P2.5）
- 新增 命令参数类型系统对比（P2.6）
- 新增 过滤器组合与自定义对比（P2.7）
- 新增 事件系统细节对比（P2.8）
- 新增 平台适配器类型系统（P2.9）
- 新增 StarTools工具集对比（P2.10）
- 新增 会话级插件管理对比（P2.11）
- 新增 命令组系统对比（P2.12）
- 新增 消息类型过滤对比（P2.13）
- 新增 PluginKVStoreMixin对比（P2.14）
- 新增 StarMetadata完整字段对比（P2.15）
- 更新覆盖率总览表格

### 2026-03-15 P0.2 完成更新
- **P0.2 消息与结果对象已全部完成 ✅**：
  - **消息组件** - `At`, `AtAll`, `Reply`, `Record`, `Video`, `File`, `Poke`, `Forward` 全部实现
  - **消息组件方法** - `Image.convert_to_file_path()`, `register_to_file_service()`, `File.get_file()` 全部实现
  - **MessageEvent 扩展方法** - `react()`, `send_typing()`, `send_streaming()`, `get_messages()`, `get_message_outline()` 全部实现
  - **结果对象** - `image_result()`, `chain_result()`, `make_result()` 全部实现
  - **额外信息** - `set_extra()`, `get_extra()`, `clear_extra()` 全部实现
- **平台兼容性说明**：
  - `send_streaming()` - 所有平台支持（14个平台）
  - `react()` - 仅 Discord、飞书(Lark)、Telegram 支持
  - `send_typing()` - 仅 Telegram 支持
  - 其他方法不依赖平台特性，全平台通用

### 2026-03-15 P0.1 完成更新
- **P0.1 阻塞迁移的关键能力已全部完成 ✅**：
  - **Memory Client** - 8 个方法全部实现，使用 JSON 文件存储
  - **HTTP Client** - 3 个方法全部实现，支持路由注册/注销/列表
  - **MessageEvent 扩展** - `self_id`, `platform_id`, `message_type`, `sender_name`, `is_admin`, `unified_msg_origin`, `is_private_chat()` 等
  - **事件控制** - `stop_event()`, `continue_event()`, `is_stopped()`
  - **基础事件类型** - `astrbot_loaded`, `platform_loaded`, `after_message_sent`
  - **工具方法** - `get_data_dir()`, `text_to_image()`, `html_render()`
  - **会话等待** - `SessionWaiter`, `SessionController`，支持注册/注销/分发
  - **Provider 实体** - `MessageSession` 类，支持 `from_str()` 解析
- **覆盖率更新**：
  - Memory Client: 0% → 100%
  - HTTP Client: 0% → 100%
  - MessageEvent: 32% → 56%
  - 事件类型: 7% → 29%
  - 会话控制: 0% → 80%

### 2026-03-15 更新
- **LLM Client 新增参数支持**：
  - `contexts` - 自定义上下文，优先于 `history`
  - `provider_id` - 显式指定聊天 Provider
  - `tool_calls_result` - 工具执行结果透传
  - `image_urls` - 多模态图片输入，已透传到底层 provider
- **LLMResponse 新增字段**：
  - `role` - 响应角色
  - `reasoning_content` - 推理内容
  - `reasoning_signature` - 推理签名
- **stream_chat 优化**：改为真实流式优先，仅 `NotImplementedError` 时降级为完整响应切片流
- **Core 端能力桥优化**：
  - 新增 `_resolve_llm_request` 方法支持 provider_id 解析
  - 新增 `_normalize_llm_payload` 方法标准化 LLM 请求参数
- **类型注解优化**：移除不必要的前向引用字符串，使用 `from __future__ import annotations`
- **协议描述符更新**：`llm.chat_raw` 和 `llm.stream_chat` 的 JSON Schema 支持新参数

### 2026-03-15 优先级重组
- **重新组织优先级结构**：
  - **P0**：旧插件替代必需能力 - 缺失会直接阻塞 legacy 插件迁移
  - **P1**：旧插件后置兼容能力 - 旧系统有，但不属于首批迁移阻塞项
  - **P2**：SDK 可扩展能力 - 新 SDK 的增强方向
- **P0.0**：基础核心能力（已实现 ✅）- LLM/DB/Platform/Metadata/装饰器/消息组件/MessageEvent
- **P0.1**：阻塞迁移的关键能力（已实现 ✅）- Memory/HTTP/MessageEvent扩展/事件控制/工具方法/会话等待/Provider实体
- **P0.2**：消息与结果对象（已实现 ✅）- 富消息组件/结果对象/事件附加信息
- **P0.3**：命令、过滤器与调度 - 命令组/参数解析/自定义过滤器/消息类型过滤/定时触发
- **P0.4**：事件与处理主链 - 完整事件类型/结果控制/插件错误与生命周期事件
- **P0.5**：LLM、工具与 Provider 使用能力 - ToolLoop/LLM Tool/TTS-STT-Embedding/Provider 查询
- **P0.6**：平台与会话能力 - 跨会话发送/群组访问/会话级插件与服务开关
- **P0.7**：Legacy Context 与开发者入口 - `register_commands`/`register_task`/`get_platform` 等迁移入口
- **P1.1**：多媒体与专用 Provider（已实现 ✅）- TTS/STT/Embedding/Rerank
- **P1.2**：高级管理器 - Persona/Conversation/KnowledgeBase
- **P1.3**：Provider 与 Platform 管理面 - Provider CRUD/Platform 状态与统计/Webhook
- **P1.4**：Star 兼容层与开发工具（已实现 ✅）- StarTools/PluginKVStoreMixin/StarMetadata/Star.context
- **P1.5**：其他系统能力 - 文件服务/MCP/事件总线/热重载/国际化/日志/依赖管理/消息撤回
- **P2.1**：CancelToken 取消机制扩展
- **P2.2**：provide_capability 能力导出扩展
- **P2.3**：Handler kind 类型实现
- **P2.4**：Permissions 权限系统扩展
- **P2.5**：插件间 Capability 调用
- **P2.6**：事件类型标准化
- **P2.7**：依赖注入扩展
- **P2.8**：调度器验证
- **整合旧系统详情**：将原 P2.5-P2.15 内容整合到"旧系统能力详情"参考章节

---

## SDK Client 方法

### LLMClient

| 方法 | 状态 | 说明 |
| --- | --- | --- |
| `chat(prompt, system?, history?, model?, temperature?)` | ✅ | 发送聊天，返回文本 |
| `chat_raw(prompt, ...)` | ✅ | 返回完整响应（含 usage、tool_calls，兼容 `role/reasoning_*` 可选扩展） |
| `stream_chat(prompt, ...)` | ✅ | 真实流式优先，仅 `NotImplementedError` 时降级为完整响应切片流 |
| `chat(image_urls=[...])` | ✅ | 多模态：图片输入，已透传到底层 provider |
| `chat(tools=[...])` | ✅ | OpenAI 风格 function tools 可桥接到底层 provider |
| `chat(contexts=[...])` | ✅ | 自定义上下文，且优先于 `history` |
| `chat(provider_id="...")` | ✅ | 显式指定聊天 Provider |
| `chat(tool_calls_result=[...])` | ✅ | 工具执行结果透传，不校验 tool_call 语义一致性 |
| `chat(audio_urls=[...])` | ⚠️ | 多模态：音频输入（暂不支持，最后考虑） |

### DBClient (KV 存储)

| 方法 | 状态 | 说明 |
| --- | --- | --- |
| `get(key)` | ✅ | 获取值 |
| `set(key, value)` | ✅ | 设置值 |
| `delete(key)` | ✅ | 删除键 |
| `list(prefix?)` | ✅ | 列出键 |
| `get_many(keys)` | ✅ | 批量获取 |
| `set_many(items)` | ✅ | 批量设置 |
| `watch(prefix?)` | ⚠️ | 订阅变更（SDK已定义，Core端MVP不支持） |

### PlatformClient

| 方法 | 状态 | 说明 |
| --- | --- | --- |
| `send(session, text)` | ✅ | 发送文本 |
| `send_image(session, url)` | ✅ | 发送图片 |
| `send_chain(session, chain)` | ✅ | 发送消息链 |
| `get_members(session)` | ✅ | 获取当前消息所属群成员；不支持任意群主动查询 |
| `send_by_id(platform_id, session_id, ...)` | ✅ | 根据ID发送消息（跨会话发送） |
| `send_by_session(session, chain)` | ✅ | 通过可持久化会话数据发送消息 |

### MetadataClient

| 方法 | 状态 | 说明 |
| --- | --- | --- |
| `get_plugin(name)` | ✅ | 获取插件信息 |
| `list_plugins()` | ✅ | 列出所有插件 |
| `get_current_plugin()` | ✅ | 获取当前插件 |
| `get_plugin_config(name?)` | ✅ | 获取插件配置 |

### MemoryClient

| 方法 | 状态 | 说明 |
| --- | --- | --- |
| `search(query, top_k?)` | ✅ | 已支持，Core 端当前使用简单字符串匹配实现 |
| `save(key, value)` | ✅ | 保存记忆 |
| `save_with_ttl(key, value, ttl)` | ✅ | 已支持，TTL 仅记录但不实际过期 |
| `get(key)` | ✅ | 获取记忆 |
| `get_many(keys)` | ✅ | 批量获取 |
| `delete(key)` | ✅ | 删除记忆 |
| `delete_many(keys)` | ✅ | 批量删除 |
| `stats()` | ✅ | 统计信息，包含 `total_items/total_bytes/plugin_id/ttl_entries` |

### HTTPClient

| 方法 | 状态 | 说明 |
| --- | --- | --- |
| `register_api(route, handler, methods?)` | ✅ | 注册 API，Core 端通过独立 SDK dispatch 表承载 |
| `unregister_api(route)` | ✅ | 注销 API |
| `list_apis()` | ✅ | 列出已注册 API |

---

## MessageEvent

| 属性/方法 | 状态 | 说明 |
| --- | --- | --- |
| `text` | ✅ | 消息文本 |
| `platform` | ✅ | 平台名称 |
| `session_id` | ✅ | 会话 ID |
| `user_id` | ✅ | 发送者 ID |
| `group_id` | ✅ | 群组 ID |
| `raw` | ✅ | 原始数据 |
| `reply(text)` | ✅ | 回复文本 |
| `reply_image(url)` | ✅ | 回复图片 |
| `reply_chain(chain)` | ✅ | 回复消息链 |
| `plain_result(text)` | ✅ | 创建纯文本结果 |
| `platform_id` | ✅ | 平台实例 ID |
| `message_type` | ✅ | 消息类型（group/private/other） |
| `self_id` | ✅ | 机器人 ID |
| `sender_name` | ✅ | 发送者名称 |
| `unified_msg_origin` | ✅ | 统一消息来源字符串 |
| `is_private_chat()` | ✅ | 是否私聊 |
| `is_admin()` | ✅ | 是否管理员 |
| `is_wake_up()` | ❌ | 是否唤醒 |
| `stop_event()` | ✅ | 停止 SDK 本地阶段传播 |
| `continue_event()` | ✅ | 恢复 SDK 本地阶段传播 |
| `is_stopped()` | ✅ | 是否已停止 |
| `get_messages()` | ✅ | 返回 SDK 消息组件列表，未知段落保留为 `UnknownComponent` |
| `get_message_outline()` | ✅ | 获取消息概要 |
| `react(emoji)` | ✅ | 表情回应，平台不支持时返回 `False` |
| `send_typing()` | ✅ | 输入中状态，平台不支持时返回 `False` |
| `send_streaming()` | ✅ | 通过 core 复用 legacy streaming/fallback |
| `set_extra(k, v)` | ✅ | 当前 `MessageEvent` 实例内的本地附加信息 |
| `get_extra(k?)` | ✅ | 获取当前事件本地附加信息 |
| `clear_extra()` | ✅ | 清除当前事件本地附加信息 |
| `image_result(url)` | ✅ | 创建图片结果 |
| `chain_result(chain)` | ✅ | 创建消息链结果 |
| `get_group()` | ✅ | 获取当前消息所属群聊数据；私聊返回 `None` |
| `request_llm()` | ✅ | 触发默认 LLM 请求 |
| `set_result()` | ✅ | 设置处理结果 |
| `get_result()` | ✅ | 获取处理结果 |
| `clear_result()` | ✅ | 清空处理结果 |
| `make_result()` | ✅ | 构造 SDK 本地标准结果对象 |
| `should_call_llm()` | ✅ | 标记/查询是否继续默认 LLM |
| `get_platform_id()` | ✅ | 获取平台实例 ID |
| `get_message_type()` | ✅ | 获取消息类型 |
| `get_session_id()` | ✅ | 获取会话 ID |

---

## 装饰器/触发器

| 装饰器 | 状态 | 说明 |
| --- | --- | --- |
| `@on_command("cmd")` | ✅ | 命令触发 |
| `@on_message(regex="...")` | ✅ | 正则触发 |
| `@on_message(keywords=[...])` | ✅ | 关键词触发 |
| `@require_admin` | ✅ | 管理员权限 |
| `@provide_capability(...)` | ✅ | 声明能力 |
| `@on_command(aliases=[...])` | 🔄 | 命令别名 |
| `@on_message(platforms=[...])` | 🔄 | 平台过滤 |
| `@on_event("type")` | 🔄 | 已支持 `astrbot_loaded/platform_loaded/after_message_sent`，其他事件仍待补齐 |
| `@on_schedule(cron="...")` | ✅ | Cron 定时触发 |
| `@on_schedule(interval_seconds=N)` | ✅ | 间隔定时触发 |
| `@on_message(message_types=[...])` | ✅ | 消息类型过滤（GROUP/PRIVATE/OTHER） |
| `@register_llm_tool()` | ✅ | LLM 工具注册 |
| `@register_agent()` | ✅ | Agent 注册（metadata 注册，实际执行仍由 Core tool loop 驱动） |
| `@session_waiter(timeout=30)` | ✅ | 会话等待装饰器 |
| `@custom_filter` | ✅ | 自定义过滤器 |
| 命令组/子命令 | ✅ | 子命令路由（CommandGroup） |
| 命令参数类型解析 | ✅ | 自动解析 int/float/bool/str/GreedyStr 类型参数 |

---

## 事件类型

| 事件 | 状态 | 说明 |
| --- | --- | --- |
| 消息事件 | ✅ | `@on_command`, `@on_message` |
| astrbot_loaded | ✅ | Core 启动完成 |
| platform_loaded | ✅ | 平台连接成功 |
| waiting_llm_request | ✅ | 准备调用 LLM（获取锁之前通知） |
| llm_request | ✅ | LLM 请求开始 |
| llm_response | ✅ | LLM 响应完成 |
| decorating_result | ✅ | 发送前装饰 |
| calling_func_tool | ✅ | 函数工具调用 |
| using_llm_tool | ✅ | LLM 工具使用 |
| llm_tool_respond | ✅ | LLM 工具响应 |
| after_message_sent | ✅ | 消息发送后（按实际发送次数触发） |
| plugin_error | ✅ | 插件错误 |
| plugin_loaded | ✅ | 插件加载 |
| plugin_unloaded | ✅ | 插件卸载 |

---

## 消息组件

| 组件 | 状态 | 说明 |
| --- | --- | --- |
| Plain (文本) | ✅ | 已支持 |
| Image (图片) | ✅ | 已支持 |
| **At (@某人)** | ✅ | @提及 |
| **AtAll (@全体)** | ✅ | @全体成员 |
| **Reply (引用)** | ✅ | 引用回复 |
| **Record (语音)** | ✅ | 语音消息 |
| **Video (视频)** | ✅ | 视频消息 |
| **File (文件)** | ✅ | 文件附件 |
| **Face (表情)** | ❌ | QQ 表情 |
| **Forward (转发)** | ✅ | 合并转发 |
| **Poke (戳一戳)** | ✅ | 戳一戳动作 |
| **Node (转发节点)** | ❌ | 合并转发节点 |
| **Nodes (多节点)** | ❌ | 多个转发节点 |
| **Json (JSON)** | ❌ | JSON 消息 |
| **RPS (猜拳)** | ❌ | 石头剪刀布 |
| **Dice (骰子)** | ❌ | 骰子消息 |
| **Shake (窗口抖动)** | ❌ | 窗口抖动 |
| **Share (分享)** | ❌ | 链接分享卡片 |
| **Contact (联系人)** | ❌ | 联系人推荐 |
| **Location (位置)** | ❌ | 地理位置 |
| **Music (音乐)** | ❌ | 音乐分享 |
| **WechatEmoji (微信表情)** | ❌ | 微信表情包 |

### 消息组件方法对比

| 方法/功能 | 旧系统状态 | 说明 |
| --- | --- | --- |
| `Image.fromURL()` | ✅ | 从URL创建图片 |
| `Image.fromFileSystem()` | ✅ | 从本地文件创建图片 |
| `Image.fromBase64()` | ✅ | 从Base64创建图片 |
| `Image.fromBytes()` | ✅ | 从字节创建图片 |
| `Image.convert_to_file_path()` | ✅ | 转换为本地文件路径 |
| `Image.convert_to_base64()` | ❌ | 转换为Base64编码 |
| `Image.register_to_file_service()` | ✅ | 注册到文件服务 |
| `Record.fromFileSystem()` | ✅ | 从文件系统创建语音 |
| `Record.fromURL()` | ✅ | 从URL创建语音 |
| `Record.convert_to_file_path()` | ✅ | 转换为本地文件路径 |
| `Record.register_to_file_service()` | ✅ | 注册到文件服务 |
| `Video.fromFileSystem()` | ✅ | 从文件系统创建视频 |
| `Video.fromURL()` | ✅ | 从URL创建视频 |
| `Video.convert_to_file_path()` | ✅ | 转换为本地文件路径 |
| `File.get_file()` | ✅ | 异步获取文件 |
| `File.register_to_file_service()` | ✅ | 注册到文件服务 |
| `Node` / `Nodes` | ❌ | 合并转发消息构造 |
| `toDict()` | ✅ | 同步转换为字典 |
| `to_dict()` | ✅ | 异步转换为字典 |

---

## Legacy Context 兼容

| Legacy 方法 | SDK 等价 | 状态 | 说明 |
| --- | --- | --- | --- |
| `llm_generate()` | `ctx.llm.chat()` | ✅ | 基本对话 |
| `get_registered_star()` | `ctx.metadata.get_plugin()` | ✅ | 获取插件 |
| `get_all_stars()` | `ctx.metadata.list_plugins()` | ✅ | 列出插件 |
| `get_config()` | `ctx.metadata.get_plugin_config()` | ✅ | 获取配置 |
| `send_message()` | `ctx.platform.send()` | ✅ | 发送消息 |
| `get_db()` | `ctx.db` | ✅ | 数据库 |
| `llm_generate(image_urls=...)` | `ctx.llm.chat(image_urls=...)` | ✅ | 图片输入 |
| `llm_generate(tools=...)` | `ctx.llm.chat(tools=...)` | ✅ | 工具调用 |
| `tool_loop_agent()` | `ctx.tool_loop_agent()` | ✅ | Agent 循环（始终走 Core ToolLoopAgentRunner） |
| `get_llm_tool_manager()` | `ctx.get_llm_tool_manager()` | ✅ | 工具管理器 |
| `activate_llm_tool()` | `ctx.activate_llm_tool()` | ✅ | 激活工具 |
| `deactivate_llm_tool()` | `ctx.deactivate_llm_tool()` | ✅ | 停用工具 |
| `add_llm_tools()` | `ctx.add_llm_tools()` | ✅ | 添加工具 |
| `get_using_provider()` | `ctx.get_using_provider()` | ✅ | 获取 Provider |
| `get_current_chat_provider_id()` | `ctx.get_current_chat_provider_id()` | ✅ | 获取当前会话正在使用的聊天 Provider ID |
| `get_all_providers()` | `ctx.get_all_providers()` | ✅ | 列出 Provider |
| `get_all_tts_providers()` | `ctx.get_all_tts_providers()` | ✅ | 列出 TTS Provider |
| `get_all_stt_providers()` | `ctx.get_all_stt_providers()` | ✅ | 列出 STT Provider |
| `get_all_embedding_providers()` | `ctx.get_all_embedding_providers()` | ✅ | 列出 Embedding Provider |
| `get_using_tts_provider()` | `ctx.get_using_tts_provider()` | ✅ | TTS Provider |
| `get_using_stt_provider()` | `ctx.get_using_stt_provider()` | ✅ | STT Provider |
| `register_web_api()` | `ctx.http.register_api()` | ✅ | 注册 API |
| `register_commands()` | `ctx.register_commands()` | ✅ | 注册命令描述/帮助信息；仅在 `astrbot_loaded`/`platform_loaded` 事件中可用 |
| `register_task()` | `ctx.register_task()` | ✅ | 注册后台任务；返回 SDK 后台任务对象 |
| `get_platform()` | `ctx.get_platform()` | ✅ | 按平台类型获取 `PlatformCompatFacade` |
| `get_platform_inst()` | `ctx.get_platform_inst()` | ✅ | 按平台实例 ID 获取 `PlatformCompatFacade` |
| `get_event_queue()` | 无 | ❌ | 事件队列 |

---

## 工具方法

| 方法 | 状态 | 说明 |
| --- | --- | --- |
| `Star.text_to_image(text)` | ✅ | 通过 `ctx.text_to_image()` 等价覆盖 |
| `Star.html_render(html)` | ✅ | 通过 `ctx.html_render()` 等价覆盖 |
| `get_data_dir()` | ✅ | 通过 `ctx.get_data_dir()` 获取插件数据目录 |
| `create_message()` | ❌ | 创建消息对象 |
| `create_event()` | ❌ | 创建并提交事件 |
| `MessageChain.get_plain_text()` | ✅ | 获取消息链纯文本 |

---

## 会话控制（SessionWaiter）

| 类/方法 | 状态 | 说明 |
| --- | --- | --- |
| `SessionWaiterManager` | ✅ | 会话等待管理器（SDK内部使用） |
| `SessionController` | ✅ | 会话控制器 |
| `SessionController.stop()` | ✅ | 立即结束会话 |
| `SessionController.keep(timeout)` | ✅ | 保持会话 |
| `SessionController.get_history_chains()` | ✅ | 获取历史消息链 |
| `@session_waiter(timeout=30)` | ✅ | 会话等待装饰器 |

---

## 过滤器（Filter）

| 过滤器 | 状态 | 说明 |
| --- | --- | --- |
| `CustomFilter` | ✅ | 自定义过滤器基类 |
| `CustomFilter.__and__()` | ✅ | 过滤器与运算（`all_of`） |
| `CustomFilter.__or__()` | ✅ | 过滤器或运算（`any_of`） |
| `MessageTypeFilter` | ✅ | 消息类型过滤器（GROUP/PRIVATE/OTHER） |
| `PlatformFilter` | ✅ | 平台适配器过滤器 |

---

## 高级管理器

| 管理器/方法 | 状态 | 说明 |
| --- | --- | --- |
| **PersonaManager** | ✅ | 人格管理器 |
| `get_persona(persona_id)` | ✅ | 获取人格 |
| `get_all_personas()` | ✅ | 获取所有人格 |
| `create_persona(...)` | ✅ | 创建人格 |
| `update_persona(...)` | ✅ | 更新人格 |
| `delete_persona(persona_id)` | ✅ | 删除人格 |
| **ConversationManager** | ✅ | 对话管理器 |
| `new_conversation(umo)` | ✅ | 新建对话 |
| `switch_conversation(umo, cid)` | ✅ | 切换对话 |
| `delete_conversation(umo, cid)` | ✅ | 删除对话 |
| `get_conversation(umo, cid)` | ✅ | 获取对话 |
| `get_conversations(umo)` | ✅ | 获取对话列表 |
| `update_conversation(...)` | ✅ | 更新对话 |
| **KnowledgeBaseManager** | ✅ | 知识库管理器 |
| `get_kb(kb_id)` | ✅ | 获取知识库 |
| `create_kb(...)` | ✅ | 创建知识库 |
| `delete_kb(kb_id)` | ✅ | 删除知识库 |

---

## Provider 管理

| 方法 | 状态 | 说明 |
| --- | --- | --- |
| `set_provider(provider_id, type, umo)` | ✅ | 设置提供商 |
| `get_provider_by_id(provider_id)` | ✅ | 根据ID获取提供商实例 |
| `get_using_provider(type, umo)` | ✅ | 获取当前使用的提供商（通过 Provider 查询接口暴露） |
| `load_provider(config)` | ✅ | 加载提供商 |
| `terminate_provider(provider_id)` | ✅ | 终止提供商 |
| `create_provider(config)` | ✅ | 创建提供商 |
| `update_provider(origin_id, config)` | ✅ | 更新提供商 |
| `delete_provider(provider_id)` | ✅ | 删除提供商 |
| `register_provider_change_hook(hook)` | ✅ | 注册提供商变更钩子 |
| `get_insts()` | ✅ | 获取所有提供商实例列表 |
| `get_merged_provider_config(config)` | ✅ | 获取合并后的提供商配置 |

### Provider 类型枚举

| 类型 | 状态 | 说明 |
| --- | --- | --- |
| `ProviderType.CHAT_COMPLETION` | ✅ | 聊天完成 |
| `ProviderType.SPEECH_TO_TEXT` | ✅ | 语音转文字 |
| `ProviderType.TEXT_TO_SPEECH` | ✅ | 文字转语音 |
| `ProviderType.EMBEDDING` | ✅ | 嵌入向量 |
| `ProviderType.RERANK` | ✅ | 重排序 |

---

## Provider 实体类

| 类 | 状态 | 说明 |
| --- | --- | --- |
| `ProviderMeta` | ✅ | 提供商元数据（id, model, type, provider_type） |
| `ProviderRequest` | ✅ | 提供商请求对象 |
| `TokenUsage` | ❌ | Token 使用统计 |
| `LLMResponse` (完整版) | 🔄 | 已包含 `usage`、`tool_calls`、`reasoning_content`、`reasoning_signature`，但未提供 legacy 风格完整实体集 |
| `ToolCallsResult` | ✅ | 工具调用结果 |
| `RerankResult` | ✅ | 重排序结果 |
| `MessageSession` | ✅ | 消息会话对象（platform_name, message_type, session_id） |
| `MessageSession.from_str()` | ✅ | 从字符串解析会话 |
| `Providers` 类型别名 | ❌ | Provider/STT/TTS/Embedding/Rerank 联合类型 |

---

## TTS/STT/Embedding Provider

| 方法 | 状态 | 说明 |
| --- | --- | --- |
| **STTProvider** | ✅ | 语音转文字提供商 |
| `get_text(audio_url)` | ✅ | 获取音频的文本 |
| **TTSProvider** | ✅ | 文字转语音提供商 |
| `get_audio(text)` | ✅ | 获取文本的音频（返回文件路径） |
| `get_audio_stream(text_q, audio_q)` | ✅ | 流式 TTS 处理 |
| `support_stream()` | ✅ | 是否支持流式 TTS |
| **EmbeddingProvider** | ✅ | 嵌入向量提供商 |
| **RerankProvider** | ✅ | 重排序提供商 |

---

## Platform 实体

| 类/方法 | 状态 | 说明 |
| --- | --- | --- |
| `PlatformStatus` 枚举 | ✅ | 平台状态（PENDING/RUNNING/ERROR/STOPPED） |
| `PlatformError` | ✅ | 平台错误信息 |
| `Platform.record_error()` | ❌ | 记录平台错误 |
| `Platform.last_error` | ✅ | 最近一次平台错误 |
| `Platform.errors` | ✅ | 平台错误历史 |
| `Platform.clear_errors()` | ✅ | 清空平台错误历史 |
| `Platform.send_by_session()` | ✅ | 通过会话发送消息 |
| `Platform.commit_event()` | ❌ | 提交事件到队列 |
| `Platform.get_client()` | ❌ | 获取平台客户端对象 |
| `Platform.get_stats()` | ✅ | 获取平台统计信息 |
| `Platform.unified_webhook()` | 🔄 | 已支持统一 webhook 状态观测，不提供 legacy 原始方法入口 |
| `Platform.webhook_callback()` | ❌ | Webhook 回调 |

---

## Agent 运行器

| 类/方法 | 状态 | 说明 |
| --- | --- | --- |
| `BaseAgentRunner` | ✅ | Agent 运行器基类（SDK 抽象入口） |
| `AgentState` 枚举 | ❌ | Agent 状态（IDLE/RUNNING/DONE/ERROR） |
| `reset(context, hooks)` | ❌ | 重置 Agent 状态 |
| `step()` | ❌ | 执行单步 |
| `step_until_done(max_step)` | ❌ | 执行直到完成 |
| `done()` | ❌ | 检查是否完成 |
| `get_final_llm_resp()` | ❌ | 获取最终 LLM 响应 |

---

## Handler 注册表

| 类/方法 | 状态 | 说明 |
| --- | --- | --- |
| `StarHandlerRegistry` | ❌ | Handler 注册表 |
| `get_handlers_by_event_type(type)` | ✅ | 按事件类型获取 Handler |
| `get_handler_by_full_name(name)` | ✅ | 按全名获取 Handler |
| `get_handlers_by_module_name(name)` | ❌ | 按模块名获取 Handler |
| `StarHandlerMetadata` | ❌ | Handler 元数据 |

---

## 优先级

### P0 - 旧插件替代必需能力

**说明**：这些是旧系统已有、且缺失后会直接阻塞插件迁移的能力。判断标准是“老插件作者常用、直接影响消息主链/触发/发送/Provider 调用/会话行为”。

#### P0.0 - 基础核心能力（已实现 ✅）

> **路由机制验证**：以下能力已确认正确实现"旧插件走旧逻辑，新插件走SDK"的分离路由：
> - 消息分发：`ProcessStage.process()` 先处理旧插件 `activated_handlers`，后处理 SDK 插件 `sdk_plugin_bridge.dispatch_message()`
> - 旧插件：同进程直接调用 `Context` 对象
> - SDK 插件：独立 Worker 进程，通过 `CoreCapabilityBridge` → `CapabilityProxy` 协议调用

1. **LLM Client** - 基本对话功能（`chat`, `chat_raw`, `stream_chat`）
   - 旧插件：`context.llm_generate()` / `context.tool_loop_agent()`
   - SDK 插件：`ctx.llm.chat()` / `ctx.llm.chat_raw()` / `ctx.llm.stream_chat()`
2. **DB Client (KV)** - 键值存储（`get`, `set`, `delete`, `list`, `get_many`, `set_many`）
   - 旧插件：`context.get_db()` 返回 `BaseDatabase`
   - SDK 插件：`ctx.db.get()` / `ctx.db.set()` 等
3. **Platform Client** - 基础消息发送（`send`, `send_image`, `send_chain`）
   - 旧插件：`context.send_message(session, chain)`
   - SDK 插件：`ctx.platform.send()` / `ctx.platform.send_image()` / `ctx.platform.send_chain()`
4. **Metadata Client** - 插件元数据（`get_plugin`, `list_plugins`, `get_current_plugin`, `get_plugin_config`）
   - 旧插件：`context.get_registered_star()` / `context.get_all_stars()`
   - SDK 插件：`ctx.metadata.get_plugin()` / `ctx.metadata.list_plugins()`
5. **基础装饰器** - `@on_command`, `@on_message`, `@require_admin`, `@provide_capability`
   - 旧插件：`@star.register(...)` 等
   - SDK 插件：独立的 `astrbot_sdk.decorators` 模块
6. **基础消息组件** - `Plain`, `Image`
   - 旧插件：`MessageChain([Plain(...), Image(...)])`
   - SDK 插件：SDK 原生 `Plain`, `Image` 组件
7. **MessageEvent** 基础属性 - `text`, `platform`, `session_id`, `user_id`, `group_id`, `raw`
   - 旧插件：`event.message_str`, `event.unified_msg_origin` 等
   - SDK 插件：`astrbot_sdk.events.MessageEvent` 独立类
8. **基础回复方法** - `reply()`, `reply_image()`, `reply_chain()`, `plain_result()`
   - 旧插件：`event.set_result(MessageEventResult().message(...))`
   - SDK 插件：`event.reply()` / `event.reply_image()` / `event.reply_chain()` / `event.plain_result()`

#### P0.1 - 阻塞迁移的关键能力 ✅ 已完成

| 项目 | 状态 | 实现说明 |
|------|------|---------|
| **Memory Client** | ✅ | 8个方法全部实现，使用 JSON 文件存储（`capability_bridge.py`） |
| **HTTP Client** | ✅ | 3个方法全部实现，支持路由注册/注销/列表（`plugin_bridge.py`） |
| **MessageEvent 扩展** | ✅ | `self_id`, `platform_id`, `message_type`, `sender_name`, `is_admin`, `unified_msg_origin`, `is_private_chat()` 等 |
| **事件控制** | ✅ | `stop_event()`, `continue_event()`, `is_stopped()` |
| **基础事件类型** | ✅ | `astrbot_loaded`, `platform_loaded`, `after_message_sent` |
| **工具方法** | ✅ | `get_data_dir()`, `text_to_image()`, `html_render()` |
| **会话等待** | ✅ | `SessionWaiter`, `SessionController`，支持注册/注销/分发 |
| **Provider 实体** | ✅ | `MessageSession` 类，支持 `from_str()` 解析 |

#### P0.2 - 消息与结果对象 ✅ 已完成

| 项目 | 状态 | 实现说明 |
|------|------|---------|
| **消息组件** | ✅ | `At`, `AtAll`, `Reply`, `Record`, `Video`, `File`, `Poke`, `Forward` 全部实现 |
| **消息组件方法** | ✅ | `Image.convert_to_file_path()`, `register_to_file_service()`, `File.get_file()` 全部实现 |
| **MessageEvent 扩展方法** | ✅ | `react()`, `send_typing()`, `send_streaming()`, `get_messages()`, `get_message_outline()` |
| **结果对象** | ✅ | `image_result()`, `chain_result()`, `make_result()` |
| **额外信息** | ✅ | `set_extra()`, `get_extra()`, `clear_extra()` |

> **平台兼容性说明**：
> #TODO:我们需要限制平台的能力
> - `send_streaming()` - ✅ 所有平台支持（aiocqhttp, discord, dingtalk, lark, line, misskey, qqofficial, satori, slack, telegram, webchat, wecom, wecom_ai_bot, weixin_official_account）
> - `react()` - ⚠️ 仅 Discord、飞书(Lark)、Telegram 支持，其他平台返回 `False`
> - `send_typing()` - ⚠️ 仅 Telegram 支持，其他平台返回 `False`
> - 消息组件、结果对象、额外信息方法不依赖平台特性，全平台通用

#### P0.3 - 命令、过滤器与调度 ✅ 已完成
1. **触发器扩展** - ✅ `@on_event`, ✅ `@on_schedule(cron/interval)`, ✅ `@on_message(message_types=[])`
2. **自定义过滤器** - ✅ `CustomFilter`, ✅ `@custom_filter`, ✅ 过滤器组合 `all_of()` / `any_of()`
3. **命令组系统** - ✅ `CommandGroup`, ✅ 子命令路由, ✅ `print_cmd_tree()`
4. **命令参数类型解析** - ✅ `int`, ✅ `float`, ✅ `bool`, ✅ `Optional[T]`, ✅ `GreedyStr`
5. **平台/消息类型过滤** - ✅ `PlatformFilter`, ✅ `MessageTypeFilter`
6. **命令别名** - ✅ `@on_command(aliases=[])`

#### P0.4 - 事件与处理主链 ✅ 已完成
1. **完整事件类型** - ✅ `waiting_llm_request`, ✅ `llm_request`, ✅ `llm_response`, ✅ `decorating_result`, ✅ `calling_func_tool`, ✅ `using_llm_tool`, ✅ `llm_tool_respond`, ✅ `plugin_error`, ✅ `plugin_loaded`, ✅ `plugin_unloaded`
2. **默认 LLM 控制** - ✅ `request_llm()`, ✅ `should_call_llm()`
3. **结果控制** - ✅ `set_result()`, ✅ `get_result()`, ✅ `clear_result()`
4. **Handler 注册表与可观测性** - ✅ `RegistryClient`, ✅ `get_handlers_by_event_type()`, ✅ `get_handler_by_full_name()`
5. **Handler 白名单** - ✅ `set_handler_whitelist()`, ✅ `get_handler_whitelist()`, ✅ `clear_handler_whitelist()` 按插件名称过滤

#### P0.5 - LLM、工具与 Provider 使用能力 ✅ 已完成
1. **Agent 运行器** - ✅ `BaseAgentRunner`, ✅ `tool_loop_agent()`
2. **LLM 工具管理** - ✅ `get_llm_tool_manager()`, ✅ `activate_llm_tool()`, ✅ `deactivate_llm_tool()`, ✅ `add_llm_tools()`
3. **LLM 工具注册** - ✅ `@register_llm_tool()`
4. **Agent 注册** - ✅ `@register_agent()`
5. **Provider 查询** - ✅ `get_using_provider()`, ✅ `get_current_chat_provider_id()`, ✅ `get_all_providers()`, ✅ `get_all_tts_providers()`, ✅ `get_all_stt_providers()`, ✅ `get_all_embedding_providers()`, ✅ `get_using_tts_provider()`, ✅ `get_using_stt_provider()`
6. **Provider 类型与结果实体** - ✅ `ProviderType.*`, ✅ `ProviderMeta`, ✅ `ProviderRequest`, ✅ `ToolCallsResult`, ✅ `RerankResult`

#### P0.6 - 平台与会话能力 ✅ 已完成
1. **PlatformClient 扩展** - ✅ `send_by_id()`, ✅ `send_by_session()`, ✅ `get_members()`
2. **群组管理** - ✅ `get_group()`, ✅ 群成员列表获取
3. **会话级插件管理** - ✅ `SessionPluginManager`, ✅ `is_plugin_enabled_for_session()`, ✅ `filter_handlers_by_session()`
4. **会话级服务开关** - ✅ `SessionServiceManager`, ✅ `is_llm_enabled_for_session()`, ✅ `set_llm_status_for_session()`, ✅ `should_process_llm_request()`, ✅ `is_tts_enabled_for_session()`, ✅ `set_tts_status_for_session()`, ✅ `should_process_tts_request()`

#### P0.7 - Legacy Context 与开发者入口 🔄 部分完成
1. **Legacy Context 迁移入口** - ✅ `register_commands()`, ✅ `register_task()`, ✅ `get_platform()`, ✅ `get_platform_inst()`；❌ `get_event_queue()`
2. **StarTools 迁移入口** - ❌ `create_message()`, ❌ `create_event()`；✅ `MessageChain.get_plain_text()`

---

### P1 - 旧插件后置兼容能力

**说明**：这些能力旧系统里有，但不属于首批迁移阻塞项。它们仍然需要补齐，只是优先级低于 P0。

#### P1.1 - 多媒体与专用 Provider ✅ 已完成
1. **STTProvider** - ✅ `get_text(audio_url)`
2. **TTSProvider** - ✅ `get_audio(text)`, ✅ `get_audio_stream()`, ✅ `support_stream()`
3. **EmbeddingProvider** - ✅ 嵌入向量提供商
4. **RerankProvider** - ✅ 重排序提供商

#### P1.2 - 高级管理器
1. **PersonaManager** - ✅ 人格管理器（`get_persona()`, `get_all_personas()`, `create_persona()`, `update_persona()`, `delete_persona()`）
2. **ConversationManager** - ✅ 对话管理器（`new_conversation()`, `switch_conversation()`, `delete_conversation()`, `get_conversation()`, `get_conversations()`, `update_conversation()`）
3. **KnowledgeBaseManager** - ✅ 知识库管理器（`get_kb()`, `create_kb()`, `delete_kb()`）

#### P1.3 - Provider 与 Platform 管理面 🔄 部分完成
1. **Provider 管理** - ✅ `set_provider()`, `get_provider_by_id()`, `get_using_provider()`, `load_provider()`, `terminate_provider()`, `create_provider()`, `update_provider()`, `delete_provider()`, `register_provider_change_hook()`, `get_insts()`, `get_merged_provider_config()`
2. **Platform 实体** - ✅ `PlatformStatus` 枚举, `PlatformError`, `last_error`, `errors`, `clear_errors()`, `send_by_session()`, `get_stats()`；🔄 `unified_webhook()`；❌ `record_error()`, `commit_event()`, `get_client()`
3. **Webhook 处理** - 🔄 只补统一 webhook 状态观测；`webhook_callback()` 原始请求入口与 Dashboard webhook 路由延期

#### P1.4 - Star 兼容层与开发工具 ✅ 已完成
1. **Star 基类方法/属性** - `context` 属性及剩余兼容层 ✅
2. **PluginKVStoreMixin** - `put_kv_data()`, `get_kv_data()`, `delete_kv_data()`, `plugin_id` ✅
3. **StarMetadata 字段** - `support_platforms`, `astrbot_version` ✅
4. **StarTools 补齐** - `send_message()`, `send_message_by_id()`, `_context`, 剩余 LLM Tool 工具方法 ✅
5. **动态 LLM Tool 注册** - `register_llm_tool()`, `unregister_llm_tool()` ✅

#### P1.5 - 其他系统能力
1. **文件服务** - `ctx.files.register_file()`, `ctx.files.handle_file()`, `register_to_file_service()` ✅
2. **MCP 支持** - `MCPClient`, `MCPTool`
3. **事件总线** - `EventBus`, `event_queue`
4. **热重载** - `_watch_plugins_changes()`
5. **国际化** - `ConfigMetadataI18n`, `convert_to_i18n_keys()`
6. **插件依赖管理** - `PluginVersionIncompatibleError`, `PluginDependencyInstallError`, `_import_plugin_with_dependency_recovery()`
7. **消息撤回** - 消息撤回 API
8. **日志系统** - `ctx.logger.watch()` ✅；`LogBroker` / `LogManager.GetLogger()` 延期
9. **Cron 定时任务管理** - `CronJobManager`, 任务持久化 //被替代
10. **Reply 消息组件属性** - `id`, `chain`, `sender_id`, `sender_nickname`, `message_str` ✅

---

### P2 - SDK 可扩展能力

**说明**：这些不是 legacy 替代的硬性要求，而是新 SDK 可以继续增强的方向。

#### P2.1 - CancelToken 取消机制扩展
1. `cancel(reason: str)` - 取消时传递原因
2. `on_cancel(callback)` - 注册取消回调，支持清理逻辑
3. `with_timeout(seconds)` - 辅助方法：超时自动取消
4. `CancelToken.any(*tokens)` - 组合取消：任一取消即触发
5. `CancelToken.all(*tokens)` - 组合取消：全部取消才触发

#### P2.2 - provide_capability 能力导出扩展
1. `version: str` - 能力版本控制
2. `requires: list[str]` - 声明依赖的其他 capability
3. `middleware: list[Middleware]` - 能力拦截器/中间件支持
4. `rate_limit: RateLimit` - 速率限制声明
5. `cache_policy: CachePolicy` - 缓存策略声明

#### P2.3 - Handler kind 类型实现
1. `hook` - 钩子类型（定义但未在运行时实现）
2. `tool` - LLM Function Calling 工具类型
3. `session` - 会话级处理器类型

#### P2.4 - Permissions 权限系统扩展
1. `roles: list[str]` - 角色系统支持
2. `scopes: list[str]` - 细粒度权限范围
3. `platforms: list[str]` - 平台级权限限制
4. `allow_users: list[str]` - 用户白名单
5. `deny_users: list[str]` - 用户黑名单

#### P2.5 - 插件间 Capability 调用
1. `ctx.capability.discover()` - 发现其他插件导出的 capability
2. `ctx.capability.invoke(name, payload)` - 调用其他插件的 capability（当前只支持同步）
3. `ctx.capability.invoke_stream(name, payload)` - 流式调用其他插件的 capability
4. 版本协商 - capability 版本兼容性检查

#### P2.6 - 事件类型标准化
1. `EventType` 枚举 - 标准化事件类型常量，避免拼写不一致
2. 事件 payload schema - 每种事件的标准化 payload 结构定义

#### P2.7 - 依赖注入扩展
1. 自定义类型注入器 - 允许插件注册自定义类型的依赖注入
2. 配置注入 - 自动注入插件配置项到 handler 参数
3. 依赖注入容器 - 支持更复杂的依赖关系

#### P2.8 - 调度器验证
1. `@on_schedule` Core 端调度器验证 - 验证 Core 端是否有完整调度器实现
2. 持久化任务验证 - 验证定时任务是否支持持久化

---

### 优先级说明

- **P0**：旧系统真实有，且缺了就会直接阻塞插件迁移
  - **P0.0**：已实现的基础能力 ✅
  - **P0.1**：已完成的关键 bridge 能力 ✅
  - **P0.2**：消息与结果对象 ✅
  - **P0.3**：命令、过滤器与调度
  - **P0.4**：事件与处理主链
  - **P0.5**：LLM、工具与 Provider 使用能力
  - **P0.6**：平台与会话能力
  - **P0.7**：Legacy Context 与开发者入口

- **P1**：旧系统有，但可排在首批迁移之后补齐
  - **P1.1**：多媒体与专用 Provider（已实现 ✅）
  - **P1.2**：高级管理器
  - **P1.3**：Provider 与 Platform 管理面
  - **P1.4**：Star 兼容层与开发工具（已实现 ✅）
  - **P1.5**：其他系统能力

- **P2**：新 SDK 的可扩展增强方向
  - **P2.1**：CancelToken 扩展
  - **P2.2**：provide_capability 扩展
  - **P2.3**：Handler kind 实现
  - **P2.4**：Permissions 扩展
  - **P2.5**：插件间 Capability 调用
  - **P2.6**：事件类型标准化
  - **P2.7**：依赖注入扩展
  - **P2.8**：调度器验证

> 注：这里把“旧系统有但不是首批迁移阻塞项”的内容从原 P0 后半段下沉到了 P1，这样 P0 更聚焦，也更符合实际替代路径。

---

## 旧系统能力详情（已整合到 P0/P1）

> 说明：以下是旧系统各模块的详细能力列表，已按类别整合到上述 P0 / P1 优先级中。

### Star基类扩展方法 → P1.4

说明：本节按”能力是否被 SDK 等价覆盖”判定，不要求 API 同名。

| 方法 | 状态 | 说明 | 建议实现 |
| --- | --- | --- | --- |
| `Star.text_to_image(text)` | ✅ | 文本转图片渲染 | 已由 `ctx.text_to_image()` / `Star.text_to_image()` 等价覆盖 |
| `Star.html_render(tmpl, data)` | ✅ | HTML模板渲染 | 已由 `ctx.html_render()` / `Star.html_render()` 等价覆盖 |
| `Star.initialize()` | ✅ | 插件激活时调用（旧系统生命周期） | SDK 已用 `on_start()` 等价覆盖 |
| `Star.terminate()` | ✅ | 插件禁用时调用（旧系统生命周期） | SDK 已用 `on_stop()` 等价覆盖 |
| `Star.__init_subclass__()` | ✅ | 自动注册插件到star_map | SDK已实现类似的`__init_subclass__` |
| `Star.context` | 🔄 | 插件上下文引用 | SDK 通过 handler 参数传递 `ctx`，跨方法需显式透传或自行保存 |
| `Star._get_context_config()` | ✅ | 获取上下文配置 | SDK 已由 `ctx.metadata.get_plugin_config()` 等价覆盖 |

### 命令参数类型系统 → P0.3 ✅

| 参数类型 | 状态 | 说明 | 旧系统实现位置 |
| --- | --- | --- | --- |
| `str` 自动解析 | ✅ | 字符串参数 | `CommandFilter.validate_and_convert_params()` |
| `int` 自动转换 | ✅ | 整数参数自动转换 | `CommandFilter.validate_and_convert_params()` |
| `float` 自动转换 | ✅ | 浮点数参数自动转换 | `CommandFilter.validate_and_convert_params()` |
| `bool` 自动转换 | ✅ | 布尔参数自动转换（支持true/false/yes/no/1/0） | `CommandFilter.validate_and_convert_params()` |
| `Optional[T]` 支持 | ✅ | 可选类型参数 | `CommandFilter.validate_and_convert_params()` |
| `GreedyStr` 贪婪匹配 | ✅ | 捕获剩余所有文本作为单个参数 | `CommandFilter.GreedyStr` |
| `unwrap_optional()` | ✅ | 解析Optional类型注解的工具函数 | `loader._unwrap_optional()` |
| `print_types()` | ❌ | 打印命令参数类型信息用于帮助 | `CommandFilter.print_types()` |

### 过滤器组合与自定义 → P0.3 ✅

| 功能 | 状态 | 说明 | 旧系统实现 |
| --- | --- | --- | --- |
| `CustomFilter` 基类 | ✅ | 自定义过滤器抽象基类 | `astrbot_sdk/filters.py` |
| `CustomFilter.__and__()` | ✅ | 过滤器与运算（&） | `FilterBinding.__and__()` |
| `CustomFilter.__or__()` | ✅ | 过滤器或运算（|） | `FilterBinding.__or__()` |
| `all_of()` | ✅ | 与运算过滤器组合 | `filters.all_of()` |
| `any_of()` | ✅ | 或运算过滤器组合 | `filters.any_of()` |
| `@custom_filter` 装饰器 | ✅ | 将过滤器附加到 handler | `decorators.custom_filter()` |

### 事件系统细节 → P0.4

| 旧系统特性 | 新SDK状态 | 说明 |
| --- | --- | --- |
| `EventType` 枚举（14种事件） | 🔄 | SDK 已覆盖主要事件类型，但未提供 legacy 风格事件枚举对象 |
| `OnWaitingLLMRequestEvent` | ✅ | 以 `waiting_llm_request` 事件类型覆盖 |
| `OnCallingFuncToolEvent` | ✅ | 以 `calling_func_tool` 事件类型覆盖 |
| `OnUsingLLMToolEvent` | ✅ | 以 `using_llm_tool` 事件类型覆盖 |
| `OnLLMToolRespondEvent` | ✅ | 以 `llm_tool_respond` 事件类型覆盖 |
| `StarHandlerRegistry` | ❌ | Handler注册表（全局单例） |
| Handler优先级排序 | ✅ | SDK bridge 按 `priority/load_order/declaration_order` 排序执行 |
| Handler白名单过滤 | ✅ | 已支持按插件名称设置白名单 |

### 平台适配器类型系统 → P0.3

| 平台类型 | 状态 | 说明 |
| --- | --- | --- |
| `PlatformAdapterType` 枚举 | ❌ | 支持15+种平台类型 |
| `AIOCQHTTP` | ❌ | QQ机器人协议 |
| `QQOFFICIAL` | ❌ | QQ官方API |
| `TELEGRAM` | ❌ | Telegram |
| `WECOM`/`WECOM_AI_BOT` | ❌ | 企业微信 |
| `LARK` | ❌ | 飞书 |
| `DINGTALK` | ❌ | 钉钉 |
| `DISCORD` | ❌ | Discord |
| `SLACK` | ❌ | Slack |
| `KOOK` | ❌ | KOOK |
| `VOCECHAT` | ❌ | VoceChat |
| `WEIXIN_OFFICIAL_ACCOUNT` | ❌ | 微信公众号 |
| `SATORI` | ❌ | Satori协议 |
| `MISSKEY` | ❌ | Misskey |
| `LINE` | ❌ | LINE |
| `ADAPTER_NAME_2_TYPE` 映射 | ❌ | 平台名称到类型的映射 |

### StarTools 工具集 → P0.5 / P0.7 / P1.4

| 方法 | 状态 | 说明 | 使用场景 |
| --- | --- | --- | --- |
| `StarTools.send_message(session, chain)` | ✅ | 根据session主动发送消息 | 定时任务、后台通知 |
| `StarTools.send_message_by_id(type, id, chain, platform)` | ✅ | 根据ID直接发送消息 | 跨会话发送 |
| `StarTools.create_message(...)` | ❌ | 创建AstrBotMessage对象 | 构造人工消息事件 |
| `StarTools.create_event(abm, platform)` | ❌ | 创建并提交事件到平台 | 触发处理流程 |
| `StarTools.activate_llm_tool(name)` | ✅ | 激活LLM工具 | 动态控制工具 |
| `StarTools.deactivate_llm_tool(name)` | ✅ | 停用LLM工具 | 动态控制工具 |
| `StarTools.register_llm_tool(...)` | ✅ | 注册LLM工具 | 动态注册 |
| `StarTools.unregister_llm_tool(name)` | ✅ | 注销LLM工具 | 动态注销 |
| `StarTools.get_data_dir(plugin_name?)` | ❌ | 获取插件数据目录 | 文件存储 |
| `StarTools._context` | ✅ | 类级别的Context引用 | 工具方法访问Core |

### 会话级插件管理 → P0.6

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| `SessionPluginManager` 类 | ✅ | 会话级插件管理器 |
| `is_plugin_enabled_for_session(session_id, plugin_name)` | ✅ | 检查插件在会话中是否启用 |
| `filter_handlers_by_session(event, handlers)` | ✅ | 根据会话配置过滤处理器 |
| `session_plugin_config` 配置 | ✅ | 会话插件配置存储 |
| `enabled_plugins` 列表 | ✅ | 会话启用的插件列表 |
| `disabled_plugins` 列表 | ✅ | 会话禁用的插件列表 |

### 会话级 LLM/TTS 开关 → P0.6

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| `SessionServiceManager` 类 | ✅ | 会话级服务开关管理器 |
| `is_llm_enabled_for_session(session_id)` | ✅ | 检查会话是否启用 LLM |
| `set_llm_status_for_session(session_id, enabled)` | ✅ | 设置会话 LLM 开关 |
| `should_process_llm_request(session_id)` | ✅ | 判断是否处理默认 LLM 请求 |
| `is_tts_enabled_for_session(session_id)` | ✅ | 检查会话是否启用 TTS |
| `set_tts_status_for_session(session_id, enabled)` | ✅ | 设置会话 TTS 开关 |
| `should_process_tts_request(session_id)` | ✅ | 判断是否处理 TTS 请求 |
| `is_session_enabled(session_id)` | ❌ | 汇总判断会话服务是否可用 |

### 命令组系统 → P0.3 ✅

| 功能 | 状态 | 说明 | 示例 |
| --- | --- | --- | --- |
| `CommandGroup` 类 | ✅ | 命令组类 | `command_group("admin")` |
| `group.name` 属性 | ✅ | 命令组名称 | - |
| `group.subgroups` 列表 | ✅ | 子命令组列表 | - |
| `group.parent` 引用 | ✅ | 父命令组引用 | 支持嵌套 |
| `group.group()` | ✅ | 添加子命令组 | - |
| `group.command()` | ✅ | 添加子命令（装饰器） | - |
| `group.path` | ✅ | 获取完整命令路径 | `["admin", "echo"]` |
| `print_cmd_tree()` | ✅ | 打印命令树 | 帮助文档 |
| 别名笛卡尔积展开 | ✅ | 组+命令别名组合 | `_expand_aliases()` |

### 消息类型过滤 → P0.3 ✅

| 类型 | 状态 | 说明 |
| --- | --- | --- |
| `MessageTypeFilter` | ✅ | 消息类型过滤器 |
| `group` | ✅ | 群聊消息 |
| `private` | ✅ | 私聊消息 |
| `other` | ✅ | 其他消息 |
| `@on_message(message_types=[...])` | ✅ | 装饰器参数支持 |
| `PlatformFilter` | ✅ | 平台过滤器 |
| 过滤器组合 | ✅ | `all_of()` / `any_of()` |

### PluginKVStoreMixin → P1.4

| 方法 | 状态 | 说明 | 替代方案 |
| --- | --- | --- | --- |
| `PluginKVStoreMixin` 类 | ✅ | 已提供兼容层/等价能力 | SDK的`ctx.db` |
| `put_kv_data(key, value)` | ✅ | 存储键值对 | `ctx.db.set()` |
| `get_kv_data(key, default)` | ✅ | 获取键值对 | `ctx.db.get()` |
| `delete_kv_data(key)` | ✅ | 删除键值对 | `ctx.db.delete()` |
| `plugin_id` 属性 | ✅ | 插件ID标识 | SDK自动处理 |

### StarMetadata 完整字段 → P1.4

| 字段 | 状态 | 说明 |
| --- | --- | --- |
| `name` | ✅ | 插件名称 |
| `author` | ✅ | 插件作者 |
| `desc` | ✅ | 插件描述 |
| `version` | ✅ | 插件版本 |
| `repo` | ✅ | 仓库地址 |
| `star_cls_type` | ✅ | 插件类类型 |
| `module_path` | ✅ | 模块路径 |
| `star_cls` | ✅ | 插件类实例 |
| `module` | ✅ | 模块对象 |
| `root_dir_name` | ✅ | 根目录名称 |
| `reserved` | ✅ | 是否保留插件 |
| `activated` | ✅ | 是否激活 |
| `config` | ✅ | 插件配置 |
| `star_handler_full_names` | ✅ | Handler全名列表 |
| `display_name` | ✅ | 显示名称 |
| `logo_path` | ✅ | Logo路径 |
| `support_platforms` | ✅ | 支持的平台列表 |
| `astrbot_version` | ✅ | 要求的AstrBot版本范围 |

---

## 架构说明

### Core端 MVP 不支持的功能
以下功能 SDK 已定义接口，但 Core 端 `capability_bridge.py` 标记为 MVP 不支持：

1. **db.watch()** 流式订阅

### Core端简化实现的功能
以下功能 Core 端有简化实现，但非完整功能：

1. **memory.search** - 简单字符串匹配，非语义搜索
2. **memory.save_with_ttl** - TTL 仅记录但不实际过期

### 新 SDK 新增能力
以下能力是新 SDK 独有，旧系统没有的：

1. `@provide_capability` - 声明对外暴露的能力
2. `CancelToken` - 取消令牌机制
3. `DBClient.watch()` - 数据库变更订阅
4. `ctx.logger` - 绑定插件 ID 的日志器
5. `AstrBotError` - 完善的错误模型（含错误码、重试标记、序列化）

### 旧系统独有能力
以下能力是旧系统独有，新 SDK 未实现的：

1. `PlatformAdapterType` / 平台类型枚举全量兼容
2. `StarHandlerRegistry` 全局单例与 `StarHandlerMetadata` 原样对象
3. `Platform` 原始实体方法：`record_error()` / `commit_event()` / `get_client()` / `webhook_callback()`
4. `StarTools.create_message()` / `StarTools.create_event()`
5. `get_event_queue()` 直接暴露
6. `TokenUsage` / `Providers` 类型别名 / legacy 风格完整 `LLMResponse`
7. `MCP` / `EventBus` / 热重载 / i18n / 依赖恢复 / 消息撤回
8. `CommandFilter.print_types()` - 命令参数类型打印

---

## 其他系统能力（已整合到 P1.5）

> 说明：以下能力已整合到优先级 P1.5 中，此处保留作为参考。

### 错误处理和异常类型

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `AstrBotError` 基类 | ✅ | SDK 已定义，含 code/message/hint/retryable |
| `ErrorCodes` 常量 | ✅ | SDK 已定义错误码枚举 |
| `to_payload()` / `from_payload()` | ✅ | 错误序列化/反序列化（跨进程传递） |
| `ProviderNotFoundError` | ❌ | Core 端特有异常类型 |

### 日志系统

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `ctx.logger` | ✅ | 绑定插件 ID 的日志器 |
| `LogBroker` 日志代理 | ❌ | 日志缓存和订阅分发 |
| `LogManager.GetLogger()` | ❌ | Core 端日志管理器 |
| 日志订阅机制 | ✅ | `ctx.logger.watch()` 仅订阅当前插件在 SDK worker 内的日志 |

### 文件服务

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `FileTokenService` | ❌ | 临时文件令牌服务 |
| `register_file(path, timeout) -> token` | ✅ | 通过 `ctx.files.register_file()` 注册文件获取下载令牌 |
| `handle_file(token) -> path` | ✅ | 通过 `ctx.files.handle_file()` 解析文件路径 |
| `File.register_to_file_service()` | ✅ | 消息组件通过运行时 context 调宿主文件服务 |
| `File.get_file()` | ✅ | 异步获取文件（支持 URL 下载） |

### Webhook 处理

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `Platform.unified_webhook()` | 🔄 | 已支持统一 Webhook 状态观测，不提供 legacy 原始方法入口 |
| `Platform.webhook_callback(request)` | ❌ | Webhook 回调处理 |
| `/api/platform/webhook/{uuid}` 路由 | ❌ | Dashboard Webhook 路由 |

### MCP (Model Context Protocol)

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `MCPClient.connect_to_server()` | ❌ | 连接 MCP 服务器 |
| `MCPClient.list_tools_and_save()` | ❌ | 列出并保存工具 |
| `MCPClient.call_tool_with_reconnect()` | ❌ | 调用工具（带自动重连） |
| `MCPTool` 包装器 | ❌ | MCP 工具转 Function Tool |

### 事件总线

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `EventBus` | ❌ | 事件分发和处理 |
| `event_queue` | ❌ | 异步事件队列访问 |

### 热重载

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `ASTRBOT_RELOAD=1` 环境变量 | ❌ | 启用热重载 |
| `_watch_plugins_changes()` | ❌ | 监视插件文件变化 |

### 国际化 (i18n)

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `ConfigMetadataI18n` | ❌ | 配置元数据国际化 |
| `convert_to_i18n_keys()` | ❌ | 转换为 i18n 键 |

### 插件依赖管理

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `requirements.txt` 自动安装 | ❓ | Core 端已支持，SDK 需验证 |
| `PluginVersionIncompatibleError` | ❌ | 版本不兼容异常 |
| `PluginDependencyInstallError` | ❌ | 依赖安装失败异常 |
| `_import_plugin_with_dependency_recovery()` | ❌ | 带依赖恢复的导入 |

### 消息撤回

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 消息撤回 API | ❌ | 撤回已发送消息（平台特定） |

### 群组管理

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `get_group(group_id?)` | ✅ | 获取群聊数据 |
| 群成员列表获取 | ✅ | 通过 `ctx.platform.get_members()` 支持 |

### 插件间通信

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `get_registered_star(name)` | ✅ | 通过 `ctx.metadata.get_plugin()` 支持 |
| `get_all_stars()` | ✅ | 通过 `ctx.metadata.list_plugins()` 支持 |
| `StarHandlerRegistry` 访问 | ❌ | 直接访问 Handler 注册表 |
| `get_handlers_by_event_type()` | ✅ | 按事件类型获取 Handler |
| `get_handler_by_full_name()` | ✅ | 按全名获取 Handler |

### 命令参数类型解析

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `str` 参数 | ✅ | 字符串参数 |
| `int` 参数 | ✅ | 整数参数自动转换 |
| `float` 参数 | ✅ | 浮点数参数自动转换 |
| `bool` 参数 | ✅ | 布尔参数自动转换 |
| `Optional[T]` 参数 | ✅ | 可选类型参数 |
| `GreedyStr` 参数 | ✅ | 贪婪字符串（剩余所有文本） |

### Cron 定时任务管理

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `@on_schedule(cron="...")` | ✅ | Cron 表达式定时触发 |
| `@on_schedule(interval_seconds=N)` | ✅ | 间隔秒数定时触发 |
| `ScheduleContext` | ✅ | 调度上下文（注入到 handler） |
| Core 端调度器 | ✅ | `CronJobManager` 支持 cron 和 interval |
| 任务持久化 | ❌ | 定时任务持久化存储 |

### Reply 消息组件属性

| 属性 | 状态 | 说明 |
| --- | --- | --- |
| `Reply.id` | ✅ | 被引用消息 ID |
| `Reply.chain` | ✅ | 被引用的消息段列表 |
| `Reply.sender_id` | ✅ | 发送者 ID |
| `Reply.sender_nickname` | ✅ | 发送者昵称 |
| `Reply.message_str` | ✅ | 被引用消息的纯文本 |
