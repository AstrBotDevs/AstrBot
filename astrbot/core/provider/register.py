from typing import List, Dict, Type
from .provider_metadata import ProviderMetaData
from astrbot.core import logger

provider_registry: List[ProviderMetaData] = []
'''维护了通过装饰器注册的 Provider'''
provider_cls_map: Dict[str, Type] = {}
'''维护了 Provider 类型名称和 Provider 类的映射'''

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
