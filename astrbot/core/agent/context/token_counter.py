import json

from ..message import Message, TextPart


class TokenCounter:
    def count_tokens(self, messages: list[Message]) -> int:
        total = 0
        for msg in messages:
            content = msg.content
            if isinstance(content, str):
                total += self._estimate_tokens(content)
            elif isinstance(content, list):
                # 处理多模态内容
                for part in content:
                    if isinstance(part, TextPart):
                        total += self._estimate_tokens(part.text)

            # 处理 Tool Calls
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_str = json.dumps(tc if isinstance(tc, dict) else tc.model_dump())
                    total += self._estimate_tokens(tc_str)

        return total

    def _estimate_tokens(self, text: str) -> int:
        chinese_count = len([c for c in text if "\u4e00" <= c <= "\u9fff"])
        other_count = len(text) - chinese_count
        return int(chinese_count * 0.6 + other_count * 0.3)
