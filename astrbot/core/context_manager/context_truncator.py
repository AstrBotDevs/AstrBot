"""
上下文截断器：实现对半砍策略
"""

from typing import Any


class ContextTruncator:
    """
    上下文截断器

    实现对半砍策略：删除中间50%的消息
    """

    def truncate_by_halving(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        对半砍策略：删除中间50%的消息

        规则：
        - 保留第一条系统消息（如果存在）
        - 保留最后的消息（最近的对话）
        - 删除中间的消息

        Args:
            messages: 原始消息列表

        Returns:
            截断后的消息列表
        """
        if len(messages) <= 2:
            return messages

        # 找到第一条非系统消息的索引
        first_non_system = 0
        for i, msg in enumerate(messages):
            if msg.get("role") != "system":
                first_non_system = i
                break

        # 计算要删除的消息数
        messages_to_delete = (len(messages) - first_non_system) // 2

        # 保留系统消息 + 最后的消息
        result = messages[:first_non_system]
        result.extend(messages[first_non_system + messages_to_delete :])

        return result

    def truncate_by_count(
        self, messages: list[dict[str, Any]], max_messages: int
    ) -> list[dict[str, Any]]:
        """
        按数量截断：只保留最近的X条消息

        规则：
        - 保留系统消息（如果存在）
        - 保留最近的max_messages条消息

        Args:
            messages: 原始消息列表
            max_messages: 最大保留消息数

        Returns:
            截断后的消息列表
        """
        if len(messages) <= max_messages:
            return messages

        # 分离系统消息和其他消息
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        # 保留最近的消息
        kept_other = other_msgs[-(max_messages - len(system_msgs)) :]

        return system_msgs + kept_other
