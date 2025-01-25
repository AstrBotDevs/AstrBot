import abc
import json
from collections import defaultdict
from typing import List
from astrbot.core.db import BaseDatabase
from astrbot.core import logger
from typing import TypedDict
from astrbot.core.provider.func_tool_manager import FuncCall
from astrbot.core.provider.entites import LLMResponse
from dataclasses import dataclass
class Personality(TypedDict):
    prompt: str = ""
    name: str = ""
    begin_dialogs: List[str] = []
    mood_imitation_dialogs: List[str] = []
    
    # cache
    _begin_dialogs_processed: List[dict]
    _mood_imitation_dialogs_processed: str
    
    
@dataclass
class ProviderMeta():
    id: str
    model: str
    type: str
    
    
class AbstractProvider(abc.ABC):
    def __init__(self, provider_config: dict) -> None:
        super().__init__()
        self.model_name = ""
        self.provider_config = provider_config

    def set_model(self, model_name: str):
        '''设置当前使用的模型名称'''
        self.model_name = model_name
    
    def get_model(self) -> str:
        '''获得当前使用的模型名称'''
        return self.model_name
    
    def meta(self) -> ProviderMeta:
        '''获取 Provider 的元数据'''
        return ProviderMeta(
            id=self.provider_config['id'],
            model=self.get_model(),
            type=self.provider_config['type']
        )


class Provider(AbstractProvider):
    def __init__(
        self, 
        provider_config: dict,
        provider_settings: dict, 
        persistant_history: bool = True,
        db_helper: BaseDatabase = None,
        default_persona: Personality = None
    ) -> None:
        super().__init__(provider_config)
        
        self.session_memory = defaultdict(list)
        '''维护了 session_id 的上下文，**不包含 system 指令**。'''
        
        self.provider_settings = provider_settings
        
        self.curr_personality: Personality = default_persona
        '''维护了当前的使用的 persona，即人格。可能为 None'''
        
        self.db_helper = db_helper
        '''用于持久化的数据库操作对象。'''

        if persistant_history:
            # 读取历史记录
            try:
                for history in db_helper.get_llm_history(provider_type=provider_config['type']):
                    self.session_memory[history.session_id] = json.loads(history.content)
            except BaseException as e:
                logger.warning(f"读取 LLM 对话历史记录 失败：{e}。仍可正常使用。")
    
    @abc.abstractmethod
    def get_current_key(self) -> str:
        raise NotImplementedError()
    
    def get_keys(self) -> List[str]:
        '''获得提供商 Key'''
        return self.provider_config.get("key", [])
    
    @abc.abstractmethod
    def set_key(self, key: str):
        raise NotImplementedError()
    
    @abc.abstractmethod
    def get_models(self) -> List[str]:
        '''获得支持的模型列表'''
        raise NotImplementedError()
    
    @abc.abstractmethod
    async def get_human_readable_context(self, session_id: str, page: int, page_size: int):
        '''获取人类可读的上下文
        
        page 从 1 开始

        Example:
            
            ["User: 你好", "Assistant: 你好！"]
            
        Return:
            contexts: List[str]: 上下文列表
            total_pages: int: 总页数
        '''
        raise NotImplementedError()
    
    @abc.abstractmethod
    async def text_chat(self,
                        prompt: str,
                        session_id: str=None,
                        image_urls: List[str]=None,
                        func_tool: FuncCall=None,
                        contexts: List=None,
                        system_prompt: str=None,
                        **kwargs) -> LLMResponse:
        '''获得 LLM 的文本对话结果。会使用当前的模型进行对话。
        
        Args:
            prompt: 提示词
            session_id: 会话 ID
            image_urls: 图片 URL 列表
            tools: Function-calling 工具
            contexts: 上下文
            kwargs: 其他参数
            
        Notes:
            - 如果传入了 contexts，将会提前加上上下文。否则使用 session_memory 中的上下文。
            - 可以选择性地传入 session_id，如果传入了 session_id，将会使用 session_id 对应的上下文进行对话，
            并且也会记录相应的对话上下文，实现多轮对话。如果不传入则不会记录上下文。
            - 如果传入了 image_urls，将会在对话时附上图片。如果模型不支持图片输入，将会抛出错误。
            - 如果传入了 tools，将会使用 tools 进行 Function-calling。如果模型不支持 Function-calling，将会抛出错误。
        '''
        raise NotImplementedError()
    
    @abc.abstractmethod
    async def forget(self, session_id: str) -> bool:
        '''重置某一个 session_id 的上下文'''
        raise NotImplementedError()


        
class STTProvider(AbstractProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
    
    @abc.abstractmethod
    async def get_text(self, audio_url: str) -> str:
        '''获取音频的文本'''
        raise NotImplementedError()


class TTSProvider(AbstractProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
    
    @abc.abstractmethod
    async def get_audio(self, text: str) -> str:
        '''获取文本的音频，返回音频文件路径'''
        raise NotImplementedError()