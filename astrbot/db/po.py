'''指标数据'''

from dataclasses import dataclass, field
# default_factory
from typing import List

@dataclass
class Platform():
    name: str
    count: int
    timestamp: int
    
@dataclass
class Provider():
    name: str
    count: int
    timestamp: int
    
@dataclass
class Plugin():
    name: str
    count: int
    timestamp: int
    
@dataclass
class Command():
    name: str
    count: int
    timestamp: int

@dataclass
class Stats():
    platform: List[Platform] = field(default_factory=list)
    command: List[Command] = field(default_factory=list)
    llm: List[Provider] = field(default_factory=list)
    
'''LLM 聊天时持久化的信息'''

@dataclass
class LLMHistory():
    session_id: str
    content: str