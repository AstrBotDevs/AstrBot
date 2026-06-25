# 导入 asyncio 模块，用于异步编程
import asyncio
# 导入 ipaddress 模块，用于处理 IP 地址的解析和验证
import ipaddress
# 导入 os 模块，用于操作系统相关功能（环境变量、文件路径等）
import os
# 导入 socket 模块，用于网络通信和端口检测
import socket
# 导入 time 模块，用于时间相关的操作
import time
# 从 pathlib 导入 Path 类，用于面向对象的文件路径操作
from pathlib import Path
# 从 typing 导入类型提示相关工具：Any 任意类型、Protocol 协议类、cast 类型转换
from typing import Any, Protocol, cast

# 导入 jwt 库，用于 JSON Web Token 的编码和解码
import jwt
# 导入 psutil 库，用于获取系统和进程信息
import psutil
# 从 fastapi 导入 Request 类，表示 HTTP 请求对象
from fastapi import Request
# 从 fastapi.responses 导入 JSONResponse，用于返回 JSON 格式的响应
from fastapi.responses import JSONResponse
# 从 hypercorn.asyncio 导入 serve 函数，用于启动 ASGI 服务器
from hypercorn.asyncio import serve
# 从 hypercorn.config 导入 Config 并重命名为 HyperConfig，用于配置服务器
from hypercorn.config import Config as HyperConfig
# 从 hypercorn.logging 导入 AccessLogAtoms，表示访问日志的原子数据
from hypercorn.logging import AccessLogAtoms
# 从 hypercorn.logging 导入 Logger 并重命名为 HypercornLogger，表示日志记录器
from hypercorn.logging import Logger as HypercornLogger

# 从 astrbot.core 导入 logger 对象，用于记录日志
from astrbot.core import logger
# 从配置默认模块导入 VERSION 常量，表示当前核心版本号
from astrbot.core.config.default import VERSION
# 导入核心生命周期管理器类
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
# 导入数据库抽象基类
from astrbot.core.db import BaseDatabase
# 导入获取 AstrBot 数据目录路径的工具函数
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
# 从 IO 工具模块导入多个与仪表盘静态文件相关的工具函数
from astrbot.core.utils.io import (
    get_bundled_dashboard_dist_path,       # 获取打包的内置仪表盘静态文件路径
    get_dashboard_dist_version,             # 获取仪表盘静态文件的版本号
    get_local_ip_addresses,                 # 获取本机的所有 IP 地址列表
    is_dashboard_dist_compatible,           # 检查仪表盘静态文件是否与当前核心版本兼容
    should_use_bundled_dashboard_dist,      # 判断是否应该使用内置的仪表盘静态文件
)
# 从仪表盘的 ASGI 运行时模块导入相关类
from astrbot.dashboard.asgi_runtime import (
    DashboardRequestState,   # 仪表盘请求状态对象，用于在请求中传递状态信息
    FastAPIAppAdapter,       # FastAPI 应用适配器，封装 ASGI 应用
)
# 从仪表盘响应模块导入 error 函数，用于构造错误响应
from astrbot.dashboard.responses import error

# 从当前包的 api.app 模块导入创建仪表盘 ASGI 应用的工厂函数
from .api.app import create_dashboard_asgi_app
# 导入插件页面认证类，用于验证插件页面的访问权限
from .plugin_page_auth import PluginPageAuth
# 从认证服务模块导入 JWT Cookie 名称常量
from .services.auth_service import DASHBOARD_JWT_COOKIE_NAME

# 定义需要进行速率限制的 API 端点集合（使用 frozenset 使其不可变）
# 这些端点涉及登录和更新等敏感操作，需要防止暴力破解
_RATE_LIMITED_ENDPOINTS: frozenset = frozenset(
    {
        "/api/config/astrbot/update",     # 更新配置端点
        "/api/auth/totp/setup",           # TOTP 设置端点
        "/api/v1/auth/totp/setup",        # v1 版本的 TOTP 设置端点
        "/api/auth/login",                # 登录端点
        "/api/v1/auth/login",             # v1 版本的登录端点
    }
)


