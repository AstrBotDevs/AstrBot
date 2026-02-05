import asyncio
import ipaddress
import logging
import os
import platform
import socket
from collections.abc import Callable
from ipaddress import IPv4Address, IPv6Address
from typing import cast

import jwt
import psutil
from flask.json.provider import DefaultJSONProvider
from hypercorn.asyncio import serve
from hypercorn.config import Config as HyperConfig
from quart import Quart, g, jsonify, request
from quart.logging import default_handler

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.io import get_local_ip_addresses

from .routes import *
from .routes.backup import BackupRoute
from .routes.live_chat import LiveChatRoute
from .routes.platform import PlatformRoute
from .routes.route import Response, RouteContext
from .routes.session_management import SessionManagementRoute
from .routes.subagent import SubAgentRoute
from .routes.t2i import T2iRoute


class AstrBotDashboard:
    """AstrBot Web Dashboard"""

    ALLOWED_ENDPOINT_PREFIXES = (
        "/api/auth/login",
        "/api/file",
        "/api/platform/webhook",
        "/api/stat/start-time",
        "/api/backup/download",
    )

    def __init__(
        self,
        core_lifecycle: AstrBotCoreLifecycle,
        db: BaseDatabase,
        shutdown_event: asyncio.Event,
        webui_dir: str | None = None,
    ) -> None:
        self.core_lifecycle = core_lifecycle
        self.config = core_lifecycle.astrbot_config
        self.shutdown_event = shutdown_event

        self._init_paths(webui_dir)
        self._init_app()
        self.context = RouteContext(self.config, self.app)

        self._init_routes(db)
        self._init_plugin_route_index()
        self._init_jwt_secret()

    # ------------------------------------------------------------------
    # 初始化阶段
    # ------------------------------------------------------------------

    def _init_paths(self, webui_dir: str | None):
        if webui_dir and os.path.exists(webui_dir):
            self.data_path = os.path.abspath(webui_dir)
        else:
            self.data_path = os.path.abspath(
                os.path.join(get_astrbot_data_path(), "dist")
            )

    def _init_app(self):
        self.app = Quart(
            "dashboard",
            static_folder=self.data_path,
            static_url_path="/",
        )
        self.app.config["MAX_CONTENT_LENGTH"] = 128 * 1024 * 1024
        cast(DefaultJSONProvider, self.app.json).sort_keys = False

        self.app.before_request(self.auth_middleware)
        logging.getLogger(self.app.name).removeHandler(default_handler)

    def _init_routes(self, db: BaseDatabase):
        UpdateRoute(
            self.context, self.core_lifecycle.astrbot_updator, self.core_lifecycle
        )
        StatRoute(self.context, db, self.core_lifecycle)
        PluginRoute(
            self.context, self.core_lifecycle, self.core_lifecycle.plugin_manager
        )
        CommandRoute(self.context)
        ConfigRoute(self.context, self.core_lifecycle)
        LogRoute(self.context, self.core_lifecycle.log_broker)
        StaticFileRoute(self.context)
        AuthRoute(self.context)
        ChatRoute(self.context, db, self.core_lifecycle)
        ChatUIProjectRoute(self.context, db)
        ToolsRoute(self.context, self.core_lifecycle)
        SubAgentRoute(self.context, self.core_lifecycle)
        SkillsRoute(self.context, self.core_lifecycle)
        ConversationRoute(self.context, db, self.core_lifecycle)
        FileRoute(self.context)
        SessionManagementRoute(self.context, db, self.core_lifecycle)
        PersonaRoute(self.context, db, self.core_lifecycle)
        CronRoute(self.context, self.core_lifecycle)
        T2iRoute(self.context, self.core_lifecycle)
        KnowledgeBaseRoute(self.context, self.core_lifecycle)
        PlatformRoute(self.context, self.core_lifecycle)
        BackupRoute(self.context, db, self.core_lifecycle)
        LiveChatRoute(self.context, db, self.core_lifecycle)

        self.app.add_url_rule(
            "/api/plug/<path:subpath>",
            view_func=self.srv_plug_route,
            methods=["GET", "POST"],
        )

    def _init_plugin_route_index(self):
        """将插件路由索引，避免 O(n) 查找"""
        self._plugin_route_map: dict[tuple[str, str], Callable] = {}

        for (
            route,
            handler,
            methods,
            _,
        ) in self.core_lifecycle.star_context.registered_web_apis:
            for method in methods:
                self._plugin_route_map[(route, method)] = handler

    def _init_jwt_secret(self):
        dashboard_cfg = self.config.setdefault("dashboard", {})
        if not dashboard_cfg.get("jwt_secret"):
            dashboard_cfg["jwt_secret"] = os.urandom(32).hex()
            self.config.save_config()
            logger.info("Initialized random JWT secret for dashboard.")
        self._jwt_secret = dashboard_cfg["jwt_secret"]

    # ------------------------------------------------------------------
    # Middleware中间件
    # ------------------------------------------------------------------

    async def auth_middleware(self):
        if not request.path.startswith("/api"):
            return None

        if any(request.path.startswith(p) for p in self.ALLOWED_ENDPOINT_PREFIXES):
            return None

        token = request.headers.get("Authorization")
        if not token:
            return self._unauthorized("未授权")

        try:
            payload = jwt.decode(
                token.removeprefix("Bearer "),
                self._jwt_secret,
                algorithms=["HS256"],
                options={"require": ["username"]},
            )
            g.username = payload["username"]
        except jwt.ExpiredSignatureError:
            return self._unauthorized("Token 过期")
        except jwt.PyJWTError:
            return self._unauthorized("Token 无效")

    @staticmethod
    def _unauthorized(msg: str):
        r = jsonify(Response().error(msg).to_json())
        r.status_code = 401
        return r

    # ------------------------------------------------------------------
    # 插件路由
    # ------------------------------------------------------------------

    async def srv_plug_route(self, subpath: str, *args, **kwargs):
        handler = self._plugin_route_map.get((f"/{subpath}", request.method))
        if not handler:
            return jsonify(Response().error("未找到该路由").to_json())

        try:
            return await handler(*args, **kwargs)
        except Exception:
            logger.exception("插件 Web API 执行异常")
            return jsonify(Response().error("插件执行失败").to_json())

    # ------------------------------------------------------------------
    # 网络 / 端口
    # ------------------------------------------------------------------

    def check_port_in_use(self, host: str, port: int) -> bool:
        try:
            family = socket.AF_INET6 if ":" in host else socket.AF_INET
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(2)
                return sock.connect_ex((host, port)) == 0
        except Exception:
            return True

    @staticmethod
    def get_process_using_port(port: int) -> str:
        try:
            for conn in psutil.net_connections(kind="all"):
                if conn.laddr and conn.laddr.port == port and conn.pid:
                    p = psutil.Process(conn.pid)
                    return "\n           ".join(
                        [
                            f"进程名: {p.name()}",
                            f"PID: {p.pid}",
                            f"执行路径: {p.exe()}",
                            f"工作目录: {p.cwd()}",
                            f"启动命令: {' '.join(p.cmdline())}",
                        ]
                    )
            return "未找到占用进程"
        except Exception as e:
            return f"获取进程信息失败: {e!s}"

    # ------------------------------------------------------------------
    # 启动
    # ------------------------------------------------------------------

    def run(self) -> None:
        cfg = self.config.get("dashboard", {})
        _port: str = os.environ.get("DASHBOARD_PORT") or cfg.get("port", 6185)
        port: int = int(_port)
        _host = os.environ.get("DASHBOARD_HOST") or cfg.get("host", "::")
        host: str = _host.strip("[]")
        _env = os.environ.get("DASHBOARD_ENABLE")
        enable = (
            _env.lower() in ("true", "1", "yes")
            if _env is not None
            else cfg.get("enable", True)
        )

        if not enable:
            logger.info("WebUI 已被禁用")
            return None

        display_host = f"[{host}]" if ":" in host else host
        logger.info(
            "正在启动 WebUI, 监听地址: http://%s:%s",
            display_host,
            port,
        )

        if self.check_port_in_use("127.0.0.1", port):
            info = self.get_process_using_port(port)
            raise RuntimeError(f"端口 {port} 已被占用\n{info}")

        self._print_access_urls(host, port)

        config = HyperConfig()
        binds: list[str] = [self._build_bind(host, port)]
        # 参考：https://github.com/pgjones/hypercorn/issues/85
        if host == "::" and platform.system() in ("Windows", "Darwin"):
            binds.append(self._build_bind("0.0.0.0", port))
        config.bind = binds

        if cfg.get("disable_access_log", True):
            config.accesslog = None
        else:
            config.accesslog = "-"
            config.access_log_format = "%(h)s %(r)s %(s)s %(b)s %(D)s"

        return serve(self.app, config, shutdown_trigger=self.shutdown_trigger)

    @staticmethod
    def _build_bind(host: str, port: int) -> str:
        try:
            ip: IPv4Address | IPv6Address = ipaddress.ip_address(host)
            return f"[{ip}]:{port}" if ip.version == 6 else f"{ip}:{port}"
        except ValueError:
            return f"{host}:{port}"

    def _print_access_urls(self, host: str, port: int) -> None:
        local_ips: list[IPv4Address | IPv6Address] = get_local_ip_addresses()

        parts = [f"\n ✨✨✨\n  AstrBot v{VERSION} WebUI 已启动\n\n"]

        parts.append(f"   ➜  本地: http://localhost:{port}\n")

        if host in ("::", "0.0.0.0"):
            for ip in local_ips:
                if ip.is_loopback:
                    continue

                # 再次过滤掉 fe80（第一次过滤在get_local_ip_addresses）
                if ip.is_link_local:
                    continue
                if ip.version == 6:
                    display_url = f"http://[{ip}]:{port}"
                else:
                    display_url = f"http://{ip}:{port}"

                parts.append(f"   ➜  网络: {display_url}\n")

        parts.append("   ➜  默认用户名和密码: astrbot\n ✨✨✨\n")
        logger.info("".join(parts))

    async def shutdown_trigger(self) -> None:
        await self.shutdown_event.wait()
        logger.info("AstrBot WebUI 已经被优雅地关闭")
