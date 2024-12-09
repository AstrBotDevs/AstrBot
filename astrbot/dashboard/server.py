import logging, jwt
import asyncio, os
from quart import Quart, request
from quart.logging import default_handler
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from .routes import *
from .routes.route import RouteContext, Response
from astrbot.core import logger, WEBUI_SK
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.io import get_local_ip_addresses
from astrbot.core.db import BaseDatabase

DATAPATH = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../data"))

class AstrBotDashboard():
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle, db: BaseDatabase) -> None:
        self.core_lifecycle = core_lifecycle
        self.config = core_lifecycle.astrbot_config
        self.data_path = os.path.abspath(os.path.join(DATAPATH, "dist"))
        logger.info(f"Dashboard data path: {self.data_path}")
        self.app = Quart("dashboard", static_folder=self.data_path, static_url_path="/")
        self.app.json.sort_keys = False
        self.app.before_request(self.auth_middleware)
        # token 用于验证请求
        logging.getLogger(self.app.name).removeHandler(default_handler)
        self.context = RouteContext(self.config, self.app)
        self.ur = UpdateRoute(self.context, core_lifecycle.astrbot_updator)
        self.sr = StatRoute(self.context, db, core_lifecycle)
        self.pr = PluginRoute(self.context, core_lifecycle, core_lifecycle.plugin_manager)
        self.cr = ConfigRoute(self.context, core_lifecycle)
        self.lr = LogRoute(self.context, core_lifecycle.log_broker)
        self.sfr = StaticFileRoute(self.context)
        self.ar = AuthRoute(self.context)
        
    async def auth_middleware(self):
        if not request.path.startswith("/api"):
            return
        if request.path == "/api/auth/login":
            return
        # claim jwt
        token = request.headers.get("Authorization")
        if not token:
            return Response().error("未授权").__dict__
        if token.startswith("Bearer "):
            token = token[7:]
        try:
            jwt.decode(token, WEBUI_SK, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return Response().error("Token 过期").__dict__
        except jwt.InvalidTokenError:
            return Response().error("Token 无效").__dict__
        
        
    async def shutdown_trigger_placeholder(self):
        while not self.core_lifecycle.event_queue.closed:
            await asyncio.sleep(1)
        logger.info("管理面板已关闭。")
        
    def run(self):
        ip_addr = get_local_ip_addresses()
        logger.info(f"""🌈 管理面板已启动，可访问
1. http://{ip_addr}:6185
2. http://localhost:6185
登录。默认用户名和密码是 astrbot。""")
        return self.app.run_task(host="0.0.0.0", port=6185, shutdown_trigger=self.shutdown_trigger_placeholder)