import re

from astrbot import logger

from . import ContentSafetyStrategy


class KeywordsStrategy(ContentSafetyStrategy):
    def __init__(self, extra_keywords: list) -> None:
        """Compile the configured keyword patterns once.

        The extra_keywords option documents regex support, so each entry is
        treated as a regular expression. Invalid patterns are skipped with a
        warning instead of being allowed to raise at match time, which would
        otherwise crash the message pipeline on every inbound message.

        Args:
            extra_keywords: User-configured blocked keywords, each a regex.
        """
        self._patterns: list[re.Pattern] = []
        # keywords_path = os.path.join(os.path.dirname(__file__), "unfit_words")
        # internal keywords
        # if os.path.exists(keywords_path):
        #     with open(keywords_path, "r", encoding="utf-8") as f:
        #         self.keywords.extend(
        #             json.loads(base64.b64decode(f.read()).decode("utf-8"))["keywords"]
        #         )
        for keyword in extra_keywords or []:
            try:
                self._patterns.append(re.compile(keyword))
            except re.error as e:
                logger.warning(
                    f"Skipping invalid content-safety keyword regex {keyword!r}: {e}"
                )

    def check(self, content: str) -> tuple[bool, str]:
        for pattern in self._patterns:
            if pattern.search(content):
                return False, (
                    "Content safety check failed because a blocked keyword was matched."
                )
        return True, ""
