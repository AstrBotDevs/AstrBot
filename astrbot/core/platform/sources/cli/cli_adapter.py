"""
CLI Platform Adapter - CLI平台适配器

编排层：组合各模块实现CLI测试功能。
遵循Unix哲学：原子化模块、显式I/O、管道编排。

重构后架构:
    cli_adapter.py (编排层 <200行)
    ├── ConfigLoader 加载配置
    ├── TokenManager 管理认证
    ├── SessionManager 管理会话
    ├── MessageConverter 转换消息
    └── Handler (Socket/TTY/File)
"""

import asyncio
from collections.abc import Awaitable
from typing import Any

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import Platform, PlatformMetadata
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from ...register import register_platform_adapter
from .config.config_loader import ConfigLoader
from .config.token_manager import TokenManager
from .connection_info_writer import write_connection_info
from .handlers.file_handler import FileHandler
from .handlers.socket_handler import SocketClientHandler, SocketModeHandler
from .handlers.tty_handler import TTYHandler
from .message.converter import MessageConverter
from .platform_detector import detect_platform
from .session.session_manager import SessionManager
from .socket_factory import create_socket_server


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
    """CLI平台适配器 - 编排层

    通过组合各模块实现CLI测试功能。
    """

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        """初始化CLI平台适配器"""
        super().__init__(platform_config, event_queue)

        # 加载配置
        self.config = ConfigLoader.load(platform_config, platform_settings)

        # 初始化各模块
        self.token_manager = TokenManager()
        self.session_manager = SessionManager(
            ttl=self.config.session_ttl,
            enabled=self.config.use_isolated_sessions,
        )
        self.message_converter = MessageConverter()

        # 平台元数据
        self.metadata = PlatformMetadata(
            name="cli",
            description="命令行模拟器",
            id=self.config.platform_id,
            support_streaming_message=False,
        )

        # 运行状态
        self._running = False
        self._output_queue: asyncio.Queue = asyncio.Queue()
        self._handler = None

        logger.info("[CLI] Adapter initialized, mode=%s", self.config.mode)

    def run(self) -> Awaitable[Any]:
        """启动CLI平台"""
        return self._run_loop()

    async def _run_loop(self) -> None:
        """主运行循环 - 根据模式选择Handler"""
        self._running = True

        # 启动会话清理任务
        self.session_manager.start_cleanup_task()

        try:
            # 根据模式创建并运行Handler
            if self.config.mode == "socket":
                await self._run_socket_mode()
            elif self.config.mode == "tty":
                await self._run_tty_mode()
            elif self.config.mode == "file":
                await self._run_file_mode()
            else:
                # auto模式：有TTY用交互，无TTY用socket
                import sys

                if sys.stdin.isatty():
                    await self._run_tty_mode()
                else:
                    await self._run_socket_mode()
        finally:
            self._running = False
            await self.session_manager.stop_cleanup_task()

    async def _run_socket_mode(self) -> None:
        """Socket模式"""
        platform_info = detect_platform()
        server = create_socket_server(
            platform_info,
            {
                "socket_type": self.config.socket_type,
                "socket_path": self.config.socket_path,
                "tcp_host": self.config.tcp_host,
                "tcp_port": self.config.tcp_port,
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
            use_isolated_sessions=self.config.use_isolated_sessions,
            data_path=get_astrbot_data_path(),
        )

        self._handler = SocketModeHandler(
            server=server,
            client_handler=client_handler,
            connection_info_writer=write_connection_info,
            data_path=get_astrbot_data_path(),
        )

        await self._handler.run()

    async def _run_tty_mode(self) -> None:
        """TTY交互模式"""
        self._handler = TTYHandler(
            message_converter=self.message_converter,
            platform_meta=self.metadata,
            output_queue=self._output_queue,
            event_committer=self.commit_event,
        )
        await self._handler.run()

    async def _run_file_mode(self) -> None:
        """文件轮询模式"""
        self._handler = FileHandler(
            input_file=self.config.input_file,
            output_file=self.config.output_file,
            poll_interval=self.config.poll_interval,
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
        """通过会话发送消息"""
        await self._output_queue.put(message_chain)
        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        """获取平台元数据"""
        return self.metadata

    def unified_webhook(self) -> bool:
        """CLI不使用webhook"""
        return False

    def get_stats(self) -> dict:
        """获取平台统计信息（兼容CLIConfig数据类）"""
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
            "id": meta.id or self.config.platform_id,
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
        """终止平台运行"""
        self._running = False
        if self._handler:
            self._handler.stop()
        await self.session_manager.stop_cleanup_task()
        logger.info("[CLI] Adapter terminated")
