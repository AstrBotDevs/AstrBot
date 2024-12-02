import asyncio, time, threading
from .event_bus import EventBus
from asyncio import Queue
from typing import List
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.message_event_handler import MessageEventHandler
from astrbot.core.plugin import PluginManager
from astrbot.core import LogBroker
from astrbot.core.db import BaseDatabase
from astrbot.core.updator import AstrBotUpdator
from astrbot.core import logger
from astrbot.core.config.default import VERSION

class AstrBotCoreLifecycle:
    def __init__(self, log_broker: LogBroker, db: BaseDatabase):
        self.log_broker = log_broker
        self.astrbot_config = AstrBotConfig()
        logger.info("AstrBot v"+ VERSION)
        logger.setLevel(self.astrbot_config.log_level)
        self.event_queue = Queue()
        self.event_queue.closed = False
        self.plugin_manager = PluginManager(self.astrbot_config, self.event_queue, db)
        self.message_event_handler = MessageEventHandler(self.astrbot_config, self.plugin_manager)
        self.astrbot_updator = AstrBotUpdator(self.astrbot_config.plugin_repo_mirror)
        self.event_bus = EventBus(self.event_queue, self.message_event_handler)
        self.stop_flag = False
        self.start_time = int(time.time())
        
        self.curr_tasks: List[asyncio.Task] = []

    def _load(self):
        self.plugin_manager.reload()

        platform_tasks = self.load_platform()
        event_bus_task = asyncio.create_task(self.event_bus.dispatch(), name="event_bus")
        
        self.curr_tasks = [event_bus_task, *platform_tasks]
        self.start_time = int(time.time())
    
    async def start(self):
        self._load()
        await asyncio.gather(*self.curr_tasks, return_exceptions=True)
        
    def stop(self):
        self.stop_flag = True
    
    def restart(self):
        self.event_queue.closed = True
        threading.Thread(target=self.astrbot_updator._reboot, name="restart", daemon=True).start()
        
    def load_platform(self) -> List[asyncio.Task]:
        tasks = []
        platform_insts = self.plugin_manager.get_platform_insts()
        for platform_inst in platform_insts:
            tasks.append(asyncio.create_task(platform_inst.run(), name=platform_inst.meta().name))
        return tasks