"""Socket处理器模块

处理Socket客户端连接和Socket模式的生命周期管理。
"""

import asyncio
import json
import os
import re
import tempfile
import traceback
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain

if TYPE_CHECKING:
    from astrbot.core.platform.platform_metadata import PlatformMetadata

    from .cli_event import CLIMessageEvent


# ------------------------------------------------------------------
# 连接信息写入
# ------------------------------------------------------------------


def write_connection_info(connection_info: dict[str, Any], data_dir: str) -> None:
    """写入连接信息到文件，供客户端读取"""
    if not isinstance(connection_info, dict):
        raise ValueError("connection_info must be a dict")

    conn_type = connection_info.get("type")
    if conn_type not in ("unix", "tcp"):
        raise ValueError(f"Invalid type: {conn_type}, must be 'unix' or 'tcp'")
    if conn_type == "unix" and "path" not in connection_info:
        raise ValueError("Unix socket requires 'path' field")
    if conn_type == "tcp" and (
        "host" not in connection_info or "port" not in connection_info
    ):
        raise ValueError("TCP socket requires 'host' and 'port' fields")

    target_path = os.path.join(data_dir, ".cli_connection")

    try:
        fd, temp_path = tempfile.mkstemp(
            dir=data_dir, prefix=".cli_connection.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(connection_info, f, indent=2)
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass
            os.replace(temp_path, target_path)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise
    except Exception as e:
        logger.error(f"[CLI] Failed to write connection info: {e}")
        raise


# ------------------------------------------------------------------
# 响应构建（从message/response_builder.py内联）
# ------------------------------------------------------------------


def _build_success_response(
    message_chain: MessageChain,
    request_id: str,
    images: list[dict],
    extra: dict[str, Any] | None = None,
) -> str:
    """构建成功响应JSON"""
    result = {
        "status": "success",
        "response": message_chain.get_plain_text(),
        "images": images,
        "request_id": request_id,
    }
    if extra:
        result.update(extra)
    return json.dumps(result, ensure_ascii=False)


def _build_error_response(
    error_msg: str,
    request_id: str | None = None,
    error_code: str | None = None,
) -> str:
    """构建错误响应JSON"""
    result: dict[str, Any] = {"status": "error", "error": error_msg}
    if request_id:
        result["request_id"] = request_id
    if error_code:
        result["error_code"] = error_code
    return json.dumps(result, ensure_ascii=False)


# ------------------------------------------------------------------
# Socket客户端处理器
# ------------------------------------------------------------------


class SocketClientHandler:
    """处理单个Socket客户端连接"""

    RECV_BUFFER_SIZE = 4096
    MAX_REQUEST_SIZE = 1024 * 1024  # 1MB
    RESPONSE_TIMEOUT = 120.0

    def __init__(
        self,
        token_manager,
        message_converter,
        session_manager,
        platform_meta: "PlatformMetadata",
        output_queue: asyncio.Queue,
        event_committer: Callable[["CLIMessageEvent"], None],
        use_isolated_sessions: bool = False,
        data_path: str | None = None,
    ):
        self.token_manager = token_manager
        self.message_converter = message_converter
        self.session_manager = session_manager
        self.platform_meta = platform_meta
        self.output_queue = output_queue
        self.event_committer = event_committer
        self.use_isolated_sessions = use_isolated_sessions
        self.data_path = data_path or os.path.join(os.getcwd(), "data")

    async def handle(self, client_socket) -> None:
        """处理单个客户端连接"""
        try:
            loop = asyncio.get_running_loop()

            data = await self._recv_with_limit(loop, client_socket)
            if not data:
                return

            request = self._parse_request(data)
            if request is None:
                await self._send_response(
                    loop, client_socket, _build_error_response("Invalid JSON format")
                )
                return

            request_id = request.get("request_id", str(uuid.uuid4()))
            auth_token = request.get("auth_token", "")
            action = request.get("action", "")

            if not self.token_manager.validate(auth_token):
                error_msg = (
                    "Unauthorized: missing token"
                    if not auth_token
                    else "Unauthorized: invalid token"
                )
                await self._send_response(
                    loop,
                    client_socket,
                    _build_error_response(error_msg, request_id, "AUTH_FAILED"),
                )
                return

            if action == "get_logs":
                response = await self._get_logs(request, request_id)
            elif action == "list_tools":
                response = self._list_tools(request_id)
            elif action == "call_tool":
                response = await self._call_tool(request, request_id)
            elif action == "list_sessions":
                response = await self._list_sessions(request, request_id)
            elif action == "list_session_conversations":
                response = await self._list_session_conversations(request, request_id)
            elif action == "get_session_history":
                response = await self._get_session_history(request, request_id)
            else:
                message_text = request.get("message", "")
                response = await self._process_message(message_text, request_id)

            await self._send_response(loop, client_socket, response)

        except Exception as e:
            logger.error(f"[CLI] Socket handler error: {e}", exc_info=True)
        finally:
            try:
                client_socket.close()
            except Exception as e:
                logger.warning(f"[CLI] Failed to close socket: {e}")

    async def _recv_with_limit(self, loop, client_socket) -> bytes:
        """接收数据，带大小限制"""
        chunks = []
        total_size = 0

        while True:
            chunk = await loop.sock_recv(client_socket, self.RECV_BUFFER_SIZE)
            if not chunk:
                break

            total_size += len(chunk)
            if total_size > self.MAX_REQUEST_SIZE:
                logger.warning(f"[CLI] Request too large: {total_size} bytes")
                return b""

            chunks.append(chunk)
            if chunk.rstrip().endswith(b"}"):
                break

        return b"".join(chunks)

    def _parse_request(self, data: bytes) -> dict | None:
        try:
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    async def _send_response(self, loop, client_socket, response: str) -> None:
        await loop.sock_sendall(client_socket, response.encode("utf-8"))

    async def _process_message(self, message_text: str, request_id: str) -> str:
        """处理消息并返回JSON响应"""
        from .cli_event import CLIMessageEvent, extract_images

        response_future = asyncio.Future()

        message = self.message_converter.convert(
            message_text,
            request_id=request_id,
            use_isolated_session=self.use_isolated_sessions,
        )

        self.session_manager.register(message.session_id)

        message_event = CLIMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.platform_meta,
            session_id=message.session_id,
            output_queue=self.output_queue,
            response_future=response_future,
        )

        self.event_committer(message_event)

        try:
            message_chain = await asyncio.wait_for(
                response_future, timeout=self.RESPONSE_TIMEOUT
            )
            if message_chain is None:
                return _build_success_response(MessageChain([]), request_id, [])
            images = extract_images(message_chain)
            return _build_success_response(message_chain, request_id, images)
        except asyncio.TimeoutError:
            return _build_error_response("Request timeout", request_id, "TIMEOUT")

    async def _get_logs(self, request: dict, request_id: str) -> str:
        """获取日志"""
        LEVEL_MAP = {
            "DEBUG": "DEBUG",
            "INFO": "INFO",
            "WARNING": "WARN",
            "WARN": "WARN",
            "ERROR": "ERRO",
            "CRITICAL": "CRIT",
        }

        try:
            lines = min(request.get("lines", 100), 1000)
            level_filter = request.get("level", "").upper()
            level_filter = LEVEL_MAP.get(level_filter, level_filter)
            pattern = request.get("pattern", "")
            use_regex = request.get("regex", False)

            log_path = os.path.join(self.data_path, "logs", "astrbot.log")

            if not os.path.exists(log_path):  # noqa: ASYNC240
                return json.dumps(
                    {
                        "status": "success",
                        "response": "",
                        "message": "日志文件未找到。请在配置中启用 log_file_enable 来记录日志到文件。",
                        "request_id": request_id,
                    },
                    ensure_ascii=False,
                )

            logs = []
            try:
                with open(log_path, encoding="utf-8", errors="ignore") as f:
                    all_lines = f.readlines()

                for line in reversed(all_lines):
                    if not line.strip():
                        continue
                    if level_filter and not re.search(rf"\[{level_filter}\]", line):
                        continue
                    if pattern:
                        if use_regex:
                            try:
                                if not re.search(pattern, line):
                                    continue
                            except re.error:
                                if pattern not in line:
                                    continue
                        else:
                            if pattern not in line:
                                continue
                    logs.append(line.rstrip())
                    if len(logs) >= lines:
                        break
            except OSError as e:
                logger.warning(f"[CLI] Failed to read log file: {e}")
                return _build_error_response(
                    f"Failed to read log file: {e}", request_id
                )

            logs.reverse()
            log_text = "\n".join(logs)
            return json.dumps(
                {
                    "status": "success",
                    "response": log_text,
                    "message": f"Retrieved {len(logs)} log lines",
                    "request_id": request_id,
                },
                ensure_ascii=False,
            )

        except Exception as e:
            logger.exception("[CLI] Error getting logs")
            return _build_error_response(f"Error getting logs: {e}", request_id)

    # ------------------------------------------------------------------
    # 函数工具管理（CLI专属）
    # ------------------------------------------------------------------

    def _list_tools(self, request_id: str) -> str:
        """列出所有注册的函数工具"""
        from astrbot.core.provider.func_tool_manager import get_func_tool_manager

        tool_mgr = get_func_tool_manager()
        if tool_mgr is None:
            return _build_error_response("FunctionToolManager 未初始化", request_id)

        tools = []
        for tool in tool_mgr.func_list:
            # 判断来源
            origin = "unknown"
            origin_name = "unknown"
            try:
                from astrbot.core.agent.mcp_client import MCPTool
                from astrbot.core.star.star import star_map

                if isinstance(tool, MCPTool):
                    origin = "mcp"
                    origin_name = tool.mcp_server_name
                elif tool.handler_module_path and star_map.get(
                    tool.handler_module_path
                ):
                    origin = "plugin"
                    origin_name = star_map[tool.handler_module_path].name
                else:
                    origin = "builtin"
                    origin_name = "builtin"
            except Exception:
                pass

            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "active": tool.active,
                    "origin": origin,
                    "origin_name": origin_name,
                }
            )

        return json.dumps(
            {
                "status": "success",
                "response": json.dumps(tools, ensure_ascii=False, indent=2),
                "tools": tools,
                "images": [],
                "request_id": request_id,
            },
            ensure_ascii=False,
        )

    async def _call_tool(self, request: dict, request_id: str) -> str:
        """调用指定的函数工具"""
        from astrbot.core.provider.func_tool_manager import get_func_tool_manager

        tool_mgr = get_func_tool_manager()
        if tool_mgr is None:
            return _build_error_response("FunctionToolManager 未初始化", request_id)

        tool_name = request.get("tool_name", "")
        tool_args = request.get("tool_args", {})

        if not tool_name:
            return _build_error_response("缺少 tool_name 参数", request_id)

        tool = tool_mgr.get_func(tool_name)
        if tool is None:
            return _build_error_response(f"未找到工具: {tool_name}", request_id)

        if not tool.active:
            return _build_error_response(f"工具 {tool_name} 当前已停用", request_id)

        if tool.handler is None:
            return _build_error_response(
                f"工具 {tool_name} 没有可调用的处理函数", request_id
            )

        try:
            # 构造一个最小化的 event 用于工具调用
            from .cli_event import CLIMessageEvent

            response_future = asyncio.Future()
            message = self.message_converter.convert(
                f"/tool call {tool_name}",
                request_id=request_id,
                use_isolated_session=self.use_isolated_sessions,
            )
            event = CLIMessageEvent(
                message_str=message.message_str,
                message_obj=message,
                platform_meta=self.platform_meta,
                session_id=message.session_id,
                output_queue=self.output_queue,
                response_future=response_future,
            )

            result = await tool.handler(event, **tool_args)
            result_text = str(result) if result is not None else "(无返回值)"

            return json.dumps(
                {
                    "status": "success",
                    "response": result_text,
                    "images": [],
                    "request_id": request_id,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"[CLI] Tool call error: {tool_name}: {e}")
            return _build_error_response(
                f"调用工具 {tool_name} 失败: {e}\n{traceback.format_exc()[-300:]}",
                request_id,
            )

    # ------------------------------------------------------------------
    # 跨会话浏览（CLI专属）
    # ------------------------------------------------------------------

    async def _list_sessions(self, request: dict, request_id: str) -> str:
        """列出所有会话"""
        from astrbot.core.conversation_mgr import get_conversation_manager

        conv_mgr = get_conversation_manager()
        if conv_mgr is None:
            return _build_error_response("ConversationManager 未初始化", request_id)

        try:
            page = request.get("page", 1)
            page_size = request.get("page_size", 20)
            platform = request.get("platform") or None
            search_query = request.get("search_query") or None

            sessions, total = await conv_mgr.db.get_session_conversations(
                page=page,
                page_size=page_size,
                search_query=search_query,
                platform=platform,
            )

            total_pages = (total + page_size - 1) // page_size if total > 0 else 0

            return json.dumps(
                {
                    "status": "success",
                    "sessions": sessions,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "response": f"共 {total} 个会话，第 {page}/{total_pages} 页",
                    "images": [],
                    "request_id": request_id,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            logger.exception("[CLI] Error listing sessions")
            return _build_error_response(f"列出会话失败: {e}", request_id)

    async def _list_session_conversations(self, request: dict, request_id: str) -> str:
        """列出指定会话的所有对话"""
        from astrbot.core.conversation_mgr import get_conversation_manager

        conv_mgr = get_conversation_manager()
        if conv_mgr is None:
            return _build_error_response("ConversationManager 未初始化", request_id)

        session_id = request.get("session_id", "")
        if not session_id:
            return _build_error_response("缺少 session_id 参数", request_id)

        try:
            page = request.get("page", 1)
            page_size = request.get("page_size", 20)

            conversations = await conv_mgr.get_conversations(
                unified_msg_origin=session_id,
            )

            # 手动分页
            total = len(conversations)
            total_pages = (total + page_size - 1) // page_size if total > 0 else 0
            start = (page - 1) * page_size
            end = start + page_size
            paged = conversations[start:end]

            convs_data = []
            curr_cid = await conv_mgr.get_curr_conversation_id(session_id)
            for conv in paged:
                convs_data.append(
                    {
                        "cid": conv.cid,
                        "title": conv.title or "(无标题)",
                        "persona_id": conv.persona_id,
                        "created_at": conv.created_at,
                        "updated_at": conv.updated_at,
                        "token_usage": conv.token_usage,
                        "is_current": conv.cid == curr_cid,
                    }
                )

            return json.dumps(
                {
                    "status": "success",
                    "conversations": convs_data,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "current_cid": curr_cid,
                    "response": f"会话 {session_id} 共 {total} 个对话，第 {page}/{total_pages} 页",
                    "images": [],
                    "request_id": request_id,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            logger.exception("[CLI] Error listing session conversations")
            return _build_error_response(f"列出会话对话失败: {e}", request_id)

    async def _get_session_history(self, request: dict, request_id: str) -> str:
        """获取指定会话的聊天记录"""
        from astrbot.core.conversation_mgr import get_conversation_manager

        conv_mgr = get_conversation_manager()
        if conv_mgr is None:
            return _build_error_response("ConversationManager 未初始化", request_id)

        session_id = request.get("session_id", "")
        if not session_id:
            return _build_error_response("缺少 session_id 参数", request_id)

        try:
            conversation_id = request.get("conversation_id") or None
            page = request.get("page", 1)
            page_size = request.get("page_size", 10)

            # 如果未指定 conversation_id，获取当前对话
            if not conversation_id:
                conversation_id = await conv_mgr.get_curr_conversation_id(session_id)

            if not conversation_id:
                return json.dumps(
                    {
                        "status": "success",
                        "history": [],
                        "total_pages": 0,
                        "page": page,
                        "conversation_id": None,
                        "response": f"会话 {session_id} 没有活跃的对话",
                        "images": [],
                        "request_id": request_id,
                    },
                    ensure_ascii=False,
                )

            conversation = await conv_mgr.get_conversation(session_id, conversation_id)
            if not conversation:
                return json.dumps(
                    {
                        "status": "success",
                        "history": [],
                        "total_pages": 0,
                        "page": page,
                        "conversation_id": conversation_id,
                        "session_id": session_id,
                        "response": "(无记录)",
                        "images": [],
                        "request_id": request_id,
                    },
                    ensure_ascii=False,
                )

            raw_history = json.loads(conversation.history)

            # 构建简洁的消息对列表，每对是 {"role": ..., "text": ...}
            messages = []
            for record in raw_history:
                role = record.get("role", "")
                if role not in ("user", "assistant"):
                    continue
                text = _extract_content_text(record)
                messages.append({"role": role, "text": text})

            # 分页（按消息条数）
            total = len(messages)
            total_pages = (total + page_size - 1) // page_size if total > 0 else 0
            start = (page - 1) * page_size
            end = start + page_size
            paged = messages[start:end]

            return json.dumps(
                {
                    "status": "success",
                    "history": paged,
                    "total": total,
                    "total_pages": total_pages,
                    "page": page,
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                    "response": "",
                    "images": [],
                    "request_id": request_id,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            logger.exception("[CLI] Error getting session history")
            return _build_error_response(f"获取聊天记录失败: {e}", request_id)


def _extract_content_text(record: dict) -> str:
    """从 OpenAI 格式的消息记录中提取纯文本，图片用 [图片] 占位。"""
    content = record.get("content")

    # content 是字符串（最常见情况）
    if isinstance(content, str):
        return content

    # content 是 list（多部分内容，可能含图片）
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                part_type = part.get("type", "")
                if part_type == "text":
                    parts.append(part.get("text", ""))
                elif part_type in ("image_url", "image"):
                    parts.append("[图片]")
                else:
                    parts.append(f"[{part_type}]")
            elif isinstance(part, str):
                parts.append(part)
        return " ".join(parts) if parts else ""

    # content 为 None（tool_calls 等情况）
    if content is None:
        if "tool_calls" in record:
            names = []
            for tc in record.get("tool_calls", []):
                fn = tc.get("function", {})
                names.append(fn.get("name", "?"))
            return f"[调用工具: {', '.join(names)}]"
        return ""

    return str(content)


# ------------------------------------------------------------------
# Socket模式处理器
# ------------------------------------------------------------------


class SocketModeHandler:
    """管理Socket服务器的生命周期"""

    def __init__(
        self,
        server,
        client_handler: SocketClientHandler,
        connection_info_writer: Callable[[dict, str], None],
        data_path: str,
    ):
        self.server = server
        self.client_handler = client_handler
        self.connection_info_writer = connection_info_writer
        self.data_path = data_path
        self._running = False

    async def run(self) -> None:
        self._running = True
        try:
            await self.server.start()
            logger.info(f"[CLI] Socket server started: {type(self.server).__name__}")

            connection_info = self.server.get_connection_info()
            self.connection_info_writer(connection_info, self.data_path)

            while self._running:
                try:
                    client_socket, _ = await self.server.accept_connection()
                    asyncio.create_task(self.client_handler.handle(client_socket))
                except Exception as e:
                    if self._running:
                        logger.error(f"[CLI] Socket accept error: {e}")
                    await asyncio.sleep(0.1)
        finally:
            await self.server.stop()

    def stop(self) -> None:
        self._running = False
