"""
数据模型定义
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class Message:
    """消息数据模型"""

    role: str
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        result = {"role": self.role}
        if self.content is not None:
            result["content"] = self.content
        if self.tool_calls is not None:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id is not None:
            result["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            result["name"] = self.name
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """从字典创建消息对象"""
        return cls(
            role=data.get("role", ""),
            content=data.get("content"),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
            name=data.get("name"),
        )
