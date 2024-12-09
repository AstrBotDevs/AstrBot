from __future__ import annotations
from dataclasses import dataclass
from typing import Awaitable, List, Dict
from .filter import HandlerFilter

star_handlers_registry: List[StarHandlerMetadata] = []

star_handlers_map: Dict[str, StarHandlerMetadata] = {}
'''用于快速查找。key 是 handler_full_name'''

@dataclass
class StarHandlerMetadata():
    '''描述一个 Star 所注册的某一个 Handler。'''
    
    handler_full_name: str
    '''格式为 f"{handler.__module__}_{handler.__name__}"'''
    
    handler_name: str
    '''Handler 的名字，也就是方法名'''
    
    handler_module_str: str
    '''Handler 所在的模块路径。'''
    
    handler: Awaitable
    '''Handler 的函数对象，应当是一个异步函数'''
    
    event_filters: List[HandlerFilter]
    '''一个事件过滤器，用于描述这个 Handler 能够处理、应该处理的事件'''
    
    desc: str = ""
    '''Handler 的描述信息'''
