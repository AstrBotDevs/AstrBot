"""v4 协议描述符模型。

`protocol` 是 v4 新引入的协议层抽象，不对应旧树(圣诞树)中的一个同名目录。这里
定义的是跨进程握手和调度时使用的声明式元数据，而不是运行时的具体处理器/
能力实现。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from . import _builtin_schemas
from ._builtin_schemas import *  # noqa: F403

JSONSchema = _builtin_schemas.JSONSchema
RESERVED_CAPABILITY_NAMESPACES = ("handler", "system", "internal")
RESERVED_CAPABILITY_PREFIXES = tuple(
    f"{namespace}." for namespace in RESERVED_CAPABILITY_NAMESPACES
)
BUILTIN_CAPABILITY_SCHEMAS = _builtin_schemas.BUILTIN_CAPABILITY_SCHEMAS
_BUILTIN_SCHEMA_EXPORTS = frozenset(_builtin_schemas.__all__)


def __getattr__(name: str) -> Any:
    if name in _BUILTIN_SCHEMA_EXPORTS:
        return getattr(_builtin_schemas, name)
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | _BUILTIN_SCHEMA_EXPORTS)


class _DescriptorBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Permissions(_DescriptorBase):
    """权限配置，控制处理器的访问权限。

    Attributes:
        require_admin: 是否需要管理员权限
        level: 权限等级，数值越高权限越大
    """

    require_admin: bool = False
    level: int = 0


class SessionRef(_DescriptorBase):
    """结构化会话目标。

    v4 运行时内部仍然保留 legacy `session` 字符串作为最低兼容层，
    但对外模型允许同时携带平台与原始寻址信息，避免平台发送接口长期
    只依赖一个不透明字符串。
    """

    conversation_id: str = Field(
        validation_alias=AliasChoices("conversation_id", "session"),
    )
    platform: str | None = None
    raw: dict[str, Any] | None = None

    @property
    def session(self) -> str:
        return self.conversation_id

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class CommandTrigger(_DescriptorBase):
    """命令触发器，响应特定命令。

    Attributes:
        type: 触发器类型，固定为 "command"
        command: 命令名称（不含前缀，如 "help"）
        aliases: 命令别名列表
        description: 命令描述，用于帮助文档
        platforms: 允许的平台列表，为空表示所有平台
        message_types: 限定的消息类型列表，为空表示不限
    """

    type: Literal["command"] = "command"
    command: str
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    platforms: list[str] = Field(default_factory=list)
    message_types: list[str] = Field(default_factory=list)


class MessageTrigger(_DescriptorBase):
    """消息触发器，描述消息类处理器的订阅条件。

    Attributes:
        type: 触发器类型，固定为 "message"
        regex: 正则表达式模式，匹配消息文本
        keywords: 关键词列表，消息包含任一关键词即触发
        platforms: 目标平台列表，为空表示所有平台
        message_types: 限定的消息类型列表，为空表示不限

    Note:
        `regex` 和 `keywords` 可以同时为空，此时表示 "任意消息均可触发"，
        仅由平台过滤或上层运行时进一步筛选。
    """

    type: Literal["message"] = "message"
    regex: str | None = None
    keywords: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    message_types: list[str] = Field(default_factory=list)


class EventTrigger(_DescriptorBase):
    """事件触发器，响应特定类型的事件。

    Attributes:
        type: 触发器类型，固定为 "event"
        event_type: 事件类型，字符串形式（如 "message"、"notice"）
    """

    type: Literal["event"] = "event"
    event_type: str


class ScheduleTrigger(_DescriptorBase):
    """定时触发器，按 cron 表达式或固定间隔执行。

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
    def validate_schedule(self) -> ScheduleTrigger:
        has_cron = self.cron is not None
        has_interval = self.interval_seconds is not None
        if has_cron == has_interval:
            raise ValueError("cron 和 interval_seconds 必须且只能有一个非 null")
        return self


class PlatformFilterSpec(_DescriptorBase):
    kind: Literal["platform"] = "platform"
    platforms: list[str] = Field(default_factory=list)


