'''
允许开发者注册某一个类的实例到 LLM 或者 PLATFORM 中，方便其他插件调用。

必须分别实现 Platform 和 LLMProvider 中涉及的接口
'''
from model.provider.provider import Provider as LLMProvider
from model.platform._platfrom import Platform
from type.types import GlobalObject
from type.register import RegisteredPlatform, RegisteredLLM

def register_platform(platform_name: str, platform_instance: Platform, context: GlobalObject) -> None:
    '''
    注册一个消息平台。

    Args:
        platform_name: 平台名称。
        platform_instance: 平台实例。
    '''
    
    # check 是否已经注册
    for platform in context.platforms:
        if platform.platform_name == platform_name:
            raise ValueError(f"Platform {platform_name} has been registered.")
    
    context.platforms.append(RegisteredPlatform(platform_name, platform_instance))
    
def register_llm(llm_name: str, llm_instance: LLMProvider, context: GlobalObject) -> None:
    '''
    注册一个大语言模型。

    Args:
        llm_name: 大语言模型名称。
        llm_instance: 大语言模型实例。
    '''
    # check 是否已经注册
    for llm in context.llms:
        if llm.llm_name == llm_name:
            raise ValueError(f"LLMProvider {llm_name} has been registered.")
    
    context.llms.append(RegisteredLLM(llm_name, llm_instance))

def unregister_platform(platform_name: str, context: GlobalObject) -> None:
    '''
    注销一个消息平台。

    Args:
        platform_name: 平台名称。
    '''
    for i, platform in enumerate(context.platforms):
        if platform.platform_name == platform_name:
            context.platforms.pop(i)
            return
        
def unregister_llm(llm_name: str, context: GlobalObject) -> None:
    '''
    注销一个大语言模型。

    Args:
        llm_name: 大语言模型名称。
    '''
    for i, llm in enumerate(context.llms):
        if llm.llm_name == llm_name:
            context.llms.pop(i)
            return