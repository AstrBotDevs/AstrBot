import asyncio
from .event import Event
from .ensoul.soul import Soul
from .ensoul.emotion import Emotion


class EliosEventHandler:
    async def on_event(self, event: Event, soul: Soul): ...


event_handlers_cls: dict[str, list[type[EliosEventHandler]]] = {}


def register_event_handler(event_types: set[str] | None = None):
    """注册事件处理器"""

    def decorator(cls: type[EliosEventHandler]) -> type[EliosEventHandler]:
        if event_types is not None:
            for event_type in event_types:
                event_handlers_cls[event_type] = event_handlers_cls.get(
                    event_type, []
                ) + [cls]
        else:
            event_handlers_cls["default"] = event_handlers_cls.get("default", []) + [
                cls
            ]
        return cls

    return decorator


class EliosRunner:
    def __init__(self) -> None:
        self.soul = Soul(
            emotion=Emotion(energy=0.5, valence=0.5, arousal=0.5), emotion_logs=[]
        )

        self.event_queue = asyncio.Queue()
        self.event_handler_insts: dict[str, list[EliosEventHandler]] = {}

    def start(self):
        for event_type, cls_list in event_handlers_cls.items():
            self.event_handler_insts[event_type] = []
            for cls in cls_list:
                try:
                    self.event_handler_insts[event_type].append(cls())
                except Exception as e:
                    print(f"Error initializing event handler {cls}: {e}")
        asyncio.create_task(self._worker())

    async def _worker(self):
        """监听事件队列并处理事件"""
        while True:
            event = await self.event_queue.get()
            # A man cannot handle two things at once. But this can be configurable.
            try:
                await self._process_event(event)
            except Exception as e:
                print(f"Error processing event {event}: {e}")

    async def _process_event(self, event: Event):
        """处理事件"""
        event_type = event.event_type
        handlers = self.event_handler_insts.get(
            event_type, []
        ) + self.event_handler_insts.get("default", [])

        for inst in handlers:
            try:
                await inst.on_event(event, self.soul)
            except Exception as e:
                print(f"Error processing event {event}: {e}")
