# AstrBot SDK v4 新旧对比文档

## 目录

1. [整体架构变化](#整体架构变化)
2. [文件级对比](#文件级对比)
   - [__init__.py](#__init__py)
   - [cli.py](#clipy)
   - [context.py](#contextpy)
   - [decorators.py](#decoratorspy)
   - [events.py](#eventspy)
   - [star.py](#starpy)
   - [errors.py](#errorspy)
   - [compat.py](#compatpy)
   - [_legacy_api.py](#_legacy_apipy)
3. [优点总结](#优点总结)
4. [缺点与待改进项](#缺点与待改进项)
5. [改进建议](#改进建议)

---

## 整体架构变化

| 维度 | 旧版 (v3) | 新版 (v4) |
|------|-----------|-----------|
| **架构模式** | 单体架构，插件与核心在同一进程 | 分布式架构，插件独立进程，通过 RPC 通信 |
| **Context 设计** | 抽象基类 (ABC)，由 Core 实现 | 具体类，通过 CapabilityProxy 代理 |
| **文件组织** | 功能分散在子目录 (api/, cli/, runtime/) | 核心概念提升到第一层，便于导入 |
| **兼容层** | 无独立兼容层 | 新增 `_legacy_api.py`、`compat.py`，并在 `api/` 下保留薄兼容导出 |
| **错误处理** | 无统一错误类 | 新增 AstrBotError 支持跨进程传递 |
| **取消控制** | 无统一机制 | 新增 CancelToken 数据类 |

### 目录结构对比

```
旧版 src/astrbot_sdk/
├── __main__.py          # 仅入口
├── api/                 # API 定义
│   ├── event/           # 事件相关
│   ├── star/            # Star 插件
│   └── basic/           # 基础类型
├── cli/                 # CLI 命令
├── runtime/             # 运行时
└── tests/               # 测试

新版 src-new/astrbot_sdk/
├── __init__.py          # 包入口，导出公共 API
├── __main__.py          # 入口
├── cli.py               # CLI 命令（提升到第一层）
├── context.py           # Context（提升到第一层）
├── decorators.py        # 装饰器（提升到第一层）
├── events.py            # 事件类（提升到第一层）
├── star.py              # Star 基类（提升到第一层）
├── errors.py            # 错误类（新增）
├── compat.py            # 兼容层（新增）
├── _legacy_api.py       # 旧版 API 兼容（新增）
├── api/                 # API 子模块
├── clients/             # 客户端模块（新增）
├── protocol/            # 协议模块（新增）
└── runtime/             # 运行时
```

---

## 文件级对比

### __init__.py

**旧版**: 无 `__init__.py` 文件

**新版**:
```python
from .context import Context
from .decorators import on_command, on_event, on_message, on_schedule, require_admin
from .errors import AstrBotError
from .events import MessageEvent
from .star import Star
```

| 方面 | 评价 |
|------|------|
| **优点** | 清晰的公共 API 入口，便于用户导入核心类型 |
| **缺点** | 缺少版本号导出，缺少 `__version__` 变量 |
| **改进建议** | 添加 `__version__ = "4.0.0"` 便于版本检查 |

---

### cli.py

**旧版位置**: `src/astrbot_sdk/cli/main.py`

| 对比项 | 旧版 | 新版 |
|--------|------|------|
| 文件位置 | cli/ 文件夹 | 第一层单文件 |
| docstring | 有完整命令文档 | 缺少 docstring |
| 日志输出 | 有启动日志 | 无日志输出 |
| help 参数 | 完整 | 部分缺失 |

**优点**:
- 简化为单文件，更易维护
- 使用 `Path` 类型替代 `str`，类型更明确

**缺点**:
- 缺少命令文档字符串，用户难以通过 `--help` 了解用法
- 缺少启动日志，调试困难

**改进建议**:
```python
@cli.command()
@click.option(...)
def run(plugins_dir: Path) -> None:
    """Start the plugin supervisor over stdio."""
    logger.info(f"Starting plugin supervisor with plugins dir: {plugins_dir}")
    asyncio.run(run_supervisor(plugins_dir=plugins_dir))
```

---

### context.py

**旧版位置**: `src/astrbot_sdk/api/star/context.py`

| 对比项 | 旧版 | 新版 |
|--------|------|------|
| 类型 | 抽象基类 (ABC) | 具体类 |
| 属性 | conversation_manager, persona_manager | llm, memory, db, platform 客户端 |
| 通信方式 | 直接调用 | CapabilityProxy 代理 |
| 取消控制 | 无 | CancelToken |

**优点**:
- 分布式架构，插件与核心解耦
- 客户端模式清晰，职责单一
- CancelToken 提供统一的取消机制

**缺点**:
- 顶层 `Context` 不再直接暴露 `conversation_manager`
- 缺少 `persona_manager` 属性
- 方法签名变化较大，迁移成本高

**兼容现状**:
- 旧式 `conversation_manager`、`_register_component()`、`call_context_function()` 由 `_legacy_api.py` 中的 `LegacyContext` 承接
- legacy 组件在同一插件内会共享一个 `LegacyContext`，保持旧版 `StarManager` 的上下文语义

**改进建议**:
1. 在 clients/ 中添加 `PersonaClient` 补全功能
2. 在文档中明确迁移路径：`ctx.llm_generate()` → `ctx.llm.chat_raw()`
3. 考虑添加便捷方法减少迁移成本

---

### decorators.py

**旧版位置**: `src/astrbot_sdk/api/event/filter.py`

| 对比项 | 旧版 | 新版 |
|--------|------|------|
| 装饰器数量 | 15+ | 顶层最小集 + `api.event.filter` compat 子集 |
| 类型定义 | 完整 | 核心最小化，compat 层补回高频入口 |
| 钩子装饰器 | 有 | 顶层无，compat 中部分保留名称但显式未实现 |

**当前 compat 已可运行的装饰器**:
- `command`
- `regex`
- `permission`
- `permission_type`

**当前仍未完整支持，调用会显式抛出 `NotImplementedError` 的装饰器/辅助项**:
- `custom_filter`: 自定义过滤器
- `event_message_type`: 消息类型过滤
- `platform_adapter_type`: 平台类型过滤
- `after_message_sent`: 消息发送后钩子
- `on_astrbot_loaded`: AstrBot 加载完成钩子
- `on_platform_loaded`: 平台加载完成钩子
- `on_decorating_result`: 结果装饰钩子
- `on_llm_request`: LLM 请求钩子
- `on_llm_response`: LLM 响应钩子
- `command_group`: 命令组
- `llm_tool`: LLM 工具注册

**优点**:
- 简化设计，降低学习曲线
- `on_schedule` 为新增功能

**缺点**:
- 高级钩子与扩展过滤器仍不完整，复杂插件不能完全无改动迁移
- compat 面分散在顶层 `decorators.py` 与 `api.event.filter`，需要文档明确边界

**改进建议**:
1. 按优先级逐步补全高频未实现装饰器
2. 添加 `CustomFilter` 基类支持自定义过滤逻辑
3. 优先实现 `llm_tool` 与 LLM 相关钩子

---

### events.py

**旧版位置**: `src/astrbot_sdk/api/event/astr_message_event.py`

| 对比项 | 旧版 | 新版 |
|--------|------|------|
| 事件类 | AstrMessageEvent (370+ 行) | MessageEvent (~130 行) |
| 属性 | message_obj, platform_meta, role, session 等 | text, user_id, group_id, platform, session_id |
| 方法 | 30+ 方法 | reply(), plain_result() |

**顶层 `events.py` 仍缺失的功能**:
- `get_platform_name()`, `get_platform_id()`: 平台信息
- `get_messages()`: 获取消息链
- `is_private_chat()`, `is_admin()`: 状态判断
- `set_result()`, `stop_event()`: 事件控制
- `send()`, `react()`: 消息操作

**已由 compat 子模块补回的旧类型**:
- `api.event.AstrMessageEvent`
- `api.event.AstrBotMessage`
- `api.event.MessageEventResult`
- `api.event.MessageSession`
- `api.event.MessageType`
- `api.platform.PlatformMetadata`

**优点**:
- 简化设计，专注核心功能
- 通过 `reply_handler` 实现依赖注入
- 支持序列化 (`to_payload`, `from_payload`)
- `api.event` compat 层已补回常见旧类型和 `AstrMessageEvent` 包装

**缺点**:
- 顶层 `MessageEvent` 依然是精简模型，rich event 行为主要靠 compat 层兜底
- 缺少完整消息链操作能力

**改进建议**:
1. 在 `api/` 子模块中添加扩展事件类
2. 添加 `AstrBotMessage` 类型支持富文本消息
3. 补充 `MessageType` 枚举用于消息类型判断

---

### star.py

**旧版位置**: `src/astrbot_sdk/api/star/star.py`

| 对比项 | 旧版 | 新版 |
|--------|------|------|
| 主要类型 | StarMetadata (dataclass) | Star (基类) |
| 元数据管理 | dataclass 字段 | 装饰器自动收集 |
| 生命周期 | 无 | on_start, on_stop, on_error |

**旧版曾依赖的元数据类型**:
```python
@dataclass
class StarMetadata:
    name: str
    author: str
    desc: str
    version: str
    repo: str
    module_path: str
    root_dir_name: str
    reserved: bool
    activated: bool
    config: dict
    star_handler_full_names: list[str]
    display_name: str
    logo_path: str
```

**优点**:
- Star 基类设计清晰，生命周期钩子完整
- `__init_subclass__` 自动收集处理器，减少样板代码
- `on_error` 提供默认错误处理
- `api.star` compat 层已补回 `StarMetadata`

**缺点**:
- 顶层 `star.py` 不直接承载旧版元数据类型，需要通过 `api.star` compat 导入
- 类型注解不够精确 (`ctx: Any | None`)

**改进建议**:
1. 添加 `StarMetadata` dataclass 或使用装饰器参数
2. 改进类型注解，使用 `Context` 替代 `Any`
3. 考虑添加 `__star_metadata__` 类属性存储元信息

---

### errors.py

**旧版**: 无独立 errors.py 文件

**新版**:
```python
@dataclass(slots=True)
class AstrBotError(Exception):
    code: str
    message: str
    hint: str = ""
    retryable: bool = False
```

**优点**:
- 统一的错误表示，便于跨进程传递
- 工厂方法设计优雅 (`cancelled()`, `capability_not_found()`)
- 支持 `to_payload()` / `from_payload()` 序列化

**缺点**:
- 缺少错误码常量或枚举
- 与旧版异常类可能不兼容

**改进建议**:
```python
class ErrorCode:
    CANCELLED = "cancelled"
    CAPABILITY_NOT_FOUND = "capability_not_found"
    INVALID_INPUT = "invalid_input"
    # ...
```

---

### compat.py

**旧版**: 无

**新版**: 兼容层入口之一

```python
from ._legacy_api import (
    CommandComponent,
    Context,
    LegacyContext,
    LegacyConversationManager,
)
```

**优点**:
- 提供平滑迁移路径
- 隔离新旧 API，避免污染主命名空间
- 用户可按需导入旧版类型
- 可与 `astrbot_sdk.api.*` 薄兼容导出配合使用

**缺点**:
- 仅重新导出，无额外文档
- 兼容入口分布在 `compat.py` 与 `api/`，用户可能不清楚何时使用哪一个

**改进建议**:
添加迁移说明文档链接

---

### _legacy_api.py

**旧版**: 功能分散在 `api/star/` 目录

**新版**: 集中的旧版 API 兼容实现

**包含类型**:
- `LegacyContext`: 旧版 Context 兼容实现
- `LegacyConversationManager`: 旧版会话管理器
- `CommandComponent`: 旧版命令组件基类

**优点**:
- 完整的旧版方法签名兼容
- 渐进式警告，引导用户迁移
- 会话数据使用 db 客户端存储
- `LegacyContext` 已补回 `_register_component()` / `call_context_function()` 链路
- `LegacyConversationManager` 会按旧名称 `ConversationManager.*` 自动注册
- loader 会为同一 legacy 插件复用一个 `LegacyContext`

**缺点**:
- 部分方法抛出 `NotImplementedError`:
  - `get_filtered_conversations()`
  - `get_human_readable_context()`
  - `add_llm_tools()`
- 缺少旧版依赖类型的兼容导入

**改进建议**:
1. 补全 `NotImplementedError` 方法的实现或提供替代方案
2. 添加 `ToolSet`, `FunctionTool`, `Message` 类型的兼容导入
3. 更新 `MIGRATION_DOC_URL` 为实际文档地址

---

## 优点总结

### 架构设计

| 优点 | 说明 |
|------|------|
| **分布式架构** | 插件独立进程，崩溃不影响核心，提高稳定性 |
| **清晰的职责划分** | Context → Clients，每个客户端专注单一能力 |
| **统一的取消机制** | CancelToken 提供优雅的中断处理 |
| **跨进程错误传递** | AstrBotError 支持序列化，错误信息完整 |
| **简化的导入路径** | 核心类型提升到第一层，`from astrbot_sdk import Context` |

### 兼容性

| 优点 | 说明 |
|------|------|
| **平滑迁移** | `compat.py`、`_legacy_api.py` 与 `api/` 薄兼容导出共同提供旧版入口 |
| **渐进式警告** | `_warn_once()` 避免重复警告刷屏 |
| **文档引导** | 错误消息包含迁移文档链接 |

---

## 缺点与待改进项

### 功能缺失

| 类别 | 缺失项 | 影响 |
|------|--------|------|
| **装饰器** | 多个高级装饰器/钩子未实现 | 复杂插件无法完全无改动迁移 |
| **事件** | 顶层 rich event 行为仍大幅精简 | 消息处理能力受限 |
| **类型** | 部分旧类型只存在于 compat 子模块 | 需要调整导入路径认知 |
| **钩子** | on_llm_request, after_message_sent 等 | 无法拦截关键流程 |

### 文档缺失

| 类别 | 缺失项 |
|------|--------|
| **CLI** | 命令 docstring 缺失 |
| **迁移** | MIGRATION_DOC_URL 未更新 |
| **类型** | 部分类型注解为 `Any` |

### 实现不完整

| 类别 | 问题 |
|------|------|
| **_legacy_api.py** | 3 个方法抛出 NotImplementedError |
| **clients/** | 缺少 PersonaClient |
| **compat 文档** | `compat.py` 与 `api/` 的边界说明仍不足 |

---

## 改进建议

### 短期（优先级高）

1. **补全 CLI 文档字符串**
   - 为所有命令添加 docstring
   - 补充 help 参数
   - 添加启动日志

2. **更新 MIGRATION_DOC_URL**
   - 指向实际迁移文档

3. **补全 NotImplementedError 方法**
   - 为 `get_filtered_conversations()` 提供替代实现
   - 或在文档中明确说明替代方案
   - 保持 `call_context_function()` 的 `{data: ...}` 旧语义不变

### 中期

4. **添加 StarMetadata 支持**
   ```python
   @dataclass
   class StarMetadata:
       name: str = ""
       author: str = ""
       version: str = "1.0.0"
       # ...
   ```

5. **补全关键装饰器与钩子**
   - `llm_tool`: LLM 工具注册
   - `custom_filter`: 自定义过滤
   - `on_llm_request` / `on_llm_response`: LLM 钩子

6. **添加缺失类型**
   - 优先考虑顶层直出或统一导入文档，而不是重复实现 compat 类型

### 长期

7. **扩展 MessageEvent**
   - 添加消息链操作方法
   - 支持平台特定功能

8. **添加 PersonaClient**
   - 在 clients/ 中实现 Persona 管理

9. **完善类型系统**
   - 减少使用 `Any`
   - 添加 Protocol 定义

---

## 迁移示例

### 基础插件迁移

**旧版**:
```python
from astrbot_sdk.api.star import Context, Star, command

class MyPlugin(Star):
    @command("hello")
    async def hello(self, ctx: Context, event):
        await ctx.send_message(event.session, "Hello!")
```

**新版**:
```python
from astrbot_sdk import Star, Context, on_command

class MyPlugin(Star):
    @on_command("hello")
    async def hello(self, ctx: Context, event):
        await ctx.platform.send(event.session_id, "Hello!")
```

### 兼容模式

**旧版代码保持不变**:
```python
from astrbot_sdk.compat import Context, CommandComponent

class MyPlugin(CommandComponent):
    # 使用旧版 API，会有警告提示
    pass
```

---

## 总结

新版 SDK 在架构设计上有明显改进，分布式架构提高了系统稳定性，清晰的责任划分便于维护和扩展。兼容层的引入为旧版插件提供了平滑的迁移路径。

主要不足在于高级装饰器/钩子覆盖仍不完整，顶层事件模型仍偏精简，而兼容入口又分散在 `compat.py`、`_legacy_api.py` 与 `api/` 薄导出之间。建议继续按优先级补全高频能力，并把兼容边界写清楚，避免把“已迁移”误判成“缺失”。

| 维度 | 评分 | 说明 |
|------|------|------|
| **架构设计** | ⭐⭐⭐⭐⭐ | 分布式架构，解耦清晰 |
| **功能完整** | ⭐⭐⭐ | 核心功能完整，高级功能待补全 |
| **兼容性** | ⭐⭐⭐⭐ | 兼容层设计良好，部分方法待实现 |
| **文档** | ⭐⭐ | 代码注释完整，用户文档待补充 |
| **类型系统** | ⭐⭐⭐ | 基础类型完整，部分使用 Any |
