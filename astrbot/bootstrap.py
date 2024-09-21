import asyncio
import traceback
import os
from astrbot.message.handler import MessageHandler
from astrbot.persist.helper import dbConn
from dashboard.server import AstrBotDashBoard
from model.command.manager import CommandManager
from model.command.internal_handler import InternalCommandHandler
from model.plugin.manager import PluginManager
from model.platform.manager import PlatformManager
from typing import Union
from type.types import Context
from type.config import VERSION
from SparkleLogging.utils.core import LogManager
from logging import Logger
from util.cmd_config import AstrBotConfig, try_migrate
from util.metrics import MetricUploader
from util.updator.astrbot_updator import AstrBotUpdator

logger: Logger = LogManager.GetLogger(log_name='astrbot')


class AstrBotBootstrap():
    def __init__(self) -> None:
        self.context = Context()
        
        # load configs and ensure the backward compatibility
        try_migrate()
        self.config_helper = AstrBotConfig()
        self.context.config_helper = self.config_helper
        logger.info("AstrBot v" + VERSION)
        # apply proxy settings
        http_proxy = self.context.config_helper.http_proxy
        https_proxy = self.context.config_helper.https_proxy
        if http_proxy:
            os.environ['HTTP_PROXY'] = http_proxy
        if https_proxy:
            os.environ['HTTPS_PROXY'] = https_proxy
        os.environ['NO_PROXY'] = 'https://api.sgroup.qq.com'
        
        if http_proxy and https_proxy:
            logger.info(f"使用代理: {http_proxy}, {https_proxy}")
        else:
            logger.info("未使用代理。")
            
        self.test_mode = os.environ.get('TEST_MODE', 'off') == 'on'
    
    async def run(self):
        self.command_manager = CommandManager()
        self.plugin_manager = PluginManager(self.context)
        self.updator = AstrBotUpdator()
        self.cmd_handler = InternalCommandHandler(self.command_manager, self.plugin_manager)
        self.db_conn_helper = dbConn()
        
        # load llm provider
        self.load_llm()
        
        self.message_handler = MessageHandler(self.context, self.command_manager, self.db_conn_helper)
        self.platfrom_manager = PlatformManager(self.context, self.message_handler)
        self.dashboard = AstrBotDashBoard(self.context, plugin_manager=self.plugin_manager, astrbot_updator=self.updator)
        self.metrics_uploader = MetricUploader(self.context)
        
        self.context.metrics_uploader = self.metrics_uploader
        self.context.updator = self.updator
        self.context.plugin_updator = self.plugin_manager.updator
        self.context.message_handler = self.message_handler
        self.context.command_manager = self.command_manager


        # load dashboard
        self.dashboard.run_http_server()
        dashboard_task = asyncio.create_task(self.dashboard.ws_server(), name="dashboard")
        
        if self.test_mode:
            return
        
        # load plugins, plugins' commands.
        self.load_plugins()
        self.command_manager.register_from_pcb(self.context.plugin_command_bridge)
        
        # load platforms
        platform_tasks = self.load_platform()
        # load metrics uploader
        metrics_upload_task = asyncio.create_task(self.metrics_uploader.upload_metrics(), name="metrics-uploader")
        
        tasks = [metrics_upload_task, dashboard_task, *platform_tasks, *self.context.ext_tasks]
        tasks = [self.handle_task(task) for task in tasks]
        await asyncio.gather(*tasks)

    async def handle_task(self, task: Union[asyncio.Task, asyncio.Future]):
        while True:
            try:
                result = await task
                return result
            except asyncio.CancelledError:
                logger.info(f"{task.get_name()} 任务已取消。")
                return
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error(f"{task.get_name()} 任务发生错误。")
                return
    
    def load_llm(self):
        f = False
        llms = self.context.config_helper.llm
        logger.info(f"加载 {len(llms)} 个 LLM Provider...")
        for llm in llms:
            if llm.enable:
                if llm.name == "openai" and llm.key and llm.enable:
                    self.load_openai(llm)
                    f = True
                    logger.info(f"已启用 OpenAI API 支持。")
                else:
                    logger.warn(f"未知的 LLM Provider: {llm.name}")
        if f:
            from model.command.openai_official_handler import OpenAIOfficialCommandHandler
            self.openai_command_handler = OpenAIOfficialCommandHandler(self.command_manager)
            self.openai_command_handler.set_provider(self.context.llms[0].llm_instance)

    def load_openai(self, llm_config):
        from model.provider.openai_official import ProviderOpenAIOfficial
        inst = ProviderOpenAIOfficial(llm_config)
        self.context.register_provider("internal_openai", inst)
    
    def load_plugins(self):
        self.plugin_manager.plugin_reload()
    
    def load_platform(self):
        platforms = self.platfrom_manager.load_platforms()
        if not platforms:
            logger.warn("未启用任何消息平台。")
        return platforms