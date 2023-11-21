import sys
from types import ModuleType
import asyncio
from pyppeteer import launch

from model.platform.qqchan import QQChan

from .nonebot.driver import Driver, get_driver
from .onebot.message import Message
from .onebot.message_event import MessageEvent
from .onebot.message_segment import MessageSegment
from .nonebot.command_arg import CommandArg
from .onebot.bot import Bot
from .nonebot.common import require

from nakuru import (
    GuildMessage,
    GroupMessage,
    FriendMessage
)

from typing import Union

NONEBOT = "nonebot"

class UnifiedBotCompatibleLayer():
    def __init__(self, platform_qq_sdk: QQChan) -> None:
        # 初始化兼容层
        self.plugins: dict[str, CommandOper] = {}
        self.platform_qq_sdk = platform_qq_sdk
        self._nonebot()
        self.load_plugins()

    async def check_commands(self, message: str, message_obj: Union[GroupMessage, FriendMessage, GuildMessage]):
        for k in self.plugins:
            if message.startswith(k):
                if self.plugins[k].framework_name == NONEBOT:
                    await self._nonebot_plugins_oper(message, message_obj, k)

    async def _nonebot_plugins_oper(self, message: str, message_obj: Union[GroupMessage, FriendMessage, GuildMessage], plugin_name: str = None):
        # bad implementation
        # 高并发场景下，下面的代码是不安全的
        while self.plugins[plugin_name].message_obj is not None:
            await asyncio.sleep(1)
        self.plugins[plugin_name].message_obj = message_obj
        bot, event, arg = self._nonebot_adapter(message_obj)
        await self.plugins[plugin_name].exec(bot, event, arg) # wrapper

    def load_plugins(self):
        import nonebot_plugin_gspanel.nonebot_plugin_gspanel

    def _nonebot(self):        
        # 模拟 nonebot 模块
        nonebot_module = ModuleType('nonebot')
        sys.modules['nonebot'] = nonebot_module

        nonebot_log_module = ModuleType('nonebot.log')
        sys.modules['nonebot.log'] = nonebot_log_module

        nonebot_adapter_module = ModuleType('nonebot.adapters')
        sys.modules['nonebot.adapters'] = nonebot_adapter_module

        nonebot_params_module = ModuleType('nonebot.params')
        sys.modules['nonebot.params'] = nonebot_params_module

        nonebot_drivers_module = ModuleType('nonebot.drivers')
        sys.modules['nonebot.drivers'] = nonebot_drivers_module

        nonebot_plugin_module = ModuleType('nonebot.plugin')
        sys.modules['nonebot.plugin'] = nonebot_plugin_module

        nonebot_adapter_onebot_v11_module = ModuleType('nonebot.adapters.onebot.v11')
        sys.modules['nonebot.adapters.onebot.v11'] = nonebot_adapter_onebot_v11_module

        nonebot_adapter_onebot_v11_event_module = ModuleType('nonebot.adapters.onebot.v11.event')
        sys.modules['nonebot.adapters.onebot.v11.event'] = nonebot_adapter_onebot_v11_event_module

        nonebot_adapter_onebot_v11_message_module = ModuleType('nonebot.adapters.onebot.v11.message')
        sys.modules['nonebot.adapters.onebot.v11.message'] = nonebot_adapter_onebot_v11_message_module

        nonebot_log_module.logger = lambda: None
        nonebot_adapter_module.Message = Message
        nonebot_params_module.CommandArg = CommandArg
        on_command = wrap_on_command(self)
        nonebot_plugin_module.on_command = on_command
        nonebot_adapter_onebot_v11_module.Bot = Bot
        nonebot_adapter_onebot_v11_event_module.MessageEvent = MessageEvent
        nonebot_adapter_onebot_v11_message_module.MessageSegment = MessageSegment
        nonebot_module.get_driver = get_driver
        nonebot_module.require = require
        nonebot_drivers_module.Driver = Driver
    
    def _nonebot_adapter(self, message_obj):
        bot = Bot()
        event = MessageEvent()
        arg = CommandArg()
        # tododssss
        return bot, event, arg


class BaseBot():
    def __init__(self, framework_name) -> None:
        self.framework_name = framework_name

class CommandOper(BaseBot):
    '''
    CommandOper for NoneBot
    '''
    def __init__(self, name, aliases=None, priority=1, block=False, _ubcl: UnifiedBotCompatibleLayer = None) -> None:
        super().__init__("nonebot")
        self.name = name
        self.aliases = aliases
        self.priority = priority
        self.block = block
        self.exec = None
        self._ubcl = _ubcl
        self.message_obj: Union[GroupMessage, FriendMessage, GuildMessage] = None
        _ubcl.plugins[name] = self

    def handle(self):
        def decorator(func):
            async def wrapper(bot: Bot, event: MessageEvent, arg: Message = CommandArg(), *args, **kwargs):
                # 你可以在这里添加自定义的处理逻辑
                print(f"Command {self.name} is executed.")
                await func(bot, event, arg, *args, **kwargs)
            self.exec = wrapper
            return wrapper
        return decorator

    async def finish(self, msg, at_sender = True):
        if self.message_obj is not None:
            self._ubcl.platform_qq_sdk.send(self.message_obj, msg)
            self.message_obj = None

def wrap_on_command(_ubcl: UnifiedBotCompatibleLayer):
    def on_command(name, aliases=None, priority=1, block=False):
        return CommandOper(name, aliases, priority, block, _ubcl = _ubcl)
    return on_command
