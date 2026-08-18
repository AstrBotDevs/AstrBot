"""企业微信智能机器人平台适配器包"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .wecomai_adapter import WecomAIBotAdapter
    from .wecomai_api import WecomAIBotAPIClient
    from .wecomai_event import WecomAIBotMessageEvent
    from .wecomai_server import WecomAIBotServer
    from .wecomai_utils import WecomAIBotConstants
else:
    WecomAIBotAdapter: Any
    WecomAIBotAPIClient: Any
    WecomAIBotMessageEvent: Any
    WecomAIBotServer: Any
    WecomAIBotConstants: Any

__all__ = [
    "WecomAIBotAPIClient",
    "WecomAIBotAdapter",
    "WecomAIBotConstants",
    "WecomAIBotMessageEvent",
    "WecomAIBotServer",
]


def __getattr__(name: str) -> Any:
    if name == "WecomAIBotAdapter":
        return import_module(".wecomai_adapter", __name__).WecomAIBotAdapter
    if name == "WecomAIBotAPIClient":
        return import_module(".wecomai_api", __name__).WecomAIBotAPIClient
    if name == "WecomAIBotMessageEvent":
        return import_module(".wecomai_event", __name__).WecomAIBotMessageEvent
    if name == "WecomAIBotServer":
        return import_module(".wecomai_server", __name__).WecomAIBotServer
    if name == "WecomAIBotConstants":
        return import_module(".wecomai_utils", __name__).WecomAIBotConstants
    raise AttributeError(name)
