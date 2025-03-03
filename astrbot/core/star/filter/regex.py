import re
from . import HandlerFilter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.config import AstrBotConfig


# 正则表达式过滤器不会受到 wake_prefix 的制约。
class RegexFilter(HandlerFilter):
    """正则表达式过滤器"""

    def __init__(self, regex: str):
        self.regex_str = regex
        self.regex = re.compile(regex)

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        return bool(self.regex.match(event.get_message_str().strip()))
