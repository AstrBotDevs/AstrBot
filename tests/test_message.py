import asyncio
import pytest
import os

from tests.mocks.qq_official import MockQQOfficialMessage
from tests.mocks.onebot import MockOneBotMessage

from astrbot.bootstrap import AstrBotBootstrap
from model.platform.qq_official import QQOfficial
from model.platform.qq_aiocqhttp import AIOCQHTTP
from type.astrbot_message import *
from type.message_event import *
from SparkleLogging.utils.core import LogManager
from logging import Formatter

logger = LogManager.GetLogger(
log_name='astrbot',
    out_to_console=True,
    custom_formatter=Formatter('[%(asctime)s| %(name)s - %(levelname)s|%(filename)s:%(lineno)d]: %(message)s', datefmt="%H:%M:%S")
)
pytest_plugins = ('pytest_asyncio',)

os.environ['TEST_MODE'] = 'on'
bootstrap = AstrBotBootstrap()
asyncio.run(bootstrap.run())

qq_official = QQOfficial(bootstrap.context, bootstrap.message_handler)
aiocqhttp = AIOCQHTTP(bootstrap.context, bootstrap.message_handler)

class TestBasicMessageHandle():
    @pytest.mark.asyncio
    async def test_qqofficial_group_message(self):
        group_message = MockQQOfficialMessage().create_random_group_message()
        abm = qq_official._parse_from_qqofficial(group_message, MessageType.GROUP_MESSAGE)
        ret = await qq_official.handle_msg(abm)
        print(ret)
        
    @pytest.mark.asyncio
    async def test_qqofficial_guild_message(self):
        guild_message = MockQQOfficialMessage().create_random_guild_message()
        abm = qq_official._parse_from_qqofficial(guild_message, MessageType.GUILD_MESSAGE)
        ret = await qq_official.handle_msg(abm)
        print(ret)

    # 有共同性，为了节约开销，不测试频道私聊。
    # @pytest.mark.asyncio
    # async def test_qqofficial_private_message(self):
    #     private_message = MockQQOfficialMessage().create_random_direct_message()
    #     abm = qq_official._parse_from_qqofficial(private_message, MessageType.FRIEND_MESSAGE)
    #     ret = await qq_official.handle_msg(abm)
    #     print(ret)
    
    @pytest.mark.asyncio
    async def test_aiocqhttp_group_message(self):
        event = MockOneBotMessage().create_random_group_message()
        abm = aiocqhttp.convert_message(event)
        ret = await aiocqhttp.handle_msg(abm)
        print(ret)

    @pytest.mark.asyncio
    async def test_aiocqhttp_direct_message(self):
        event = MockOneBotMessage().create_random_direct_message()
        abm = aiocqhttp.convert_message(event)
        ret = await aiocqhttp.handle_msg(abm)
        print(ret)