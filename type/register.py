from model.provider.provider import Provider as LLMProvider
from model.platform import Platform
from type.plugin import *
from typing import List
from dataclasses import dataclass

@dataclass
class RegisteredPlatform:
    '''
    注册在 AstrBot 中的平台。平台应当实现 Platform 接口。
    '''
    platform_name: str
    platform_instance: Platform
    origin: str = None  # 注册来源

    def __str__(self) -> str:
        return self.platform_name


@dataclass
class RegisteredLLM:
    '''
    注册在 AstrBot 中的大语言模型调用。大语言模型应当实现 LLMProvider 接口。
    '''
    llm_name: str
    llm_instance: LLMProvider
    origin: str = None  # 注册来源
