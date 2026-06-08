import asyncio
import ipaddress
import os
import re
import socket
import time
from pathlib import Path
from typing import Protocol, cast

import jwt
import psutil
from hypercorn.asyncio import serve
from hypercorn.config import Config as HyperConfig
from hypercorn.logging import AccessLogAtoms
from hypercorn.logging import Logger as HypercornLogger

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.io import (
    get_bundled_dashboard_dist_path,
    get_local_ip_addresses,
    should_use_bundled_dashboard_dist,
)
from astrbot.dashboard.fastapi_compat import (
    CompatG,
    FastAPIAppAdapter,
    bind_request_context,
    g,
    jsonify,
    request,
)

from .plugin_page_auth import PluginPageAuth
from .routes.api_key import ApiKeyRoute
from .routes.auth import AuthRoute
from .routes.backup import BackupRoute
from .routes.chat import ChatRoute
from .routes.chatui_project import ChatUIProjectRoute
from .routes.command import CommandRoute
from .routes.config import ConfigRoute
from .routes.conversation import ConversationRoute
from .routes.cron import CronRoute
from .routes.file import FileRoute
from .routes.knowledge_base import KnowledgeBaseRoute
from .routes.live_chat import LiveChatRoute
from .routes.log import LogRoute
from .routes.open_api import OpenApiRoute
from .routes.persona import PersonaRoute
from .routes.platform import PlatformRoute
from .routes.plugin import PluginRoute
from .routes.route import Response, RouteContext
from .routes.session_management import SessionManagementRoute
from .routes.skills import SkillsRoute
from .routes.stat import StatRoute
from .routes.static_file import StaticFileRoute
from .routes.subagent import SubAgentRoute
from .routes.t2i import T2iRoute
from .routes.tools import ToolsRoute
from .routes.update import UpdateRoute
from .services.auth_service import DASHBOARD_JWT_COOKIE_NAME
from .services.chat_service import ChatService
from .v1.app import create_v1_asgi_app

_RATE_LIMITED_ENDPOINTS: frozenset = frozenset(
    {
        "/api/config/astrbot/update",
        "/api/auth/totp/setup",
        "/api/auth/login",
    }
)


class _AuthRateLimiter:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self.last_accessed = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            self.last_accessed = now
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False


class _RateLimiterRegistry:
    """Per-IP token-bucket rate limiter registry. Idle entries expire after 1 hour."""

    _ENTRY_TTL: float = 3600.0
    _INTERVAL: float = 1800.0

    def __init__(self) -> None:
        self._limiters: dict[str, _AuthRateLimiter] = {}
        self._last_eviction = time.monotonic()

    def get_or_create(
        self, key: str, capacity: int, refill_rate: float
    ) -> _AuthRateLimiter:
        self._evict_expired()
        limiter = self._limiters.get(key)
        if limiter is None:
            limiter = _AuthRateLimiter(capacity=capacity, refill_rate=refill_rate)
            self._limiters[key] = limiter
        return limiter

    def _evict_expired(self) -> None:
        now = time.monotonic()
        if now - self._last_eviction < self._INTERVAL:
            return
        self._last_eviction = now
        cutoff = now - self._ENTRY_TTL
        stale = [k for k, v in self._limiters.items() if v.last_accessed < cutoff]
        for k in stale:
            del self._limiters[k]

    def clear(self) -> None:
        self._limiters.clear()

    def __len__(self) -> int:
        return len(self._limiters)

    def __contains__(self, key: str) -> bool:
        return key in self._limiters


class _AddrWithPort(Protocol):
    port: int


APP: FastAPIAppAdapter | None = None


def _normalize_plugin_api_route(route: str) -> str:
    route = route.strip()
    if not route.startswith("/"):
        route = f"/{route}"
    return route


def _match_registered_web_api(registered_web_apis, subpath: str, method: str):
    request_path = f"/{subpath.lstrip('/')}"
    request_method = method.upper()

    for route, view_handler, methods, _ in registered_web_apis:
        allowed_methods = [item.upper() for item in methods]
        if request_method not in allowed_methods:
            continue

        pattern = _plugin_api_route_pattern(route)
        matched = re.fullmatch(pattern, request_path)
        if not matched:
            continue
        return view_handler, matched.groupdict()

    return None


def _plugin_api_route_pattern(route: str) -> str:
    normalized = _normalize_plugin_api_route(route)
    chunks = []
    pos = 0
    for match in re.finditer(r"<(?:(path):)?([A-Za-z_][A-Za-z0-9_]*)>", normalized):
        chunks.append(re.escape(normalized[pos : match.start()]))
        name = match.group(2)
        chunks.append(f"(?P<{name}>.*)" if match.group(1) else f"(?P<{name}>[^/]+)")
        pos = match.end()
    chunks.append(re.escape(normalized[pos:]))
    return "".join(chunks)


