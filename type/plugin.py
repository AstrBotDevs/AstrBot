from enum import Enum
from types import ModuleType
from typing import List
from dataclasses import dataclass

class PluginType(Enum):
    PLATFORM = 'platform'  # 平台类插件。
    LLM = 'llm'  # 大语言模型类插件
    COMMON = 'common'  # 其他插件


@dataclass
class PluginMetadata:
    '''
    插件的元数据。
    '''
    # required
    plugin_name: str
    plugin_type: PluginType
    author: str  # 插件作者
    desc: str  # 插件简介
    version: str  # 插件版本

    # optional
    repo: str = None  # 插件仓库地址

    def __str__(self) -> str:
        return f"PluginMetadata({self.plugin_name}, {self.plugin_type}, {self.desc}, {self.version}, {self.repo})"


@dataclass
class RegisteredPlugin:
    '''
    注册在 AstrBot 中的插件。
    '''
    metadata: PluginMetadata
    plugin_instance: object
    module_path: str
    module: ModuleType
    root_dir_name: str
    trig_cnt: int = 0
    
    def reset_trig_cnt(self):
        self.trig_cnt = 0
    
    def trig(self):
        self.trig_cnt += 1

    def __str__(self) -> str:
        return f"RegisteredPlugin({self.metadata}, {self.module_path}, {self.root_dir_name})"


RegisteredPlugins = List[RegisteredPlugin]
