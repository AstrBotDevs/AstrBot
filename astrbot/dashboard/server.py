import asyncio
import copy
import ipaddress
import os
import re
import socket
import time
from pathlib import Path
from typing import Any, Protocol, Self, cast

import psutil
from fastapi import Request
from fastapi.responses import JSONResponse
from hypercorn.asyncio import serve
from hypercorn.config import Config as HyperConfig
from hypercorn.logging import AccessLogAtoms
from hypercorn.logging import Logger as HypercornLogger

from astrbot import logger
from astrbot.core.config.default import VERSION
from astrbot.core.core_runtime import CoreControl, CoreRuntime
from astrbot.core.db.protocols import DashboardStore
from astrbot.core.utils.io import get_local_ip_addresses
from astrbot.dashboard.request_state import DashboardRequestState
from astrbot.dashboard.responses import error

from .api.app import create_dashboard_asgi_app

_RATE_LIMITED_ENDPOINTS: frozenset = frozenset(
    {
        "/api/config/astrbot/update",
        "/api/v1/auth/totp/setup",
        "/api/v1/auth/login",
    }
)
_SECRET_RAW_PATH_RE = re.compile(
    r"^(/api/plugin-pages/v1/sessions/|/api/plugin-files/v1/)[^/]+"
)


async def initialize_dashboard_jwt_secret(config: Any) -> str:
    """Return a persisted Dashboard JWT secret.

    A Dashboard server must never begin serving with a newly generated secret
    that was not durably saved.  The configuration mutation is rolled back if
    the asynchronous write fails, so a later startup can safely retry.

    Args:
        config: The initialized AstrBot configuration object.

    Returns:
        The existing or newly persisted JWT secret.
    """
    dashboard_config = config.get("dashboard")
    if not isinstance(dashboard_config, dict):
        raise ValueError("Dashboard configuration is missing or invalid.")

    configured_secret = dashboard_config.get("jwt_secret")
    if configured_secret:
        return str(configured_secret)

    next_config = copy.deepcopy(dict(config))
    next_dashboard_config = next_config["dashboard"]
    jwt_secret = os.urandom(32).hex()
    next_dashboard_config["jwt_secret"] = jwt_secret

    previous_dashboard_config = copy.deepcopy(dashboard_config)
    dashboard_config.clear()
    dashboard_config.update(next_dashboard_config)
    try:
        committed = await config.save_config_async()
    except BaseException:
        dashboard_config.clear()
        dashboard_config.update(previous_dashboard_config)
        raise

    if not committed:
        # A later configuration revision won the write race. Do not start a
        # Dashboard with the locally generated secret unless it was durably
        # committed. Only restore our own unchanged mutation; a newer writer
        # may already have supplied a different Dashboard configuration.
        if dashboard_config == next_dashboard_config:
            dashboard_config.clear()
            dashboard_config.update(previous_dashboard_config)
        raise RuntimeError(
            "Dashboard JWT secret initialization was superseded by a newer "
            "configuration update."
        )

    logger.info("Initialized random JWT secret for dashboard.")
    return jwt_secret


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
    _MAX_ENTRIES: int = 10_000

    def __init__(self) -> None:
        self._limiters: dict[str, _AuthRateLimiter] = {}
        self._last_eviction = time.monotonic()

    def get_or_create(
        self, key: str, capacity: int, refill_rate: float
    ) -> _AuthRateLimiter:
        self._evict_expired()
        limiter = self._limiters.get(key)
        if limiter is None:
            if len(self._limiters) >= self._MAX_ENTRIES:
                oldest_key = min(
                    self._limiters,
                    key=lambda item: self._limiters[item].last_accessed,
                )
                del self._limiters[oldest_key]
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
        path = str(request.get("path", ""))
        redacted_path = _SECRET_RAW_PATH_RE.sub(r"\1<redacted>", path)
        if redacted_path != path:
            method = str(request.get("method", "GET"))
            protocol = request.get("http_version", "ws")
            atoms["r"] = f"{method} {redacted_path} {protocol}"
            atoms["R"] = atoms["r"]
            atoms["U"] = redacted_path
            atoms["Uq"] = redacted_path
            atoms["q"] = ""
        client_host = self._get_request_log_host(request)
        if client_host:
            atoms["h"] = client_host
        return atoms


