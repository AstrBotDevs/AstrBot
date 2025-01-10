'''指标数据'''

from dataclasses import dataclass, field
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
    provider_type: str
    session_id: str
    content: str
    
@dataclass
class ATRIVision():
    id: str
    url_or_path: str
    caption: str
    is_meme: bool
    keywords: List[str]
    platform_name: str
    session_id: str
    sender_nickname: str
    timestamp: int = -1
    
    

@dataclass
class WebChatConversation():
    user_id: str
    cid: str
    history: str = ""
    created_at: int = 0
    updated_at: int = 0
    