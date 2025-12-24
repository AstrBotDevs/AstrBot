"""
Token计数器：实现粗算Token估算
"""

import json
from typing import Any


class TokenCounter:
    """
    Token计数器

    使用粗算方法估算Token数：
    - 中文字符：0.6 token/字符
    - 其他字符：0.3 token/字符
    """

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """
        计算消息列表的总Token数

        Args:
            messages: 消息列表

        Returns:
            估算的总Token数
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self._estimate_tokens(content)
            elif isinstance(content, list):
                # 处理多模态内容
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += self._estimate_tokens(part["text"])

            # 处理Tool Calls
            if "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    tc_str = json.dumps(tc)
                    total += self._estimate_tokens(tc_str)

        return total

    def _estimate_tokens(self, text: str) -> int:
        """
        估算单个文本的Token数

        规则：
        - 中文字符：0.6 token/字符
        - 其他字符：0.3 token/字符

        Args:
            text: 要估算的文本

        Returns:
            估算的Token数
        """
        chinese_count = len([c for c in text if "\u4e00" <= c <= "\u9fff"])
        other_count = len(text) - chinese_count
        return int(chinese_count * 0.6 + other_count * 0.3)