class AstrBotDashboard:
    @classmethod
    async def create(
        cls,
        runtime: CoreRuntime,
        core_control: CoreControl,
        db: DashboardStore,
        shutdown_event: asyncio.Event,
        webui_dir: str | None = None,
    ) -> Self:
        """Persist Dashboard credentials before constructing its ASGI app."""
        jwt_secret = await initialize_dashboard_jwt_secret(runtime.astrbot_config)
        return cls(
            runtime,
            core_control,
            db,
            shutdown_event,
            webui_dir,
            jwt_secret=jwt_secret,
        )

    def __init__(
        self,
        runtime: CoreRuntime,
        core_control: CoreControl,
        db: DashboardStore,
        shutdown_event: asyncio.Event,
        webui_dir: str | None = None,
        *,
        jwt_secret: str,
    ) -> None:
        self.runtime = runtime
        self.core_control = core_control
        self.config = runtime.astrbot_config
        self.db = db
        self.data_path = (
            os.path.abspath(webui_dir)
            if webui_dir and os.path.isdir(webui_dir)
            else None
        )

        self._rate_limiter_registry = _RateLimiterRegistry()
        self._jwt_secret = jwt_secret
        self.asgi_app = create_dashboard_asgi_app(
            runtime=runtime,
            core_control=core_control,
            db=db,
            jwt_secret=self._jwt_secret,
            static_folder=self.data_path,
        )
        self.asgi_app.state.dashboard_server = self
        self.asgi_app.state.dashboard_config["MAX_CONTENT_LENGTH"] = (
            128 * 1024 * 1024
        )  # 将 Flask 允许的最大上传文件体大小设置为 128 MB
        self.app = self.asgi_app

        @self.asgi_app.middleware("http")
        async def dashboard_auth_middleware(request_, call_next):
            request_.state.dashboard_request_state = DashboardRequestState()
            auth_response = await self.auth_middleware(request_)
            if auth_response is not None:
                return auth_response
            return await call_next(request_)

        self.shutdown_event = shutdown_event

    async def auth_middleware(self, current_request: Request):
        path = current_request.url.path
        if not path.startswith("/api"):
            return None
        rate_limit_response = await self._apply_auth_rate_limit(current_request, path)
        if rate_limit_response is not None:
            return rate_limit_response
        return None

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

        remote_addr = (
            str(current_request.client.host).strip()
            if current_request.client is not None
            else ""
        )
        if remote_addr:
            try:
                return str(ipaddress.ip_address(remote_addr))
            except ValueError:
                pass

        return "unknown"

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
        dashboard_config = self.runtime.astrbot_config.get("dashboard", {})
        port = (
            os.environ.get("DASHBOARD_PORT")
            or os.environ.get("ASTRBOT_DASHBOARD_PORT")
            or dashboard_config.get("port", 6185)
        )
        host = (
            os.environ.get("DASHBOARD_HOST")
            or os.environ.get("ASTRBOT_DASHBOARD_HOST")
            or dashboard_config.get("host", "127.0.0.1")
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
        if host == str(ipaddress.IPv4Address(0)):
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

        if self.data_path and (Path(self.data_path) / "index.html").is_file():
            webui_status = "WebUI is ready"
        else:
            webui_status = (
                f"WebUI is NOT ready: static files are missing at {self.data_path}"
            )
        parts = [f"\n ✨✨✨\n  AstrBot v{VERSION} {webui_status}\n\n"]
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

        return serve(
            cast(Any, self.asgi_app), config, shutdown_trigger=self.shutdown_trigger
        )

    async def shutdown_trigger(self) -> None:
        await self.shutdown_event.wait()
        logger.info("AstrBot WebUI 已经被关闭")
