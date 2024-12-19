from dataclasses import dataclass
from typing import List
from .tool import FuncCall

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
    '''上下文'''
    system_prompt: str = ""
    '''系统提示词'''