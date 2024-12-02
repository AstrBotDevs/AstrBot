import abc, json, threading, time
from collections import defaultdict
from typing import List
from astrbot.core.db import BaseDatabase
from astrbot.core import logger
from typing import TypedDict

class Personality(TypedDict):
    prompt: str
    name: str

class Provider(abc.ABC):
    def __init__(self, db_helper: BaseDatabase, default_personality: str = None, persistant_history: bool = True) -> None:
        self.model_name = "unknown"
        # 维护了 session_id 的上下文，不包含 system 指令
        self.session_memory = defaultdict(list)
        self.curr_personality = Personality(prompt=default_personality, name="")
        
        if persistant_history:
            # 读取历史记录
            self.db_helper = db_helper
            try:
                for history in db_helper.get_llm_history():
                    self.session_memory[history.session_id] = json.loads(history.content)
            except BaseException as e:
                logger.warning(f"读取 LLM 对话历史记录 失败：{e}。仍可正常使用。")

        
    def set_model(self, model_name: str):
        self.model_name = model_name
    
    def get_model(self):
        return self.model_name
    
    async def get_human_readable_context(self, session_id: str) -> List[str]:
        '''
        获取人类可读的上下文

        example:
        ["User: 你好", "Assistant: 你好"]
        '''
        if session_id not in self.session_memory:
            raise Exception("会话 ID 不存在")

        contexts = []
        for record in self.session_memory[session_id]:
            if record['role'] == "user":
                contexts.append(f"User: {record['content']}")
            elif record['role'] == "assistant":
                contexts.append(f"Assistant: {record['content']}")

        return contexts
    
    @abc.abstractmethod
    async def text_chat(self,
                        prompt: str,
                        session_id: str,
                        image_urls: List[str] = None,
                        tools = None,
                        contexts=None,
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
    async def get_embedding(self, text: str) -> List[float]:
        '''
        获取文本的嵌入
        '''
        raise NotImplementedError()
    
    @abc.abstractmethod
    async def forget(self, session_id: str) -> bool:
        '''
        重置会话
        '''
        raise NotImplementedError()
