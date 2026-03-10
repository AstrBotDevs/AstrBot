"""企业微信智能机器人长连接客户端。"""

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from astrbot.api import logger


class WecomAIBotLongConnectionClient:
    """企业微信智能机器人 WebSocket 长连接客户端。"""

    def __init__(
        self,
        bot_id: str,
        secret: str,
        ws_url: str,
        heartbeat_interval: int,
        message_handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.bot_id = bot_id
        self.secret = secret
        self.ws_url = ws_url
        self.heartbeat_interval = max(5, int(heartbeat_interval))
        self.message_handler = message_handler

        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._shutdown_event = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._response_waiters: dict[str, asyncio.Future[dict[str, Any]]] = {}

    @staticmethod
    def gen_req_id() -> str:
        return uuid.uuid4().hex

    async def start(self) -> None:
        """启动长连接并自动重连。"""
        reconnect_delay = 1
        while not self._shutdown_event.is_set():
            try:
                await self._run_once()
                reconnect_delay = 1
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("[WecomAI][LongConn] 长连接异常: %s", e)
            if self._shutdown_event.is_set():
                break
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)

    async def _run_once(self) -> None:
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=None)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            self._session = session
            logger.info("[WecomAI][LongConn] 正在连接: %s", self.ws_url)
            async with session.ws_connect(
                self.ws_url, heartbeat=None, autoping=True
            ) as ws:
                self._ws = ws
                await self._subscribe()
                logger.info("[WecomAI][LongConn] 订阅成功，已建立长连接")

                heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                try:
                    while not self._shutdown_event.is_set():
                        message = await ws.receive()
                        if message.type == aiohttp.WSMsgType.TEXT:
                            await self._handle_text_message(message.data)
                        elif message.type in {
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.CLOSE,
                            aiohttp.WSMsgType.ERROR,
                        }:
                            break
                finally:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
                    self._ws = None

    async def _subscribe(self) -> None:
        """发送 aibot_subscribe，并等待响应。"""
        req_id = self.gen_req_id()
        payload = {
            "cmd": "aibot_subscribe",
            "headers": {"req_id": req_id},
            "body": {"bot_id": self.bot_id, "secret": self.secret},
        }
        await self._send_json(payload)

        if not self._ws:
            raise RuntimeError("WebSocket 未建立")

        reply = await self._ws.receive(timeout=10)
        if reply.type != aiohttp.WSMsgType.TEXT:
            raise RuntimeError(f"订阅失败: 非文本响应 {reply.type}")

        data = json.loads(reply.data)
        if data.get("errcode") != 0:
            raise RuntimeError(
                f"订阅失败 errcode={data.get('errcode')} errmsg={data.get('errmsg')}"
            )

    async def _heartbeat_loop(self) -> None:
        while not self._shutdown_event.is_set():
            await asyncio.sleep(self.heartbeat_interval)
            if self._shutdown_event.is_set():
                break
            try:
                await self.send_command("ping", self.gen_req_id(), None)
            except Exception as e:
                logger.warning("[WecomAI][LongConn] 发送心跳失败: %s", e)
                return

    async def _handle_text_message(self, text: str) -> None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("[WecomAI][LongConn] 收到非 JSON 消息: %s", text)
            return

        headers = payload.get("headers") or {}
        req_id = headers.get("req_id")
        if isinstance(req_id, str):
            waiter = self._response_waiters.get(req_id)
            if waiter and not waiter.done():
                waiter.set_result(payload)
                return

        cmd = payload.get("cmd")
        if cmd in {"aibot_msg_callback", "aibot_event_callback"}:
            await self.message_handler(payload)
            return

        if payload.get("errcode") not in (None, 0):
            logger.warning(
                "[WecomAI][LongConn] 服务端返回错误: errcode=%s errmsg=%s",
                payload.get("errcode"),
                payload.get("errmsg"),
            )

    async def send_command(
        self,
        cmd: str,
        req_id: str,
        body: dict[str, Any] | None,
    ) -> bool:
        """发送长连接命令。"""
        headers = {"req_id": req_id}
        payload: dict[str, Any] = {"cmd": cmd, "headers": headers}
        if body is not None:
            payload["body"] = body

        async with self._command_lock:
            max_retries = 3
            for attempt in range(max_retries + 1):
                response = await self._send_and_wait_response(req_id, payload)
                if not response:
                    if attempt < max_retries:
                        await asyncio.sleep(min(0.2 * (2**attempt), 2.0))
                        continue
                    return False

                errcode = response.get("errcode")
                if errcode in (0, None):
                    return True

                if errcode == 6000 and attempt < max_retries:
                    backoff = min(0.2 * (2**attempt), 2.0)
                    logger.warning(
                        "[WecomAI][LongConn] 命令冲突(errcode=6000)，将重试。cmd=%s req_id=%s attempt=%d",
                        cmd,
                        req_id,
                        attempt + 1,
                    )
                    await asyncio.sleep(backoff)
                    continue

                logger.warning(
                    "[WecomAI][LongConn] 命令失败: cmd=%s req_id=%s errcode=%s errmsg=%s",
                    cmd,
                    req_id,
                    errcode,
                    response.get("errmsg"),
                )
                return False

        return False

    async def _send_and_wait_response(
        self,
        req_id: str,
        payload: dict[str, Any],
        timeout: float = 10.0,
    ) -> dict[str, Any] | None:
        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._response_waiters[req_id] = waiter
        try:
            await self._send_json(payload)
            return await asyncio.wait_for(waiter, timeout=timeout)
        except TimeoutError:
            logger.warning(
                "[WecomAI][LongConn] 等待命令响应超时: cmd=%s req_id=%s",
                payload.get("cmd"),
                req_id,
            )
            return None
        finally:
            self._response_waiters.pop(req_id, None)

    async def _send_json(self, payload: dict[str, Any]) -> None:
        ws = self._ws
        if ws is None or ws.closed:
            raise RuntimeError("长连接尚未建立")
        async with self._send_lock:
            await ws.send_json(payload)

    async def shutdown(self) -> None:
        self._shutdown_event.set()
        ws = self._ws
        if ws is not None and not ws.closed:
            await ws.close()

        session = self._session
        if session is not None and not session.closed:
            await session.close()
