from typing import Dict, List
from dataclasses import dataclass

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
