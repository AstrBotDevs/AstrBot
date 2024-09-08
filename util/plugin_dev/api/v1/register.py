'''
允许开发者注册某一个类的实例到 LLM 或者 PLATFORM 中，方便其他插件调用。

必须分别实现 Platform 和 LLMProvider 中涉及的接口
'''
from model.provider.provider import Provider as LLMProvider
from model.platform import Platform
from type.types import Context
from type.register import RegisteredPlatform, RegisteredLLM

def register_platform(platform_name: str, context: Context, platform_instance: Platform = None) -> None:
    '''
    注册一个消息平台。

    Args:
        platform_name: 平台名称。
        platform_instance: 平台实例，可为空。
        context: 上下文对象。
        
    Note:
        当插件类被加载时，AstrBot 会传给插件 context 对象。插件可以通过 context 对象注册指令、长任务等。
    '''
    
    # check 是否已经注册
    for platform in context.platforms:
        if platform.platform_name == platform_name:
            raise ValueError(f"Platform {platform_name} has been registered.")
    
    context.platforms.append(RegisteredPlatform(platform_name, platform_instance))
    
def register_llm(llm_name: str, llm_instance: LLMProvider, context: Context) -> None:
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

def unregister_platform(platform_name: str, context: Context) -> None:
    '''
    注销一个消息平台。

    Args:
        platform_name: 平台名称。
    '''
    for i, platform in enumerate(context.platforms):
        if platform.platform_name == platform_name:
            context.platforms.pop(i)
            return
        
def unregister_llm(llm_name: str, context: Context) -> None:
    '''
    注销一个大语言模型。

    Args:
        llm_name: 大语言模型名称。
    '''
    for i, llm in enumerate(context.llms):
        if llm.llm_name == llm_name:
            context.llms.pop(i)
            return