def _parse_env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class _ProxyAwareHypercornLogger(HypercornLogger):
    @staticmethod
    def _get_request_log_host(request_scope) -> str | None:
        forwarded_for = None
        real_ip = None
        for raw_name, raw_value in request_scope.get("headers", []):
            header_name = raw_name.decode("latin1").lower()
            if header_name == "x-forwarded-for":
                forwarded_for = raw_value.decode("latin1")
            elif header_name == "x-real-ip":
                real_ip = raw_value.decode("latin1")

            if forwarded_for is not None and real_ip is not None:
                break

        forwarded_for = str(forwarded_for or "").strip()
        if forwarded_for:
            first_ip = forwarded_for.split(",", 1)[0].strip()
            if first_ip and first_ip.lower() != "unknown":
                try:
                    return str(ipaddress.ip_address(first_ip))
                except ValueError:
                    pass

        real_ip = str(real_ip or "").strip()
        if real_ip and real_ip.lower() != "unknown":
            try:
                return str(ipaddress.ip_address(real_ip))
            except ValueError:
                pass

        client = request_scope.get("client")
        if not client:
            return None
        host = str(client[0]).strip()
        if host:
            return host
        return None

    def atoms(self, request, response, request_time):
        atoms = AccessLogAtoms(request, response, request_time)
        client_host = self._get_request_log_host(request)
        if client_host:
            atoms["h"] = client_host
        return atoms


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
        self.db = db

        # Path priority:
        # 1. Explicit webui_dir argument
        # 2. data/dist/ (user-installed / manually updated dashboard)
        # 3. astrbot/dashboard/dist/ (bundled with the wheel)
        if webui_dir and os.path.exists(webui_dir):
            self.data_path = os.path.abspath(webui_dir)
        else:
            user_dist = os.path.join(get_astrbot_data_path(), "dist")
            bundled_dist = get_bundled_dashboard_dist_path()
            if os.path.exists(user_dist) and not should_use_bundled_dashboard_dist(
                user_dist,
                VERSION,
            ):
                self.data_path = os.path.abspath(user_dist)
            elif bundled_dist.exists():
                self.data_path = str(bundled_dist)
                logger.info("Using bundled dashboard dist: %s", self.data_path)
            else:
                # Fall back to expected user path (will fail gracefully later)
                self.data_path = os.path.abspath(user_dist)

        self._rate_limiter_registry = _RateLimiterRegistry()
        self._init_jwt_secret()
        self.asgi_app = create_v1_asgi_app(
            core_lifecycle=core_lifecycle,
            db=db,
            jwt_secret=self._jwt_secret,
        )
        self.app = FastAPIAppAdapter(self.asgi_app, static_folder=self.data_path)
        self.asgi_app.state.dashboard_app_adapter = self.app
        self.app._dashboard_server = self
        global APP
        APP = self.app
        self.app.config["MAX_CONTENT_LENGTH"] = (
            128 * 1024 * 1024
        )  # 将 Flask 允许的最大上传文件体大小设置为 128 MB

        @self.asgi_app.middleware("http")
        async def dashboard_auth_middleware(request_, call_next):
            request_.state.dashboard_g = CompatG()
            with bind_request_context(request_, self.app, request_.state.dashboard_g):
                auth_response = await self.auth_middleware()
            if auth_response is not None:
                return auth_response
            return await call_next(request_)

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
        self.command_route = CommandRoute(self.context, core_lifecycle)
        self.cr = ConfigRoute(self.context, core_lifecycle)
        self.lr = LogRoute(self.context, core_lifecycle.log_broker)
        self.sfr = StaticFileRoute(self.context)
        self.ar = AuthRoute(self.context, db)
        self.api_key_route = ApiKeyRoute(self.context, db)
        self.chat_service = ChatService(db, core_lifecycle)
        self.chat_route = ChatRoute(
            self.context,
            db,
            core_lifecycle,
            service=self.chat_service,
        )
        self.open_api_route = OpenApiRoute(
            self.context,
            db,
            core_lifecycle,
            self.chat_service,
            register_routes=False,
        )
        self.asgi_app.state.open_api_route = self.open_api_route
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
        self.asgi_app.state.live_chat_route = self.live_chat_route

        self.app.add_url_rule(
            "/api/plug/<path:subpath>",
            view_func=self.srv_plug_route,
            methods=["GET", "POST"],
        )

        self.shutdown_event = shutdown_event

    async def srv_plug_route(self, subpath, *args, **kwargs):
        """插件路由"""
        registered_web_apis = self.core_lifecycle.star_context.registered_web_apis
        matched_api = _match_registered_web_api(
            registered_web_apis,
            subpath,
            request.method,
        )
        if matched_api:
            view_handler, path_values = matched_api
            return await view_handler(*args, **{**kwargs, **path_values})
        return jsonify(Response().error("未找到该路由").__dict__)

    async def auth_middleware(self):
        if not request.path.startswith("/api"):
            return None
        if request.path.startswith("/api/v1"):
            return None

        if (
            os.environ.get("ASTRBOT_TEST_MODE") != "true"
            and request.path in _RATE_LIMITED_ENDPOINTS
        ):
            rl_config = self.config.get("dashboard", {}).get("auth_rate_limit", {})
            rl_enabled = rl_config.get("enable", True)
            if rl_enabled:
                average_interval = float(rl_config.get("average_interval", 1.0))
                max_burst = int(rl_config.get("max_burst", 3))
                if average_interval <= 0:
                    average_interval = 1.0
                if max_burst <= 0:
                    max_burst = 3
                refill_rate = 1.0 / average_interval
                client_ip = self._get_request_client_ip(request)
                limiter = self._rate_limiter_registry.get_or_create(
                    client_ip, capacity=max_burst, refill_rate=refill_rate
                )
                if not await limiter.acquire():
                    r = jsonify(
                        Response()
                        .error("验证尝试过于频繁，系统可能正在遭受暴力破解")
                        .__dict__
                    )
                    r.status_code = 429
                    return r

        allowed_exact_endpoints = {
            "/api/auth/login",
            "/api/auth/logout",
            "/api/auth/setup-status",
            "/api/auth/setup",
        }
        allowed_endpoint_prefixes = [
            "/api/file",
            "/api/v1/files/tokens",
            "/api/platform/webhook",
            "/api/stat/start-time",
            "/api/backup/download",  # 备份下载使用 URL 参数传递 token
        ]
        if request.path in allowed_exact_endpoints or any(
            request.path.startswith(prefix) for prefix in allowed_endpoint_prefixes
        ):
            return None
        is_plugin_page_path = PluginPageAuth.is_protected_path(request.path)
        token = self._extract_dashboard_jwt()
        if not token and is_plugin_page_path:
            token = PluginPageAuth.extract_asset_token()
        if not token:
            r = jsonify(Response().error("未授权").__dict__)
            r.status_code = 401
            return r
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])
            if PluginPageAuth.is_asset_token(
                payload
            ) and not PluginPageAuth.is_scope_valid(
                payload,
                request.path,
            ):
                r = jsonify(Response().error("Token 无效").__dict__)
                r.status_code = 401
                return r

            username = payload.get("username")
            if not isinstance(username, str) or not username.strip():
                raise jwt.InvalidTokenError("missing username in token payload")
            g.username = username
        except jwt.ExpiredSignatureError:
            r = jsonify(Response().error("Token 过期").__dict__)
            r.status_code = 401
            return r
        except jwt.InvalidTokenError:
            r = jsonify(Response().error("Token 无效").__dict__)
            r.status_code = 401
            return r

    def _get_request_client_ip(self, current_request) -> str:
        if bool(self.config.get("dashboard", {}).get("trust_proxy_headers", False)):
            forwarded_for = str(
                current_request.headers.get("X-Forwarded-For", "")
            ).strip()
            if forwarded_for:
                first_ip = forwarded_for.split(",", 1)[0].strip()
                if first_ip and first_ip.lower() != "unknown":
                    try:
                        return str(ipaddress.ip_address(first_ip))
                    except ValueError:
                        pass

            real_ip = str(current_request.headers.get("X-Real-IP", "")).strip()
            if real_ip and real_ip.lower() != "unknown":
                try:
                    return str(ipaddress.ip_address(real_ip))
                except ValueError:
                    pass

        remote_addr = str(current_request.remote_addr or "").strip()
        if remote_addr:
            try:
                return str(ipaddress.ip_address(remote_addr))
            except ValueError:
                pass

        return "unknown"

    @staticmethod
    def _extract_dashboard_jwt() -> str | None:
        auth_header = request.headers.get("Authorization", "").strip()
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
            if token:
                return token

        cookie_token = request.cookies.get(DASHBOARD_JWT_COOKIE_NAME, "").strip()
        if cookie_token:
            return cookie_token
        return None

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
            logger.warning(f"检查端口 {port} 时发生错误: {e!s}")
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
                            f"进程名: {process.name()}",
                            f"PID: {process.pid}",
                            f"执行路径: {process.exe()}",
                            f"工作目录: {process.cwd()}",
                            f"启动命令: {' '.join(process.cmdline())}",
                        ]
                        return "\n           ".join(proc_info)
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        return f"无法获取进程详细信息(可能需要管理员权限): {e!s}"
            return "未找到占用进程"
        except Exception as e:
            return f"获取进程信息失败: {e!s}"

    def _init_jwt_secret(self) -> None:
        if not self.config.get("dashboard", {}).get("jwt_secret", None):
            # 如果没有设置 JWT 密钥，则生成一个新的密钥
            jwt_secret = os.urandom(32).hex()
            self.config["dashboard"]["jwt_secret"] = jwt_secret
            self.config.save_config()
            logger.info("Initialized random JWT secret for dashboard.")
        self._jwt_secret = self.config["dashboard"]["jwt_secret"]

    def _build_dashboard_credentials_display(self) -> str:
        username = self.config["dashboard"].get("username", "astrbot")
        generated_password = getattr(self.config, "_generated_dashboard_password", None)
        if not generated_password:
            return f"   ➜  Username: {username}\n ✨✨✨\n"

        credentials_display = (
            f"   ➜  Initial username: {username}\n"
            f"   ➜  Initial password: {generated_password}\n"
            "   ➜  Change it after logging in\n ✨✨✨\n"
        )
        object.__setattr__(self.config, "_generated_dashboard_password", None)
        return credentials_display

    @staticmethod
    def _resolve_dashboard_ssl_config(
        ssl_config: dict,
    ) -> tuple[bool, dict[str, str]]:
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

        if not cert_file or not key_file:
            logger.warning(
                "dashboard.ssl.enable is set, but cert_file or key_file is missing. SSL disabled.",
            )
            return False, {}

        cert_path = Path(cert_file).expanduser()
        key_path = Path(key_file).expanduser()
        if not cert_path.is_file():
            logger.warning(
                f"dashboard.ssl.enable is set, but cert file is missing: {cert_path}. SSL disabled.",
            )
            return False, {}
        if not key_path.is_file():
            logger.warning(
                f"dashboard.ssl.enable is set, but key file is missing: {key_path}. SSL disabled.",
            )
            return False, {}

        resolved_ssl_config = {
            "certfile": str(cert_path.resolve()),
            "keyfile": str(key_path.resolve()),
        }

        if ca_certs:
            ca_path = Path(ca_certs).expanduser()
            if not ca_path.is_file():
                logger.warning(
                    f"dashboard.ssl.enable is set, but CA cert file is missing: {ca_path}. SSL disabled.",
                )
                return False, {}
            resolved_ssl_config["ca_certs"] = str(ca_path.resolve())

        return True, resolved_ssl_config

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
        resolved_ssl_config: dict[str, str] = {}
        if ssl_enable:
            ssl_enable, resolved_ssl_config = self._resolve_dashboard_ssl_config(
                ssl_config,
            )
        scheme = "https" if ssl_enable else "http"

        if not enable:
            logger.info("WebUI disabled.")
            return None

        logger.info("Starting WebUI at %s://%s:%s", scheme, host, port)
        if host == "0.0.0.0":
            logger.info(
                "WebUI listens on all interfaces. Check security. Set dashboard.host in data/cmd_config.json to change it.",
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
                f"3. 如需使用其他端口，请修改配置文件",
            )

            raise Exception(f"端口 {port} 已被占用")

        parts = [f"\n ✨✨✨\n  AstrBot v{VERSION} WebUI is ready\n\n"]
        parts.append(f"   ➜  Local: {scheme}://localhost:{port}\n")
        for ip in ip_addr:
            parts.append(f"   ➜  Network: {scheme}://{ip}:{port}\n")
        parts.append(self._build_dashboard_credentials_display())
        display = "".join(parts)

        if not ip_addr:
            display += (
                "Set dashboard.host in data/cmd_config.json to enable remote access.\n"
            )

        logger.info(display)

        # 配置 Hypercorn
        config = HyperConfig()
        config.bind = [f"{host}:{port}"]
        if bool(self.config.get("dashboard", {}).get("trust_proxy_headers", False)):
            config.logger_class = _ProxyAwareHypercornLogger
        if ssl_enable:
            config.certfile = resolved_ssl_config["certfile"]
            config.keyfile = resolved_ssl_config["keyfile"]
            if "ca_certs" in resolved_ssl_config:
                config.ca_certs = resolved_ssl_config["ca_certs"]

        # 根据配置决定是否禁用访问日志
        disable_access_log = dashboard_config.get("disable_access_log", True)
        if disable_access_log:
            config.accesslog = None
        else:
            # 启用访问日志，使用简洁格式
            config.accesslog = "-"
            config.access_log_format = "%(h)s %(r)s %(s)s %(b)s %(D)s"

        return serve(self.asgi_app, config, shutdown_trigger=self.shutdown_trigger)

    async def shutdown_trigger(self) -> None:
        await self.shutdown_event.wait()
        logger.info("AstrBot WebUI 已经被关闭")
