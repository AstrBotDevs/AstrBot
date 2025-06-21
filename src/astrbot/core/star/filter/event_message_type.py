import enum
from . import HandlerFilter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.message_type import MessageType


class EventMessageType(enum.Flag):
    GROUP_MESSAGE = enum.auto()
    PRIVATE_MESSAGE = enum.auto()
    OTHER_MESSAGE = enum.auto()
    ALL = GROUP_MESSAGE | PRIVATE_MESSAGE | OTHER_MESSAGE


MESSAGE_TYPE_2_EVENT_MESSAGE_TYPE = {
    MessageType.GROUP_MESSAGE: EventMessageType.GROUP_MESSAGE,
    MessageType.FRIEND_MESSAGE: EventMessageType.PRIVATE_MESSAGE,
    MessageType.OTHER_MESSAGE: EventMessageType.OTHER_MESSAGE,
}


class EventMessageTypeFilter(HandlerFilter):
    def __init__(self, event_message_type: EventMessageType):
        self.event_message_type = event_message_type

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        message_type = event.get_message_type()
        if message_type in MESSAGE_TYPE_2_EVENT_MESSAGE_TYPE:
            event_message_type = MESSAGE_TYPE_2_EVENT_MESSAGE_TYPE[message_type]
            return bool(event_message_type & self.event_message_type)
        return False
