from __future__ import annotations

from ..star_handler import star_handlers_registry, star_handlers_map, StarHandlerMetadata
from ..filter.command import CommandFilter
from ..filter.command_group import CommandGroupFilter
from ..filter.event_message_type import EventMessageTypeFilter, EventMessageType
from ..filter.platform_adapter_type import PlatformAdapterTypeFilter, PlatformAdapterType
from ..filter.regex import RegexFilter
from typing import Awaitable, List, Dict


def get_handler_full_name(awatable: Awaitable) -> str:
    '''获取 Handler 的全名'''
    return f"{awatable.__module__}_{awatable.__name__}"

def get_handler_or_create(handler: Awaitable) -> StarHandlerMetadata:
    '''获取 Handler 或者创建一个新的 Handler'''
    handler_full_name = get_handler_full_name(handler)
    if handler_full_name in star_handlers_map:
        return star_handlers_map[handler_full_name]
    else:
        md = StarHandlerMetadata(
            handler_full_name=handler_full_name,
            handler_name=handler.__name__,
            handler_module_str=handler.__module__,
            handler=handler,
            event_filters=[]
        )
        star_handlers_registry.append(md)
        star_handlers_map[handler_full_name] = md
        return md

def register_command(command_name: str = None, *args):
    '''注册一个 Command'''
    
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
        handler_md = get_handler_or_create(awaitable)
        new_command.init_handler_md(handler_md)
        if add_to_event_filters:
            # 裸指令
            handler_md.event_filters.append(new_command)
        
        return awaitable

    return decorator

def register_command_group(command_group_name: str = None, *args):
    '''注册一个 CommandGroup'''
    
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
            handler_md = get_handler_or_create(obj)
            handler_md.event_filters.append(new_group)
        
        return RegisteringCommandable(new_group)

    return decorator

class RegisteringCommandable():
    '''用于指令组级联注册'''
    group = register_command_group
    command = register_command
    
    def __init__(self, parent_group: CommandGroupFilter):
        self.parent_group = parent_group

def register_event_message_type(event_message_type: EventMessageType):
    '''注册一个 EventMessageType'''
    def decorator(awatable):
        handler_md = get_handler_or_create(awatable)
        handler_md.event_filters.append(EventMessageTypeFilter(event_message_type))
        return awatable

    return decorator

def register_platform_adapter_type(platform_adapter_type: PlatformAdapterType):
    '''注册一个 PlatformAdapterType'''
    def decorator(awatable):
        handler_md = get_handler_or_create(awatable)
        handler_md.event_filters.append(PlatformAdapterTypeFilter(platform_adapter_type))
        return awatable

    return decorator

def register_regex(regex: str):
    '''注册一个 Regex'''
    def decorator(awatable):
        handler_md = get_handler_or_create(awatable)
        handler_md.event_filters.append(RegexFilter(regex))
        return awatable

    return decorator