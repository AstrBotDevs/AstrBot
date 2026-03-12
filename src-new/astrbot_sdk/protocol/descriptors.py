"""v4 协议描述符模型。

`protocol` 是 v4 新引入的协议层抽象，不对应旧树中的一个同名目录。这里
定义的是跨进程握手和调度时使用的声明式元数据，而不是运行时的具体处理器/
能力实现。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

JSONSchema = dict[str, Any]
RESERVED_CAPABILITY_NAMESPACES = ("handler", "system", "internal")
RESERVED_CAPABILITY_PREFIXES = tuple(
    f"{namespace}." for namespace in RESERVED_CAPABILITY_NAMESPACES
)


def _object_schema(
    *,
    required: tuple[str, ...] = (),
    **properties: Any,
) -> JSONSchema:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
    }


def _nullable(schema: JSONSchema) -> JSONSchema:
    return {"anyOf": [schema, {"type": "null"}]}


_OPTIONAL_CHAT_PROPERTIES: dict[str, Any] = {
    "system": {"type": "string"},
    "history": {"type": "array", "items": {"type": "object"}},
    "model": {"type": "string"},
    "temperature": {"type": "number"},
    "image_urls": {"type": "array", "items": {"type": "string"}},
    "tools": {"type": "array"},
    "max_steps": {"type": "integer"},
}

LLM_CHAT_INPUT_SCHEMA = _object_schema(
    required=("prompt",),
    prompt={"type": "string"},
    **_OPTIONAL_CHAT_PROPERTIES,
)
LLM_CHAT_OUTPUT_SCHEMA = _object_schema(
    required=("text",),
    text={"type": "string"},
)
LLM_CHAT_RAW_INPUT_SCHEMA = _object_schema(
    required=("prompt",),
    prompt={"type": "string"},
    **_OPTIONAL_CHAT_PROPERTIES,
)
LLM_CHAT_RAW_OUTPUT_SCHEMA = _object_schema(
    required=("text",),
    text={"type": "string"},
    usage=_nullable({"type": "object"}),
    finish_reason=_nullable({"type": "string"}),
    tool_calls={"type": "array", "items": {"type": "object"}},
)
LLM_STREAM_CHAT_INPUT_SCHEMA = _object_schema(
    required=("prompt",),
    prompt={"type": "string"},
    **_OPTIONAL_CHAT_PROPERTIES,
)
LLM_STREAM_CHAT_OUTPUT_SCHEMA = _object_schema(
    required=("text",),
    text={"type": "string"},
)
MEMORY_SEARCH_INPUT_SCHEMA = _object_schema(
    required=("query",),
    query={"type": "string"},
)
MEMORY_SEARCH_OUTPUT_SCHEMA = _object_schema(
    required=("items",),
    items={"type": "array", "items": {"type": "object"}},
)
MEMORY_SAVE_INPUT_SCHEMA = _object_schema(
    required=("key", "value"),
    key={"type": "string"},
    value={"type": "object"},
)
MEMORY_SAVE_OUTPUT_SCHEMA = _object_schema()
MEMORY_GET_INPUT_SCHEMA = _object_schema(
    required=("key",),
    key={"type": "string"},
)
MEMORY_GET_OUTPUT_SCHEMA = _object_schema(
    required=("value",),
    value=_nullable({"type": "object"}),
)
MEMORY_DELETE_INPUT_SCHEMA = _object_schema(
    required=("key",),
    key={"type": "string"},
)
MEMORY_DELETE_OUTPUT_SCHEMA = _object_schema()
DB_GET_INPUT_SCHEMA = _object_schema(
    required=("key",),
    key={"type": "string"},
)
DB_GET_OUTPUT_SCHEMA = _object_schema(
    required=("value",),
    value=_nullable({"type": "object"}),
)
DB_SET_INPUT_SCHEMA = _object_schema(
    required=("key", "value"),
    key={"type": "string"},
    value={"type": "object"},
)
DB_SET_OUTPUT_SCHEMA = _object_schema()
DB_DELETE_INPUT_SCHEMA = _object_schema(
    required=("key",),
    key={"type": "string"},
)
DB_DELETE_OUTPUT_SCHEMA = _object_schema()
DB_LIST_INPUT_SCHEMA = _object_schema(
    prefix=_nullable({"type": "string"}),
)
DB_LIST_OUTPUT_SCHEMA = _object_schema(
    required=("keys",),
    keys={"type": "array", "items": {"type": "string"}},
)
PLATFORM_SEND_INPUT_SCHEMA = _object_schema(
    required=("session", "text"),
    session={"type": "string"},
    text={"type": "string"},
)
PLATFORM_SEND_OUTPUT_SCHEMA = _object_schema(
    required=("message_id",),
    message_id={"type": "string"},
)
PLATFORM_SEND_IMAGE_INPUT_SCHEMA = _object_schema(
    required=("session", "image_url"),
    session={"type": "string"},
    image_url={"type": "string"},
)
PLATFORM_SEND_IMAGE_OUTPUT_SCHEMA = _object_schema(
    required=("message_id",),
    message_id={"type": "string"},
)
PLATFORM_GET_MEMBERS_INPUT_SCHEMA = _object_schema(
    required=("session",),
    session={"type": "string"},
)
PLATFORM_GET_MEMBERS_OUTPUT_SCHEMA = _object_schema(
    required=("members",),
    members={"type": "array", "items": {"type": "object"}},
)

BUILTIN_CAPABILITY_SCHEMAS: dict[str, dict[str, JSONSchema]] = {
    "llm.chat": {
        "input": LLM_CHAT_INPUT_SCHEMA,
        "output": LLM_CHAT_OUTPUT_SCHEMA,
    },
    "llm.chat_raw": {
        "input": LLM_CHAT_RAW_INPUT_SCHEMA,
        "output": LLM_CHAT_RAW_OUTPUT_SCHEMA,
    },
    "llm.stream_chat": {
        "input": LLM_STREAM_CHAT_INPUT_SCHEMA,
        "output": LLM_STREAM_CHAT_OUTPUT_SCHEMA,
    },
    "memory.search": {
        "input": MEMORY_SEARCH_INPUT_SCHEMA,
        "output": MEMORY_SEARCH_OUTPUT_SCHEMA,
    },
    "memory.save": {
        "input": MEMORY_SAVE_INPUT_SCHEMA,
        "output": MEMORY_SAVE_OUTPUT_SCHEMA,
    },
    "memory.get": {
        "input": MEMORY_GET_INPUT_SCHEMA,
        "output": MEMORY_GET_OUTPUT_SCHEMA,
    },
    "memory.delete": {
        "input": MEMORY_DELETE_INPUT_SCHEMA,
        "output": MEMORY_DELETE_OUTPUT_SCHEMA,
    },
    "db.get": {
        "input": DB_GET_INPUT_SCHEMA,
        "output": DB_GET_OUTPUT_SCHEMA,
    },
    "db.set": {
        "input": DB_SET_INPUT_SCHEMA,
        "output": DB_SET_OUTPUT_SCHEMA,
    },
    "db.delete": {
        "input": DB_DELETE_INPUT_SCHEMA,
        "output": DB_DELETE_OUTPUT_SCHEMA,
    },
    "db.list": {
        "input": DB_LIST_INPUT_SCHEMA,
        "output": DB_LIST_OUTPUT_SCHEMA,
    },
    "platform.send": {
        "input": PLATFORM_SEND_INPUT_SCHEMA,
        "output": PLATFORM_SEND_OUTPUT_SCHEMA,
    },
    "platform.send_image": {
        "input": PLATFORM_SEND_IMAGE_INPUT_SCHEMA,
        "output": PLATFORM_SEND_IMAGE_OUTPUT_SCHEMA,
    },
    "platform.get_members": {
        "input": PLATFORM_GET_MEMBERS_INPUT_SCHEMA,
        "output": PLATFORM_GET_MEMBERS_OUTPUT_SCHEMA,
    },
}


class _DescriptorBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Permissions(_DescriptorBase):
    """权限配置，控制处理器的访问权限。

    与旧版对比：
        旧版: 通过 extras_configs 字典配置
            {"require_admin": true, "level": 1}
        新版: 使用 Permissions 模型，类型安全

    Attributes:
        require_admin: 是否需要管理员权限
        level: 权限等级，数值越高权限越大
    """

    require_admin: bool = False
    level: int = 0


class CommandTrigger(_DescriptorBase):
    """命令触发器，响应特定命令。

    与旧版对比：
        旧版: 使用 @command_handler("help") 装饰器注册
        新版: 使用 CommandTrigger 声明式定义，支持别名

    Attributes:
        type: 触发器类型，固定为 "command"
        command: 命令名称（不含前缀，如 "help"）
        aliases: 命令别名列表
        description: 命令描述，用于帮助文档
    """

    type: Literal["command"] = "command"
    command: str
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None


class MessageTrigger(_DescriptorBase):
    """消息触发器，描述消息类处理器的订阅条件。

    与旧版对比：
        旧版: 使用 @regex_handler(r"pattern") 或 @message_handler 装饰器
        新版: 使用 MessageTrigger 声明式定义，支持正则、关键词和平台过滤

    Attributes:
        type: 触发器类型，固定为 "message"
        regex: 正则表达式模式，匹配消息文本
        keywords: 关键词列表，消息包含任一关键词即触发
        platforms: 目标平台列表，为空表示所有平台

    Note:
        `regex` 和 `keywords` 可以同时为空，此时表示“任意消息均可触发”，
        仅由平台过滤或上层运行时进一步筛选。
    """

    type: Literal["message"] = "message"
    regex: str | None = None
    keywords: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)


class EventTrigger(_DescriptorBase):
    """事件触发器，响应特定类型的事件。

    与旧版对比：
        旧版: 使用整数 event_type，如 3 表示消息事件
        新版: 使用字符串 event_type，如 "message" 或 "3"，更灵活

    Attributes:
        type: 触发器类型，固定为 "event"
        event_type: 事件类型，字符串形式（如 "message"、"notice"）
    """

    type: Literal["event"] = "event"
    event_type: str


class ScheduleTrigger(_DescriptorBase):
    """定时触发器，按 cron 表达式或固定间隔执行。

    与旧版对比：
        旧版: 使用 @scheduled("0 * * * *") 装饰器
        新版: 使用 ScheduleTrigger 声明式定义

    Attributes:
        type: 触发器类型，固定为 "schedule"
        cron: cron 表达式（如 "0 9 * * *" 表示每天 9 点）
        interval_seconds: 执行间隔（秒）

    Note:
        cron 和 interval_seconds 必须且只能有一个非空。
    """

    type: Literal["schedule"] = "schedule"
    cron: str | None = Field(
        default=None,
        validation_alias=AliasChoices("cron", "schedule"),
    )
    interval_seconds: int | None = None

    @property
    def schedule(self) -> str | None:
        return self.cron

    @model_validator(mode="after")
    def validate_schedule(self) -> "ScheduleTrigger":
        has_cron = self.cron is not None
        has_interval = self.interval_seconds is not None
        if has_cron == has_interval:
            raise ValueError("cron 和 interval_seconds 必须且只能有一个非 null")
        return self


Trigger = Annotated[
    CommandTrigger | MessageTrigger | EventTrigger | ScheduleTrigger,
    Field(discriminator="type"),
]
"""触发器联合类型，使用 type 字段作为判别器自动解析具体类型。"""


class HandlerDescriptor(_DescriptorBase):
    """处理器描述符，描述一个事件处理函数的元信息。

    与旧版对比：
        旧版 handshake 响应中的处理器信息:
            {
                "event_type": 3,
                "handler_full_name": "plugin.handler",
                "handler_name": "handler",
                "handler_module_path": "plugin",
                "desc": "描述",
                "extras_configs": {"priority": 0, "require_admin": false}
            }

        新版 HandlerDescriptor:
            {
                "id": "plugin.handler",
                "trigger": {"type": "event", "event_type": "message"},
                "priority": 0,
                "permissions": {"require_admin": false, "level": 0}
            }

    Attributes:
        id: 处理器唯一标识，通常是 "模块.函数名" 格式
        trigger: 触发器配置，决定何时执行该处理器
        priority: 优先级，数值越大越先执行
        permissions: 权限配置，控制谁可以触发该处理器
    """

    id: str
    trigger: Trigger
    priority: int = 0
    permissions: Permissions = Field(default_factory=Permissions)


class CapabilityDescriptor(_DescriptorBase):
    """能力描述符，描述一个可调用的远程能力。

    与旧版对比：
        旧版: 无独立的能力描述，通过 method 名称隐式定义
        新版: 使用 CapabilityDescriptor 显式声明能力，支持 JSON Schema 验证

    能力命名规范：
        - 使用 "namespace.action" 格式，如 "llm.chat"、"db.set"
        - 内置能力以 "internal." 开头，如 "internal.legacy.call_context_function"

    Attributes:
        name: 能力名称，格式为 "namespace.action"
        description: 能力描述，用于文档和调试
        input_schema: 输入参数的 JSON Schema，用于验证
        output_schema: 输出结果的 JSON Schema，用于验证
        supports_stream: 是否支持流式响应
        cancelable: 是否支持取消
    """

    name: str
    description: str
    input_schema: JSONSchema | None = None
    output_schema: JSONSchema | None = None
    supports_stream: bool = False
    cancelable: bool = False

    @model_validator(mode="after")
    def validate_builtin_schema_governance(self) -> "CapabilityDescriptor":
        if self.name in BUILTIN_CAPABILITY_SCHEMAS and (
            self.input_schema is None or self.output_schema is None
        ):
            raise ValueError(
                f"内建 capability {self.name} 必须同时提供 input_schema 和 output_schema"
            )
        return self


__all__ = [
    "BUILTIN_CAPABILITY_SCHEMAS",
    "CapabilityDescriptor",
    "CommandTrigger",
    "DB_DELETE_INPUT_SCHEMA",
    "DB_DELETE_OUTPUT_SCHEMA",
    "DB_GET_INPUT_SCHEMA",
    "DB_GET_OUTPUT_SCHEMA",
    "DB_LIST_INPUT_SCHEMA",
    "DB_LIST_OUTPUT_SCHEMA",
    "DB_SET_INPUT_SCHEMA",
    "DB_SET_OUTPUT_SCHEMA",
    "EventTrigger",
    "HandlerDescriptor",
    "JSONSchema",
    "LLM_CHAT_INPUT_SCHEMA",
    "LLM_CHAT_OUTPUT_SCHEMA",
    "LLM_CHAT_RAW_INPUT_SCHEMA",
    "LLM_CHAT_RAW_OUTPUT_SCHEMA",
    "LLM_STREAM_CHAT_INPUT_SCHEMA",
    "LLM_STREAM_CHAT_OUTPUT_SCHEMA",
    "MEMORY_DELETE_INPUT_SCHEMA",
    "MEMORY_DELETE_OUTPUT_SCHEMA",
    "MEMORY_GET_INPUT_SCHEMA",
    "MEMORY_GET_OUTPUT_SCHEMA",
    "MEMORY_SAVE_INPUT_SCHEMA",
    "MEMORY_SAVE_OUTPUT_SCHEMA",
    "MEMORY_SEARCH_INPUT_SCHEMA",
    "MEMORY_SEARCH_OUTPUT_SCHEMA",
    "MessageTrigger",
    "PLATFORM_GET_MEMBERS_INPUT_SCHEMA",
    "PLATFORM_GET_MEMBERS_OUTPUT_SCHEMA",
    "PLATFORM_SEND_IMAGE_INPUT_SCHEMA",
    "PLATFORM_SEND_IMAGE_OUTPUT_SCHEMA",
    "PLATFORM_SEND_INPUT_SCHEMA",
    "PLATFORM_SEND_OUTPUT_SCHEMA",
    "Permissions",
    "RESERVED_CAPABILITY_NAMESPACES",
    "RESERVED_CAPABILITY_PREFIXES",
    "ScheduleTrigger",
    "Trigger",
]
