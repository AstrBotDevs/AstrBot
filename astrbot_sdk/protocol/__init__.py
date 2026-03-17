"""AstrBot v4 协议公共入口。

这里暴露 v4 原生协议的消息模型、描述符和解析函数。

握手阶段由 `InitializeMessage` 发起，返回值不是另一条 initialize 消息，而是
`ResultMessage(kind="initialize_result")`，其 `output` 负载可解析为
`InitializeOutput`。

## 插件作者指南：什么时候用什么？

### CapabilityDescriptor vs BUILTIN_CAPABILITY_SCHEMAS

**CapabilityDescriptor** 用于**声明**能力：
- 当你的插件想**暴露**一个可被其他插件或核心调用的能力时
- 例如：你的插件提供了一个翻译功能，想让其他插件调用

    ```python
    from astrbot_sdk.protocol import CapabilityDescriptor

    descriptor = CapabilityDescriptor(
        name="my_plugin.translate",  # 格式: 插件名.能力名
        description="翻译文本到指定语言",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要翻译的文本"},
                "target_lang": {"type": "string", "description": "目标语言"},
            },
            "required": ["text", "target_lang"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "translated": {"type": "string"},
            },
        },
    )
    ```

**BUILTIN_CAPABILITY_SCHEMAS** 用于**查询**内置能力的参数格式：
- 当你想**调用**核心提供的内置能力时，用它了解参数结构
- 例如：你想调用 `llm.chat`，但不确定参数格式

    ```python
    from astrbot_sdk.protocol import BUILTIN_CAPABILITY_SCHEMAS

    # 查看 llm.chat 的输入参数格式
    schema = BUILTIN_CAPABILITY_SCHEMAS["llm.chat"]
    print(schema["input"])  # 输入参数的 JSON Schema
    print(schema["output"])  # 输出结果的 JSON Schema
    ```

### 命名规范

能力名称必须遵循 `{namespace}.{action}` 或 `{namespace}.{sub_namespace}.{action}` 格式：
- `llm.chat` - LLM 对话
- `db.set` - 数据库写入
- `llm_tool.manager.activate` - LLM 工具管理

**保留命名空间**（插件不可使用）：
- `handler.` - 处理器相关
- `system.` - 系统内部能力
- `internal.` - 内部实现细节

### 常用内置能力速查

| 能力名 | 用途 |
|-------|------|
| `llm.chat` | 同步 LLM 对话 |
| `llm.stream_chat` | 流式 LLM 对话 |
| `memory.save` / `memory.get` | 短期记忆存储 |
| `db.set` / `db.get` | 持久化键值存储 |
| `platform.send` | 发送消息 |
| `provider.get_using` | 获取当前 Provider |
"""

from __future__ import annotations

from typing import Any

from . import _builtin_schemas as builtin_schemas
from .descriptors import (  # noqa: F401
    BUILTIN_CAPABILITY_SCHEMAS,
    CapabilityDescriptor,
    CommandRouteSpec,
    CommandTrigger,
    CompositeFilterSpec,
    EventTrigger,
    FilterSpec,
    HandlerDescriptor,
    LocalFilterRefSpec,
    MessageTrigger,
    MessageTypeFilterSpec,
    ParamSpec,
    Permissions,
    PlatformFilterSpec,
    ScheduleTrigger,
    SessionRef,
    Trigger,
)
from .messages import (  # noqa: F401
    CancelMessage,
    ErrorPayload,
    EventMessage,
    InitializeMessage,
    InitializeOutput,
    InvokeMessage,
    PeerInfo,
    ProtocolMessage,
    ResultMessage,
    parse_message,
)

_DIRECT_EXPORTS = [
    "BUILTIN_CAPABILITY_SCHEMAS",
    "CapabilityDescriptor",
    "CommandRouteSpec",
    "CommandTrigger",
    "CancelMessage",
    "builtin_schemas",
    "CompositeFilterSpec",
    "ErrorPayload",
    "EventTrigger",
    "EventMessage",
    "FilterSpec",
    "HandlerDescriptor",
    "InitializeMessage",
    "InitializeOutput",
    "InvokeMessage",
    "LocalFilterRefSpec",
    "MessageTrigger",
    "MessageTypeFilterSpec",
    "ParamSpec",
    "PeerInfo",
    "PlatformFilterSpec",
    "Permissions",
    "ProtocolMessage",
    "ResultMessage",
    "ScheduleTrigger",
    "SessionRef",
    "Trigger",
    "parse_message",
]

_BUILTIN_SCHEMA_EXPORTS = tuple(
    name for name in builtin_schemas.__all__ if name != "BUILTIN_CAPABILITY_SCHEMAS"
)


def __getattr__(name: str) -> Any:
    if name in _BUILTIN_SCHEMA_EXPORTS:
        return getattr(builtin_schemas, name)
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_BUILTIN_SCHEMA_EXPORTS))


__all__ = list(dict.fromkeys([*_DIRECT_EXPORTS, *_BUILTIN_SCHEMA_EXPORTS]))
