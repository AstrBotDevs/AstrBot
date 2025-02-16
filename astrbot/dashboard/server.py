import logging
import jwt
import asyncio
import os
from astrbot.core.config.default import VERSION
from quart import Quart, request, jsonify, g
from quart.logging import default_handler
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from .routes import *
from .routes.route import RouteContext, Response
from astrbot.core import logger, WEBUI_SK
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.io import get_local_ip_addresses

DATAPATH = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../data"))

class AstrBotDashboard():
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle, db: BaseDatabase) -> None:
        self.core_lifecycle = core_lifecycle
        self.config = core_lifecycle.astrbot_config
        self.data_path = os.path.abspath(os.path.join(DATAPATH, "dist"))
        self.app = Quart("dashboard", static_folder=self.data_path, static_url_path="/")
        self.app.json.sort_keys = False
        self.app.before_request(self.auth_middleware)
        # token 用于验证请求
        logging.getLogger(self.app.name).removeHandler(default_handler)
        self.context = RouteContext(self.config, self.app)
        self.ur = UpdateRoute(self.context, core_lifecycle.astrbot_updator, core_lifecycle)
        self.sr = StatRoute(self.context, db, core_lifecycle)
        self.pr = PluginRoute(self.context, core_lifecycle, core_lifecycle.plugin_manager)
        self.cr = ConfigRoute(self.context, core_lifecycle)
        self.lr = LogRoute(self.context, core_lifecycle.log_broker)
        self.sfr = StaticFileRoute(self.context)
        self.ar = AuthRoute(self.context)
        self.chat_route = ChatRoute(self.context, db, core_lifecycle)
        
    async def auth_middleware(self):
        if not request.path.startswith("/api"):
            return
        if request.path == "/api/auth/login":
            return
        if request.path == "/api/chat/get_file":
            return
        # claim jwt
        token = request.headers.get("Authorization")
        if not token:
            r = jsonify(Response().error("未授权").__dict__)
            r.status_code = 401
            return r
        if token.startswith("Bearer "):
            token = token[7:]
        try:
            payload = jwt.decode(token, WEBUI_SK, algorithms=["HS256"])
            g.username = payload["username"]
        except jwt.ExpiredSignatureError:
            r = jsonify(Response().error("Token 过期").__dict__)
            r.status_code = 401
            return r
        except jwt.InvalidTokenError:
            r = jsonify(Response().error("Token 无效").__dict__)
            r.status_code = 401
            return r
        
        
    async def shutdown_trigger_placeholder(self):
        while not self.core_lifecycle.event_queue.closed:
            await asyncio.sleep(1)
        logger.info("管理面板已关闭。")
        
    def run(self):
        try:
            ip_addr = get_local_ip_addresses()
        except Exception as e:
            ip_addr = []
            
        port = self.core_lifecycle.astrbot_config['dashboard'].get("port", 6185)
        if isinstance(port, str):
            port = int(port)
    
        display = f"\n ✨✨✨\n  AstrBot v{VERSION} 管理面板已启动，可访问\n\n"
        display += f"   ➜  本地: http://localhost:{port}\n"
        for ip in ip_addr:
            display += f"   ➜  网络: http://{ip}:{port}\n"
        display += "   ➜  默认用户名和密码: astrbot\n ✨✨✨\n"
        logger.info(display)
        

        return self.app.run_task(host="0.0.0.0", port=port, shutdown_trigger=self.shutdown_trigger_placeholder)