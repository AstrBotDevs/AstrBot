import asyncio

from util.io import port_checker
from type.register import RegisteredPlatform
from type.types import Context
from SparkleLogging.utils.core import LogManager
from logging import Logger
from astrbot.message.handler import MessageHandler

logger: Logger = LogManager.GetLogger(log_name='astrbot')


class PlatformManager():
    def __init__(self, context: Context, message_handler: MessageHandler) -> None:
        self.context = context
        self.config = context.base_config
        self.msg_handler = message_handler
        
    def load_platforms(self):
        tasks = []
        
        if 'gocqbot' in self.config and self.config['gocqbot']['enable']:
            logger.info("启用 QQ(nakuru 适配器)")
            tasks.append(asyncio.create_task(self.gocq_bot()))
        
        if 'aiocqhttp' in self.config and self.config['aiocqhttp']['enable']:
            logger.info("启用 QQ(aiocqhttp 适配器)")
            tasks.append(asyncio.create_task(self.aiocq_bot()))

        # QQ频道
        if 'qqbot' in self.config and self.config['qqbot']['enable'] and self.config['qqbot']['appid'] != None:
            logger.info("启用 QQ(官方 API) 机器人消息平台")
            tasks.append(asyncio.create_task(self.qqchan_bot()))
            
        return tasks

    async def gocq_bot(self):
        '''
        运行 QQ(nakuru 适配器) 
        '''
        from model.platform.qq_nakuru import QQGOCQ
        noticed = False
        host = self.config.get("gocq_host", "127.0.0.1")
        port = self.config.get("gocq_websocket_port", 6700)
        http_port = self.config.get("gocq_http_port", 5700)
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
            qq_gocq = QQGOCQ(self.context, self.msg_handler)
            self.context.platforms.append(RegisteredPlatform(
                platform_name="gocq", platform_instance=qq_gocq, origin="internal"))
            await qq_gocq.run()
        except BaseException as e:
            logger.error("启动 nakuru 适配器时出现错误: " + str(e))

    def aiocq_bot(self):
        '''
        运行 QQ(aiocqhttp 适配器)
        '''
        from model.platform.qq_aiocqhttp import AIOCQHTTP
        qq_aiocqhttp = AIOCQHTTP(self.context, self.msg_handler)
        self.context.platforms.append(RegisteredPlatform(
            platform_name="aiocqhttp", platform_instance=qq_aiocqhttp, origin="internal"))
        return qq_aiocqhttp.run_aiocqhttp()

    def qqchan_bot(self):
        '''
        运行 QQ 官方机器人适配器
        '''
        try:
            from model.platform.qq_official import QQOfficial
            qqchannel_bot = QQOfficial(self.context, self.msg_handler)
            self.context.platforms.append(RegisteredPlatform(
                platform_name="qqchan", platform_instance=qqchannel_bot, origin="internal"))
            return qqchannel_bot.run()
        except BaseException as e:
            logger.error("启动 QQ官方机器人适配器时出现错误: " + str(e))
