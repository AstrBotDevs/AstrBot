from __future__ import annotations
import enum
from dataclasses import dataclass
from typing import Awaitable, List, Dict, TypeVar, Generic
from .filter import HandlerFilter
from .star import star_map

T = TypeVar('T', bound='StarHandlerMetadata')
class StarHandlerRegistry(Generic[T], List[T]):
    '''用于存储所有的 Star Handler'''
    
    star_handlers_map: Dict[str, StarHandlerMetadata] = {}
    '''用于快速查找。key 是 handler_full_name'''
    
    def append(self, handler: StarHandlerMetadata):
        '''添加一个 Handler'''
        super().append(handler)
        self.star_handlers_map[handler.handler_full_name] = handler
        
    def get_handlers_by_event_type(self, event_type: EventType, only_activated = True) -> List[StarHandlerMetadata]:
        '''通过事件类型获取 Handler'''
        if only_activated:
            return [
                handler 
                for handler in self 
                if handler.event_type == event_type and 
                star_map[handler.handler_module_path] and 
                star_map[handler.handler_module_path].activated
            ]
        else:
            return [handler for handler in self if handler.event_type == event_type]
    
    def get_handler_by_full_name(self, full_name: str) -> StarHandlerMetadata:
        '''通过 Handler 的全名获取 Handler'''
        return self.star_handlers_map.get(full_name, None)
    
    def get_handlers_by_module_name(self, module_name: str) -> List[StarHandlerMetadata]:
        '''通过模块名获取 Handler'''
        return [handler for handler in self if handler.handler_module_path == module_name]
    
star_handlers_registry = StarHandlerRegistry()

class EventType(enum.Enum):
    '''表示一个 AstrBot 内部事件的类型。如适配器消息事件、LLM 请求事件、发送消息前的事件等
    
    用于对 Handler 的职能分组。
    '''
    AdapterMessageEvent = enum.auto() # 收到适配器发来的消息
    OnLLMRequestEvent = enum.auto() # 收到 LLM 请求（可以是用户也可以是插件）
    OnDecoratingResultEvent = enum.auto() # 发送消息前
    OnCallingFuncToolEvent = enum.auto() # 调用函数工具
    OnAfterMessageSentEvent = enum.auto() # 发送消息后

@dataclass
class StarHandlerMetadata():
    '''描述一个 Star 所注册的某一个 Handler。'''
    
    event_type: EventType
    '''Handler 的事件类型'''
    
    handler_full_name: str
    '''格式为 f"{handler.__module__}_{handler.__name__}"'''
    
    handler_name: str
    '''Handler 的名字，也就是方法名'''
    
    handler_module_path: str
    '''Handler 所在的模块路径。'''
    
    handler: Awaitable
    '''Handler 的函数对象，应当是一个异步函数'''
    
    event_filters: List[HandlerFilter]
    '''一个适配器消息事件过滤器，用于描述这个 Handler 能够处理、应该处理的适配器消息事件'''
    
    desc: str = ""
    '''Handler 的描述信息'''
