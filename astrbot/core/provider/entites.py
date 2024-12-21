from dataclasses import dataclass
from typing import List, Dict
from .func_tool_manager import FuncCall


@dataclass
class ProviderMetaData():
    type: str # 提供商适配器名称，如 openai, ollama
    desc: str = "" # 提供商适配器描述.
    

@dataclass
class ProviderRequest():
    prompt: str
    '''提示词'''
    session_id: str = ""
    '''会话 ID'''
    image_urls: List[str] = None
    '''图片 URL 列表'''
    func_tool: FuncCall = None
    '''工具'''
    contexts: List = None
    '''上下文。格式与 openai 的上下文格式一致：
    参考 https://platform.openai.com/docs/api-reference/chat/create#chat-create-messages
    '''
    
    system_prompt: str = ""
    '''系统提示词'''
    
    
@dataclass
class LLMResponse:
    role: str
    '''角色'''
    completion_text: str = None
    '''LLM 返回的文本'''
    tools_call_args: List[Dict[str, any]] = None
    '''工具调用参数'''
    tools_call_name: List[str] = None
    '''工具调用名称'''