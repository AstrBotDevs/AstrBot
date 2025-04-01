"""指标数据"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Platform:
    """平台使用统计数据"""

    name: str
    count: int
    timestamp: int


@dataclass
class Provider:
    """供应商使用统计数据"""

    name: str
    count: int
    timestamp: int


@dataclass
class Plugin:
    """插件使用统计数据"""

    name: str
    count: int
    timestamp: int


@dataclass
class Command:
    """命令使用统计数据"""

    name: str
    count: int
    timestamp: int


@dataclass
class Stats:
    platform: List[Platform] = field(default_factory=list)
    command: List[Command] = field(default_factory=list)
    llm: List[Provider] = field(default_factory=list)


@dataclass
class LLMHistory:
    """LLM 聊天时持久化的信息"""

    provider_type: str
    session_id: str
    content: str


@dataclass
class ATRIVision:
    """Deprecated"""

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
class Conversation:
    """LLM 对话存储

    对于网页聊天，history 存储了包括指令、回复、图片等在内的所有消息。
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
