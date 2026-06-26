import asyncio
import errno
import ipaddress
import os
import platform
import socket
import time
from pathlib import Path
from typing import Any, Protocol, cast

import jwt
import psutil
from fastapi import Request
from fastapi.responses import JSONResponse
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
from astrbot.dashboard.asgi_runtime import DashboardRequestState, FastAPIAppAdapter
from astrbot.dashboard.responses import error
from astrbot.dashboard.services.auth_service import DASHBOARD_JWT_COOKIE_NAME

from .api.app import create_dashboard_asgi_app
from .plugin_page_auth import PluginPageAuth

_RATE_LIMITED_ENDPOINTS: frozenset = frozenset(
    {
        "/api/config/astrbot/update",
        "/api/auth/totp/setup",
        "/api/v1/auth/totp/setup",
        "/api/auth/login",
        "/api/v1/auth/login",
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


def _parse_env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_dashboard_value(
    value: str | int | None, *, field_name: str
) -> str | int | None:
    if not isinstance(value, str):
        return value
    return _expand_env_placeholders(value, field_name).strip()


def _expand_env_placeholders(value: str, field_name: str) -> str:
    missing_vars: list[str] = []
    import re

    pattern = re.compile(
        r"\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^}]*)?\}|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))"
    )

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

    expanded = pattern.sub(_replace, value)
    if missing_vars:
        missing = ", ".join(sorted(set(missing_vars)))
        raise ValueError(
            f"Unresolved environment variable(s) in dashboard {field_name}: {missing}"
        )
    return expanded


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
    """AstrBot Web Dashboard"""

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
        self._webui_fallback = False

        self._init_paths(webui_dir)
        self._rate_limiter_registry = _RateLimiterRegistry()
        self._init_jwt_secret()

        self.asgi_app = create_dashboard_asgi_app(
            core_lifecycle=core_lifecycle,
            db=db,
            jwt_secret=self._jwt_secret,
            static_folder=self.data_path,
        )

        self.app = FastAPIAppAdapter(self.asgi_app, static_folder=self.data_path)
        self.asgi_app.state.dashboard_app_adapter = self.app
        self.app._dashboard_server = self

        global APP
        APP = self.app

        self.app.config["MAX_CONTENT_LENGTH"] = 128 * 1024 * 1024  # compatibility

        @self.asgi_app.middleware("http")
        async def dashboard_auth_middleware(current_request: Request, call_next):
            current_request.state.dashboard_g = DashboardRequestState()
            auth_response = await self.auth_middleware(current_request)
            if auth_response is not None:
                return auth_response
            return await call_next(current_request)

    def _check_webui_enabled(self) -> bool:
        cfg = self.config.get("dashboard", {})
        _env = os.environ.get("ASTRBOT_DASHBOARD_ENABLE")
        if _env is not None:
            return _env.lower() in ("true", "1", "yes")
        return cfg.get("enable", True)

    def _init_paths(self, webui_dir: str | None):
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
                self.data_path = os.path.abspath(user_dist)

        if self.enable_webui and not (Path(self.data_path) / "index.html").exists():
            logger.warning(
                "前端未内置或未初始化 (index.html missing in %s), "
                "回退到仅启动后端. 请访问在线面板: dash.astrbot.men",
                self.data_path,
            )
            self.enable_webui = False
            self._webui_fallback = True

    async def auth_middleware(self, current_request: Request):
        path = current_request.url.path
        if not path.startswith("/api"):
            return None

        rate_limit_response = await self._apply_auth_rate_limit(current_request, path)
        if rate_limit_response is not None:
            return rate_limit_response

        if path.startswith("/api/v1"):
            return None

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
            "/api/backup/download",
        ]
        if path in allowed_exact_endpoints or any(
            path.startswith(prefix) for prefix in allowed_endpoint_prefixes
        ):
            return None

        is_plugin_page_path = PluginPageAuth.is_protected_path(path)
        token = self._extract_dashboard_jwt(current_request)
        if not token and is_plugin_page_path:
            token = PluginPageAuth.extract_asset_token(current_request.query_params)
        if not token:
            r = JSONResponse(error("未授权"))
            r.status_code = 401
            return r
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])
            if PluginPageAuth.is_asset_token(
                payload
            ) and not PluginPageAuth.is_scope_valid(payload, path):
                r = JSONResponse(error("Token 无效"))
                r.status_code = 401
                return r

            username = payload.get("username")
            if not isinstance(username, str) or not username.strip():
                raise jwt.InvalidTokenError("missing username in token payload")
            current_request.state.dashboard_g.username = username
        except jwt.ExpiredSignatureError:
            r = JSONResponse(error("Token 过期"))
            r.status_code = 401
            return r
        except jwt.InvalidTokenError:
            r = JSONResponse(error("Token 无效"))
            r.status_code = 401
            return r

    async def _apply_auth_rate_limit(
        self,
        current_request: Request,
        path: str,
    ) -> JSONResponse | None:
        if (
            os.environ.get("ASTRBOT_TEST_MODE") != "true"
            and path in _RATE_LIMITED_ENDPOINTS
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
                client_ip = self._get_request_client_ip(current_request)
                limiter = self._rate_limiter_registry.get_or_create(
                    client_ip, capacity=max_burst, refill_rate=refill_rate
                )
                if not await limiter.acquire():
                    r = JSONResponse(
                        error("验证尝试过于频繁，系统可能正在遭受暴力破解")
                    )
                    r.status_code = 429
                    return r
        return None

    def check_port_in_use(self, host: str, port: int) -> bool:
        """跨平台检测端口是否被占用"""
        probe_host = host
        if host in ("", "0.0.0.0"):
            probe_host = "127.0.0.1"
        elif host == "::":
            probe_host = "::1"

        family = socket.AF_INET6 if ":" in probe_host else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((probe_host, port))
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

    def _init_jwt_secret(self) -> None:
        dashboard_cfg = self.config.setdefault("dashboard", {})
        if not dashboard_cfg.get("jwt_secret"):
            dashboard_cfg["jwt_secret"] = os.urandom(32).hex()
            self.config.save_config()
            logger.info("Initialized random JWT secret for dashboard.")
        self._jwt_secret = dashboard_cfg["jwt_secret"]

    def _get_request_client_ip(self, current_request: Request) -> str:
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

        remote_addr = (
            str(current_request.client.host).strip() if current_request.client else ""
        )
        if remote_addr:
            try:
                return str(ipaddress.ip_address(remote_addr))
            except ValueError:
                pass

        return "unknown"

    @staticmethod
    def _extract_dashboard_jwt(current_request: Request) -> str | None:
        auth_header = current_request.headers.get("Authorization", "").strip()
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
            if token:
                return token

        cookie_token = current_request.cookies.get(
            DASHBOARD_JWT_COOKIE_NAME, ""
        ).strip()
        if cookie_token:
            return cookie_token
        return None

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
            or os.environ.get("ASTRBOT_SSL_CERT")
            or ssl_config.get("cert_file", "")
        )
        key_file = (
            os.environ.get("DASHBOARD_SSL_KEY")
            or os.environ.get("ASTRBOT_DASHBOARD_SSL_KEY")
            or os.environ.get("ASTRBOT_SSL_KEY")
            or ssl_config.get("key_file", "")
        )
        ca_certs = (
            os.environ.get("DASHBOARD_SSL_CA_CERTS")
            or os.environ.get("ASTRBOT_DASHBOARD_SSL_CA_CERTS")
            or os.environ.get("ASTRBOT_SSL_CA_CERTS")
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
                f"dashboard.ssl.enable is set, but cert file is missing: {cert_path}. SSL disabled."
            )
            return False, {}
        if not key_path.is_file():
            logger.warning(
                f"dashboard.ssl.enable is set, but key file is missing: {key_path}. SSL disabled."
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
                    f"dashboard.ssl.enable is set, but CA cert file is missing: {ca_path}. SSL disabled."
                )
                return False, {}
            resolved_ssl_config["ca_certs"] = str(ca_path.resolve())

        return True, resolved_ssl_config

    async def run(self) -> None:
        if self._webui_fallback:
            logger.warning(
                "前端未内置或未初始化, 回退到仅启动后端. 请访问在线面板: dash.astrbot.men",
            )
        elif not self.enable_webui:
            logger.warning("前端已禁用, 请访问在线面板: dash.astrbot.men")

        dashboard_config = self.core_lifecycle.astrbot_config.get("dashboard", {})

        host_value = (
            os.environ.get("DASHBOARD_HOST")
            or os.environ.get("ASTRBOT_DASHBOARD_HOST")
            or os.environ.get("ASTRBOT_HOST")
            or dashboard_config.get("host", "0.0.0.0")
        )
        host = _normalize_dashboard_value(host_value, field_name="host")
        if not isinstance(host, str) or not host:
            raise ValueError("Dashboard host must be a non-empty string")

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

        port_value = (
            os.environ.get("DASHBOARD_PORT")
            or os.environ.get("ASTRBOT_DASHBOARD_PORT")
            or dashboard_config.get("port", 6185)
        )
        port = _normalize_dashboard_value(port_value, field_name="port")
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise ValueError("Dashboard port must be an integer between 1 and 65535")

        scheme = "https" if ssl_enable else "http"
        ip_addr: list[Any] = get_local_ip_addresses()
        binds: list[str] = [self._build_bind(host, port)]
        if host == "::" and platform.system() in ("Windows", "Darwin"):
            binds.append(self._build_bind("0.0.0.0", port))

        logger.info("Starting WebUI at %s://%s:%s", scheme, host, port)
        if host == "0.0.0.0":
            logger.info(
                "WebUI listens on all interfaces. Check security. Set dashboard.host in data/cmd_config.json to change it.",
            )

        if not self.enable_webui:
            logger.info(
                "API server is enabled only. Listening on: %s",
                ", ".join(f"{scheme}://{bind}" for bind in binds),
            )
            logger.info(
                "\n ✨✨✨\n  AstrBot v%s API Server is ready\n",
                VERSION,
            )
        else:
            logger.info(
                "正在启动 WebUI + API, 监听: %s",
                ", ".join(f"{scheme}://{bind}" for bind in binds),
            )

        check_hosts = {host}
        if host not in ("127.0.0.1", "localhost", "::1"):
            check_hosts.add("127.0.0.1")
        for check_host in check_hosts:
            if self.check_port_in_use(check_host, port):
                info = self.get_process_using_port(port)
                raise RuntimeError(f"端口 {port} 已被占用\n{info}")

        parts = [f"\n ✨✨✨\n  AstrBot v{VERSION} WebUI is ready\n\n"]
        if self.enable_webui:
            parts.append(f"   ➜  本地: {scheme}://localhost:{port}\n")
        for ip in ip_addr:
            if self.enable_webui or ip != "127.0.0.1":
                parts.append(f"   ➜  Network: {scheme}://{ip}:{port}\n")
        parts.append(self._build_dashboard_credentials_display())
        if not ip_addr:
            parts.append(
                "Set dashboard.host in data/cmd_config.json to enable remote access.\n"
            )
        logger.info("".join(parts))

        config = HyperConfig()
        config.bind = binds
        if bool(self.config.get("dashboard", {}).get("trust_proxy_headers", False)):
            config.logger_class = _ProxyAwareHypercornLogger
        if ssl_enable:
            config.certfile = resolved_ssl_config["certfile"]
            config.keyfile = resolved_ssl_config["keyfile"]
            if ca_certs := resolved_ssl_config.get("ca_certs"):
                config.ca_certs = ca_certs

        disable_access_log = dashboard_config.get("disable_access_log", True)
        if disable_access_log:
            config.accesslog = None
        else:
            config.accesslog = "-"
            config.access_log_format = "%(h)s %(r)s %(s)s %(b)s %(D)s"

        return await serve(
            cast(Any, self.asgi_app), config, shutdown_trigger=self.shutdown_trigger
        )

    @staticmethod
    def _build_bind(host: str, port: int) -> str:
        try:
            ip = ipaddress.ip_address(host)
            return f"[{ip}]:{port}" if ip.version == 6 else f"{ip}:{port}"
        except ValueError:
            return f"{host}:{port}"

    async def shutdown_trigger(self):
        await self.shutdown_event.wait()
        logger.info("AstrBot WebUI 已经被关闭")
