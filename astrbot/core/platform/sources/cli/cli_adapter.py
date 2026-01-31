"""
CLI Platform Adapter - 命令行模拟器

用于快速测试AstrBot插件，无需连接真实的IM平台。
遵循Unix哲学：原子化模块、显式I/O、管道编排。
"""

import asyncio
import sys
import uuid
from collections.abc import Awaitable
from typing import Any

from astrbot import logger
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion

from ...register import register_platform_adapter
from .cli_event import CLIMessageEvent


@register_platform_adapter(
    "cli",
    "命令行模拟器，用于快速测试插件功能，无需连接真实IM平台",
    default_config_tmpl={
        "type": "cli",
        "enable": True,  # 默认启用
        "mode": "socket",  # 默认使用Socket模式
        "socket_path": "/tmp/astrbot.sock",
        "whitelist": [],  # 空白名单表示允许所有
        "use_isolated_sessions": False,  # 是否启用会话隔离（每个请求独立会话）
        "session_ttl": 30  # 会话过期时间（秒），仅在use_isolated_sessions=True时生效，测试用30秒，生产建议1800秒（30分钟）
    },
    support_streaming_message=False,
)
class CLIPlatformAdapter(Platform):
    """CLI平台适配器

    提供命令行交互界面，模拟消息收发流程。

    数据流管道:
        用户输入 → convert_input → AstrBotMessage → handle_msg → commit_event
    """

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        """初始化CLI平台适配器

        Args:
            platform_config: 平台配置
            platform_settings: 平台设置
            event_queue: 事件队列
        """
        super().__init__(platform_config, event_queue)

        # 尝试从独立配置文件加载CLI配置
        import json
        import os
        config_file = platform_config.get('config_file', 'cli_config.json')
        cli_config_path = f"/AstrBot/data/{config_file}"
        if os.path.exists(cli_config_path):
            try:
                with open(cli_config_path, 'r', encoding='utf-8') as f:
                    cli_config = json.load(f)
                    # 使用独立配置文件中的配置覆盖传入的参数
                    if "platform_config" in cli_config:
                        platform_config.update(cli_config["platform_config"])
                    if "platform_settings" in cli_config:
                        platform_settings = cli_config["platform_settings"]
                    logger.info("[PROCESS] Loaded CLI config from %s", cli_config_path)
            except Exception as e:
                logger.warning("[WARN] Failed to load CLI config from %s: %s", cli_config_path, e)

        logger.info("[ENTRY] CLIPlatformAdapter.__init__ inputs={config=%s}", platform_config)

        self.settings = platform_settings
        self.session_id = "cli_session"
        self.user_id = "cli_user"
        self.user_nickname = "CLI User"

        # 运行模式配置
        self.mode = platform_config.get("mode", "auto")  # "auto", "tty", "file", "socket"

        # 文件I/O配置
        self.input_file = platform_config.get("input_file", "/tmp/astrbot_cli/input.txt")
        self.output_file = platform_config.get("output_file", "/tmp/astrbot_cli/output.txt")
        self.poll_interval = platform_config.get("poll_interval", 1.0)

        # Unix Socket配置
        self.socket_path = platform_config.get("socket_path", "/tmp/astrbot.sock")

        # 会话隔离配置
        self.use_isolated_sessions = platform_config.get("use_isolated_sessions", False)
        self.session_ttl = platform_config.get("session_ttl", 30)  # 默认30秒（测试），生产建议1800秒

        self.metadata = PlatformMetadata(
            name="cli",
            description="命令行模拟器",
            id=platform_config.get("id", "cli"),
            support_streaming_message=False,
        )

        self._running = False
        self._output_queue: asyncio.Queue = asyncio.Queue()

        # 会话过期跟踪（仅在use_isolated_sessions=True时使用）
        self._session_timestamps: dict[str, float] = {}  # {session_id: timestamp}
        self._cleanup_task: asyncio.Task | None = None

        logger.info("[EXIT] CLIPlatformAdapter.__init__ return=None")

    def run(self) -> Awaitable[Any]:
        """启动CLI平台

        Returns:
            协程对象，用于异步运行
        """
        logger.info("[ENTRY] CLIPlatformAdapter.run inputs={}")
        return self._run_loop()

    async def _run_loop(self) -> None:
        """主运行循环

        管道流程:
            1. 读取用户输入 (InputReader)
            2. 转换为消息对象 (MessageConverter)
            3. 处理消息事件 (EventHandler)
            4. 输出响应 (OutputWriter)
        """
        logger.info("[PROCESS] Starting CLI loop")

        # 启动会话清理任务（仅在use_isolated_sessions=True时）
        if self.use_isolated_sessions:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
            logger.info("[PROCESS] Session cleanup task started")

        # 决定运行模式
        has_tty = sys.stdin.isatty()

        # Socket模式优先
        if self.mode == "socket":
            logger.info("[PROCESS] Starting Unix Socket mode")
            await self._run_socket_mode()
            return

        # 其他模式
        if self.mode == "auto":
            # 自动模式：有TTY用交互，无TTY用文件
            use_file_mode = not has_tty
        elif self.mode == "file":
            use_file_mode = True
        elif self.mode == "tty":
            use_file_mode = False
            if not has_tty:
                logger.warning(
                    "[PROCESS] TTY mode requested but no TTY detected. "
                    "CLI platform will not start."
                )
                return
        else:
            logger.error(f"[ERROR] Unknown mode: {self.mode}")
            return

        if use_file_mode:
            logger.info("[PROCESS] Starting file polling mode")
            await self._run_file_mode()
        else:
            logger.info("[PROCESS] Starting TTY interactive mode")
            await self._run_tty_mode()

    async def _run_tty_mode(self) -> None:
        """TTY交互模式"""
        self._running = True

        print("\n" + "="*60)
        print("AstrBot CLI Simulator")
        print("="*60)
        print("Type your message and press Enter to send.")
        print("Type 'exit' or 'quit' to stop.")
        print("="*60 + "\n")

        # 启动输出监听器
        output_task = asyncio.create_task(self._output_monitor("tty"))

        try:
            while self._running:
                # [原子模块1] InputReader: 读取用户输入
                user_input = await self._read_input()

                if not user_input:
                    continue

                # 处理退出命令
                if user_input.lower() in ["exit", "quit"]:
                    logger.info("[PROCESS] User requested exit")
                    break

                # [原子模块2] MessageConverter: 转换为AstrBotMessage
                message = self._convert_input(user_input)

                # [原子模块3] EventHandler: 处理消息
                await self._handle_msg(message)

        except KeyboardInterrupt:
            logger.info("[PROCESS] Received KeyboardInterrupt")
        finally:
            self._running = False
            output_task.cancel()
            logger.info("[EXIT] CLIPlatformAdapter._run_tty_mode return=None")

    async def _run_file_mode(self) -> None:
        """文件轮询模式"""
        import os
        import time

        self._running = True

        # 确保目录存在
        os.makedirs(os.path.dirname(self.input_file), exist_ok=True)
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)

        # 创建输入文件（如果不存在）
        if not os.path.exists(self.input_file):
            with open(self.input_file, 'w') as f:
                f.write("")

        logger.info(f"[PROCESS] File mode started")
        logger.info(f"[PROCESS] Input file: {self.input_file}")
        logger.info(f"[PROCESS] Output file: {self.output_file}")
        logger.info(f"[PROCESS] Poll interval: {self.poll_interval}s")

        # 启动输出监听器
        output_task = asyncio.create_task(self._output_monitor("file"))

        try:
            while self._running:
                # 读取输入文件
                commands = await self._read_from_file()

                for cmd in commands:
                    if not cmd:
                        continue

                    logger.info(f"[PROCESS] Processing command: {cmd}")

                    # 转换并处理消息
                    message = self._convert_input(cmd)
                    await self._handle_msg(message)

                # 等待下一次轮询
                await asyncio.sleep(self.poll_interval)

        except Exception as e:
            logger.error(f"[ERROR] File mode error: {e}")
        finally:
            self._running = False
            output_task.cancel()
            logger.info("[EXIT] CLIPlatformAdapter._run_file_mode return=None")

    async def _run_socket_mode(self) -> None:
        """Unix Socket服务器模式

        管道流程:
            客户端连接 → 接收JSON请求 → 解析消息 → 创建事件 → 等待响应 → 返回JSON
        """
        import os
        import socket
        import json

        self._running = True

        # 删除旧的socket文件
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
            logger.info(f"[PROCESS] Removed old socket file: {self.socket_path}")

        # 创建Unix socket
        server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_socket.bind(self.socket_path)
        server_socket.listen(5)
        server_socket.setblocking(False)

        logger.info(f"[PROCESS] Unix Socket server started: {self.socket_path}")

        try:
            while self._running:
                try:
                    # 接受连接（非阻塞）
                    loop = asyncio.get_event_loop()
                    client_socket, _ = await loop.sock_accept(server_socket)

                    # 处理连接（异步）
                    asyncio.create_task(self._handle_socket_client(client_socket))

                except Exception as e:
                    logger.error(f"[ERROR] Socket accept error: {e}")
                    await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"[ERROR] Socket mode error: {e}")
        finally:
            self._running = False
            server_socket.close()
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)
            logger.info("[EXIT] CLIPlatformAdapter._run_socket_mode return=None")

    async def _handle_socket_client(self, client_socket) -> None:
        """[原子模块] SocketHandler: 处理单个socket客户端连接

        I/O契约:
            Input: socket连接
            Output: None (发送JSON响应到客户端)
        """
        import json

        logger.debug("[ENTRY] _handle_socket_client")

        try:
            loop = asyncio.get_event_loop()

            # 接收请求数据
            data = await loop.sock_recv(client_socket, 4096)
            if not data:
                logger.debug("[PROCESS] Empty request, closing connection")
                return

            # 解析JSON请求
            try:
                request = json.loads(data.decode('utf-8'))
                message_text = request.get('message', '')
                request_id = request.get('request_id', str(uuid.uuid4()))

                logger.info(f"[PROCESS] Received socket request: {message_text[:50]}...")

            except json.JSONDecodeError as e:
                logger.error(f"[ERROR] Invalid JSON request: {e}")
                error_response = json.dumps({
                    'status': 'error',
                    'error': 'Invalid JSON format'
                })
                await loop.sock_sendall(client_socket, error_response.encode('utf-8'))
                return

            # 创建响应Future
            response_future = asyncio.Future()

            # 转换并处理消息（传递request_id实现会话隔离）
            message = self._convert_input(message_text, request_id=request_id)

            # 创建带response_future的事件
            message_event = CLIMessageEvent(
                message_str=message.message_str,
                message_obj=message,
                platform_meta=self.meta(),
                session_id=message.session_id,
                output_queue=self._output_queue,
                response_future=response_future,
            )

            # 提交事件
            self.commit_event(message_event)

            # 等待响应（超时30秒）
            try:
                message_chain = await asyncio.wait_for(response_future, timeout=30.0)

                # 提取文本
                response_text = message_chain.get_plain_text()

                # 提取图片
                from astrbot.core.message.components import Image
                images = []
                for comp in message_chain.chain:
                    if isinstance(comp, Image):
                        image_info = {}
                        if comp.file:
                            if comp.file.startswith("http"):
                                image_info["type"] = "url"
                                image_info["url"] = comp.file
                            elif comp.file.startswith("file:///"):
                                image_info["type"] = "file"
                                file_path = comp.file[8:]  # 去掉 file:///
                                image_info["path"] = file_path

                                # 立即读取文件内容并转换为base64（避免临时文件被删除）
                                try:
                                    import base64
                                    with open(file_path, 'rb') as f:
                                        image_data = f.read()
                                        base64_data = base64.b64encode(image_data).decode('utf-8')
                                        image_info["base64_data"] = base64_data
                                        image_info["size"] = len(image_data)
                                        logger.debug(f"[PROCESS] Read image file: {file_path}, size: {len(image_data)} bytes")
                                except Exception as e:
                                    logger.error(f"[ERROR] Failed to read image file {file_path}: {e}")
                                    image_info["error"] = str(e)
                            elif comp.file.startswith("base64://"):
                                image_info["type"] = "base64"
                                # 返回完整的base64数据
                                base64_data = comp.file[9:]
                                image_info["base64_data"] = base64_data
                                image_info["base64_length"] = len(base64_data)
                        images.append(image_info)

                # 发送成功响应
                response = json.dumps({
                    'status': 'success',
                    'response': response_text,
                    'images': images,
                    'request_id': request_id
                }, ensure_ascii=False)

                await loop.sock_sendall(client_socket, response.encode('utf-8'))
                logger.info(f"[PROCESS] Sent response for request {request_id}")

            except asyncio.TimeoutError:
                logger.error(f"[ERROR] Request {request_id} timeout")
                error_response = json.dumps({
                    'status': 'error',
                    'error': 'Request timeout',
                    'request_id': request_id
                })
                await loop.sock_sendall(client_socket, error_response.encode('utf-8'))

        except Exception as e:
            logger.error(f"[ERROR] Socket client handler error: {e}")
            import traceback
            logger.error(traceback.format_exc())

        finally:
            client_socket.close()
            logger.debug("[EXIT] _handle_socket_client return=None")

    async def _read_input(self) -> str:
        """[原子模块] InputReader: 从命令行读取用户输入

        I/O契约:
            Input: None
            Output: str (用户输入的文本)
        """
        logger.debug("[ENTRY] _read_input inputs={}")

        # 使用asyncio在事件循环中运行阻塞的input()
        loop = asyncio.get_event_loop()
        user_input = await loop.run_in_executor(None, input, "You: ")

        logger.debug("[EXIT] _read_input return={input=%s}", user_input)
        return user_input.strip()

    async def _read_from_file(self) -> list[str]:
        """[原子模块] FileReader: 从文件读取命令

        I/O契约:
            Input: None
            Output: list[str] (命令列表)
        """
        import os

        try:
            if not os.path.exists(self.input_file):
                return []

            # 读取文件内容
            with open(self.input_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            if not content:
                return []

            # 按行分割命令
            commands = [line.strip() for line in content.split('\n') if line.strip()]

            # 清空输入文件
            with open(self.input_file, 'w', encoding='utf-8') as f:
                f.write("")

            logger.debug(f"[EXIT] _read_from_file return={len(commands)} commands")
            return commands

        except Exception as e:
            logger.error(f"[ERROR] Failed to read from file: {e}")
            return []

    def _convert_input(self, text: str, request_id: str = None) -> AstrBotMessage:
        """[原子模块] MessageConverter: 将文本转换为AstrBotMessage

        I/O契约:
            Input: str (原始文本), request_id (可选，用于会话隔离)
            Output: AstrBotMessage (标准消息对象)
        """
        logger.debug("[ENTRY] _convert_input inputs={text=%s, request_id=%s}", text, request_id)

        message = AstrBotMessage()
        message.self_id = "cli_bot"
        message.message_str = text
        message.message = [Plain(text)]  # 使用Plain组件对象，而不是字典
        message.type = MessageType.FRIEND_MESSAGE

        # 添加message_id属性，避免插件访问时出错
        import uuid
        message.message_id = str(uuid.uuid4())

        # 根据配置决定是否使用会话隔离
        if self.use_isolated_sessions and request_id:
            # 启用会话隔离：每个请求独立会话
            session_id = f"cli_session_{request_id}"
            message.session_id = session_id

            # 记录会话创建时间（用于过期清理）
            import time
            if session_id not in self._session_timestamps:
                self._session_timestamps[session_id] = time.time()
                logger.debug(f"[PROCESS] Created isolated session: {session_id}, TTL={self.session_ttl}s")
        else:
            # 默认模式：使用固定会话ID
            message.session_id = self.session_id

        message.sender = MessageMember(
            user_id=self.user_id,
            nickname=self.user_nickname,
        )

        logger.debug("[EXIT] _convert_input return={message=%s}", message)
        return message

    async def _handle_msg(self, message: AstrBotMessage) -> None:
        """[原子模块] EventHandler: 处理消息并提交事件

        I/O契约:
            Input: AstrBotMessage
            Output: None (提交到事件队列)
        """
        logger.debug("[ENTRY] _handle_msg inputs={message=%s}", message.message_str)

        # 创建消息事件
        message_event = CLIMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            output_queue=self._output_queue,
        )

        logger.info("[PROCESS] Committing event to queue: session_id=%s", message.session_id)

        # 提交到事件队列
        self.commit_event(message_event)

        logger.debug("[EXIT] _handle_msg return=None")

    async def _output_monitor(self, mode: str = "tty") -> None:
        """[原子模块] ResponseMonitor: 监听响应队列并输出

        I/O契约:
            Input: MessageChain (从响应队列)
            Output: None (输出到stdout或文件)

        Args:
            mode: 输出模式，"tty"或"file"
        """
        logger.debug(f"[ENTRY] _output_monitor inputs={{mode={mode}}}")

        while self._running:
            try:
                # 从输出队列获取响应
                message_chain = await asyncio.wait_for(
                    self._output_queue.get(),
                    timeout=0.5
                )

                # 根据模式选择输出方式
                if mode == "file":
                    await self._write_to_file(message_chain)
                else:
                    self._write_output(message_chain)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("[ERROR] Output monitor error: %s", e)

        logger.debug("[EXIT] _output_monitor return=None")

    def _write_output(self, message_chain: MessageChain) -> None:
        """[原子模块] OutputWriter: 将消息输出到命令行

        I/O契约:
            Input: MessageChain
            Output: None (打印到stdout)
        """
        logger.debug("[ENTRY] _write_output inputs={message_chain=%s}", message_chain)

        print(f"\nBot: {message_chain.get_plain_text()}\n")

        logger.debug("[EXIT] _write_output return=None")

    async def _write_to_file(self, message_chain: MessageChain) -> None:
        """[原子模块] FileWriter: 将消息输出到文件

        I/O契约:
            Input: MessageChain
            Output: None (写入文件)
        """
        import datetime

        logger.debug("[ENTRY] _write_to_file inputs={message_chain=%s}", message_chain)

        try:
            # 获取消息文本
            text = message_chain.get_plain_text()

            # 添加时间戳
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            output_line = f"[{timestamp}] Bot: {text}\n"

            # 追加到输出文件
            with open(self.output_file, 'a', encoding='utf-8') as f:
                f.write(output_line)

            logger.info(f"[PROCESS] Output written to file: {self.output_file}")

        except Exception as e:
            logger.error(f"[ERROR] Failed to write to file: {e}")

        logger.debug("[EXIT] _write_to_file return=None")

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        """通过会话发送消息

        Args:
            session: 消息会话
            message_chain: 消息链
        """
        logger.debug("[ENTRY] send_by_session inputs={session=%s}", session)

        # 将消息放入输出队列
        await self._output_queue.put(message_chain)

        await super().send_by_session(session, message_chain)

        logger.debug("[EXIT] send_by_session return=None")

    def meta(self) -> PlatformMetadata:
        """获取平台元数据

        Returns:
            平台元数据
        """
        return self.metadata

    async def _cleanup_expired_sessions(self) -> None:
        """[后台任务] 定期清理过期的会话记录

        仅在use_isolated_sessions=True时运行。
        定期检查_session_timestamps，删除过期的会话记录。
        """
        import time

        logger.info("[ENTRY] _cleanup_expired_sessions started, TTL=%s seconds", self.session_ttl)

        while self._running:
            try:
                await asyncio.sleep(10)  # 每10秒检查一次

                if not self.use_isolated_sessions:
                    continue

                current_time = time.time()
                expired_sessions = []

                # 找出过期的会话
                for session_id, timestamp in list(self._session_timestamps.items()):
                    if current_time - timestamp > self.session_ttl:
                        expired_sessions.append(session_id)

                # 清理过期会话
                for session_id in expired_sessions:
                    logger.info(f"[PROCESS] Cleaning expired session: {session_id}")
                    self._session_timestamps.pop(session_id, None)

                    # TODO: 从数据库删除会话记录（如果需要）
                    # await self.context.db.delete_platform_session(session_id)

                if expired_sessions:
                    logger.info(f"[PROCESS] Cleaned {len(expired_sessions)} expired sessions")

            except Exception as e:
                logger.error(f"[ERROR] Session cleanup error: {e}")

        logger.info("[EXIT] _cleanup_expired_sessions stopped")

    async def terminate(self) -> None:
        """终止平台运行"""
        logger.info("[ENTRY] CLIPlatformAdapter.terminate inputs={}")
        self._running = False

        # 停止清理任务
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                logger.info("[PROCESS] Cleanup task cancelled")

        logger.info("[EXIT] CLIPlatformAdapter.terminate return=None")
