import re

from . import ContentSafetyStrategy


class KeywordsStrategy(ContentSafetyStrategy):
    def __init__(self, extra_keywords: list) -> None:
        self.keywords = []
        if extra_keywords is None:
            extra_keywords = []
        self.keywords.extend(extra_keywords)

    async def check(self, content: str) -> tuple[bool, str]:
        for keyword in self.keywords:
            if re.search(keyword, content):
                return False, "内容安全检查不通过，匹配到敏感词。"
        return True, ""
