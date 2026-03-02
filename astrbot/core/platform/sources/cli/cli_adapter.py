"""CLI平台适配器

编排层：组合各模块实现CLI测试功能。
"""

import asyncio
import json
import os
import secrets
import time
from collections.abc import Awaitable
from typing import Any

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import Platform, PlatformMetadata
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_temp_path

from ...register import register_platform_adapter
from .cli_event import MessageConverter
from .file_handler import FileHandler
from .socket_handler import (
    SocketClientHandler,
    SocketModeHandler,
    write_connection_info,
)
from .socket_server import create_socket_server, detect_platform

# ------------------------------------------------------------------
# Token管理
# ------------------------------------------------------------------


class TokenManager:
    """Token管理器"""

    TOKEN_FILE = ".cli_token"

    def __init__(self):
        self._token: str | None = None
        self._token_file = os.path.join(get_astrbot_data_path(), self.TOKEN_FILE)

    @property
    def token(self) -> str | None:
        if self._token is None:
            self._token = self._ensure_token()
        return self._token

    def _ensure_token(self) -> str | None:
        try:
            if os.path.exists(self._token_file):
                with open(self._token_file, encoding="utf-8") as f:
                    token = f.read().strip()
                if token:
                    logger.info("[CLI] Authentication token loaded from file")
                    return token

            token = secrets.token_urlsafe(32)
            with open(self._token_file, "w", encoding="utf-8") as f:
                f.write(token)
            try:
                os.chmod(self._token_file, 0o600)
            except OSError:
                pass
            logger.info(f"[CLI] Generated new authentication token: {token}")
            logger.info(f"[CLI] Token saved to: {self._token_file}")
            return token
        except Exception as e:
            logger.error(f"[CLI] Failed to ensure token: {e}")
            logger.warning("[CLI] Authentication disabled due to token error")
            return None

    def validate(self, provided_token: str) -> bool:
        if not self.token:
            return True
        if not provided_token:
            logger.warning("[CLI] Request rejected: missing auth_token")
            return False
        if provided_token != self.token:
            logger.warning(
                f"[CLI] Request rejected: invalid auth_token (length={len(provided_token)})"
            )
            return False
        return True


# ------------------------------------------------------------------
# 会话管理
# ------------------------------------------------------------------


class SessionManager:
    """会话管理器"""

    CLEANUP_INTERVAL = 10

    def __init__(self, ttl: int = 30, enabled: bool = False):
        self.ttl = ttl
        self.enabled = enabled
        self._timestamps: dict[str, float] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._running = False

    def register(self, session_id: str) -> None:
        if not self.enabled:
            return
        if session_id not in self._timestamps:
            self._timestamps[session_id] = time.time()
            logger.debug(
                f"[CLI] Created isolated session: {session_id}, TTL={self.ttl}s"
            )

    def touch(self, session_id: str) -> None:
        if self.enabled and session_id in self._timestamps:
            self._timestamps[session_id] = time.time()

    def is_expired(self, session_id: str) -> bool:
        if not self.enabled:
            return False
        timestamp = self._timestamps.get(session_id)
        if timestamp is None:
            return True
        return time.time() - timestamp > self.ttl

    def start_cleanup_task(self) -> None:
        if not self.enabled:
            return
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"[CLI] Session cleanup task started, TTL={self.ttl}s")

    async def stop_cleanup_task(self) -> None:
        self._running = False
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                if not self.enabled:
                    continue
                current_time = time.time()
                expired = [
                    sid
                    for sid, ts in list(self._timestamps.items())
                    if current_time - ts > self.ttl
                ]
                for session_id in expired:
                    logger.info(f"[CLI] Cleaning expired session: {session_id}")
                    self._timestamps.pop(session_id, None)
                if expired:
                    logger.info(f"[CLI] Cleaned {len(expired)} expired sessions")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[CLI] Session cleanup error: {e}")
        logger.info("[CLI] Session cleanup task stopped")


# ------------------------------------------------------------------
# 配置加载
# ------------------------------------------------------------------


def _load_config(platform_config: dict, platform_settings: dict | None = None) -> dict:
    """加载配置，合并配置文件覆盖"""
    config_filename = platform_config.get("config_file", "cli_config.json")
    config_path = os.path.join(get_astrbot_data_path(), config_filename)

    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                file_config = json.load(f)
            logger.info(f"[CLI] Loaded config from {config_path}")
            if "platform_config" in file_config:
                merged = platform_config.copy()
                merged.update(file_config["platform_config"])
                platform_config = merged
        except Exception as e:
            logger.warning(f"[CLI] Failed to load config from {config_path}: {e}")

    return platform_config


# ------------------------------------------------------------------
# CLI平台适配器
# ------------------------------------------------------------------


