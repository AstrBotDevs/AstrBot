import asyncio
import errno
import hashlib
import logging
import os
import platform
import re
import socket
import ssl
from collections.abc import Callable
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address, ip_address
from pathlib import Path

import anyio
import jwt
import psutil
import werkzeug.exceptions
from flask.json.provider import DefaultJSONProvider
from hypercorn.asyncio import serve
from hypercorn.config import Config as HyperConfig
from quart import Quart, g, jsonify, request
from quart.logging import default_handler
from quart.typing import ResponseReturnValue
from quart_cors import cors

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.datetime_utils import to_utc_isoformat
from astrbot.core.utils.io import get_local_ip_addresses

from .routes import (
    ApiKeyRoute,
    AuthRoute,
    BackupRoute,
    ChatRoute,
    ChatUIProjectRoute,
    CommandRoute,
    ConfigRoute,
    ConversationRoute,
    CronRoute,
    FileRoute,
    KnowledgeBaseRoute,
    LiveChatRoute,
    LogRoute,
    OpenApiRoute,
    PersonaRoute,
    PlatformRoute,
    PluginRoute,
    Response,
    RouteContext,
    SessionManagementRoute,
    SkillsRoute,
    StaticFileRoute,
    StatRoute,
    SubAgentRoute,
    T2iRoute,
    ToolsRoute,
    TUIChatRoute,
    UpdateRoute,
)
from .routes.api_key import ALL_OPEN_API_SCOPES
from .routes.route import is_runtime_request_ready, runtime_loading_response

# Static assets shipped inside the wheel (built during `hatch build`).
_BUNDLED_DIST = Path(__file__).parent / "dist"

_PUBLIC_ALLOWED_ENDPOINT_PREFIXES = (
    "/api/auth/login",
    "/api/file",
    "/api/platform/webhook",
    "/api/stat/start-time",
    "/api/backup/download",
)
_RUNTIME_EXTRA_BYPASS_ENDPOINT_PREFIXES = (
    "/api/stat/version",
    "/api/stat/runtime-status",
    "/api/stat/restart-core",
    "/api/stat/changelog",
    "/api/stat/changelog/list",
    "/api/stat/first-notice",
)
_RUNTIME_BYPASS_ENDPOINT_PREFIXES = (
    tuple(
        prefix
        for prefix in _PUBLIC_ALLOWED_ENDPOINT_PREFIXES
        if prefix != "/api/platform/webhook"
    )
    + _RUNTIME_EXTRA_BYPASS_ENDPOINT_PREFIXES
)
_RUNTIME_FAILED_RECOVERY_ENDPOINT_PREFIXES = (
    "/api/config/",
    "/api/plugin/reload-failed",
    "/api/plugin/uninstall-failed",
    "/api/plugin/source/get-failed-plugins",
)


APP: Quart
_ENV_PLACEHOLDER_RE = re.compile(
    r"\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^}]*))?\}|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))"
)


def _parse_env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _expand_env_placeholders(value: str, field_name: str) -> str:
    missing_vars: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group("braced") or match.group("plain")
        default = match.group("default")
        env_value = os.environ.get(var_name)
        if env_value is not None:
            return env_value
        if default is not None:
            return default
        missing_vars.append(var_name)
        return match.group(0)

    expanded = _ENV_PLACEHOLDER_RE.sub(_replace, value)
    if missing_vars:
        missing = ", ".join(sorted(set(missing_vars)))
        raise ValueError(
            f"Unresolved environment variable(s) in dashboard {field_name}: {missing}"
        )
    return expanded


def _resolve_dashboard_value(
    value: str | int | None,
    *,
    field_name: str,
) -> str | int | None:
    if not isinstance(value, str):
        return value
    return _expand_env_placeholders(value, field_name).strip()


class AstrBotJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, datetime):
            return to_utc_isoformat(obj)
        return super().default(obj)


