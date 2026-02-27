import asyncio
import hashlib
import logging
import os
import platform
import socket
from collections.abc import Callable
from ipaddress import IPv4Address, IPv6Address, ip_address
from pathlib import Path
from typing import Protocol

import jwt
import psutil
from flask.json.provider import DefaultJSONProvider
from hypercorn.asyncio import serve
from hypercorn.config import Config as HyperConfig
from quart import Quart, g, jsonify, request
from quart.logging import default_handler
from quart_cors import cors

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.io import get_local_ip_addresses

from .routes import *
from .routes.api_key import ALL_OPEN_API_SCOPES


class _AddrWithPort(Protocol):
    port: int


APP: Quart


def _parse_env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
        self.db = db
        self.shutdown_event = shutdown_event

        self.enable_webui = self._check_webui_enabled()

        self._init_paths(webui_dir)
        self._init_app()
        self.context = RouteContext(self.config, self.app)

        self._init_routes(db)
        self._init_plugin_route_index()
        self._init_jwt_secret()

    # ------------------------------------------------------------------
    # 初始化阶段
    # ------------------------------------------------------------------

    def _check_webui_enabled(self) -> bool:
        cfg = self.config.get("dashboard", {})
        _env = os.environ.get("DASHBOARD_ENABLE")
        if _env is not None:
            return _env.lower() in ("true", "1", "yes")
        return cfg.get("enable", True)

    def _init_paths(self, webui_dir: str | None):
        if webui_dir and os.path.exists(webui_dir):
            self.data_path = os.path.abspath(webui_dir)
        else:
            self.data_path = os.path.abspath(
                os.path.join(get_astrbot_data_path(), "dist")
            )

    def _init_app(self):
        """初始化 Quart 应用"""
        global APP
        self.app = Quart(
            "AstrBotDashboard",
            static_folder=self.data_path,
            static_url_path="/",
        )
        APP = self.app
        self.app.json_provider_class = DefaultJSONProvider
        self.app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB

        # 配置 CORS
        self.app = cors(
            self.app,
            allow_origin="*",
            allow_headers=["Authorization", "Content-Type", "X-API-Key"],
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        )

        @self.app.route("/")
        async def index():
            if not self.enable_webui:
                return "WebUI is disabled."
            return await self.app.send_static_file("index.html")

        @self.app.errorhandler(404)
        async def not_found(e):
            if not self.enable_webui:
                return "WebUI is disabled."
            if request.path.startswith("/api/"):
                return jsonify(Response().error("Not Found").to_json()), 404
            return await self.app.send_static_file("index.html")

        @self.app.before_serving
        async def startup():
            pass

        @self.app.after_serving
        async def shutdown():
            pass

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
        self.command_route = CommandRoute(self.context)
        self.cr = ConfigRoute(self.context, self.core_lifecycle)
        self.lr = LogRoute(self.context, self.core_lifecycle.log_broker)
        self.sfr = StaticFileRoute(self.context)
        self.ar = AuthRoute(self.context)
        self.api_key_route = ApiKeyRoute(self.context, db)
        self.chat_route = ChatRoute(self.context, db, self.core_lifecycle)
        self.open_api_route = OpenApiRoute(
            self.context,
            db,
            self.core_lifecycle,
            self.chat_route,
        )
        self.chatui_project_route = ChatUIProjectRoute(self.context, db)
        self.tools_root = ToolsRoute(self.context, self.core_lifecycle)
        self.subagent_route = SubAgentRoute(self.context, self.core_lifecycle)
        self.skills_route = SkillsRoute(self.context, self.core_lifecycle)
        self.conversation_route = ConversationRoute(
            self.context, db, self.core_lifecycle
        )
        self.file_route = FileRoute(self.context)
        self.session_management_route = SessionManagementRoute(
            self.context,
            db,
            self.core_lifecycle,
        )
        self.persona_route = PersonaRoute(self.context, db, self.core_lifecycle)
        self.cron_route = CronRoute(self.context, self.core_lifecycle)
        self.t2i_route = T2iRoute(self.context, self.core_lifecycle)
        self.kb_route = KnowledgeBaseRoute(self.context, self.core_lifecycle)
        self.platform_route = PlatformRoute(self.context, self.core_lifecycle)
        self.backup_route = BackupRoute(self.context, db, self.core_lifecycle)
        self.live_chat_route = LiveChatRoute(self.context, db, self.core_lifecycle)

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
        # 放行CORS预检请求
        if request.method == "OPTIONS":
            return None
        if not request.path.startswith("/api"):
            return None
        if request.path.startswith("/api/v1"):
            raw_key = self._extract_raw_api_key()
            if not raw_key:
                r = jsonify(Response().error("Missing API key").__dict__)
                r.status_code = 401
                return r
            key_hash = hashlib.pbkdf2_hmac(
                "sha256",
                raw_key.encode("utf-8"),
                b"astrbot_api_key",
                100_000,
            ).hex()
            api_key = await self.db.get_active_api_key_by_hash(key_hash)
            if not api_key:
                r = jsonify(Response().error("Invalid API key").__dict__)
                r.status_code = 401
                return r

            if isinstance(api_key.scopes, list):
                scopes = api_key.scopes
            else:
                scopes = list(ALL_OPEN_API_SCOPES)
            required_scope = self._get_required_open_api_scope(request.path)
            if required_scope and "*" not in scopes and required_scope not in scopes:
                r = jsonify(Response().error("Insufficient API key scope").__dict__)
                r.status_code = 403
                return r

            g.api_key_id = api_key.key_id
            g.api_key_scopes = scopes
            g.username = f"api_key:{api_key.key_id}"
            await self.db.touch_api_key(api_key.key_id)
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
            return jsonify(Response().error("插件 Web API 执行异常").to_json())

    @staticmethod
    def _extract_raw_api_key() -> str | None:
        if key := request.args.get("api_key"):
            return key.strip()
        if key := request.args.get("key"):
            return key.strip()
        if key := request.headers.get("X-API-Key"):
            return key.strip()
        auth_header = request.headers.get("Authorization", "").strip()
        if auth_header.startswith("Bearer "):
            return auth_header.removeprefix("Bearer ").strip()
        if auth_header.startswith("ApiKey "):
            return auth_header.removeprefix("ApiKey ").strip()
        return None

    @staticmethod
    def _get_required_open_api_scope(path: str) -> str | None:
        scope_map = {
            "/api/v1/chat": "chat",
            "/api/v1/chat/ws": "chat",
            "/api/v1/chat/sessions": "chat",
            "/api/v1/configs": "config",
            "/api/v1/file": "file",
            "/api/v1/im/message": "im",
            "/api/v1/im/bots": "im",
        }
        return scope_map.get(path)

    def check_port_in_use(self, host: str, port: int) -> bool:
        """跨平台检测端口是否被占用"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return False
            except OSError:
                return True

    def get_process_using_port(self, port: int) -> str:
        """获取占用端口的进程信息"""
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    connections = proc.net_connections()
                    for conn in connections:
                        if conn.laddr.port == port:
                            return f"PID: {proc.info['pid']}, Name: {proc.info['name']}"  # type: ignore
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    pass
        except Exception as e:
            return f"获取进程信息失败: {e!s}"
        return "未知进程"

    # ------------------------------------------------------------------
    # 启动与运行
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Run dashboard server (blocking)"""
        if not self.enable_webui:
            logger.warning(
                "WebUI 已禁用 (dashboard.enable=false or DASHBOARD_ENABLE=false)"
            )

        dashboard_config = self.config.get("dashboard", {})
        host = os.environ.get("DASHBOARD_HOST") or dashboard_config.get(
            "host", "0.0.0.0"
        )
        port = int(
            os.environ.get("DASHBOARD_PORT") or dashboard_config.get("port", 6185)
        )
        ssl_config = dashboard_config.get("ssl", {})
        ssl_enable = _parse_env_bool(
            os.environ.get("DASHBOARD_SSL_ENABLE"),
            ssl_config.get("enable", False),
        )

        scheme = "https" if ssl_enable else "http"
        display_host = f"[{host}]" if ":" in host else host

        if self.enable_webui:
            logger.info(
                "正在启动 WebUI + API, 监听地址: %s://%s:%s",
                scheme,
                display_host,
                port,
            )
        else:
            logger.info(
                "正在启动 API Server (WebUI 已分离), 监听地址: %s://%s:%s",
                scheme,
                display_host,
                port,
            )

        check_hosts = {host}
        if host not in ("127.0.0.1", "localhost", "::1"):
            check_hosts.add("127.0.0.1")
        for check_host in check_hosts:
            if self.check_port_in_use(check_host, port):
                info = self.get_process_using_port(port)
                raise RuntimeError(f"端口 {port} 已被占用\n{info}")

        if self.enable_webui:
            self._print_access_urls(host, port, scheme)

        # 配置 Hypercorn
        config = HyperConfig()
        binds: list[str] = [self._build_bind(host, port)]
        # 参考：https://github.com/pgjones/hypercorn/issues/85
        if host == "::" and platform.system() in ("Windows", "Darwin"):
            binds.append(self._build_bind("0.0.0.0", port))
        config.bind = binds

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
                raise ValueError(
                    "dashboard.ssl.enable 为 true 时，必须配置 cert_file 和 key_file。",
                )
            if not cert_path.is_file():
                raise ValueError(f"SSL 证书文件不存在: {cert_path}")
            if not key_path.is_file():
                raise ValueError(f"SSL 私钥文件不存在: {key_path}")

            config.certfile = str(cert_path.resolve())
            config.keyfile = str(key_path.resolve())

            if ca_certs:
                ca_path = Path(ca_certs).expanduser()
                if not ca_path.is_file():
                    raise ValueError(f"SSL CA 证书文件不存在: {ca_path}")
                config.ca_certs = str(ca_path.resolve())

        # 根据配置决定是否禁用访问日志
        disable_access_log = dashboard_config.get("disable_access_log", True)
        if disable_access_log:
            config.accesslog = None
        else:
            config.accesslog = "-"
            config.access_log_format = "%(h)s %(r)s %(s)s %(b)s %(D)s"

        return asyncio.run(
            serve(self.app, config, shutdown_trigger=self.shutdown_trigger)
        )

    @staticmethod
    def _build_bind(host: str, port: int) -> str:
        try:
            ip: IPv4Address | IPv6Address = ip_address(host)
            return f"[{ip}]:{port}" if ip.version == 6 else f"{ip}:{port}"
        except ValueError:
            return f"{host}:{port}"

    def _print_access_urls(self, host: str, port: int, scheme: str = "http") -> None:
        local_ips: list[IPv4Address | IPv6Address] = get_local_ip_addresses()

        parts = [f"\n ✨✨✨\n  AstrBot v{VERSION} WebUI 已启动\n\n"]

        parts.append(f"   ➜  本地: {scheme}://localhost:{port}\n")

        if host in ("::", "0.0.0.0"):
            for ip in local_ips:
                if ip.is_loopback:
                    continue

                if ip.version == 6:
                    display_url = f"{scheme}://[{ip}]:{port}"
                else:
                    display_url = f"{scheme}://{ip}:{port}"

                parts.append(f"   ➜  网络: {display_url}\n")

        parts.append("   ➜  默认用户名和密码: astrbot\n ✨✨✨\n")

        if not local_ips:
            parts.append(
                "可在 data/cmd_config.json 中配置 dashboard.host 以便远程访问。\n"
            )

        logger.info("".join(parts))

    async def shutdown_trigger(self):
        await self.shutdown_event.wait()