# 基于令牌桶算法的认证速率限制器类
class _AuthRateLimiter:
    # 初始化速率限制器，设置桶容量和令牌补充速率
    def __init__(self, capacity: int, refill_rate: float):
        # 桶的最大容量（允许的最大突发请求数）
        self.capacity = capacity
        # 令牌补充速率（每秒补充的令牌数）
        self.refill_rate = refill_rate
        # 当前桶中的令牌数量，初始为满桶
        self.tokens = float(capacity)
        # 上次补充令牌的时间戳
        self.last_refill = time.monotonic()
        # 上次访问时间，用于过期淘汰判断
        self.last_accessed = time.monotonic()
        # 异步锁，确保并发安全
        self.lock = asyncio.Lock()

    # 尝试获取一个令牌，返回是否成功
    async def acquire(self) -> bool:
        # 使用异步锁保护临界区
        async with self.lock:
            # 获取当前时间
            now = time.monotonic()
            # 计算距离上次补充经过的时间
            elapsed = now - self.last_refill
            # 根据经过的时间和补充速率计算新令牌数，不超过桶容量
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            # 更新上次补充时间
            self.last_refill = now
            # 更新最后访问时间
            self.last_accessed = now
            # 如果桶中至少有一个令牌
            if self.tokens >= 1:
                # 消耗一个令牌
                self.tokens -= 1
                return True
            # 令牌不足，请求被限流
            return False


# 基于 IP 的令牌桶速率限制器注册表类
class _RateLimiterRegistry:
    """Per-IP token-bucket rate limiter registry. Idle entries expire after 1 hour."""
    # 每个 IP 限流器实例的过期时间（秒），闲置超过此时间将被清除
    _ENTRY_TTL: float = 3600.0  # 1 小时
    # 过期清理的时间间隔（秒），每半小时检查一次
    _INTERVAL: float = 1800.0   # 30 分钟

    # 初始化注册表
    def __init__(self) -> None:
        # 存储 IP 地址到速率限制器实例的映射字典
        self._limiters: dict[str, _AuthRateLimiter] = {}
        # 上次执行过期清理的时间戳
        self._last_eviction = time.monotonic()

    # 获取或创建指定 IP 的速率限制器
    def get_or_create(
        self, key: str, capacity: int, refill_rate: float
    ) -> _AuthRateLimiter:
        # 先执行过期清理（根据时间间隔判断是否需要清理）
        self._evict_expired()
        # 尝试获取已存在的限制器
        limiter = self._limiters.get(key)
        # 如果不存在
        if limiter is None:
            # 创建新的速率限制器实例
            limiter = _AuthRateLimiter(capacity=capacity, refill_rate=refill_rate)
            # 存入注册表
            self._limiters[key] = limiter
        # 返回限制器
        return limiter

    # 清除过期的速率限制器条目
    def _evict_expired(self) -> None:
        # 获取当前时间
        now = time.monotonic()
        # 如果距离上次清理未达到间隔时间，则跳过
        if now - self._last_eviction < self._INTERVAL:
            return
        # 更新上次清理时间
        self._last_eviction = now
        # 计算过期时间点（当前时间减去 TTL）
        cutoff = now - self._ENTRY_TTL
        # 找出所有最后访问时间早于过期时间点的 IP 列表
        stale = [k for k, v in self._limiters.items() if v.last_accessed < cutoff]
        # 删除所有过期的条目
        for k in stale:
            del self._limiters[k]

    # 清空所有速率限制器
    def clear(self) -> None:
        self._limiters.clear()

    # 返回当前注册的限制器数量
    def __len__(self) -> int:
        return len(self._limiters)

    # 检查指定 IP 是否有对应的限制器
    def __contains__(self, key: str) -> bool:
        return key in self._limiters


# 定义带有 port 属性的协议类，用于类型提示
class _AddrWithPort(Protocol):
    # 端口号属性
    port: int


# 全局变量，存储当前的 FastAPI 应用适配器实例，初始为 None
APP: FastAPIAppAdapter | None = None


# 解析环境变量中的布尔值
def _parse_env_bool(value: str | None, default: bool) -> bool:
    # 如果值为 None，返回默认值
    if value is None:
        return default
    # 去除首尾空格并转为小写，判断是否在真值集合中
    return value.strip().lower() in {"1", "true", "yes", "on"}