class AstrBotDashboard:
    """AstrBot Web Dashboard"""

    ALLOWED_ENDPOINT_PREFIXES = _PUBLIC_ALLOWED_ENDPOINT_PREFIXES
    RUNTIME_BYPASS_ENDPOINT_PREFIXES = _RUNTIME_BYPASS_ENDPOINT_PREFIXES
    RUNTIME_FAILED_RECOVERY_ENDPOINT_PREFIXES = (
        _RUNTIME_FAILED_RECOVERY_ENDPOINT_PREFIXES
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
        self._webui_fallback = False  # True if frontend was enabled but files missing

        self._init_paths(webui_dir)
        self._init_app()
        self.context = RouteContext(self.config, self.app)

        self._init_routes(db)
        self._init_plugin_route_index()
        self._init_jwt_secret()

    def _check_webui_enabled(self) -> bool:
        cfg = self.config.get("dashboard", {})
        _env = os.environ.get("ASTRBOT_DASHBOARD_ENABLE")
        if _env is not None:
            return _env.lower() in ("true", "1", "yes")
        return cfg.get("enable", True)

    def _init_paths(self, webui_dir: str | None):
        # Path priority:
        # 1. Explicit webui_dir argument
        # 2. data/dist/ (user-installed / manually updated dashboard)
        # 3. astrbot/dashboard/dist/ (bundled with the wheel)
        # resolve() is used throughout to follow symlinks to their real paths.
        if webui_dir and os.path.exists(webui_dir):
            self.data_path = os.path.abspath(webui_dir)
        else:
            user_dist = os.path.join(get_astrbot_data_path(), "dist")
            if os.path.exists(user_dist):
                self.data_path = os.path.abspath(user_dist)
            elif _BUNDLED_DIST.exists():
                # resolve() follows symlinks so self.data_path points to the
                # actual directory, not the symlink itself.
                self.data_path = str(_BUNDLED_DIST.resolve())
                logger.info("Using bundled dashboard dist: %s", self.data_path)
            else:
                self.data_path = os.path.abspath(user_dist)

        if self.enable_webui and not (Path(self.data_path) / "index.html").exists():
            logger.warning(
                f"前端未内置或未初始化 (index.html missing in {self.data_path}), "
                "回退到仅启动后端. 请访问在线面板: dash.astrbot.men"
            )
            self.enable_webui = False
            self._webui_fallback = True

    def _init_app(self):
        """初始化 Quart 应用"""
        global APP

        static_folder = self.data_path if self.enable_webui else None
        static_url_path = "/" if self.enable_webui else None

        self.app = Quart(
            "AstrBotDashboard",
            static_folder=static_folder,
            static_url_path=static_url_path,
        )
        APP = self.app
        self.app.json_provider_class = DefaultJSONProvider
        self.app.config["MAX_CONTENT_LENGTH"] = 128 * 1024 * 1024  # 128MB
        self.app.json = AstrBotJSONProvider(self.app)
        self.app.json.sort_keys = False

        # 配置 CORS
        # 支持通过环境变量 CORS_ALLOW_ORIGIN 配置允许的域名,多个域名用逗号分隔
        # 如果前端使用 withCredentials:true,需要设置具体的域名而非 "*"
        cors_allow_origin = os.environ.get("CORS_ALLOW_ORIGIN", "*")
        cors_allow_credentials = False
        if cors_allow_origin != "*":
            cors_allow_origin = [
                origin.strip() for origin in cors_allow_origin.split(",")
            ]
            # 只有设置具体域名时才允许凭据
            cors_allow_credentials = True
        self.app = cors(
            self.app,
            allow_origin=cors_allow_origin,
            allow_credentials=cors_allow_credentials,
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-API-Key",
                "Accept-Language",
            ],
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        )

        @self.app.route("/")
        async def index():
            if not self.enable_webui:
                return "前端未启用, 请访问在线面板: dash.astrbot.men"
            try:
                return await self.app.send_static_file("index.html")
            except werkzeug.exceptions.NotFound:
                logger.error(f"Dashboard index.html not found in {self.data_path}")
                return "Dashboard files not found.", 404

        @self.app.errorhandler(404)
        async def not_found(e):
            if not self.enable_webui:
                return "前端未启用, 请访问在线面板: dash.astrbot.men"
            if request.path.startswith("/api/"):
                return jsonify(Response().error("Not Found").to_json()), 404
            try:
                return await self.app.send_static_file("index.html")
            except werkzeug.exceptions.NotFound:
                return "Dashboard files not found.", 404

        @self.app.before_serving
        async def startup():
            pass

        @self.app.after_serving
        async def shutdown():
            pass

        self.app.before_request(self.auth_middleware)
        logging.getLogger(self.app.name).removeHandler(default_handler)

    def _init_routes(self, db: BaseDatabase):
        astrbot_updator = self.core_lifecycle.astrbot_updator
        plugin_manager = self.core_lifecycle.plugin_manager
        assert astrbot_updator is not None
        assert plugin_manager is not None

        UpdateRoute(self.context, astrbot_updator, self.core_lifecycle)
        StatRoute(self.context, db, self.core_lifecycle)
        PluginRoute(self.context, self.core_lifecycle, plugin_manager)

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
        self.tui_chat_route = TUIChatRoute(self.context, db, self.core_lifecycle)

        self.app.add_url_rule(
            "/api/plug/<path:subpath>",
            view_func=self.guarded_srv_plug_route,
            methods=["GET", "POST"],
        )

    def _init_plugin_route_index(self):
        """将插件路由索引,避免 O(n) 查找"""
        self._plugin_route_map: dict[tuple[str, str], Callable] = {}
        star_context = self.core_lifecycle.star_context
        if star_context is None:
            return
        if star_context.registered_web_apis is None:
            star_context.registered_web_apis = []
        for (
            route,
            handler,
            methods,
            _,
        ) in star_context.registered_web_apis:
            for method in methods:
                self._plugin_route_map[(route, method)] = handler

    def _init_jwt_secret(self):
        dashboard_cfg = self.config.setdefault("dashboard", {})
        if not dashboard_cfg.get("jwt_secret"):
            dashboard_cfg["jwt_secret"] = os.urandom(32).hex()
            self.config.save_config()
            logger.info("Initialized random JWT secret for dashboard.")
        self._jwt_secret = dashboard_cfg["jwt_secret"]

    async def guarded_srv_plug_route(
        self, subpath: str, *args, **kwargs
    ) -> ResponseReturnValue:
        guard_resp = self._maybe_runtime_guard(request.path)
        if guard_resp is not None:
            return guard_resp
        return await self.srv_plug_route(subpath, *args, **kwargs)

    def _should_bypass_runtime_guard(self, path: str) -> bool:
        return any(
            path.startswith(prefix) for prefix in self.RUNTIME_BYPASS_ENDPOINT_PREFIXES
        )

    def _should_allow_failed_runtime_recovery(self, path: str) -> bool:
        if not (
            self.core_lifecycle.runtime_failed
            or self.core_lifecycle.runtime_bootstrap_error is not None
        ):
            return False
        return any(
            path.startswith(prefix)
            for prefix in self.RUNTIME_FAILED_RECOVERY_ENDPOINT_PREFIXES
        )

    def _maybe_runtime_guard(
        self,
        path: str,
        *,
        include_failure_details: bool = True,
    ) -> ResponseReturnValue | None:
        if self._should_bypass_runtime_guard(path):
            return None
        if self._should_allow_failed_runtime_recovery(path):
            return None
        if not is_runtime_request_ready(self.core_lifecycle):
            return runtime_loading_response(
                self.core_lifecycle,
                include_failure_details=include_failure_details,
            )
        return None

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
            guard_resp = self._maybe_runtime_guard(
                request.path,
                include_failure_details=False,
            )
            if guard_resp is not None:
                return guard_resp
            return None

        if any(request.path.startswith(p) for p in self.ALLOWED_ENDPOINT_PREFIXES):
            guard_resp = self._maybe_runtime_guard(
                request.path,
                include_failure_details=False,
            )
            if guard_resp is not None:
                return guard_resp
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

        guard_resp = self._maybe_runtime_guard(request.path)
        if guard_resp is not None:
            return guard_resp

    @staticmethod
    def _unauthorized(msg: str):
        r = jsonify(Response().error(msg).to_json())
        r.status_code = 401
        return r

    def _get_plugin_handler(self, subpath: str, method: str) -> Callable | None:
        handler = self._plugin_route_map.get((f"/{subpath}", method))
        if handler is not None:
            return handler
        self._init_plugin_route_index()
        return self._plugin_route_map.get((f"/{subpath}", method))

    async def srv_plug_route(self, subpath: str, *args, **kwargs):
        handler = self._get_plugin_handler(subpath, request.method)
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
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host, port))
                return False
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                return True
            logger.warning(
                "Skip port preflight for %s:%s due to bind probe failure: %s",
                host,
                port,
                exc,
            )
            return False

    def get_process_using_port(self, port: int) -> str:
        """获取占用端口的进程信息"""
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    connections = proc.net_connections()
                    for conn in connections:
                        if conn.laddr.port == port:
                            return f"PID: {proc.info['pid']}, Name: {proc.info['name']}"
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    pass
        except Exception as e:
            return f"获取进程信息失败: {e!s}"
        return "未知进程"

    async def run(self) -> None:
        """Run dashboard server (blocking)"""
        if self._webui_fallback:
            logger.warning(
                "前端未内置或未初始化, 回退到仅启动后端. 请访问在线面板: dash.astrbot.men"
            )
        elif not self.enable_webui:
            logger.warning("前端已禁用, 请访问在线面板: dash.astrbot.men")

        dashboard_config = self.config.get("dashboard", {})
        host_value = os.environ.get("ASTRBOT_HOST") or dashboard_config.get(
            "host", "0.0.0.0"
        )
        host = _resolve_dashboard_value(host_value, field_name="host")
        if not isinstance(host, str) or not host:
            raise ValueError("Dashboard host must be a non-empty string")

        # Port priority: ASTRBOT_PORT env var > cmd_config.json dashboard.port > default 6185
        env_port = os.environ.get("ASTRBOT_PORT")
        json_port = dashboard_config.get("port")
        if env_port is not None:
            port_value = env_port
            logger.info(
                "[Dashboard] Using port from ASTRBOT_PORT environment variable: %s",
                env_port,
            )
        elif json_port is not None:
            port_value = json_port
            logger.info("[Dashboard] Using port from cmd_config.json: %s", json_port)
        else:
            port_value = 6185
            logger.info("[Dashboard] Using default port: 6185")
        resolved_port = _resolve_dashboard_value(port_value, field_name="port")
        if resolved_port is None:
            raise ValueError("Port configuration is missing")
        port = int(resolved_port)
        ssl_config = dashboard_config.get("ssl", {})
        ssl_enable = _parse_env_bool(
            os.environ.get("ASTRBOT_SSL_ENABLE"),
            ssl_config.get("enable", False),
        )

        scheme = "https" if ssl_enable else "http"
        binds: list[str] = [self._build_bind(host, port)]
        if host == "::" and platform.system() in ("Windows", "Darwin"):
            binds.append(self._build_bind("0.0.0.0", port))

        if self.enable_webui:
            logger.info(
                "正在启动 WebUI + API, 监听: %s",
                ", ".join(f"{scheme}://{bind}" for bind in binds),
            )
        else:
            logger.info(
                "正在启动 API Server, 监听: %s",
                ", ".join(f"{scheme}://{bind}" for bind in binds),
            )

        check_hosts = {host}
        if host not in ("127.0.0.1", "localhost", "::1"):
            check_hosts.add("127.0.0.1")
        for check_host in check_hosts:
            if self.check_port_in_use(check_host, port):
                info = self.get_process_using_port(port)
                raise RuntimeError(f"端口 {port} 已被占用\n{info}")

        self._print_access_urls(host, port, scheme, self.enable_webui)

        # 配置 Hypercorn
        config = HyperConfig()
        config.bind = binds

        if ssl_enable:
            cert_file = os.environ.get("ASTRBOT_SSL_CERT") or ssl_config.get(
                "cert_file", ""
            )
            cert_file = _resolve_dashboard_value(cert_file, field_name="ssl.cert_file")
            key_file = os.environ.get("ASTRBOT_SSL_KEY") or ssl_config.get(
                "key_file", ""
            )
            key_file = _resolve_dashboard_value(key_file, field_name="ssl.key_file")
            ca_certs = os.environ.get("ASTRBOT_SSL_CA_CERTS") or ssl_config.get(
                "ca_certs", ""
            )
            ca_certs = _resolve_dashboard_value(ca_certs, field_name="ssl.ca_certs")

            if cert_file and key_file:
                cert_path = await anyio.Path(str(cert_file)).expanduser()
                key_path = await anyio.Path(str(key_file)).expanduser()
                if not await cert_path.is_file():
                    raise ValueError(f"SSL 证书文件不存在: {cert_path}")
                if not await key_path.is_file():
                    raise ValueError(f"SSL 私钥文件不存在: {key_path}")

                config.certfile = str(await cert_path.resolve())
                config.keyfile = str(await key_path.resolve())

            if ca_certs:
                ca_path = await anyio.Path(str(ca_certs)).expanduser()
                if not await ca_path.is_file():
                    raise ValueError(f"SSL CA 证书文件不存在: {ca_path}")
                config.ca_certs = str(await ca_path.resolve())

        # 根据配置决定是否禁用访问日志
        disable_access_log = dashboard_config.get("disable_access_log", True)
        if disable_access_log:
            config.accesslog = None
        else:
            config.accesslog = "-"
            config.access_log_format = "%(h)s %(r)s %(s)s %(b)s %(D)s"

        try:
            await serve(self.app, config, shutdown_trigger=self.shutdown_trigger)
        except (ssl.SSLError, asyncio.CancelledError):
            # Client disconnected abruptly — SSL shutdown errors are benign.
            pass

    @staticmethod
    def _build_bind(host: str, port: int) -> str:
        try:
            ip: IPv4Address | IPv6Address = ip_address(host)
            return f"[{ip}]:{port}" if ip.version == 6 else f"{ip}:{port}"
        except ValueError:
            return f"{host}:{port}"

    def _print_access_urls(
        self,
        host: str,
        port: int,
        scheme: str = "http",
        enable_webui: bool = True,
    ) -> None:
        local_ips: list[IPv4Address | IPv6Address] = get_local_ip_addresses()
        mode_label = "WebUI + API" if enable_webui else "API Server (WebUI 已分离)"

        parts = [f"\n ✨✨✨\n  AstrBot v{VERSION} {mode_label} 已启动\n\n"]

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
        else:
            if ":" in host:
                parts.append(f"   ➜  指定监听: {scheme}://[{host}]:{port}\n")
            else:
                parts.append(f"   ➜  指定监听: {scheme}://{host}:{port}\n")

        if enable_webui:
            parts.append("   ➜  默认用户名和密码: astrbot\n")
        parts.append(" ✨✨✨\n")

        if not local_ips:
            parts.append(
                "可在 data/cmd_config.json 中配置 dashboard.host 以便远程访问｡\n"
            )

        logger.info("".join(parts))

    async def shutdown_trigger(self):
        await self.shutdown_event.wait()
