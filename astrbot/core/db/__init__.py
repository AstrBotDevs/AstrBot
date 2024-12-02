import abc
from dataclasses import dataclass
from typing import List
from astrbot.core.db.po import Stats, LLMHistory

@dataclass
class BaseDatabase(abc.ABC):
    '''
    数据库基类
    '''
    def __init__(self) -> None:
        pass
    
    def insert_base_metrics(self, metrics: dict):
        '''插入基础指标数据'''
        self.insert_platform_metrics(metrics['platform_stats'])
        self.insert_plugin_metrics(metrics['plugin_stats'])
        self.insert_command_metrics(metrics['command_stats'])
        self.insert_llm_metrics(metrics['llm_stats'])
    
    @abc.abstractmethod
    def insert_platform_metrics(self, metrics: dict):
        '''插入平台指标数据'''
        raise NotImplementedError
    
    @abc.abstractmethod
    def insert_plugin_metrics(self, metrics: dict):
        '''插入插件指标数据'''
        raise NotImplementedError
    
    @abc.abstractmethod
    def insert_command_metrics(self, metrics: dict):
        '''插入指令指标数据'''
        raise NotImplementedError
    
    @abc.abstractmethod
    def insert_llm_metrics(self, metrics: dict):
        '''插入 LLM 指标数据'''
        raise NotImplementedError
    
    @abc.abstractmethod
    def update_llm_history(self, session_id: str, content: str):
        '''更新 LLM 历史记录。当不存在 session_id 时插入'''
        raise NotImplementedError
    
    @abc.abstractmethod
    def get_llm_history(self, session_id: str = None) -> List[LLMHistory]:
        '''获取 LLM 历史记录, 如果 session_id 为 None, 返回所有'''
        raise NotImplementedError
    
    @abc.abstractmethod
    def get_base_stats(self, offset_sec: int = 86400) -> Stats:
        '''获取基础统计数据'''
        raise NotImplementedError
    
    @abc.abstractmethod
    def get_total_message_count(self) -> int:
        '''获取总消息数'''
        raise NotImplementedError
    
    @abc.abstractmethod
    def get_grouped_base_stats(self, offset_sec: int = 86400) -> Stats:
        '''获取基础统计数据(合并)'''
        raise NotImplementedError