class MessageTypeFilterSpec(_DescriptorBase):
    kind: Literal["message_type"] = "message_type"
    message_types: list[str] = Field(default_factory=list)


class LocalFilterRefSpec(_DescriptorBase):
    kind: Literal["local"] = "local"
    filter_id: str
    args: dict[str, Any] = Field(default_factory=dict)


class CompositeFilterSpec(_DescriptorBase):
    kind: Literal["and", "or"]
    children: list[FilterSpec] = Field(default_factory=list)


FilterSpec = Annotated[
    PlatformFilterSpec
    | MessageTypeFilterSpec
    | LocalFilterRefSpec
    | CompositeFilterSpec,
    Field(discriminator="kind"),
]


class ParamSpec(_DescriptorBase):
    name: str
    type: Literal["str", "int", "float", "bool", "optional", "greedy_str"]
    required: bool = True
    inner_type: Literal["str", "int", "float", "bool"] | None = None


class CommandRouteSpec(_DescriptorBase):
    group_path: list[str] = Field(default_factory=list)
    display_command: str
    group_help: str | None = None


CompositeFilterSpec.model_rebuild()


Trigger = Annotated[
    CommandTrigger | MessageTrigger | EventTrigger | ScheduleTrigger,
    Field(discriminator="type"),
]
"""触发器联合类型，使用 type 字段作为判别器自动解析具体类型。"""


class HandlerDescriptor(_DescriptorBase):
    """处理器描述符，描述一个事件处理函数的元信息。

    Attributes:
        id: 处理器唯一标识，通常是 "模块.函数名" 格式
        trigger: 触发器配置，决定何时执行该处理器
        kind: 处理器类别，默认普通 handler
        contract: 运行时契约名，描述入参/执行语义
        priority: 优先级，数值越大越先执行
        permissions: 权限配置，控制谁可以触发该处理器

    使用场景：
        HandlerDescriptor 通常由 `@on_command`、`@on_message` 等装饰器自动创建，
        插件作者一般不需要手动实例化。但了解其结构有助于理解插件注册机制。

    触发器类型：
        - CommandTrigger: 响应特定命令，如 `/help`
        - MessageTrigger: 响应消息（正则/关键词匹配）
        - EventTrigger: 响应特定事件类型
        - ScheduleTrigger: 定时触发

    示例：
        插件作者通常通过装饰器声明处理器，框架会自动生成 HandlerDescriptor：

        ```python
        from astrbot_sdk.decorators import on_command, on_message

        # 命令处理器
        @on_command("hello")
        async def hello_handler(ctx: Context):
            await ctx.reply("Hello!")

        # 消息处理器（正则匹配）
        @on_message(regex=r"^test\\s+(.+)$")
        async def test_handler(ctx: Context):
            await ctx.reply(f"收到: {ctx.match.group(1)}")
        ```

    See Also:
        Trigger: 触发器联合类型
        Permissions: 权限配置
    """

    id: str
    trigger: Trigger
    kind: Literal["handler", "hook", "tool", "session"] = "handler"
    contract: str | None = None
    priority: int = 0
    permissions: Permissions = Field(default_factory=Permissions)
    filters: list[FilterSpec] = Field(default_factory=list)
    param_specs: list[ParamSpec] = Field(default_factory=list)
    command_route: CommandRouteSpec | None = None

    @model_validator(mode="after")
    def validate_contract_defaults(self) -> HandlerDescriptor:
        if self.contract is None:
            if isinstance(self.trigger, ScheduleTrigger):
                self.contract = "schedule"
            else:
                self.contract = "message_event"
        return self


