import abc
from collections import defaultdict
from typing import List
# from core.utils.func_call import FuncCall

class Provider(abc.ABC):
    def __init__(self) -> None:
        self.model_name = "unknown"
        
    def set_model(self, model_name: str):
        self.model_name = model_name
    
    def get_model(self):
        return self.model_name
    
    @abc.abstractmethod
    async def text_chat(self,
                        prompt: str,
                        session_id: str,
                        image_urls: List[str] = None,
                        tool = None,
                        **kwargs) -> str:
        '''
        prompt: 提示词
        session_id: 会话id

        [optional]
        image_url: 图片url（识图）
        tools: 函数调用工具
        '''
        raise NotImplementedError()
    
    @abc.abstractmethod
    async def image_generate(self, prompt: str, session_id: str, **kwargs) -> str:
        '''
        prompt: 提示词
        session_id: 会话id
        '''
        raise NotImplementedError()
    
    @abc.abstractmethod
    async def forget(self, session_id: str) -> bool:
        '''
        重置会话
        '''
        raise NotImplementedError()
