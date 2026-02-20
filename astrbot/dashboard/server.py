import asyncio
import logging
import os
import socket
from pathlib import Path
from typing import Protocol, cast

import jwt
import psutil
from flask.json.provider import DefaultJSONProvider
from hypercorn.asyncio import serve
from hypercorn.config import Config as HyperConfig
from quart import Quart, g, jsonify, request
from quart.logging import default_handler

from astrbot.core import logger, t
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
from .routes.lang_route import LangRoute


class _AddrWithPort(Protocol):
    port: int


APP: Quart


def _parse_env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class AstrBotDashboard:
    def __init__(
        self,
        core_lifecycle: AstrBotCoreLifecycle,
        db: BaseDatabase,
        shutdown_event: asyncio.Event,
        webui_dir: str | None = None,
    ) -> None:
        self.core_lifecycle = core_lifecycle
        self.config = core_lifecycle.astrbot_config

        # 参数指定webui目录
        if webui_dir and os.path.exists(webui_dir):
            self.data_path = os.path.abspath(webui_dir)
        else:
            self.data_path = os.path.abspath(
                os.path.join(get_astrbot_data_path(), "dist"),
            )

        self.app = Quart("dashboard", static_folder=self.data_path, static_url_path="/")
        APP = self.app  # noqa
        self.app.config["MAX_CONTENT_LENGTH"] = (
            128 * 1024 * 1024
        )  # 将 Flask 允许的最大上传文件体大小设置为 128 MB
        cast(DefaultJSONProvider, self.app.json).sort_keys = False
        self.app.before_request(self.auth_middleware)
        # token 用于验证请求
        logging.getLogger(self.app.name).removeHandler(default_handler)
        self.context = RouteContext(self.config, self.app)
        self.ur = UpdateRoute(
            self.context,
            core_lifecycle.astrbot_updator,
            core_lifecycle,
        )
        self.sr = StatRoute(self.context, db, core_lifecycle)
        self.pr = PluginRoute(
            self.context,
            core_lifecycle,
            core_lifecycle.plugin_manager,
        )
        self.command_route = CommandRoute(self.context)
        self.cr = ConfigRoute(self.context, core_lifecycle)
        self.lr = LogRoute(self.context, core_lifecycle.log_broker)
        self.sfr = StaticFileRoute(self.context)
        self.ar = AuthRoute(self.context)
        self.chat_route = ChatRoute(self.context, db, core_lifecycle)
        self.chatui_project_route = ChatUIProjectRoute(self.context, db)
        self.tools_root = ToolsRoute(self.context, core_lifecycle)
        self.subagent_route = SubAgentRoute(self.context, core_lifecycle)
        self.skills_route = SkillsRoute(self.context, core_lifecycle)
        self.conversation_route = ConversationRoute(self.context, db, core_lifecycle)
        self.file_route = FileRoute(self.context)
        self.session_management_route = SessionManagementRoute(
            self.context,
            db,
            core_lifecycle,
        )
        self.persona_route = PersonaRoute(self.context, db, core_lifecycle)
        self.cron_route = CronRoute(self.context, core_lifecycle)
        self.t2i_route = T2iRoute(self.context, core_lifecycle)
        self.kb_route = KnowledgeBaseRoute(self.context, core_lifecycle)
        self.platform_route = PlatformRoute(self.context, core_lifecycle)
        self.backup_route = BackupRoute(self.context, db, core_lifecycle)
        self.live_chat_route = LiveChatRoute(self.context, db, core_lifecycle)
        self.lang_route = LangRoute(self.context)

        self.app.add_url_rule(
            "/api/plug/<path:subpath>",
            view_func=self.srv_plug_route,
            methods=["GET", "POST"],
        )

        self.shutdown_event = shutdown_event

        self._init_jwt_secret()

    async def srv_plug_route(self, subpath, *args, **kwargs):
        """插件路由"""
        registered_web_apis = self.core_lifecycle.star_context.registered_web_apis
        for api in registered_web_apis:
            route, view_handler, methods, _ = api
            if route == f"/{subpath}" and request.method in methods:
                return await view_handler(*args, **kwargs)
        return jsonify(Response().error(t("dashboard-server-route-not-found")).__dict__)

    async def auth_middleware(self):
        if not request.path.startswith("/api"):
            return None
        allowed_endpoints = [
            "/api/auth/login",
            "/api/file",
            "/api/platform/webhook",
            "/api/stat/start-time",
            "/api/backup/download",  # 备份下载使用 URL 参数传递 token
        ]
        if any(request.path.startswith(prefix) for prefix in allowed_endpoints):
            return None
        # 声明 JWT
        token = request.headers.get("Authorization")
        if not token:
            r = jsonify(Response().error(t("dashboard-server-unauthorized")).__dict__)
            r.status_code = 401
            return r
        token = token.removeprefix("Bearer ")
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])
            g.username = payload["username"]
        except jwt.ExpiredSignatureError:
            r = jsonify(Response().error(t("dashboard-server-token-expired")).__dict__)
            r.status_code = 401
            return r
        except jwt.InvalidTokenError:
            r = jsonify(Response().error(t("dashboard-server-token-invalid")).__dict__)
            r.status_code = 401
            return r

    def check_port_in_use(self, port: int) -> bool:
        """跨平台检测端口是否被占用"""
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
            logger.warning(t("dashboard-server-port-check-error", port=port, e=e))
            # 如果出现异常，保守起见认为端口可能被占用
            return True

    def get_process_using_port(self, port: int) -> str:
        """获取占用端口的进程详细信息"""
        try:
            for conn in psutil.net_connections(kind="inet"):
                if cast(_AddrWithPort, conn.laddr).port == port:
                    try:
                        process = psutil.Process(conn.pid)
                        # 获取详细信息
                        proc_info = [
                            t("dashboard-server-proc-name", name=process.name()),
                            t("dashboard-server-pid", pid=process.pid),
                            t("dashboard-server-exec-path", exe=process.exe()),
                            t("dashboard-server-work-dir", cwd=process.cwd()),
                            t(
                                "dashboard-server-cmd-line",
                                cmd=" ".join(process.cmdline()),
                            ),
                        ]
                        return "\n           ".join(proc_info)
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        return t("dashboard-server-access-denied", e=e)
            return t("dashboard-server-proc-not-found")
        except Exception as e:
            return t("dashboard-server-get-proc-failed", e=e)

    def _init_jwt_secret(self) -> None:
        if not self.config.get("dashboard", {}).get("jwt_secret", None):
            # 如果没有设置 JWT 密钥，则生成一个新的密钥
            jwt_secret = os.urandom(32).hex()
            self.config["dashboard"]["jwt_secret"] = jwt_secret
            self.config.save_config()
            logger.info("Initialized random JWT secret for dashboard.")
        self._jwt_secret = self.config["dashboard"]["jwt_secret"]

    def run(self):
        ip_addr = []
        dashboard_config = self.core_lifecycle.astrbot_config.get("dashboard", {})
        port = (
            os.environ.get("DASHBOARD_PORT")
            or os.environ.get("ASTRBOT_DASHBOARD_PORT")
            or dashboard_config.get("port", 6185)
        )
        host = (
            os.environ.get("DASHBOARD_HOST")
            or os.environ.get("ASTRBOT_DASHBOARD_HOST")
            or dashboard_config.get("host", "0.0.0.0")
        )
        enable = dashboard_config.get("enable", True)
        ssl_config = dashboard_config.get("ssl", {})
        if not isinstance(ssl_config, dict):
            ssl_config = {}
        ssl_enable = _parse_env_bool(
            os.environ.get("DASHBOARD_SSL_ENABLE")
            or os.environ.get("ASTRBOT_DASHBOARD_SSL_ENABLE"),
            bool(ssl_config.get("enable", False)),
        )
        scheme = "https" if ssl_enable else "http"

        if not enable:
            logger.info(t("dashboard-server-webui-disabled"))
            return None

        logger.info(t("dashboard-server-starting", url=f"{scheme}://{host}:{port}"))
        if host == "0.0.0.0":
            logger.info(t("dashboard-server-security-tip"))

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
                t("dashboard-server-port-in-use", port=port, info=process_info)
            )

            raise Exception(f"端口 {port} 已被占用")

        parts = [t("dashboard-server-started-banner", version=VERSION)]
        parts.append(
            t("dashboard-server-local-url", url=f"{scheme}://localhost:{port}")
        )
        for ip in ip_addr:
            parts.append(
                t("dashboard-server-network-url", url=f"{scheme}://{ip}:{port}")
            )
        parts.append(t("dashboard-server-default-creds"))
        display = "".join(parts)

        if not ip_addr:
            display += t("dashboard-server-remote-access-tip")

        logger.info(display)

        # 配置 Hypercorn
        config = HyperConfig()
        config.bind = [f"{host}:{port}"]
        if ssl_enable:
            cert_file = (
                os.environ.get("DASHBOARD_SSL_CERT")
                or os.environ.get("ASTRBOT_DASHBOARD_SSL_CERT")
                or ssl_config.get("cert_file", "")
            )
            key_file = (
                os.environ.get("DASHBOARD_SSL_KEY")
                or os.environ.get("ASTRBOT_DASHBOARD_SSL_KEY")
                or ssl_config.get("key_file", "")
            )
            ca_certs = (
                os.environ.get("DASHBOARD_SSL_CA_CERTS")
                or os.environ.get("ASTRBOT_DASHBOARD_SSL_CA_CERTS")
                or ssl_config.get("ca_certs", "")
            )

            cert_path = Path(cert_file).expanduser()
            key_path = Path(key_file).expanduser()
            if not cert_file or not key_file:
                raise ValueError(t("dashboard-server-ssl-config-required"))
            if not cert_path.is_file():
                raise ValueError(
                    t("dashboard-server-ssl-cert-not-found", path=cert_path)
                )
            if not key_path.is_file():
                raise ValueError(t("dashboard-server-ssl-key-not-found", path=key_path))

            config.certfile = str(cert_path.resolve())
            config.keyfile = str(key_path.resolve())

            if ca_certs:
                ca_path = Path(ca_certs).expanduser()
                if not ca_path.is_file():
                    raise ValueError(
                        t("dashboard-server-ssl-ca-not-found", path=ca_path)
                    )
                config.ca_certs = str(ca_path.resolve())

        # 根据配置决定是否禁用访问日志
        disable_access_log = dashboard_config.get("disable_access_log", True)
        if disable_access_log:
            config.accesslog = None
        else:
            # 启用访问日志，使用简洁格式
            config.accesslog = "-"
            config.access_log_format = "%(h)s %(r)s %(s)s %(b)s %(D)s"

        return serve(self.app, config, shutdown_trigger=self.shutdown_trigger)

    async def shutdown_trigger(self) -> None:
        await self.shutdown_event.wait()
        logger.info(t("dashboard-server-shutdown"))
