from __future__ import annotations
import docstring_parser

from ..star_handler import star_handlers_registry, StarHandlerMetadata, EventType
from ..filter.command import CommandFilter
from ..filter.command_group import CommandGroupFilter
from ..filter.event_message_type import EventMessageTypeFilter, EventMessageType
from ..filter.platform_adapter_type import (
    PlatformAdapterTypeFilter,
    PlatformAdapterType,
)
from ..filter.permission import PermissionTypeFilter, PermissionType
from ..filter.custom_filter import CustomFilterAnd, CustomFilterOr
from ..filter.regex import RegexFilter
from typing import Awaitable
from astrbot.core.provider.func_tool_manager import SUPPORTED_TYPES
from astrbot.core.provider.register import llm_tools


def get_handler_full_name(awaitable: Awaitable) -> str:
    """获取 Handler 的全名"""
    return f"{awaitable.__module__}_{awaitable.__name__}"


def get_handler_or_create(
    handler: Awaitable, event_type: EventType, dont_add=False, **kwargs
) -> StarHandlerMetadata:
    """获取 Handler 或者创建一个新的 Handler"""
    handler_full_name = get_handler_full_name(handler)
    md = star_handlers_registry.get_handler_by_full_name(handler_full_name)
    if md:
        return md
    else:
        md = StarHandlerMetadata(
            event_type=event_type,
            handler_full_name=handler_full_name,
            handler_name=handler.__name__,
            handler_module_path=handler.__module__,
            handler=handler,
            event_filters=[],
        )

        # 插件handler的附加额外信息
        if handler.__doc__:
            md.desc = handler.__doc__.strip()
        if "desc" in kwargs:
            md.desc = kwargs["desc"]
            del kwargs["desc"]
        md.extras_configs = kwargs

        if not dont_add:
            star_handlers_registry.append(md)
        return md


def register_command(
    command_name: str = None, sub_command: str = None, alias: set = None, **kwargs
):
    """注册一个 Command."""
    new_command = None
    add_to_event_filters = False
    if isinstance(command_name, RegisteringCommandable):
        # 子指令
        parent_command_names = command_name.parent_group.get_complete_command_names()
        new_command = CommandFilter(
            sub_command, alias, None, parent_command_names=parent_command_names
        )
        command_name.parent_group.add_sub_command_filter(new_command)
    else:
        # 裸指令
        new_command = CommandFilter(command_name, alias, None)
        add_to_event_filters = True

    def decorator(awaitable):
        if not add_to_event_filters:
            kwargs["sub_command"] = (
                True  # 打一个标记，表示这是一个子指令，再 wakingstage 阶段这个 handler 将会直接被跳过（其父指令会接管）
            )
        handler_md = get_handler_or_create(
            awaitable, EventType.AdapterMessageEvent, **kwargs
        )
        new_command.init_handler_md(handler_md)
        handler_md.event_filters.append(new_command)
        return awaitable

    return decorator


