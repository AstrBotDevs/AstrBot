import logging
import jwt
import asyncio
import os
import socket
import psutil
from astrbot.core.config.default import VERSION
from quart import Quart, request, jsonify, g
from quart.logging import default_handler
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from .routes import *
from .routes.route import RouteContext, Response
from .routes.session_management import SessionManagementRoute
from astrbot.core import logger, WEBUI_SK
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.io import get_local_ip_addresses
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

APP: Quart = None


class AstrBotDashboard:
    def __init__(
        self,
        core_lifecycle: AstrBotCoreLifecycle,
        db: BaseDatabase,
        shutdown_event: asyncio.Event,
    ) -> None:
        self.core_lifecycle = core_lifecycle
        self.config = core_lifecycle.astrbot_config
        self.data_path = os.path.abspath(os.path.join(get_astrbot_data_path(), "dist"))
        self.app = Quart("dashboard", static_folder=self.data_path, static_url_path="/")
        APP = self.app  # noqa
        self.app.config["MAX_CONTENT_LENGTH"] = (
            128 * 1024 * 1024
        )  # 将 Flask 允许的最大上传文件体大小设置为 128 MB
        self.app.json.sort_keys = False
        self.app.before_request(self.auth_middleware)
        # token 用于验证请求        logging.getLogger(self.app.name).removeHandler(default_handler)
        self.context = RouteContext(self.config, self.app)
        self.ur = UpdateRoute(
            self.context, core_lifecycle.astrbot_updator, core_lifecycle
        )
        self.sr = StatRoute(self.context, db, core_lifecycle)
        self.pr = PluginRoute(
            self.context, core_lifecycle, core_lifecycle.plugin_manager
        )
        self.cr = ConfigRoute(self.context, core_lifecycle)
        self.lr = LogRoute(self.context, core_lifecycle.log_broker)
        self.sfr = StaticFileRoute(self.context)
        self.ar = AuthRoute(self.context)
        self.chat_route = ChatRoute(self.context, db, core_lifecycle)
        self.tools_root = ToolsRoute(self.context, core_lifecycle)
        self.conversation_route = ConversationRoute(self.context, db, core_lifecycle)
        self.file_route = FileRoute(self.context)
        self.session_management_route = SessionManagementRoute(self.context, db, core_lifecycle)

        self.app.add_url_rule(
            "/api/plug/<path:subpath>",
            view_func=self.srv_plug_route,
            methods=["GET", "POST"],
        )

        self.shutdown_event = shutdown_event

    async def srv_plug_route(self, subpath, *args, **kwargs):
        """
        插件路由
        """
        registered_web_apis = self.core_lifecycle.star_context.registered_web_apis
        for api in registered_web_apis:
            route, view_handler, methods, _ = api
            if route == f"/{subpath}" and request.method in methods:
                return await view_handler(*args, **kwargs)
        return jsonify(Response().error("未找到该路由").__dict__)

    async def auth_middleware(self):
        if not request.path.startswith("/api"):
            return
        allowed_endpoints = ["/api/auth/login", "/api/file"]
        if any(request.path.startswith(prefix) for prefix in allowed_endpoints):
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

    def check_port_in_use(self, port: int) -> bool:
        """
        跨平台检测端口是否被占用
        """
        try:
            # 创建 IPv4 TCP Socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # 设置超时时间
            sock.settimeout(2)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            # result 为 0 表示端口被占用
            return result == 0
        except Exception as e:
            logger.warning(f"检查端口 {port} 时发生错误: {str(e)}")
            # 如果出现异常，保守起见认为端口可能被占用
            return True

    def get_process_using_port(self, port: int) -> str:
        """获取占用端口的进程详细信息"""
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr.port == port:
                    try:
                        process = psutil.Process(conn.pid)
                        # 获取详细信息
                        proc_info = [
                            f"进程名: {process.name()}",
                            f"PID: {process.pid}",
                            f"执行路径: {process.exe()}",
                            f"工作目录: {process.cwd()}",
                            f"启动命令: {' '.join(process.cmdline())}",
                        ]
                        return "\n           ".join(proc_info)
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        return f"无法获取进程详细信息(可能需要管理员权限): {str(e)}"
            return "未找到占用进程"
        except Exception as e:
            return f"获取进程信息失败: {str(e)}"

    def run(self):
        ip_addr = []
        if p := os.environ.get("DASHBOARD_PORT"):
            port = p
        else:
            port = self.core_lifecycle.astrbot_config["dashboard"].get("port", 6185)
        host = self.core_lifecycle.astrbot_config["dashboard"].get("host", "0.0.0.0")

        logger.info(f"正在启动 WebUI, 监听地址: http://{host}:{port}")

        if host == "0.0.0.0":
            logger.info(
                "提示: WebUI 将监听所有网络接口，请注意安全。（可在 data/cmd_config.json 中配置 dashboard.host 以修改 host）"
            )

        if host not in ["localhost", "127.0.0.1"]:
            try:
                ip_addr = get_local_ip_addresses()
            except Exception as _:
                pass
        if isinstance(port, str):
            port = int(port)

        if self.check_port_in_use(port):
            process_info = self.get_process_using_port(port)
            logger.error(
                f"错误：端口 {port} 已被占用\n"
                f"占用信息: \n           {process_info}\n"
                f"请确保：\n"
                f"1. 没有其他 AstrBot 实例正在运行\n"
                f"2. 端口 {port} 没有被其他程序占用\n"
                f"3. 如需使用其他端口，请修改配置文件"
            )

            raise Exception(f"端口 {port} 已被占用")

        display = f"\n ✨✨✨\n  AstrBot v{VERSION} WebUI 已启动，可访问\n\n"
        display += f"   ➜  本地: http://localhost:{port}\n"
        for ip in ip_addr:
            display += f"   ➜  网络: http://{ip}:{port}\n"
        display += "   ➜  默认用户名和密码: astrbot\n ✨✨✨\n"

        if not ip_addr:
            display += (
                "可在 data/cmd_config.json 中配置 dashboard.host 以便远程访问。\n"
            )

        logger.info(display)

        return self.app.run_task(
            host=host, port=port, shutdown_trigger=self.shutdown_trigger
        )

    async def shutdown_trigger(self):
        await self.shutdown_event.wait()
        logger.info("AstrBot WebUI 已经被优雅地关闭")
