from typing import List, Dict, Type
from .platform_metadata import PlatformMetadata
from astrbot.core import logger

platform_registry: List[PlatformMetadata] = []
'''维护了通过装饰器注册的平台适配器'''
platform_cls_map: Dict[str, Type] = {}
'''维护了平台适配器名称和适配器类的映射'''

def register_platform_adapter(adapter_name: str, desc: str):
    '''用于注册平台适配器的带参装饰器'''
    def decorator(cls):
        if adapter_name in platform_cls_map:
            raise ValueError(f"平台适配器 {adapter_name} 已经注册过了，可能发生了适配器命名冲突。")

        pm = PlatformMetadata(
            name=adapter_name,
            description=desc,
        )
        platform_registry.append(pm)
        platform_cls_map[adapter_name] = cls
        logger.debug(f"平台适配器 {adapter_name} 已注册")
        return cls
    
    return decorator
