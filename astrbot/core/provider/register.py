import docstring_parser
from typing import List, Dict, Type, Awaitable
from .provider_metadata import ProviderMetaData
from astrbot.core import logger
from .tool import FuncCall, SUPPORTED_TYPES

provider_registry: List[ProviderMetaData] = []
'''维护了通过装饰器注册的 Provider'''
provider_cls_map: Dict[str, Type] = {}
'''维护了 Provider 类型名称和 Provider 类的映射'''

llm_tools = FuncCall()

def register_provider_adapter(provider_type_name: str, desc: str):
    '''用于注册平台适配器的带参装饰器'''
    def decorator(cls):
        if provider_type_name in provider_cls_map:
            raise ValueError(f"检测到大模型提供商适配器 {provider_type_name} 已经注册，可能发生了大模型提供商适配器类型命名冲突。")

        pm = ProviderMetaData(
            type=provider_type_name,
            desc=desc,
        )
        provider_registry.append(pm)
        provider_cls_map[provider_type_name] = cls
        logger.debug(f"Provider {provider_type_name} 已注册")
        return cls
    
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
    
    '''
    name_ = name
    
    def decorator(func_obj: Awaitable):
        llm_tool_name = name_ if name_ else func_obj.__name__
        module_name = func_obj.__module__
        docstring = docstring_parser.parse(func_obj.__doc__)
        args = []
        for arg in docstring.params:
            if arg.type_name not in SUPPORTED_TYPES:
                raise ValueError(f"LLM 函数工具 {func_obj.__module__}_{llm_tool_name} 不支持的参数类型：{arg.type_name}")
            args.append({
                "type": arg.type_name,
                "name": arg.arg_name,
                "description": arg.description
            })
        llm_tools.add_func(llm_tool_name, args, docstring.short_description, func_obj, module_name)
        
        logger.debug(f"LLM 函数工具 {llm_tool_name} 已注册")
        return func_obj
    
    return decorator