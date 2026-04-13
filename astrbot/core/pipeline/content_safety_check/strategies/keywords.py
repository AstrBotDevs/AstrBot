import re

from astrbot.core.i18n import t

from . import ContentSafetyStrategy


class KeywordsStrategy(ContentSafetyStrategy):
    def __init__(self, extra_keywords: list) -> None:
        self.keywords = []
        if extra_keywords is None:
            extra_keywords = []
        self.keywords.extend(extra_keywords)
        # keywords_path = os.path.join(os.path.dirname(__file__), "unfit_words")
        # internal keywords
        # if os.path.exists(keywords_path):
        #     with open(keywords_path, "r", encoding="utf-8") as f:
        #         self.keywords.extend(
        #             json.loads(base64.b64decode(f.read()).decode("utf-8"))["keywords"]
        #         )

    def check(self, content: str, locale: str | None = None) -> tuple[bool, str]:
        for keyword in self.keywords:
            if re.search(keyword, content):
                return False, t("pipeline.keyword_blocked_reason", locale=locale)
        return True, ""