def register_custom_filter(custom_type_filter, *args, **kwargs):
    """注册一个自定义的 CustomFilter

    Args:
        custom_type_filter: 在裸指令时为CustomFilter对象
                                        在指令组时为父指令的RegisteringCommandable对象，即self或者command_group的返回
        raise_error: 如果没有权限，是否抛出错误到消息平台，并且停止事件传播。默认为 True
    """
    add_to_event_filters = False
    raise_error = True

    # 判断是否是指令组，指令组则添加到指令组的CommandGroupFilter对象中在waking_check的时候一起判断
    if isinstance(custom_type_filter, RegisteringCommandable):
        # 子指令, 此时函数为RegisteringCommandable对象的方法，首位参数为RegisteringCommandable对象的self。
        parent_register_commandable = custom_type_filter
        custom_filter = args[0]
        if len(args) > 1:
            raise_error = args[1]
    else:
        # 裸指令
        add_to_event_filters = True
        custom_filter = custom_type_filter
        if args:
            raise_error = args[0]

    if not isinstance(custom_filter, (CustomFilterAnd, CustomFilterOr)):
        custom_filter = custom_filter(raise_error)

    def decorator(awaitable):
        # 裸指令，子指令与指令组的区分，指令组会因为标记跳过wake。
        if (
            not add_to_event_filters
            and isinstance(awaitable, RegisteringCommandable)
            or (add_to_event_filters and isinstance(awaitable, RegisteringCommandable))
        ):
            # 指令组 与 根指令组，添加到本层的grouphandle中一起判断
            awaitable.parent_group.add_custom_filter(custom_filter)
        else:
            handler_md = get_handler_or_create(
                awaitable, EventType.AdapterMessageEvent, **kwargs
            )

            if not add_to_event_filters and not isinstance(
                awaitable, RegisteringCommandable
            ):
                # 底层子指令
                handle_full_name = get_handler_full_name(awaitable)
                for (
                    sub_handle
                ) in parent_register_commandable.parent_group.sub_command_filters:
                    # 所有符合fullname一致的子指令handle添加自定义过滤器。
                    # 不确定是否会有多个子指令有一样的fullname，比如一个方法添加多个command装饰器？
                    sub_handle_md = sub_handle.get_handler_md()
                    if (
                        sub_handle_md
                        and sub_handle_md.handler_full_name == handle_full_name
                    ):
                        sub_handle.add_custom_filter(custom_filter)

            else:
                # 裸指令
                handler_md = get_handler_or_create(
                    awaitable, EventType.AdapterMessageEvent, **kwargs
                )
                handler_md.event_filters.append(custom_filter)

        return awaitable

    return decorator


def register_command_group(
    command_group_name: str = None, sub_command: str = None, alias: set = None, **kwargs
):
    """注册一个 CommandGroup"""
    new_group = None
    if isinstance(command_group_name, RegisteringCommandable):
        # 子指令组
        new_group = CommandGroupFilter(
            sub_command, alias, parent_group=command_group_name.parent_group
        )
        command_group_name.parent_group.add_sub_command_filter(new_group)
    else:
        # 根指令组
        new_group = CommandGroupFilter(command_group_name, alias)

    def decorator(obj):
        # 根指令组
        handler_md = get_handler_or_create(obj, EventType.AdapterMessageEvent, **kwargs)
        handler_md.event_filters.append(new_group)

        return RegisteringCommandable(new_group)

    return decorator


class RegisteringCommandable:
    """用于指令组级联注册"""

    group: CommandGroupFilter = register_command_group
    command: CommandFilter = register_command
    custom_filter = register_custom_filter

    def __init__(self, parent_group: CommandGroupFilter):
        self.parent_group = parent_group


def register_event_message_type(event_message_type: EventMessageType, **kwargs):
    """注册一个 EventMessageType"""

    def decorator(awaitable):
        handler_md = get_handler_or_create(
            awaitable, EventType.AdapterMessageEvent, **kwargs
        )
        handler_md.event_filters.append(EventMessageTypeFilter(event_message_type))
        return awaitable

    return decorator


def register_platform_adapter_type(
    platform_adapter_type: PlatformAdapterType, **kwargs
):
    """注册一个 PlatformAdapterType"""

    def decorator(awaitable):
        handler_md = get_handler_or_create(awaitable, EventType.AdapterMessageEvent)
        handler_md.event_filters.append(
            PlatformAdapterTypeFilter(platform_adapter_type)
        )
        return awaitable

    return decorator


def register_regex(regex: str, **kwargs):
    """注册一个 Regex"""

    def decorator(awaitable):
        handler_md = get_handler_or_create(
            awaitable, EventType.AdapterMessageEvent, **kwargs
        )
        handler_md.event_filters.append(RegexFilter(regex))
        return awaitable

    return decorator


