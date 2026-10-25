from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionEnumResult:
    """平台会话枚举结果。

    groups/friends 中每个条目形如 {"id": str, "name": str}。
    error 非空表示枚举完全或部分失败，调用方应降级处理。
    """

    groups: list[dict] = field(default_factory=list)
    friends: list[dict] = field(default_factory=list)
    error: str = ""


class SessionEnumerator:
    """平台适配器可选实现的会话枚举能力协议。

    支持枚举的平台（如 aiocqhttp）实现 enumerate_sessions()，
    让会话管理页能列出"从未和机器人说过话"的群聊/私聊。
    """

    async def enumerate_sessions(self) -> SessionEnumResult:
        raise NotImplementedError
