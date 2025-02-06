from __future__ import annotations
import docstring_parser

from ..star_handler import star_handlers_registry, StarHandlerMetadata, EventType
from ..filter.command import CommandFilter
from ..filter.command_group import CommandGroupFilter
from ..filter.event_message_type import EventMessageTypeFilter, EventMessageType
from ..filter.platform_adapter_type import PlatformAdapterTypeFilter, PlatformAdapterType
from ..filter.permission import PermissionTypeFilter, PermissionType
from ..filter.regex import RegexFilter
from typing import Awaitable
from astrbot.core.provider.func_tool_manager import SUPPORTED_TYPES
from astrbot.core.provider.register import llm_tools
from astrbot.core import logger

def get_handler_full_name(awaitable: Awaitable) -> str:
    '''获取 Handler 的全名'''
    return f"{awaitable.__module__}_{awaitable.__name__}"

def get_handler_or_create(
        handler: Awaitable, 
        event_type: EventType, 
        dont_add = False, 
        **kwargs
) -> StarHandlerMetadata:
    '''获取 Handler 或者创建一个新的 Handler'''
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
            event_filters=[]
        )
        
        # 插件handler的附加额外信息
        if handler.__doc__:
            md.desc = handler.__doc__.strip()
        if 'desc' in kwargs:
            md.desc = kwargs['desc']
            del kwargs['desc']
        md.extras_configs = kwargs
        
        if not dont_add:
            star_handlers_registry.append(md)
        return md

def register_command(command_name: str = None, *args, **kwargs):
    '''注册一个 Command.
    '''
    
    # print("command: ", command_name, args, kwargs)
    
    new_command = None
    add_to_event_filters = False
    if isinstance(command_name, RegisteringCommandable):
        # 子指令
        new_command = CommandFilter(args[0], None)
        command_name.parent_group.add_sub_command_filter(new_command)
    else:
        # 裸指令
        new_command = CommandFilter(command_name, None)
        add_to_event_filters = True
    
    def decorator(awaitable):
        handler_md = get_handler_or_create(awaitable, EventType.AdapterMessageEvent, **kwargs)
        new_command.init_handler_md(handler_md)
        if add_to_event_filters:
            # 裸指令
            handler_md.event_filters.append(new_command)
        
        return awaitable

    return decorator

def register_command_group(command_group_name: str = None, *args, **kwargs):
    '''注册一个 CommandGroup
    '''
    
    # print("commandgroup: ", command_group_name,args,  kwargs)
    
    new_group = None
    add_to_event_filters = False
    if isinstance(command_group_name, RegisteringCommandable):
        # 子指令组
        new_group = CommandGroupFilter(args[0])
        command_group_name.parent_group.add_sub_command_filter(new_group)
    else:
        # 根指令组
        new_group = CommandGroupFilter(command_group_name)
        add_to_event_filters = True
    
    def decorator(obj):
        if add_to_event_filters:
            # 根指令组
            handler_md = get_handler_or_create(obj, EventType.AdapterMessageEvent, **kwargs)
            handler_md.event_filters.append(new_group)
        
        return RegisteringCommandable(new_group)

    return decorator

class RegisteringCommandable():
    '''用于指令组级联注册'''
    group = register_command_group
    command = register_command
    
    def __init__(self, parent_group: CommandGroupFilter):
        self.parent_group = parent_group

def register_event_message_type(event_message_type: EventMessageType, **kwargs):
    '''注册一个 EventMessageType'''
    def decorator(awaitable):
        handler_md = get_handler_or_create(awaitable, EventType.AdapterMessageEvent, kwargs)
        handler_md.event_filters.append(EventMessageTypeFilter(event_message_type))
        return awaitable

    return decorator

def register_platform_adapter_type(platform_adapter_type: PlatformAdapterType, **kwargs):
    '''注册一个 PlatformAdapterType'''
    def decorator(awaitable):
        handler_md = get_handler_or_create(awaitable, EventType.AdapterMessageEvent)
        handler_md.event_filters.append(PlatformAdapterTypeFilter(platform_adapter_type))
        return awaitable

    return decorator