# 支持代理感知的 Hypercorn 日志记录器类
class _ProxyAwareHypercornLogger(HypercornLogger):
    # 静态方法：从请求作用域中提取真实的客户端 IP 地址
    @staticmethod
    def _get_request_log_host(request_scope) -> str | None:
        # 初始化代理头变量
        forwarded_for = None
        real_ip = None
        # 遍历请求头
        for raw_name, raw_value in request_scope.get("headers", []):
            # 解码头名称并转为小写
            header_name = raw_name.decode("latin1").lower()
            # 如果找到 X-Forwarded-For 头
            if header_name == "x-forwarded-for":
                # 解码并存储其值
                forwarded_for = raw_value.decode("latin1")
            # 如果找到 X-Real-IP 头
            elif header_name == "x-real-ip":
                # 解码并存储其值
                real_ip = raw_value.decode("latin1")

            # 如果两个头都找到了，提前跳出循环
            if forwarded_for is not None and real_ip is not None:
                break

        # 处理 X-Forwarded-For 头，提取第一个 IP
        forwarded_for = str(forwarded_for or "").strip()
        if forwarded_for:
            # 用逗号分割，取第一个 IP 地址
            first_ip = forwarded_for.split(",", 1)[0].strip()
            # 如果 IP 有效且不是 "unknown"
            if first_ip and first_ip.lower() != "unknown":
                try:
                    # 尝试解析为 IP 地址并返回
                    return str(ipaddress.ip_address(first_ip))
                except ValueError:
                    # 解析失败则继续尝试其他方式
                    pass

        # 处理 X-Real-IP 头
        real_ip = str(real_ip or "").strip()
        if real_ip and real_ip.lower() != "unknown":
            try:
                # 尝试解析并返回
                return str(ipaddress.ip_address(real_ip))
            except ValueError:
                pass

        # 如果代理头都不可用，尝试从连接信息中获取
        client = request_scope.get("client")
        if not client:
            return None
        # 提取客户端 IP 地址
        host = str(client[0]).strip()
        if host:
            return host
        return None

    # 重写 atoms 方法，使用代理感知的 IP 地址构建访问日志
    def atoms(self, request, response, request_time):
        # 调用父类方法获取基本日志原子数据
        atoms = AccessLogAtoms(request, response, request_time)
        # 获取真实的客户端 IP
        client_host = self._get_request_log_host(request)
        # 如果获取到了真实 IP
        if client_host:
            # 替换日志中的主机地址
            atoms["h"] = client_host
        return atoms


