"""描述符模块。

定义处理器和能力的描述符，用于声明式注册和发现。

描述符类型概览：
    HandlerDescriptor: 处理器描述符，描述一个事件处理函数
    CapabilityDescriptor: 能力描述符，描述一个可调用的远程能力
    Permissions: 权限配置，控制处理器的访问权限
    Trigger: 触发器联合类型，支持多种触发方式

触发器类型：
    CommandTrigger: 命令触发器，响应特定命令（如 /help）
    MessageTrigger: 消息触发器，响应匹配正则或关键词的消息
    EventTrigger: 事件触发器，响应特定类型的事件
    ScheduleTrigger: 定时触发器，按 cron 或间隔时间执行

与旧版对比：
    旧版:
        - 处理器元信息分散在 handshake 响应中
        - 使用 event_type 整数区分事件类型
        - 缺少声明式的触发器定义
        - 配置通过 extras_configs 字典传递

    新版:
        - 使用 HandlerDescriptor 统一描述处理器
        - 使用字符串 event_type，更语义化
        - 支持多种触发器类型，声明式定义
        - 使用 Pydantic 模型，类型安全

TODO:
    - HandlerDescriptor 缺少 timeout 超时配置
    - HandlerDescriptor 缺少 retry 重试配置
    - CapabilityDescriptor 缺少 rate_limit 限流配置
    - ScheduleTrigger 缺错时错过执行的处理策略
    - 缺少 HandlerGroupDescriptor 处理器组描述符
    - 缺少 DependencyDescriptor 依赖声明
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


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
    """消息触发器，响应匹配正则或关键词的消息。

    与旧版对比：
        旧版: 使用 @regex_handler(r"pattern") 或 @message_handler 装饰器
        新版: 使用 MessageTrigger 声明式定义，支持正则、关键词和平台过滤

    Attributes:
        type: 触发器类型，固定为 "message"
        regex: 正则表达式模式，匹配消息文本
        keywords: 关键词列表，消息包含任一关键词即触发
        platforms: 目标平台列表，为空表示所有平台
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
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    supports_stream: bool = False
    cancelable: bool = False
