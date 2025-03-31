from dataclasses import dataclass, field
from typing import List


@dataclass
class Platform:
    """平台消息计数"""
    name: str
    count: int
    timestamp: int


@dataclass
class Provider:
    name: str
    count: int
    timestamp: int


@dataclass
class Command:
    name: str
    count: int
    timestamp: int


@dataclass
class Stats:
    platform: List[Platform] = field(default_factory=list)
    command: List[Command] = field(default_factory=list)
    llm: List[Provider] = field(default_factory=list)


@dataclass
class Conversation:
    """LLM 对话存储

    对于网页聊天, history 存储了包括指令、回复、图片等在内的所有消息。
    对于其他平台的聊天，不存储非 LLM 的回复（因为考虑到已经存储在各自的平台上）。
    """

    user_id: str
    cid: str
    history: str = ""
    """字符串格式的列表。"""
    created_at: int = 0
    updated_at: int = 0
    title: str = ""
    persona_id: str = ""
