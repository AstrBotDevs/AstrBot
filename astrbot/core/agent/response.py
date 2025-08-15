from dataclasses import dataclass
import typing as T
from astrbot.core.message.message_event_result import MessageChain

class AgentResponseData(T.TypedDict):
    chain: MessageChain


@dataclass
class AgentResponse:
    type: str
    data: AgentResponseData
