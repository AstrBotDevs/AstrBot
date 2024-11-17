import logging
import asyncio
from quart import Quart
from quart.logging import default_handler
from type.types import Context
from .routes import *
from . import logger
from astrbot.db import BaseDatabase
from model.plugin.manager import PluginManager
from util.updator.astrbot_updator import AstrBotUpdator
from util.io import get_local_ip_addresses

class AstrBotDashboard():
    def __init__(self, context: Context, 
                 plugin_manager: PluginManager, 
                 astrbot_updator: AstrBotUpdator, 
                 db_helper: BaseDatabase) -> None:
        self.context = context
        self.app = Quart("dashboard", static_folder="dist", static_url_path="/")
        self.app.json.sort_keys = False
        
        logging.getLogger(self.app.name).removeHandler(default_handler)
        
        self.ar = AuthRoute(context, self.app)
        self.ur = UpdateRoute(context, self.app, astrbot_updator)
        self.sr = StatRoute(context, self.app, db_helper)
        self.pr = PluginRoute(context, self.app, astrbot_updator, plugin_manager)
        self.cr = ConfigRoute(context, self.app, astrbot_updator)
        self.lr = LogRoute(context, self.app)
        self.sfr = StaticFileRoute(context, self.app)
    
    async def shutdown_trigger_placeholder(self):
        while self.context.running:
            await asyncio.sleep(1)
        
    def run(self):
        ip_addr = get_local_ip_addresses()
        logger.info(f"管理面板已启动，可访问 http://{ip_addr}:6185 登录。")
        return self.app.run_task(host="0.0.0.0", port=6185, shutdown_trigger=self.shutdown_trigger_placeholder)