@register_platform_adapter(
    "cli",
    "CLI测试器，用于快速测试和调试插件，构建快速反馈循环",
    default_config_tmpl={
        "type": "cli",
        "enable": False,
        "mode": "socket",
        "socket_type": "auto",
        "socket_path": None,
        "tcp_host": "127.0.0.1",
        "tcp_port": 0,
        "whitelist": [],
        "use_isolated_sessions": False,
        "session_ttl": 30,
    },
    support_streaming_message=False,
)
class CLIPlatformAdapter(Platform):
    """CLI平台适配器"""

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)

        # 加载配置
        cfg = _load_config(platform_config, platform_settings)
        self.mode = cfg.get("mode", "socket")
        self.socket_type = cfg.get("socket_type", "auto")
        self.socket_path = cfg.get("socket_path") or os.path.join(
            get_astrbot_temp_path(), "astrbot.sock"
        )
        self.tcp_host = cfg.get("tcp_host", "127.0.0.1")
        self.tcp_port = cfg.get("tcp_port", 0)
        self.input_file = cfg.get("input_file") or os.path.join(
            get_astrbot_temp_path(), "astrbot_cli", "input.txt"
        )
        self.output_file = cfg.get("output_file") or os.path.join(
            get_astrbot_temp_path(), "astrbot_cli", "output.txt"
        )
        self.poll_interval = cfg.get("poll_interval", 1.0)
        self.use_isolated_sessions = cfg.get("use_isolated_sessions", False)
        self.session_ttl = cfg.get("session_ttl", 30)
        self.whitelist = cfg.get("whitelist", [])
        self.platform_id = cfg.get("id", "cli")

        # 初始化模块
        self.token_manager = TokenManager()
        self.session_manager = SessionManager(
            ttl=self.session_ttl, enabled=self.use_isolated_sessions
        )
        self.message_converter = MessageConverter()

        # 平台元数据
        self.metadata = PlatformMetadata(
            name="cli",
            description="命令行模拟器",
            id=self.platform_id,
            support_streaming_message=False,
        )

        # 运行状态
        self._running = False
        self._output_queue: asyncio.Queue = asyncio.Queue()
        self._handler = None

        logger.info(f"[CLI] Adapter initialized, mode={self.mode}")

    def run(self) -> Awaitable[Any]:
        return self._run_loop()

    async def _run_loop(self) -> None:
        self._running = True
        self.session_manager.start_cleanup_task()

        try:
            if self.mode == "socket":
                await self._run_socket_mode()
            elif self.mode == "file":
                await self._run_file_mode()
            else:
                await self._run_socket_mode()
        finally:
            self._running = False
            await self.session_manager.stop_cleanup_task()

    async def _run_socket_mode(self) -> None:
        platform_info = detect_platform()
        server = create_socket_server(
            platform_info,
            {
                "socket_type": self.socket_type,
                "socket_path": self.socket_path,
                "tcp_host": self.tcp_host,
                "tcp_port": self.tcp_port,
            },
            self.token_manager.token,
        )

        client_handler = SocketClientHandler(
            token_manager=self.token_manager,
            message_converter=self.message_converter,
            session_manager=self.session_manager,
            platform_meta=self.metadata,
            output_queue=self._output_queue,
            event_committer=self.commit_event,
            use_isolated_sessions=self.use_isolated_sessions,
            data_path=get_astrbot_data_path(),
        )

        self._handler = SocketModeHandler(
            server=server,
            client_handler=client_handler,
            connection_info_writer=write_connection_info,
            data_path=get_astrbot_data_path(),
        )

        await self._handler.run()

    async def _run_file_mode(self) -> None:
        self._handler = FileHandler(
            input_file=self.input_file,
            output_file=self.output_file,
            poll_interval=self.poll_interval,
            message_converter=self.message_converter,
            platform_meta=self.metadata,
            output_queue=self._output_queue,
            event_committer=self.commit_event,
        )
        await self._handler.run()

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        await self._output_queue.put(message_chain)
        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return self.metadata

    def unified_webhook(self) -> bool:
        return False

    def get_stats(self) -> dict:
        meta = self.meta()
        meta_info = {
            "id": meta.id,
            "name": meta.name,
            "display_name": meta.adapter_display_name or meta.name,
            "description": meta.description,
            "support_streaming_message": meta.support_streaming_message,
            "support_proactive_message": meta.support_proactive_message,
        }
        return {
            "id": meta.id or self.platform_id,
            "type": meta.name,
            "display_name": meta.adapter_display_name or meta.name,
            "status": self._status.value,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "error_count": len(self._errors),
            "last_error": {
                "message": self.last_error.message,
                "timestamp": self.last_error.timestamp.isoformat(),
                "traceback": self.last_error.traceback,
            }
            if self.last_error
            else None,
            "unified_webhook": False,
            "meta": meta_info,
        }

    async def terminate(self) -> None:
        self._running = False
        if self._handler:
            self._handler.stop()
        await self.session_manager.stop_cleanup_task()
        logger.info("[CLI] Adapter terminated")
