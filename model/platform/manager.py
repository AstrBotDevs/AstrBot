import asyncio

from util.io import port_checker
from type.register import RegisteredPlatform
from type.types import Context
from SparkleLogging.utils.core import LogManager
from logging import Logger
from astrbot.message.handler import MessageHandler
from util.cmd_config import (
    PlatformConfig, 
    AiocqhttpPlatformConfig, 
    NakuruPlatformConfig, 
    QQOfficialPlatformConfig
)

logger: Logger = LogManager.GetLogger(log_name='astrbot')


class PlatformManager():
    def __init__(self, context: Context, message_handler: MessageHandler) -> None:
        self.context = context
        self.msg_handler = message_handler
        
    def load_platforms(self):
        tasks = []
        
        platforms = self.context.config_helper.platform
        logger.info(f"加载 {len(platforms)} 个机器人消息平台...")
        for platform in platforms:
            if not platform.enable:
                continue
            if platform.name == "qq_official":
                assert isinstance(platform, QQOfficialPlatformConfig), "qq_official: 无法识别的配置类型。"
                logger.info(f"加载 QQ官方 机器人消息平台 (appid: {platform.appid})")
                tasks.append(asyncio.create_task(self.qqofficial_bot(platform), name="qqofficial-adapter"))
            elif platform.name == "nakuru":
                assert isinstance(platform, NakuruPlatformConfig), "nakuru: 无法识别的配置类型。"
                logger.info(f"加载 QQ(nakuru) 机器人消息平台 ({platform.host}, {platform.websocket_port}, {platform.port})")
                tasks.append(asyncio.create_task(self.nakuru_bot(platform), name="nakuru-adapter"))
            elif platform.name == "aiocqhttp":
                assert isinstance(platform, AiocqhttpPlatformConfig), "aiocqhttp: 无法识别的配置类型。"
                logger.info("加载 QQ(aiocqhttp) 机器人消息平台")
                tasks.append(asyncio.create_task(self.aiocq_bot(platform), name="aiocqhttp-adapter"))

        return tasks

    async def nakuru_bot(self, config: NakuruPlatformConfig):
        '''
        运行 QQ(nakuru 适配器) 
        '''
        from model.platform.qq_nakuru import QQNakuru
        noticed = False
        host = config.host
        port = config.websocket_port
        http_port = config.port
        logger.info(
            f"正在检查连接...host: {host}, ws port: {port}, http port: {http_port}")
        while True:
            if not port_checker(port=port, host=host) or not port_checker(port=http_port, host=host):
                if not noticed:
                    noticed = True
                    logger.warning(
                        f"连接到{host}:{port}（或{http_port}）失败。程序会每隔 5s 自动重试。")
                await asyncio.sleep(5)
            else:
                logger.info("nakuru 适配器已连接。")
                break
        try:
            qq_gocq = QQNakuru(self.context, self.msg_handler, config)
            self.context.platforms.append(RegisteredPlatform(
                platform_name="nakuru", platform_instance=qq_gocq, origin="internal"))
            await qq_gocq.run()
        except BaseException as e:
            logger.error("启动 nakuru 适配器时出现错误: " + str(e))

    def aiocq_bot(self, config):
        '''
        运行 QQ(aiocqhttp 适配器)
        '''
        from model.platform.qq_aiocqhttp import AIOCQHTTP
        qq_aiocqhttp = AIOCQHTTP(self.context, self.msg_handler, config)
        self.context.platforms.append(RegisteredPlatform(
            platform_name="aiocqhttp", platform_instance=qq_aiocqhttp, origin="internal"))
        return qq_aiocqhttp.run_aiocqhttp()

    def qqofficial_bot(self, config):
        '''
        运行 QQ 官方机器人适配器
        '''
        try:
            from model.platform.qq_official import QQOfficial
            qqchannel_bot = QQOfficial(self.context, self.msg_handler, config)
            self.context.platforms.append(RegisteredPlatform(
                platform_name="qqofficial", platform_instance=qqchannel_bot, origin="internal"))
            return qqchannel_bot.run()
        except BaseException as e:
            logger.error("启动 QQ官方机器人适配器时出现错误: " + str(e))