def register_permission_type(permission_type: PermissionType, raise_error: bool = True):
    """注册一个 PermissionType

    Args:
        permission_type: PermissionType
        raise_error: 如果没有权限，是否抛出错误到消息平台，并且停止事件传播。默认为 True
    """

    def decorator(awaitable):
        handler_md = get_handler_or_create(awaitable, EventType.AdapterMessageEvent)
        handler_md.event_filters.append(
            PermissionTypeFilter(permission_type, raise_error)
        )
        return awaitable

    return decorator


def register_on_astrbot_loaded(**kwargs):
    """当 AstrBot 加载完成时"""

    def decorator(awaitable):
        _ = get_handler_or_create(awaitable, EventType.OnAstrBotLoadedEvent, **kwargs)
        return awaitable

    return decorator


def register_on_llm_request(**kwargs):
    """当有 LLM 请求时的事件

    Examples:
    ```py
    from astrbot.api.provider import ProviderRequest

    @on_llm_request()
    async def test(self, event: AstrMessageEvent, request: ProviderRequest) -> None:
        request.system_prompt += "你是一个猫娘..."
    ```

    请务必接收两个参数：event, request
    """

    def decorator(awaitable):
        _ = get_handler_or_create(awaitable, EventType.OnLLMRequestEvent, **kwargs)
        return awaitable

    return decorator


def register_on_llm_response(**kwargs):
    """当有 LLM 请求后的事件

    Examples:
    ```py
    from astrbot.api.provider import LLMResponse

    @on_llm_response()
    async def test(self, event: AstrMessageEvent, response: LLMResponse) -> None:
        ...
    ```

    请务必接收两个参数：event, request
    """

    def decorator(awaitable):
        _ = get_handler_or_create(awaitable, EventType.OnLLMResponseEvent, **kwargs)
        return awaitable

    return decorator


def register_llm_tool(name: str = None):
    """为函数调用（function-calling / tools-use）添加工具。

    请务必按照以下格式编写一个工具（包括函数注释，AstrBot 会尝试解析该函数注释）

    ```
    @llm_tool(name="get_weather") # 如果 name 不填，将使用函数名
    async def get_weather(event: AstrMessageEvent, location: str):
        \'\'\'获取天气信息。

        Args:
            location(string): 地点
        \'\'\'
        # 处理逻辑
    ```

    可接受的参数类型有：string, number, object, array, boolean。

    返回值：
        - 返回 str：结果会被加入下一次 LLM 请求的 prompt 中，用于让 LLM 总结工具返回的结果
        - 返回 None：结果不会被加入下一次 LLM 请求的 prompt 中。

    可以使用 yield 发送消息、终止事件。

    发送消息：请参考文档。

    终止事件：
    ```
    event.stop_event()
    yield
    ```
    """

    name_ = name

    def decorator(awaitable: Awaitable):
        llm_tool_name = name_ if name_ else awaitable.__name__
        docstring = docstring_parser.parse(awaitable.__doc__)
        args = []
        for arg in docstring.params:
            if arg.type_name not in SUPPORTED_TYPES:
                raise ValueError(
                    f"LLM 函数工具 {awaitable.__module__}_{llm_tool_name} 不支持的参数类型：{arg.type_name}"
                )
            args.append(
                {
                    "type": arg.type_name,
                    "name": arg.arg_name,
                    "description": arg.description,
                }
            )
        md = get_handler_or_create(awaitable, EventType.OnCallingFuncToolEvent)
        llm_tools.add_func(
            llm_tool_name, args, docstring.description.strip(), md.handler
        )
        return awaitable

    return decorator


def register_on_decorating_result(**kwargs):
    """在发送消息前的事件"""

    def decorator(awaitable):
        _ = get_handler_or_create(
            awaitable, EventType.OnDecoratingResultEvent, **kwargs
        )
        return awaitable

    return decorator


def register_after_message_sent(**kwargs):
    """在消息发送后的事件"""

    def decorator(awaitable):
        _ = get_handler_or_create(
            awaitable, EventType.OnAfterMessageSentEvent, **kwargs
        )
        return awaitable

    return decorator
