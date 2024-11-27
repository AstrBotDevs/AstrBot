import asyncio
from asyncio import Queue
from collections import defaultdict
from typing import List
from .message_event_handler import MessageEventHandler
from core import logger
from .platform import AstrMessageEvent
from nakuru.entities.components import Plain, Image

class EventBus:
    def __init__(self, event_queue: Queue, message_event_handler: MessageEventHandler):
        self.event_queue = event_queue
        self.message_event_handler = message_event_handler

    async def dispatch(self):
        logger.info("事件总线已打开。")
        while True:
            event: AstrMessageEvent = await self.event_queue.get()
            self._print_event(event)
            asyncio.create_task(self.message_event_handler.handle(event))
            
    def _print_event(self, event: AstrMessageEvent):        
        if event.get_sender_name():
            logger.info(f"[{event.get_platform_name()}] {event.get_sender_name()}/{event.get_sender_id()}: {event.get_message_outline()}")
        else:
            logger.info(f"[{event.get_platform_name()}] {event.get_sender_id()}: {event.get_message_outline()}")