
from astrbot.core.plugin import Context
from astrbot.core.platform import AstrMessageEvent, Platform, AstrBotMessage, MessageMember, MessageType, PlatformMetadata
from astrbot.core.message_event_result import MessageEventResult, MessageChain, CommandResult
from astrbot.core.provider import Provider
from astrbot.core.config.astrbot_config import AstrBotConfig
from nakuru.entities.components import *
from astrbot import logger
from astrbot.core.utils.personality import personalities

from astrbot.core.utils.command_parser import CommandParser, CommandTokens
from astrbot.core.utils.func_call import FuncCall
from astrbot.core import html_renderer

command_parser = CommandParser()