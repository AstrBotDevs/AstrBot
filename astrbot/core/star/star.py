from __future__ import annotations

from types import ModuleType
from typing import List, Dict
from dataclasses import dataclass

star_registry: List[StarMetadata] = []
star_map: Dict[str, StarMetadata] = {}
'''key 是模块路径，__module__'''

@dataclass
class StarMetadata:
    '''
    Star 的元数据。
    '''
    name: str
    author: str  # 插件作者
    desc: str  # 插件简介
    version: str  # 插件版本
    repo: str = None  # 插件仓库地址

    star_cls_type: type = None
    '''Star 的类对象的类型'''
    module_path: str = None
    '''Star 的模块路径'''
    
    star_cls: object = None
    '''Star 的类对象'''
    module: ModuleType = None
    '''Star 的模块对象'''
    root_dir_name: str = None
    '''Star 的根目录名'''
    reserved: bool = False
    '''是否是 AstrBot 的保留 Star'''
    
    activated: bool = True
    '''是否被激活'''

    def __str__(self) -> str:
        return f"StarMetadata({self.name}, {self.desc}, {self.version}, {self.repo})"