def register_regex(regex: str, **kwargs):
    '''注册一个 Regex'''
    def decorator(awaitable):
        handler_md = get_handler_or_create(awaitable, EventType.AdapterMessageEvent, **kwargs)
        handler_md.event_filters.append(RegexFilter(regex))
        return awaitable

    return decorator

def register_permission_type(permission_type: PermissionType, raise_error: bool = True):
    '''注册一个 PermissionType
    
    Args:
        permission_type: PermissionType
        raise_error: 如果没有权限，是否抛出错误到消息平台，并且停止事件传播。默认为 True
    '''
    def decorator(awaitable):
        handler_md = get_handler_or_create(awaitable, EventType.AdapterMessageEvent)
        handler_md.event_filters.append(PermissionTypeFilter(permission_type, raise_error))
        return awaitable

    return decorator

def register_on_llm_request(**kwargs):
    '''当有 LLM 请求时的事件
    
    Examples:
    ```py
    from astrbot.api.provider import ProviderRequest
    
    @on_llm_request()
    async def test(self, event: AstrMessageEvent, request: ProviderRequest) -> None:
        request.system_prompt += "你是一个猫娘..."
    ```
    
    请务必接收两个参数：event, request
    '''
    def decorator(awaitable):
        _ = get_handler_or_create(awaitable, EventType.OnLLMRequestEvent, **kwargs)
        return awaitable
    
    return decorator

def register_on_llm_response(**kwargs):
    '''当有 LLM 请求后的事件
    
    Examples:
    ```py
    from astrbot.api.provider import LLMResponse
    
    @on_llm_response()
    async def test(self, event: AstrMessageEvent, response: LLMResponse) -> None:
        ...
    ```
    
    请务必接收两个参数：event, request
    '''
    def decorator(awaitable):
        _ = get_handler_or_create(awaitable, EventType.OnLLMResponseEvent, **kwargs)
        return awaitable
    
    return decorator


def register_llm_tool(name: str = None):
    '''为函数调用（function-calling / tools-use）添加工具。
    
    请务必按照以下格式编写一个工具（包括函数注释，AstrBot 会尝试解析该函数注释）
    
    ```
    @llm_tool(name="get_weather") # 如果 name 不填，将使用函数名
    async def get_weather(event: AstrMessageEvent, location: str) -> MessageEventResult:
        \'\'\'获取天气信息。
        
        Args:
            location(string): 地点
        \'\'\'
        # 处理逻辑
    ```
    
    可接受的参数类型有：string, number, object, array, boolean。
    '''
    name_ = name
    
    def decorator(awaitable: Awaitable):
        llm_tool_name = name_ if name_ else awaitable.__name__
        docstring = docstring_parser.parse(awaitable.__doc__)
        args = []
        for arg in docstring.params:
            if arg.type_name not in SUPPORTED_TYPES:
                raise ValueError(f"LLM 函数工具 {awaitable.__module__}_{llm_tool_name} 不支持的参数类型：{arg.type_name}")
            args.append({
                "type": arg.type_name,
                "name": arg.arg_name,
                "description": arg.description
            })
        md = get_handler_or_create(awaitable, EventType.OnCallingFuncToolEvent)
        llm_tools.add_func(llm_tool_name, args, docstring.description, md.handler)
        
        logger.debug(f"LLM 函数工具 {llm_tool_name} 已注册")
        return awaitable
    
    return decorator

def register_on_decorating_result(**kwargs):
    '''在发送消息前的事件'''
    def decorator(awaitable):
        _ = get_handler_or_create(awaitable, EventType.OnDecoratingResultEvent, **kwargs)
        return awaitable
    
    return decorator

def register_after_message_sent(**kwargs):
    '''在消息发送后的事件'''
    def decorator(awaitable):
        _ = get_handler_or_create(awaitable, EventType.OnAfterMessageSentEvent, **kwargs)
        return awaitable
    
    return decorator