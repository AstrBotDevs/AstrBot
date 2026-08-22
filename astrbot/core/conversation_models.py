from dataclasses import dataclass


@dataclass
class Conversation:
    """LLM 对话类

    对于 WebChat，history 存储了包括指令、回复、图片等在内的所有消息。
    对于其他平台的聊天，不存储非 LLM 的回复（因为考虑到已经存储在各自的平台上）。

    在 v4.0.0 版本及之后，WebChat 的历史记录被迁移至 `PlatformMessageHistory` 表中，
    """

    platform_id: str
    user_id: str
    cid: str
    """对话 ID, 是 uuid 格式的字符串"""
    history: str = ""
    """字符串格式的对话列表。"""
    title: str | None = ""
    persona_id: str | None = ""
    created_at: int = 0
    updated_at: int = 0
    token_usage: int = 0
    """对话的总 token 数量。AstrBot 会保留最近一次 LLM 请求返回的总 token 数，方便统计。token_usage 可能为 0，表示未知。"""
