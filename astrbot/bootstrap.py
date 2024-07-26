import asyncio
import traceback
from astrbot.message.handler import MessageHandler
from astrbot.persist.helper import dbConn
from dashboard.server import AstrBotDashBoard
from model.provider.provider import Provider
from model.command.manager import CommandManager
from model.command.internal_handler import InternalCommandHandler
from model.plugin.manager import PluginManager
from model.platform.manager import PlatformManager
from typing import Dict, List, Union
from type.types import Context
from SparkleLogging.utils.core import LogManager
from logging import Logger
from util.cmd_config import CmdConfig
from util.metrics import MetricUploader
from util.config_utils import *
from util.updator.astrbot_updator import AstrBotUpdator

logger: Logger = LogManager.GetLogger(log_name='astrbot')


class AstrBotBootstrap():
    def __init__(self) -> None:        
        self.context = Context()
        self.config_helper: CmdConfig = CmdConfig()
        
        # load configs and ensure the backward compatibility
        init_configs()
        try_migrate_config()
        self.configs = inject_to_context(self.context)
        logger.info("AstrBot v" + self.context.version)
        self.context.config_helper = self.config_helper
        
        # apply proxy settings
        http_proxy = self.context.base_config.get("http_proxy")
        https_proxy = self.context.base_config.get("https_proxy")
        if http_proxy:
            os.environ['HTTP_PROXY'] = http_proxy
        if https_proxy:
            os.environ['HTTPS_PROXY'] = https_proxy
        os.environ['NO_PROXY'] = 'https://api.sgroup.qq.com'
        
        if http_proxy and https_proxy:
            logger.info(f"使用代理: {http_proxy}, {https_proxy}")
        else:
            logger.info("未使用代理。")
    
    async def run(self):
        self.command_manager = CommandManager()
        self.plugin_manager = PluginManager(self.context)
        self.updator = AstrBotUpdator()
        self.cmd_handler = InternalCommandHandler(self.command_manager, self.plugin_manager)
        self.db_conn_helper = dbConn()
        
        # load llm provider
        self.llm_instance: Provider = None
        self.load_llm()
        
        self.message_handler = MessageHandler(self.context, self.command_manager, self.db_conn_helper, self.llm_instance)
        self.platfrom_manager = PlatformManager(self.context, self.message_handler)
        self.dashboard = AstrBotDashBoard(self.context, plugin_manager=self.plugin_manager, astrbot_updator=self.updator)
        self.metrics_uploader = MetricUploader(self.context)
        
        self.context.metrics_uploader = self.metrics_uploader
        self.context.updator = self.updator
        self.context.plugin_updator = self.plugin_manager.updator
        self.context.message_handler = self.message_handler
        
        # load plugins, plugins' commands.
        self.load_plugins()
        self.command_manager.register_from_pcb(self.context.plugin_command_bridge)
        
        # load platforms
        platform_tasks = self.load_platform()
        # load metrics uploader
        metrics_upload_task = asyncio.create_task(self.metrics_uploader.upload_metrics(), name="metrics-uploader")
        # load dashboard
        self.dashboard.run_http_server()
        dashboard_task = asyncio.create_task(self.dashboard.ws_server(), name="dashboard")
        tasks = [metrics_upload_task, dashboard_task, *platform_tasks, *self.context.ext_tasks]
        tasks = [self.handle_task(task) for task in tasks]
        await asyncio.gather(*tasks)

    async def handle_task(self, task: Union[asyncio.Task, asyncio.Future]):
        while True:
            try:
                result = await task
                return result
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error(f"{task.get_name()} 任务发生错误，将在 5 秒后重试。")
                await asyncio.sleep(5)
    
    def load_llm(self):
        if 'openai' in self.configs and \
            len(self.configs['openai']['key']) and \
            self.configs['openai']['key'][0] is not None:
            from model.provider.openai_official import ProviderOpenAIOfficial
            from model.command.openai_official_handler import OpenAIOfficialCommandHandler
            self.openai_command_handler = OpenAIOfficialCommandHandler(self.command_manager)
            self.llm_instance = ProviderOpenAIOfficial(self.context)
            self.openai_command_handler.set_provider(self.llm_instance)
            logger.info("已启用 OpenAI API 支持。")
    
    def load_plugins(self):
        self.plugin_manager.plugin_reload()
    
    def load_platform(self):
        return self.platfrom_manager.load_platforms()