class CapabilityDescriptor(_DescriptorBase):
    """能力描述符，描述一个可调用的远程能力。

    能力命名规范：
        - 使用 "namespace.action" 格式，如 "llm.chat"、"db.set"
        - 支持多级命名空间，如 "llm_tool.manager.activate"
        - 内置能力以 "internal." 开头，如 "internal.legacy.call_context_function"

    保留命名空间（插件不可使用）：
        - `handler.` - 处理器相关
        - `system.` - 系统内部能力
        - `internal.` - 内部实现细节

    Attributes:
        name: 能力名称，格式为 "namespace.action"
        description: 能力描述，用于文档和调试
        input_schema: 输入参数的 JSON Schema，用于验证
        output_schema: 输出结果的 JSON Schema，用于验证
        supports_stream: 是否支持流式响应
        cancelable: 是否支持取消

    使用场景：
        当你的插件需要**暴露**一个可被其他插件调用的能力时，使用此类声明。

    示例：
        ```python
        from astrbot_sdk.protocol import CapabilityDescriptor

        # 声明一个翻译能力
        translate_desc = CapabilityDescriptor(
            name="my_plugin.translate",
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

        # 声明一个流式数据能力
        stream_desc = CapabilityDescriptor(
            name="my_plugin.stream_data",
            description="流式返回数据",
            supports_stream=True,
            cancelable=True,
            input_schema={"type": "object", "properties": {"count": {"type": "integer"}}},
            output_schema={"type": "object", "properties": {"items": {"type": "array"}}},
        )
        ```

    注意：
        如果你要调用**内置能力**（如 `llm.chat`、`db.set`），不需要手动创建
        CapabilityDescriptor，而是直接通过 `Context.invoke()` 调用，或查阅
        `BUILTIN_CAPABILITY_SCHEMAS` 了解参数格式。

    See Also:
        BUILTIN_CAPABILITY_SCHEMAS: 内置能力的 schema 定义，用于查询参数格式
    """

    name: str
    description: str
    input_schema: JSONSchema | None = None
    output_schema: JSONSchema | None = None
    supports_stream: bool = False
    cancelable: bool = False

    @model_validator(mode="after")
    def validate_builtin_schema_governance(self) -> CapabilityDescriptor:
        builtin_schema = BUILTIN_CAPABILITY_SCHEMAS.get(self.name)
        if builtin_schema is None:
            return self
        if self.input_schema is None or self.output_schema is None:
            raise ValueError(
                f"内建 capability {self.name} 必须同时提供 input_schema 和 output_schema"
            )
        if (
            self.input_schema != builtin_schema["input"]
            or self.output_schema != builtin_schema["output"]
        ):
            raise ValueError(
                f"内建 capability {self.name} 的 schema 必须与协议注册表保持一致"
            )
        return self