# AstrBot 仪表盘主类，管理 WebUI 的配置、启动和运行
class AstrBotDashboard:
    # 初始化仪表盘实例
    def __init__(
        self,
        core_lifecycle: AstrBotCoreLifecycle,  # 核心生命周期管理器
        db: BaseDatabase,                      # 数据库实例
        shutdown_event: asyncio.Event,         # 关闭事件，用于通知服务器停止
        webui_dir: str | None = None,          # WebUI 静态文件目录路径（可选）
    ) -> None:
        # 保存核心生命周期引用
        self.core_lifecycle = core_lifecycle
        # 保存配置对象引用
        self.config = core_lifecycle.astrbot_config
        # 保存数据库引用
        self.db = db

        # 确定静态文件路径的优先级顺序：
        # 1. 明确指定的 webui_dir 参数
        # 2. data/dist/ 目录（如果与核心版本匹配）
        # 3. 内置的 astrbot/dashboard/dist/ 目录（如果与核心版本匹配）
        if webui_dir and os.path.exists(webui_dir):
            # 如果指定了路径且存在，使用该路径
            self.data_path = os.path.abspath(webui_dir)
        else:
            # 获取用户数据目录下的 dist 路径
            user_dist = os.path.join(get_astrbot_data_path(), "dist")
            # 获取内置打包的仪表盘静态文件路径
            bundled_dist = get_bundled_dashboard_dist_path()
            # 获取用户 dist 目录的版本
            user_version = get_dashboard_dist_version(user_dist)
            # 如果用户 dist 存在且与当前核心版本兼容
            if os.path.exists(user_dist) and is_dashboard_dist_compatible(
                user_dist,
                VERSION,
            ):
                # 使用用户 dist 目录
                self.data_path = os.path.abspath(user_dist)
            # 如果建议使用内置版本，或内置版本兼容
            elif should_use_bundled_dashboard_dist(
                user_dist,
                VERSION,
            ) or is_dashboard_dist_compatible(bundled_dist, VERSION):
                # 使用内置打包的静态文件路径
                self.data_path = str(bundled_dist)
                # 记录日志
                logger.info("Using bundled dashboard dist: %s", self.data_path)
            # 如果用户 dist 存在且包含 index.html
            elif (
                os.path.exists(user_dist) and (Path(user_dist) / "index.html").is_file()
            ):
                # 警告：版本不匹配，但回退使用用户 dist
                logger.warning(
                    "Using existing data/dist as a fallback even though WebUI version mismatches core: %s, expected v%s. "
                    "Some dashboard features may not work until the matching WebUI is available.",
                    user_version,
                    VERSION,
                )
                self.data_path = os.path.abspath(user_dist)
            # 如果用户 dist 存在但不完整
            elif os.path.exists(user_dist):
                # 警告：文件不完整，忽略
                logger.warning(
                    "Ignoring data/dist because WebUI files are incomplete for core v%s.",
                    VERSION,
                )
                self.data_path = None
            else:
                # 最后回退到用户路径（后续会优雅失败）
                self.data_path = os.path.abspath(user_dist)

        # 创建速率限制器注册表
        self._rate_limiter_registry = _RateLimiterRegistry()
        # 初始化 JWT 密钥
        self._init_jwt_secret()
        # 创建 ASGI 应用（包括所有 API 路由和服务）
        self.asgi_app = create_dashboard_asgi_app(  # 启动dashboard页面
            core_lifecycle=core_lifecycle,
            db=db,
            jwt_secret=self._jwt_secret,
            static_folder=self.data_path,
        )
        # 创建 FastAPI 应用适配器，封装 ASGI 应用
        self.app = FastAPIAppAdapter(self.asgi_app, static_folder=self.data_path)
        # 将适配器实例挂载到 ASGI 应用的状态中，方便路由访问
        self.asgi_app.state.dashboard_app_adapter = self.app
        # 建立反向引用，让适配器可以访问仪表盘服务器实例
        self.app._dashboard_server = self
        # 设置全局 APP 变量
        global APP
        APP = self.app
        # 设置最大上传文件体大小限制为 128 MB
        self.app.config["MAX_CONTENT_LENGTH"] = (
            128 * 1024 * 1024
        )  # 将 Flask 允许的最大上传文件体大小设置为 128 MB

        # 注册 HTTP 中间件，用于仪表盘认证
        @self.asgi_app.middleware("http")
        async def dashboard_auth_middleware(request_, call_next):
            # 初始化请求状态对象
            request_.state.dashboard_g = DashboardRequestState()
            # 调用认证中间件
            auth_response = await self.auth_middleware(request_)
            # 如果认证失败（返回了错误响应），直接返回
            if auth_response is not None:
                return auth_response
            # 认证成功，继续处理请求
            return await call_next(request_)

        # 保存关闭事件引用
        self.shutdown_event = shutdown_event

    # 认证中间件：验证请求的 JWT 令牌和权限
    async def auth_middleware(self, current_request: Request):
        # 获取请求路径
        path = current_request.url.path
        # 如果路径不以 /api 开头，不需要认证
        if not path.startswith("/api"):
            return None
        # 应用速率限制检查
        rate_limit_response = await self._apply_auth_rate_limit(current_request, path)
        # 如果触发了速率限制，返回错误响应
        if rate_limit_response is not None:
            return rate_limit_response
        # V1 版本的 API 使用不同的认证机制（OpenAPI Bearer Token），此处放行
        if path.startswith("/api/v1"):
            return None

        # 定义不需要认证的精确匹配端点集合
        allowed_exact_endpoints = {
            "/api/auth/login",          # 登录接口
            "/api/auth/logout",         # 登出接口
            "/api/auth/setup-status",   # 设置状态查询
            "/api/auth/setup",          # 初始设置
            "/api/stat/versions",       # 版本信息查询
        }
        # 定义不需要认证的路径前缀列表
        allowed_endpoint_prefixes = [
            "/api/file",                # 文件相关接口
            "/api/v1/files/tokens",     # 文件令牌接口
            "/api/platform/webhook",    # 平台 Webhook 回调
            "/api/stat/start-time",     # 启动时间查询
            "/api/backup/download",     # 备份下载（使用 URL 参数传递 token）
        ]
        # 如果路径在白名单中，跳过认证
        if path in allowed_exact_endpoints or any(
            path.startswith(prefix) for prefix in allowed_endpoint_prefixes
        ):
            return None
        # 检查是否为受保护的插件页面路径
        is_plugin_page_path = PluginPageAuth.is_protected_path(path)
        # 从请求中提取仪表盘 JWT（从 Header 或 Cookie 中）
        dashboard_token = self._extract_dashboard_jwt(current_request)
        # 如果是插件页面路径，尝试从查询参数中提取资产令牌
        asset_token = (
            PluginPageAuth.extract_asset_token(current_request.query_params)
            if is_plugin_page_path
            else None
        )
        # 收集所有候选令牌
        token_candidates = []
        if dashboard_token:
            token_candidates.append(dashboard_token)
        if asset_token and asset_token != dashboard_token:
            token_candidates.append(asset_token)
        # 如果没有提供任何令牌，返回 401 未授权
        if not token_candidates:
            r = JSONResponse(error("未授权"))
            r.status_code = 401
            return r

        # 记录验证失败的错误信息
        token_errors: list[str] = []
        # 遍历候选令牌进行验证
        for token in token_candidates:
            # 验证令牌有效性
            payload, token_error = self._validate_dashboard_token(token, path)
            # 如果验证成功
            if payload is not None:
                # 将用户名存入请求状态
                current_request.state.dashboard_g.username = cast(
                    str, payload["username"]
                )
                return None
            # 记录错误信息
            token_errors.append(token_error)

        # 根据错误类型返回不同的错误消息
        error_message = (
            "Token 过期"
            if token_errors and all(item == "Token 过期" for item in token_errors)
            else "Token 无效"
        )
        r = JSONResponse(error(error_message))
        r.status_code = 401
        return r

    # 验证仪表盘 JWT 令牌或插件页面资产令牌
    def _validate_dashboard_token(
        self,
        token: str,  # JWT 令牌字符串
        path: str,   # 当前请求路径，用于插件页面令牌的作用域检查
    ) -> tuple[dict[str, Any] | None, str]:
        """Validate a dashboard JWT or scoped plugin page asset token.

        Args:
            token: JWT value from the Authorization header, cookie, or query string.
            path: Current request path used for plugin page asset token scope checks.

        Returns:
            A tuple of the decoded payload and an error message. The payload is
            present only when the token is valid for the current request path.
        """
        try:
            # 尝试解码 JWT 令牌
            payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            # 令牌过期
            return None, "Token 过期"
        except jwt.InvalidTokenError:
            # 令牌无效
            return None, "Token 无效"

        # 如果是资产令牌，检查作用域是否有效
        if PluginPageAuth.is_asset_token(payload) and not PluginPageAuth.is_scope_valid(
            payload,
            path,
        ):
            return None, "Token 无效"

        # 验证载荷中是否包含有效的用户名
        username = payload.get("username")
        if not isinstance(username, str) or not username.strip():
            return None, "Token 无效"

        # 返回解码后的载荷和空错误消息（表示验证成功）
        return payload, ""

    # 对敏感端点应用认证速率限制
    async def _apply_auth_rate_limit(
        self,
        current_request: Request,
        path: str,
    ) -> JSONResponse | None:
        # 如果不在测试模式且当前路径在速率限制端点集合中
        if (
            os.environ.get("ASTRBOT_TEST_MODE") != "true"
            and path in _RATE_LIMITED_ENDPOINTS
        ):
            # 获取速率限制配置
            rl_config = self.config.get("dashboard", {}).get("auth_rate_limit", {})
            # 检查是否启用速率限制（默认启用）
            rl_enabled = rl_config.get("enable", True)
            if rl_enabled:
                # 获取平均请求间隔（秒），默认 1 秒
                average_interval = float(rl_config.get("average_interval", 1.0))
                # 获取最大突发请求数，默认 3
                max_burst = int(rl_config.get("max_burst", 3))
                # 参数验证和修正
                if average_interval <= 0:
                    average_interval = 1.0
                if max_burst <= 0:
                    max_burst = 3
                # 计算令牌补充速率（每秒补充的令牌数）
                refill_rate = 1.0 / average_interval
                # 获取客户端 IP 地址
                client_ip = self._get_request_client_ip(current_request)
                # 获取或创建该 IP 的速率限制器
                limiter = self._rate_limiter_registry.get_or_create(
                    client_ip, capacity=max_burst, refill_rate=refill_rate
                )
                # 尝试获取令牌
                if not await limiter.acquire():
                    # 令牌不足，返回 429 状态码
                    r = JSONResponse(
                        error("验证尝试过于频繁，系统可能正在遭受暴力破解")
                    )
                    r.status_code = 429
                    return r
        # 速率限制通过或不适用
        return None

    # 获取请求的真实客户端 IP 地址
    def _get_request_client_ip(self, current_request) -> str:
        # 如果配置了信任代理头
        if bool(self.config.get("dashboard", {}).get("trust_proxy_headers", False)):
            # 尝试从 X-Forwarded-For 头获取
            forwarded_for = str(
                current_request.headers.get("X-Forwarded-For", "")
            ).strip()
            if forwarded_for:
                # 取第一个 IP 地址
                first_ip = forwarded_for.split(",", 1)[0].strip()
                # 验证 IP 有效性
                if first_ip and first_ip.lower() != "unknown":
                    try:
                        return str(ipaddress.ip_address(first_ip))
                    except ValueError:
                        pass

            # 尝试从 X-Real-IP 头获取
            real_ip = str(current_request.headers.get("X-Real-IP", "")).strip()
            if real_ip and real_ip.lower() != "unknown":
                try:
                    return str(ipaddress.ip_address(real_ip))
                except ValueError:
                    pass

        # 从连接信息中获取远程地址
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

        # 无法获取有效 IP，返回 unknown
        return "unknown"

    # 从请求中提取仪表盘 JWT 令牌（静态方法）
    @staticmethod
    def _extract_dashboard_jwt(current_request: Request) -> str | None:
        # 尝试从 Authorization 头中提取 Bearer 令牌
        auth_header = current_request.headers.get("Authorization", "").strip()
        if auth_header.startswith("Bearer "):
            # 移除 "Bearer " 前缀并去除空白
            token = auth_header.removeprefix("Bearer ").strip()
            if token:
                return token

        # 尝试从 Cookie 中提取令牌
        cookie_token = current_request.cookies.get(
            DASHBOARD_JWT_COOKIE_NAME,
            "",
        ).strip()
        if cookie_token:
            return cookie_token
        # 没有找到令牌
        return None

    # 检测指定端口是否被占用
    def check_port_in_use(self, port: int) -> bool:
        """跨平台检测端口是否被占用"""
        try:
            # 创建 IPv4 TCP Socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # 设置 SO_REUSEADDR 选项，允许重用地址
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # 设置连接超时时间为 2 秒
            sock.settimeout(2)
            # 尝试连接到本地指定端口
            result = sock.connect_ex(("127.0.0.1", port))
            # 关闭 Socket
            sock.close()
            # result 为 0 表示端口被占用
            return result == 0
        except Exception as e:
            # 出现异常时记录警告日志
            logger.warning(f"检查端口 {port} 时发生错误: {e!s}")
            # 保守起见认为端口可能被占用
            return True

    # 获取占用指定端口的进程详细信息
    def get_process_using_port(self, port: int) -> str:
        """获取占用端口的进程详细信息"""
        try:
            # 遍历所有网络连接
            for conn in psutil.net_connections(kind="inet"):
                # 如果连接的本地端口与指定端口匹配
                if cast(_AddrWithPort, conn.laddr).port == port:
                    try:
                        # 获取占用端口的进程对象
                        process = psutil.Process(conn.pid)
                        # 构造进程详细信息列表
                        proc_info = [
                            f"进程名: {process.name()}",                    # 进程名称
                            f"PID: {process.pid}",                          # 进程 ID
                            f"执行路径: {process.exe()}",                   # 可执行文件路径
                            f"工作目录: {process.cwd()}",                   # 工作目录
                            f"启动命令: {' '.join(process.cmdline())}",     # 完整启动命令
                        ]
                        # 将信息用换行和空格连接
                        return "\n           ".join(proc_info)
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        # 进程不存在或无权限访问
                        return f"无法获取进程详细信息(可能需要管理员权限): {e!s}"
            # 未找到占用端口的进程
            return "未找到占用进程"
        except Exception as e:
            # 获取进程信息失败
            return f"获取进程信息失败: {e!s}"

    # 初始化 JWT 密钥
    def _init_jwt_secret(self) -> None:
        # 检查配置中是否已经设置了 JWT 密钥
        if not self.config.get("dashboard", {}).get("jwt_secret", None):
            # 如果没有设置，生成一个随机的 32 字节密钥（十六进制字符串）
            jwt_secret = os.urandom(32).hex()
            # 将密钥存入配置
            self.config["dashboard"]["jwt_secret"] = jwt_secret
            # 保存配置到文件
            self.config.save_config()
            # 记录日志
            logger.info("Initialized random JWT secret for dashboard.")
        # 从配置中读取 JWT 密钥
        self._jwt_secret = self.config["dashboard"]["jwt_secret"]

    # 构建仪表盘登录凭据显示信息
    def _build_dashboard_credentials_display(self) -> str:
        # 获取用户名
        username = self.config["dashboard"].get("username", "astrbot")
        # 获取生成的初始密码（仅首次设置时存在）
        generated_password = getattr(self.config, "_generated_dashboard_password", None)
        # 如果没有生成的密码，只显示用户名
        if not generated_password:
            return f"   ➜  Username: {username}\n ✨✨✨\n"

        # 如果有生成的初始密码，显示用户名和密码
        credentials_display = (
            f"   ➜  Initial username: {username}\n"
            f"   ➜  Initial password: {generated_password}\n"
            "   ➜  Change it after logging in\n ✨✨✨\n"
        )
        # 清除生成的密码（仅显示一次），避免在后续日志中再次出现
        object.__setattr__(self.config, "_generated_dashboard_password", None)
        return credentials_display

    # 解析并验证仪表盘的 SSL 配置（静态方法）
    @staticmethod
    def _resolve_dashboard_ssl_config(
        ssl_config: dict,
    ) -> tuple[bool, dict[str, str]]:
        # 从环境变量或配置中获取证书文件路径
        cert_file = (
            os.environ.get("DASHBOARD_SSL_CERT")
            or os.environ.get("ASTRBOT_DASHBOARD_SSL_CERT")
            or ssl_config.get("cert_file", "")
        )
        # 从环境变量或配置中获取私钥文件路径
        key_file = (
            os.environ.get("DASHBOARD_SSL_KEY")
            or os.environ.get("ASTRBOT_DASHBOARD_SSL_KEY")
            or ssl_config.get("key_file", "")
        )
        # 从环境变量或配置中获取 CA 证书文件路径
        ca_certs = (
            os.environ.get("DASHBOARD_SSL_CA_CERTS")
            or os.environ.get("ASTRBOT_DASHBOARD_SSL_CA_CERTS")
            or ssl_config.get("ca_certs", "")
        )

        # 如果证书或私钥文件路径缺失，SSL 不可用
        if not cert_file or not key_file:
            logger.warning(
                "dashboard.ssl.enable is set, but cert_file or key_file is missing. SSL disabled.",
            )
            return False, {}

        # 展开用户目录路径（如 ~/ 替换为实际路径）
        cert_path = Path(cert_file).expanduser()
        key_path = Path(key_file).expanduser()
        # 检查证书文件是否存在
        if not cert_path.is_file():
            logger.warning(
                f"dashboard.ssl.enable is set, but cert file is missing: {cert_path}. SSL disabled.",
            )
            return False, {}
        # 检查私钥文件是否存在
        if not key_path.is_file():
            logger.warning(
                f"dashboard.ssl.enable is set, but key file is missing: {key_path}. SSL disabled.",
            )
            return False, {}

        # 构建 SSL 配置字典
        resolved_ssl_config = {
            "certfile": str(cert_path.resolve()),  # 证书文件的绝对路径
            "keyfile": str(key_path.resolve()),    # 私钥文件的绝对路径
        }

        # 如果配置了 CA 证书
        if ca_certs:
            ca_path = Path(ca_certs).expanduser()
            # 检查 CA 证书文件是否存在
            if not ca_path.is_file():
                logger.warning(
                    f"dashboard.ssl.enable is set, but CA cert file is missing: {ca_path}. SSL disabled.",
                )
                return False, {}
            # 添加 CA 证书路径
            resolved_ssl_config["ca_certs"] = str(ca_path.resolve())

        # SSL 配置成功
        return True, resolved_ssl_config

    # 启动仪表盘服务器
    def run(self):
        # 初始化 IP 地址列表
        ip_addr = []
        # 获取仪表盘配置
        dashboard_config = self.core_lifecycle.astrbot_config.get("dashboard", {})
        # 获取端口配置（优先级：环境变量 > 配置文件 > 默认值 6185）
        port = (
            os.environ.get("DASHBOARD_PORT")
            or os.environ.get("ASTRBOT_DASHBOARD_PORT")
            or dashboard_config.get("port", 6185)
        )
        # 获取主机配置（优先级：环境变量 > 配置文件 > 默认值 0.0.0.0）
        host = (
            os.environ.get("DASHBOARD_HOST")
            or os.environ.get("ASTRBOT_DASHBOARD_HOST")
            or dashboard_config.get("host", "0.0.0.0")
        )
        # 是否启用仪表盘
        enable = dashboard_config.get("enable", True)
        # 获取 SSL 配置
        ssl_config = dashboard_config.get("ssl", {})
        # 确保 ssl_config 是字典类型
        if not isinstance(ssl_config, dict):
            ssl_config = {}
        # 解析是否启用 SSL（优先级：环境变量 > 配置文件）
        ssl_enable = _parse_env_bool(
            os.environ.get("DASHBOARD_SSL_ENABLE")
            or os.environ.get("ASTRBOT_DASHBOARD_SSL_ENABLE"),
            bool(ssl_config.get("enable", False)),
        )
        # 初始化 SSL 配置字典
        resolved_ssl_config: dict[str, str] = {}
        # 如果启用了 SSL，解析 SSL 证书配置
        if ssl_enable:
            ssl_enable, resolved_ssl_config = self._resolve_dashboard_ssl_config(
                ssl_config,
            )
        # 根据是否启用 SSL 确定协议方案
        scheme = "https" if ssl_enable else "http"

        # 如果仪表盘被禁用，记录日志并返回
        if not enable:
            logger.info("WebUI disabled.")
            return None

        # 记录启动信息
        logger.info("Starting WebUI at %s://%s:%s", scheme, host, port)
        # 如果监听在所有接口上，发出安全警告
        if host == "0.0.0.0":
            logger.info(
                "WebUI listens on all interfaces. Check security. Set dashboard.host in data/cmd_config.json to change it.",
            )

        # 如果主机不是本地地址，获取本机的 IP 地址列表用于显示
        if host not in ["localhost", "127.0.0.1"]:
            try:
                ip_addr = get_local_ip_addresses()
            except Exception as _:
                pass
        # 确保端口是整数类型
        if isinstance(port, str):
            port = int(port)

        # 检查端口是否被占用
        if self.check_port_in_use(port):
            # 获取占用端口的进程信息
            process_info = self.get_process_using_port(port)
            # 记录错误日志
            logger.error(
                f"错误：端口 {port} 已被占用\n"
                f"占用信息: \n           {process_info}\n"
                f"请确保：\n"
                f"1. 没有其他 AstrBot 实例正在运行\n"
                f"2. 端口 {port} 没有被其他程序占用\n"
                f"3. 如需使用其他端口，请修改配置文件",
            )
            # 抛出异常阻止启动
            raise Exception(f"端口 {port} 已被占用")

        # 检查 WebUI 静态文件是否就绪
        if self.data_path and (Path(self.data_path) / "index.html").is_file():
            webui_status = "WebUI is ready"
        else:
            webui_status = (
                f"WebUI is NOT ready: static files are missing at {self.data_path}"
            )
        # 构建欢迎信息
        parts = [f"\n ✨✨✨\n  AstrBot v{VERSION} {webui_status}\n\n"]
        # 添加本地访问地址
        parts.append(f"   ➜  Local: {scheme}://localhost:{port}\n")
        # 添加网络访问地址
        for ip in ip_addr:
            parts.append(f"   ➜  Network: {scheme}://{ip}:{port}\n")
        # 添加登录凭据信息
        parts.append(self._build_dashboard_credentials_display())
        # 拼接显示字符串
        display = "".join(parts)

        # 如果没有获取到 IP 地址，提示如何启用远程访问
        if not ip_addr:
            display += (
                "Set dashboard.host in data/cmd_config.json to enable remote access.\n"
            )

        # 记录欢迎信息
        logger.info(display)

        # 配置 Hypercorn ASGI 服务器
        config = HyperConfig()
        # 设置绑定的主机和端口
        config.bind = [f"{host}:{port}"]
        # 如果信任代理头，使用代理感知的日志记录器
        if bool(self.config.get("dashboard", {}).get("trust_proxy_headers", False)):
            config.logger_class = _ProxyAwareHypercornLogger
        # 如果启用了 SSL，配置证书
        if ssl_enable:
            config.certfile = resolved_ssl_config["certfile"]
            config.keyfile = resolved_ssl_config["keyfile"]
            if "ca_certs" in resolved_ssl_config:
                config.ca_certs = resolved_ssl_config["ca_certs"]

        # 根据配置决定是否禁用访问日志
        disable_access_log = dashboard_config.get("disable_access_log", True)
        if disable_access_log:
            # 禁用访问日志
            config.accesslog = None
        else:
            # 启用访问日志，使用简洁格式：主机 请求行 状态码 响应大小 响应时间(微秒)
            config.accesslog = "-"
            config.access_log_format = "%(h)s %(r)s %(s)s %(b)s %(D)s"

        # 启动 Hypercorn ASGI 服务器，传入关闭触发器
        return serve(
            cast(Any, self.asgi_app), config, shutdown_trigger=self.shutdown_trigger
        )

    # 关闭触发器协程：等待关闭事件被触发
    async def shutdown_trigger(self) -> None:
        # 等待关闭事件
        await self.shutdown_event.wait()
        # 记录关闭日志
        logger.info("AstrBot WebUI 已经被关闭")