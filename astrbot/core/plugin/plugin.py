from enum import Enum
from types import ModuleType
from typing import List
from dataclasses import dataclass

@dataclass
class PluginMetadata:
    '''
    插件的元数据。
    '''
    # required
    plugin_name: str
    author: str  # 插件作者
    desc: str  # 插件简介
    version: str  # 插件版本

    # optional
    repo: str = None  # 插件仓库地址

    def __str__(self) -> str:
        return f"PluginMetadata({self.plugin_name}, {self.desc}, {self.version}, {self.repo})"


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
    reserved: bool # 是否是 AstrBot 的保留插件

    def __str__(self) -> str:
        return f"RegisteredPlugin({self.metadata}, {self.module_path}, {self.root_dir_name})"



class Plugin:
    def __init__(self):
        pass