__all__ = [
    "AGENT_REGISTRY_GET_INPUT_SCHEMA",
    "AGENT_REGISTRY_GET_OUTPUT_SCHEMA",
    "AGENT_REGISTRY_LIST_INPUT_SCHEMA",
    "AGENT_REGISTRY_LIST_OUTPUT_SCHEMA",
    "AGENT_SPEC_SCHEMA",
    "AGENT_TOOL_LOOP_RUN_INPUT_SCHEMA",
    "AGENT_TOOL_LOOP_RUN_OUTPUT_SCHEMA",
    "BUILTIN_CAPABILITY_SCHEMAS",
    "CapabilityDescriptor",
    "CommandRouteSpec",
    "CommandTrigger",
    "CompositeFilterSpec",
    "DB_DELETE_INPUT_SCHEMA",
    "DB_DELETE_OUTPUT_SCHEMA",
    "DB_GET_INPUT_SCHEMA",
    "DB_GET_MANY_INPUT_SCHEMA",
    "DB_GET_MANY_OUTPUT_SCHEMA",
    "DB_GET_OUTPUT_SCHEMA",
    "DB_LIST_INPUT_SCHEMA",
    "DB_LIST_OUTPUT_SCHEMA",
    "DB_SET_INPUT_SCHEMA",
    "DB_SET_MANY_INPUT_SCHEMA",
    "DB_SET_MANY_OUTPUT_SCHEMA",
    "DB_SET_OUTPUT_SCHEMA",
    "DB_WATCH_INPUT_SCHEMA",
    "DB_WATCH_OUTPUT_SCHEMA",
    "EventTrigger",
    "FilterSpec",
    "HTTP_LIST_APIS_INPUT_SCHEMA",
    "HTTP_LIST_APIS_OUTPUT_SCHEMA",
    "HTTP_REGISTER_API_INPUT_SCHEMA",
    "HTTP_REGISTER_API_OUTPUT_SCHEMA",
    "HTTP_UNREGISTER_API_INPUT_SCHEMA",
    "HTTP_UNREGISTER_API_OUTPUT_SCHEMA",
    "HandlerDescriptor",
    "JSONSchema",
    "LLM_CHAT_INPUT_SCHEMA",
    "LLM_CHAT_OUTPUT_SCHEMA",
    "LLM_CHAT_RAW_INPUT_SCHEMA",
    "LLM_CHAT_RAW_OUTPUT_SCHEMA",
    "LLM_STREAM_CHAT_INPUT_SCHEMA",
    "LLM_STREAM_CHAT_OUTPUT_SCHEMA",
    "LLM_TOOL_MANAGER_ACTIVATE_INPUT_SCHEMA",
    "LLM_TOOL_MANAGER_ACTIVATE_OUTPUT_SCHEMA",
    "LLM_TOOL_MANAGER_ADD_INPUT_SCHEMA",
    "LLM_TOOL_MANAGER_ADD_OUTPUT_SCHEMA",
    "LLM_TOOL_MANAGER_DEACTIVATE_INPUT_SCHEMA",
    "LLM_TOOL_MANAGER_DEACTIVATE_OUTPUT_SCHEMA",
    "LLM_TOOL_MANAGER_GET_INPUT_SCHEMA",
    "LLM_TOOL_MANAGER_GET_OUTPUT_SCHEMA",
    "LLM_TOOL_SPEC_SCHEMA",
    "LocalFilterRefSpec",
    "MEMORY_DELETE_INPUT_SCHEMA",
    "MEMORY_DELETE_MANY_INPUT_SCHEMA",
    "MEMORY_DELETE_MANY_OUTPUT_SCHEMA",
    "MEMORY_DELETE_OUTPUT_SCHEMA",
    "MEMORY_GET_INPUT_SCHEMA",
    "MEMORY_GET_MANY_INPUT_SCHEMA",
    "MEMORY_GET_MANY_OUTPUT_SCHEMA",
    "MEMORY_GET_OUTPUT_SCHEMA",
    "MEMORY_SAVE_INPUT_SCHEMA",
    "MEMORY_SAVE_OUTPUT_SCHEMA",
    "MEMORY_SAVE_WITH_TTL_INPUT_SCHEMA",
    "MEMORY_SAVE_WITH_TTL_OUTPUT_SCHEMA",
    "MEMORY_SEARCH_INPUT_SCHEMA",
    "MEMORY_SEARCH_OUTPUT_SCHEMA",
    "MEMORY_STATS_INPUT_SCHEMA",
    "MEMORY_STATS_OUTPUT_SCHEMA",
    "METADATA_GET_PLUGIN_CONFIG_INPUT_SCHEMA",
    "METADATA_GET_PLUGIN_CONFIG_OUTPUT_SCHEMA",
    "METADATA_GET_PLUGIN_INPUT_SCHEMA",
    "METADATA_GET_PLUGIN_OUTPUT_SCHEMA",
    "METADATA_LIST_PLUGINS_INPUT_SCHEMA",
    "METADATA_LIST_PLUGINS_OUTPUT_SCHEMA",
    "MessageTrigger",
    "MessageTypeFilterSpec",
    "PROVIDER_GET_CURRENT_CHAT_PROVIDER_ID_INPUT_SCHEMA",
    "PROVIDER_GET_CURRENT_CHAT_PROVIDER_ID_OUTPUT_SCHEMA",
    "PROVIDER_GET_USING_INPUT_SCHEMA",
    "PROVIDER_GET_USING_OUTPUT_SCHEMA",
    "PROVIDER_LIST_ALL_INPUT_SCHEMA",
    "PROVIDER_LIST_ALL_OUTPUT_SCHEMA",
    "PROVIDER_META_SCHEMA",
    "PLATFORM_GET_GROUP_INPUT_SCHEMA",
    "PLATFORM_GET_GROUP_OUTPUT_SCHEMA",
    "PLATFORM_GET_MEMBERS_INPUT_SCHEMA",
    "PLATFORM_GET_MEMBERS_OUTPUT_SCHEMA",
    "PLATFORM_INSTANCE_SCHEMA",
    "PLATFORM_LIST_INSTANCES_INPUT_SCHEMA",
    "PLATFORM_LIST_INSTANCES_OUTPUT_SCHEMA",
    "PLATFORM_SEND_BY_SESSION_INPUT_SCHEMA",
    "PLATFORM_SEND_BY_SESSION_OUTPUT_SCHEMA",
    "PLATFORM_SEND_CHAIN_INPUT_SCHEMA",
    "PLATFORM_SEND_CHAIN_OUTPUT_SCHEMA",
    "PLATFORM_SEND_IMAGE_INPUT_SCHEMA",
    "PLATFORM_SEND_IMAGE_OUTPUT_SCHEMA",
    "PLATFORM_SEND_INPUT_SCHEMA",
    "PLATFORM_SEND_OUTPUT_SCHEMA",
    "ParamSpec",
    "Permissions",
    "PlatformFilterSpec",
    "REGISTRY_COMMAND_REGISTER_INPUT_SCHEMA",
    "REGISTRY_COMMAND_REGISTER_OUTPUT_SCHEMA",
    "REGISTRY_GET_HANDLER_BY_FULL_NAME_INPUT_SCHEMA",
    "REGISTRY_GET_HANDLER_BY_FULL_NAME_OUTPUT_SCHEMA",
    "REGISTRY_GET_HANDLERS_BY_EVENT_TYPE_INPUT_SCHEMA",
    "REGISTRY_GET_HANDLERS_BY_EVENT_TYPE_OUTPUT_SCHEMA",
    "RESERVED_CAPABILITY_NAMESPACES",
    "RESERVED_CAPABILITY_PREFIXES",
    "SESSION_PLUGIN_FILTER_HANDLERS_INPUT_SCHEMA",
    "SESSION_PLUGIN_FILTER_HANDLERS_OUTPUT_SCHEMA",
    "SESSION_PLUGIN_IS_ENABLED_INPUT_SCHEMA",
    "SESSION_PLUGIN_IS_ENABLED_OUTPUT_SCHEMA",
    "SESSION_REF_SCHEMA",
    "SESSION_SERVICE_IS_LLM_ENABLED_INPUT_SCHEMA",
    "SESSION_SERVICE_IS_LLM_ENABLED_OUTPUT_SCHEMA",
    "SESSION_SERVICE_IS_TTS_ENABLED_INPUT_SCHEMA",
    "SESSION_SERVICE_IS_TTS_ENABLED_OUTPUT_SCHEMA",
    "SESSION_SERVICE_SET_LLM_STATUS_INPUT_SCHEMA",
    "SESSION_SERVICE_SET_LLM_STATUS_OUTPUT_SCHEMA",
    "SESSION_SERVICE_SET_TTS_STATUS_INPUT_SCHEMA",
    "SESSION_SERVICE_SET_TTS_STATUS_OUTPUT_SCHEMA",
    "ScheduleTrigger",
    "SessionRef",
    "SYSTEM_EVENT_HANDLER_WHITELIST_GET_INPUT_SCHEMA",
    "SYSTEM_EVENT_HANDLER_WHITELIST_GET_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_HANDLER_WHITELIST_SET_INPUT_SCHEMA",
    "SYSTEM_EVENT_HANDLER_WHITELIST_SET_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_LLM_GET_STATE_INPUT_SCHEMA",
    "SYSTEM_EVENT_LLM_GET_STATE_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_LLM_REQUEST_INPUT_SCHEMA",
    "SYSTEM_EVENT_LLM_REQUEST_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_REACT_INPUT_SCHEMA",
    "SYSTEM_EVENT_REACT_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_RESULT_CLEAR_INPUT_SCHEMA",
    "SYSTEM_EVENT_RESULT_CLEAR_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_RESULT_GET_INPUT_SCHEMA",
    "SYSTEM_EVENT_RESULT_GET_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_RESULT_SET_INPUT_SCHEMA",
    "SYSTEM_EVENT_RESULT_SET_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_CHUNK_INPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_CHUNK_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_CLOSE_INPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_CLOSE_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_INPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_TYPING_INPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_TYPING_OUTPUT_SCHEMA",
    "Trigger",
]
