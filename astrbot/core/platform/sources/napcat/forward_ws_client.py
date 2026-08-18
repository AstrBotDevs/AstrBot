from __future__ import annotations

import asyncio
import json
import ssl
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from time import monotonic
from typing import Any, cast

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from astrbot import logger

from .exceptions import NapCatApiError, NapCatTransportError
from .inbound_events import NapCatInboundEvent, dispatch_inbound_event
from .types import (
    NapCatFetchedMessage,
    NapCatLoginInfo,
    NapCatSendMessageResult,
    NapCatStatus,
    NapCatVersionInfo,
)


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _strip_none_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class _RawMessageSegment:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.payload


class NapCatForwardWebSocketClient:
    _VALIDATION_SLOW_LOG_THRESHOLD_S = 0.1
    _PAYLOAD_HANDLE_SLOW_LOG_THRESHOLD_S = 0.2

    def __init__(
        self,
        *,
        ws_url: str,
        token: str | None = None,
        action_timeout_seconds: float = 30.0,
        reconnect_interval_seconds: float = 5.0,
        verify_ssl: bool = True,
        max_size_bytes: int = 50 * 1024 * 1024,
        on_event: Callable[[NapCatInboundEvent], Awaitable[None]],
    ) -> None:
        self.ws_url = ws_url.strip()
        self.token = token.strip() if token else ""
        self.action_timeout_seconds = action_timeout_seconds
        self.reconnect_interval_seconds = reconnect_interval_seconds
        self.verify_ssl = verify_ssl
        self.max_size_bytes = max_size_bytes
        self.on_event = on_event

        self._runner_task: asyncio.Task[None] | None = None
        self._socket: ClientConnection | None = None
        self._connected_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._authentication_failed_event = asyncio.Event()
        self._authentication_error: NapCatApiError | None = None
        self._send_lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._payload_tasks: set[asyncio.Task[None]] = set()
        self._connection_generation = 0

    def _build_api_error(
        self, operation: str, payload: Mapping[str, Any]
    ) -> NapCatApiError:
        status = payload.get("status")
        retcode = _coerce_int(payload.get("retcode"))
        message = payload.get("message")
        wording = payload.get("wording")
        return NapCatApiError(
            operation,
            status=str(status) if status is not None else None,
            retcode=retcode,
            message=str(message) if isinstance(message, str) else None,
            wording=str(wording) if isinstance(wording, str) else None,
        )

    async def start(self) -> None:
        self._raise_authentication_error()
        if self._runner_task is not None:
            if not self._runner_task.done():
                return
            self._runner_task = None
        if not self.ws_url.startswith(("ws://", "wss://")):
            raise ValueError(
                f"NapCat forward WebSocket URL must start with ws:// or wss://: {self.ws_url}"
            )

        self._stop_event.clear()
        self._runner_task = asyncio.create_task(self._run_loop())
        try:
            await self._wait_until_connected("start")
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        self._stop_event.set()
        socket = self._socket
        runner_task = self._runner_task
        try:
            if socket is not None:
                await socket.close(code=1000, reason="Adapter shutdown")
        finally:
            if runner_task is not None:
                if not runner_task.done():
                    runner_task.cancel()
                try:
                    await runner_task
                except asyncio.CancelledError:
                    pass
                if self._runner_task is runner_task:
                    self._runner_task = None
            payload_tasks = list(self._payload_tasks)
            if payload_tasks:
                await asyncio.gather(*payload_tasks, return_exceptions=True)
            self._payload_tasks.clear()
            self._fail_pending("client closed")
            self._socket = None
            self._connected_event.clear()

    async def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    await self._connect_and_listen()
                except asyncio.CancelledError:
                    raise
                except InvalidStatus as exc:
                    if exc.response.status_code in {401, 403}:
                        self._set_authentication_error(
                            NapCatApiError(
                                "forward_ws",
                                status="failed",
                                retcode=exc.response.status_code,
                                message="WebSocket authentication failed",
                                wording=None,
                            )
                        )
                        logger.error(
                            "[NapCat] Forward WebSocket authentication failed with HTTP %s",
                            exc.response.status_code,
                        )
                        break
                    if self._stop_event.is_set():
                        break
                    logger.warning(
                        "[NapCat] Forward WebSocket disconnected from %s: %s. Retrying in %.1fs.",
                        self.ws_url,
                        exc,
                        self.reconnect_interval_seconds,
                    )
                except Exception as exc:
                    if self._stop_event.is_set():
                        break
                    logger.warning(
                        "[NapCat] Forward WebSocket disconnected from %s: %s. Retrying in %.1fs.",
                        self.ws_url,
                        exc,
                        self.reconnect_interval_seconds,
                    )

                if self._stop_event.is_set():
                    break
                await self._wait_for_reconnect()
        finally:
            self._fail_pending("client stopped")
            self._socket = None
            self._connected_event.clear()

    async def _wait_for_reconnect(self) -> None:
        try:
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=self.reconnect_interval_seconds,
            )
        except TimeoutError:
            pass

    async def _connect_and_listen(self) -> None:
        ssl_context: ssl.SSLContext | bool | None = None
        if self.ws_url.startswith("wss://"):
            ssl_context = True

        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        logger.info("[NapCat] Connecting forward WebSocket to %s", self.ws_url)
        async with connect(
            self.ws_url,
            additional_headers=headers or None,
            max_size=self.max_size_bytes,
            compression=None,
            ssl=ssl_context,
        ) as websocket:
            self._socket = websocket
            self._connection_generation += 1
            connection_generation = self._connection_generation
            self._connected_event.set()
            logger.info(
                "[NapCat] Forward WebSocket transport connected to %s", self.ws_url
            )

            try:
                async for payload in websocket:
                    self._start_payload_task(
                        payload,
                        connection_generation=connection_generation,
                    )
            except ConnectionClosed as exc:
                raise NapCatTransportError(
                    "forward_ws",
                    f"connection closed code={exc.code} reason={exc.reason}",
                ) from exc
            finally:
                self._socket = None
                self._connected_event.clear()
                self._fail_pending("connection lost")

    def _start_payload_task(
        self,
        payload: str | bytes,
        *,
        connection_generation: int | None = None,
    ) -> None:
        task = asyncio.create_task(
            self._handle_ws_payload(
                payload,
                connection_generation=connection_generation,
            ),
            name="napcat:forward-ws-payload",
        )
        self._payload_tasks.add(task)
        task.add_done_callback(self._on_payload_task_done)

    def _on_payload_task_done(self, task: asyncio.Task[None]) -> None:
        self._payload_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "[NapCat] Forward WebSocket payload handling failed", exc_info=exc
            )

    async def _handle_ws_payload(
        self,
        payload: str | bytes,
        *,
        connection_generation: int | None = None,
    ) -> None:
        started_at = monotonic()
        if isinstance(payload, bytes):
            try:
                payload = payload.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning(
                    "[NapCat] Forward WebSocket received non-UTF8 binary frame"
                )
                return

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning(
                "[NapCat] Forward WebSocket received non-JSON payload: %r", payload
            )
            return

        if not isinstance(parsed, dict):
            logger.debug(
                "[NapCat] Forward WebSocket ignored non-object payload: %r", parsed
            )
            return

        if (
            connection_generation is not None
            and connection_generation != self._connection_generation
        ):
            logger.debug(
                "[NapCat] Forward WebSocket ignored payload from stale connection %s",
                connection_generation,
            )
            return

        if await dispatch_inbound_event(
            parsed,
            self.on_event,
            started_at=started_at,
            validation_slow_log_threshold_s=self._VALIDATION_SLOW_LOG_THRESHOLD_S,
            payload_handle_slow_log_threshold_s=self._PAYLOAD_HANDLE_SLOW_LOG_THRESHOLD_S,
        ):
            return

        echo = parsed.get("echo")
        if echo is None:
            if parsed.get("status") == "failed":
                error = self._build_api_error("forward_ws", parsed)
                logger.warning(
                    "[NapCat] Forward WebSocket received failed response without echo: %s",
                    error,
                )
                self._fail_pending_with_exception(error)
                socket = self._socket
                if error.retcode == 1403:
                    self._set_authentication_error(error)
                if error.retcode == 1403 and socket is not None:
                    await socket.close(
                        code=1008,
                        reason="NapCat WebSocket authentication failed",
                    )
                return
            logger.debug(
                "[NapCat] Forward WebSocket ignored response without echo: %s", parsed
            )
            return

        future = self._pending.pop(str(echo), None)
        if future is None:
            logger.debug(
                "[NapCat] Forward WebSocket ignored unmatched echo response: %s", echo
            )
            return
        if not future.done():
            future.set_result(parsed)

    async def call_action(self, action: str, **params: Any) -> dict[str, Any]:
        await self._wait_until_connected(action)
        socket = self._socket
        if socket is None:
            raise NapCatTransportError(action, "forward websocket is not connected")

        payload = {
            "action": action,
            "params": _strip_none_values(params),
            "echo": uuid.uuid4().hex,
        }
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[payload["echo"]] = future

        try:
            async with self._send_lock:
                await socket.send(json.dumps(payload, ensure_ascii=False))
            return await asyncio.wait_for(future, timeout=self.action_timeout_seconds)
        except asyncio.CancelledError:
            self._pending.pop(payload["echo"], None)
            if not future.done():
                future.cancel()
            raise
        except TimeoutError as exc:
            self._pending.pop(payload["echo"], None)
            if not future.done():
                future.cancel()
            raise NapCatTransportError(
                action,
                f"timed out waiting for response after {self.action_timeout_seconds:.1f}s",
            ) from exc
        except ConnectionClosed as exc:
            self._pending.pop(payload["echo"], None)
            if not future.done():
                future.cancel()
            raise NapCatTransportError(
                action,
                f"forward websocket closed code={exc.code} reason={exc.reason}",
            ) from exc

    async def _wait_until_connected(self, operation: str) -> None:
        self._raise_authentication_error()
        if self._connected_event.is_set():
            return

        connected_wait = asyncio.create_task(self._connected_event.wait())
        authentication_failure_wait = asyncio.create_task(
            self._authentication_failed_event.wait()
        )
        try:
            done, _ = await asyncio.wait(
                {connected_wait, authentication_failure_wait},
                timeout=self.action_timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (connected_wait, authentication_failure_wait):
                if not task.done():
                    task.cancel()
            await asyncio.gather(
                connected_wait,
                authentication_failure_wait,
                return_exceptions=True,
            )

        if authentication_failure_wait in done:
            self._raise_authentication_error()
        if connected_wait in done and self._connected_event.is_set():
            return
        raise NapCatTransportError(
            operation,
            f"forward websocket did not connect within {self.action_timeout_seconds:.1f}s",
        )

    def _set_authentication_error(self, error: NapCatApiError) -> None:
        self._authentication_error = error
        self._authentication_failed_event.set()
        self._stop_event.set()

    def _raise_authentication_error(self) -> None:
        error = self._authentication_error
        if error is None:
            return
        raise NapCatApiError(
            error.operation,
            status=error.status,
            retcode=error.retcode,
            message=error.message,
            wording=error.wording,
        )

    def _fail_pending(self, detail: str) -> None:
        self._fail_pending_with_exception(
            NapCatTransportError("forward_ws", f"pending action failure: {detail}")
        )

    def _fail_pending_with_exception(self, exc: Exception) -> None:
        for echo, future in list(self._pending.items()):
            if future.done():
                continue
            if isinstance(exc, NapCatTransportError):
                error: Exception = NapCatTransportError(
                    exc.operation,
                    f"pending action {echo} failed: {exc.detail}",
                )
            elif isinstance(exc, NapCatApiError):
                error = NapCatApiError(
                    exc.operation,
                    status=exc.status,
                    retcode=exc.retcode,
                    message=exc.message,
                    wording=exc.wording,
                )
            else:
                error = exc
            future.set_exception(error)
        self._pending.clear()

    def text(self, content: str) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "text", "data": {"text": content}})

    def at(self, qq: int | str, *, name: str | None = None) -> _RawMessageSegment:
        data = {"qq": str(qq)}
        if name:
            data["name"] = name
        return _RawMessageSegment({"type": "at", "data": data})

    def at_all(self) -> _RawMessageSegment:
        return self.at("all")

    def reply(self, message_id: int | str) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "reply", "data": {"id": str(message_id)}})

    def face(self, face_id: int | str) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "face", "data": {"id": str(face_id)}})

    def mface(
        self,
        *,
        emoji_package_id: int | float,
        emoji_id: str,
        key: str,
        summary: str,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "mface",
                "data": {
                    "emoji_package_id": int(emoji_package_id),
                    "emoji_id": emoji_id,
                    "key": key,
                    "summary": summary,
                },
            }
        )

    def contact(
        self, *, contact_type: str, contact_id: int | str
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {"type": "contact", "data": {"type": contact_type, "id": str(contact_id)}}
        )

    def location(
        self,
        *,
        lat: float,
        lon: float,
        title: str | None = None,
        content: str | None = None,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "location",
                "data": _strip_none_values(
                    {
                        "lat": str(lat),
                        "lon": str(lon),
                        "title": title,
                        "content": content,
                    }
                ),
            }
        )

    def poke(
        self,
        *,
        target_id: int | str | None = None,
        poke_type: int | str | None = None,
        user_id: int | str | None = None,
    ) -> _RawMessageSegment:
        resolved_target_id = target_id if target_id is not None else user_id
        if resolved_target_id is None:
            raise ValueError("poke segments require target_id or user_id")
        return _RawMessageSegment(
            {
                "type": "poke",
                "data": _strip_none_values(
                    {
                        "type": str(poke_type) if poke_type is not None else None,
                        "id": str(resolved_target_id),
                    }
                ),
            }
        )

    def json_message(self, data: Any) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "json", "data": {"data": data}})

    def markdown_message(self, content: str) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "markdown", "data": {"content": content}})

    def mini_app_message(self, data: str) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "miniapp", "data": {"data": data}})

    def online_file(
        self,
        *,
        msg_id: str,
        element_id: str,
        file_name: str,
        file_size: str,
        is_dir: bool,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "onlinefile",
                "data": {
                    "msgId": msg_id,
                    "elementId": element_id,
                    "fileName": file_name,
                    "fileSize": file_size,
                    "isDir": is_dir,
                },
            }
        )

    def xml_message(self, data: str) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "xml", "data": {"data": data}})

    def flash_transfer(self, *, file_set_id: str) -> _RawMessageSegment:
        return _RawMessageSegment(
            {"type": "flashtransfer", "data": {"fileSetId": file_set_id}}
        )

    def share(
        self,
        *,
        url: str,
        title: str,
        content: str | None = None,
        image: str | None = None,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "share",
                "data": _strip_none_values(
                    {
                        "url": url,
                        "title": title,
                        "content": content,
                        "image": image,
                    }
                ),
            }
        )

    def dice(self) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "dice", "data": {}})

    def rps(self) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "rps", "data": {}})

    def shake(self) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "shake", "data": {}})

    def music(
        self,
        *,
        music_type: str,
        music_id: int | str | None = None,
        url: str | None = None,
        audio: str | None = None,
        title: str | None = None,
        content: str | None = None,
        image: str | None = None,
    ) -> _RawMessageSegment:
        if music_type == "custom":
            if not url or not image:
                raise ValueError(
                    "custom music segments require both url and image fields"
                )
            return _RawMessageSegment(
                {
                    "type": "music",
                    "data": {
                        "type": music_type,
                        "id": None,
                        "url": url,
                        "audio": audio,
                        "title": title,
                        "content": content,
                        "image": image,
                    },
                }
            )
        if music_id is None:
            raise ValueError("id music segments require a music_id")
        return _RawMessageSegment(
            {"type": "music", "data": {"type": music_type, "id": str(music_id)}}
        )

    def forward(self, forward_id: str | int) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "forward", "data": {"id": str(forward_id)}})

    def image(
        self,
        *,
        file: str,
        url: str | None = None,
        path: str | None = None,
        name: str | None = None,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "image",
                "data": _strip_none_values(
                    {"file": file, "url": url, "path": path, "name": name}
                ),
            }
        )

    def record(
        self,
        *,
        file: str,
        url: str | None = None,
        path: str | None = None,
        name: str | None = None,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "record",
                "data": _strip_none_values(
                    {"file": file, "url": url, "path": path, "name": name}
                ),
            }
        )

    def video(
        self,
        *,
        file: str,
        url: str | None = None,
        path: str | None = None,
        name: str | None = None,
        thumb: str | None = None,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "video",
                "data": _strip_none_values(
                    {
                        "file": file,
                        "url": url,
                        "path": path,
                        "name": name,
                        "thumb": thumb,
                    }
                ),
            }
        )

    def file(
        self,
        *,
        file: str,
        file_id: str | None = None,
        name: str | None = None,
        path: str | None = None,
        url: str | None = None,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "file",
                "data": _strip_none_values(
                    {
                        "file": file,
                        "file_id": file_id,
                        "name": name,
                        "path": path,
                        "url": url,
                    }
                ),
            }
        )

    async def get_login_info(self) -> NapCatLoginInfo:
        payload = await self.call_action("get_login_info")
        data = self._require_data_dict("get_login_info", payload)
        user_id = _coerce_int(data.get("user_id"))
        if user_id is None:
            raise NapCatTransportError(
                "get_login_info",
                "successful response did not contain numeric user_id",
            )
        nickname = _string_or_none(data.get("nickname"))
        if nickname is None:
            raise NapCatTransportError(
                "get_login_info",
                "successful response did not contain nickname",
            )
        return NapCatLoginInfo(
            user_id=user_id,
            nickname=nickname,
            qid=_string_or_none(data.get("qid")),
            remark=_string_or_none(data.get("remark")),
            sex=_string_or_none(data.get("sex")),
            age=_coerce_int(data.get("age")),
            level=_coerce_int(data.get("level")),
            login_days=_coerce_int(data.get("login_days")),
            extra={
                key: value
                for key, value in data.items()
                if key
                not in {
                    "user_id",
                    "nickname",
                    "qid",
                    "remark",
                    "sex",
                    "age",
                    "level",
                    "login_days",
                }
            },
        )

    async def get_status(self) -> NapCatStatus:
        payload = await self.call_action("get_status")
        data = self._require_data_dict("get_status", payload)
        stats = data.get("stat")
        if not isinstance(stats, dict):
            stats = {}
        return NapCatStatus(
            online=bool(data.get("online", False)),
            good=bool(data.get("good", False)),
            stats=stats,
            extra={key: value for key, value in data.items() if key != "stat"},
        )

    async def get_version_info(self) -> NapCatVersionInfo:
        payload = await self.call_action("get_version_info")
        data = self._require_data_dict("get_version_info", payload)
        app_name = _string_or_none(data.get("app_name"))
        app_version = _string_or_none(data.get("app_version"))
        protocol_version = _string_or_none(data.get("protocol_version"))
        if app_name is None or app_version is None or protocol_version is None:
            raise NapCatTransportError(
                "get_version_info",
                "successful response did not contain app_name/app_version/protocol_version",
            )
        return NapCatVersionInfo(
            app_name=app_name,
            app_version=app_version,
            protocol_version=protocol_version,
            extra={
                key: value
                for key, value in data.items()
                if key not in {"app_name", "app_version", "protocol_version"}
            },
        )

    async def get_message(self, message_id: int | str) -> NapCatFetchedMessage:
        payload = await self.call_action("get_msg", message_id=str(message_id))
        data = self._require_data_dict("get_message", payload)
        sender = data.get("sender")
        if not isinstance(sender, dict):
            sender = {}
        sender_nickname = (
            sender.get("card") or sender.get("nickname") or sender.get("nick")
        )
        raw_message = data.get("raw_message")
        return NapCatFetchedMessage(
            message_id=_coerce_int(data.get("message_id")) or int(message_id),
            sender_id=_coerce_int(data.get("user_id")),
            sender_nickname=str(sender_nickname) if sender_nickname else None,
            time=_coerce_int(data.get("time")),
            message_str=str(raw_message) if isinstance(raw_message, str) else "",
            raw_message=str(raw_message) if isinstance(raw_message, str) else "",
            message_payload=data.get("message"),
            extra={
                "sender": sender,
                "message": data.get("message"),
                **{
                    key: value
                    for key, value in data.items()
                    if key not in {"sender", "message"}
                },
            },
        )

    async def get_group_info(self, group_id: int | str) -> dict[str, Any]:
        return self._require_data_dict(
            "get_group_info",
            await self.call_action("get_group_info", group_id=str(group_id)),
        )

    async def get_group_member_info(
        self,
        group_id: int | str,
        user_id: int | str,
        *,
        no_cache: bool | None = None,
    ) -> dict[str, Any]:
        return self._require_data_dict(
            "get_group_member_info",
            await self.call_action(
                "get_group_member_info",
                group_id=str(group_id),
                user_id=str(user_id),
                no_cache=no_cache,
            ),
        )

    async def get_group_member_list(
        self,
        group_id: int | str,
        *,
        no_cache: bool | None = None,
    ) -> list[Any]:
        payload = await self.call_action(
            "get_group_member_list",
            group_id=str(group_id),
            no_cache=no_cache,
        )
        data = self._require_data("get_group_member_list", payload)
        if not isinstance(data, list):
            raise NapCatTransportError(
                "get_group_member_list",
                "successful response did not contain a member list",
            )
        return data

    async def get_stranger_info(
        self,
        user_id: int | str,
        *,
        no_cache: bool = False,
    ) -> dict[str, Any]:
        return self._require_data_dict(
            "get_stranger_info",
            await self.call_action(
                "get_stranger_info",
                user_id=str(user_id),
                no_cache=no_cache,
            ),
        )

    async def get_forward_message(self, forward_id: int | str) -> dict[str, Any]:
        forward_id_str = str(forward_id).strip()
        if not forward_id_str:
            raise ValueError("forward_id must not be empty")
        payload = await self.call_action("get_forward_msg", message_id=forward_id_str)
        data = self._require_data("get_forward_message", payload)
        if isinstance(data, list):
            payload["data"] = {"messages": data}
            return payload
        if not isinstance(data, dict):
            raise NapCatTransportError(
                "get_forward_message",
                "successful response did not contain object or list data payload",
            )
        return payload

    async def get_image(
        self,
        *,
        file: str | None = None,
        file_id: str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action("get_image", file=file, file_id=file_id)
        )

    async def get_file(
        self,
        *,
        file: str | None = None,
        file_id: str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action("get_file", file=file, file_id=file_id)
        )

    async def get_group_file_url(
        self, *, group_id: int | str, file_id: str
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "get_group_file_url",
                group_id=str(group_id),
                file_id=file_id,
            )
        )

    async def get_private_file_url(self, *, file_id: str) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action("get_private_file_url", file_id=file_id)
        )

    async def get_online_file_messages(self, *, user_id: int | str) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action("get_online_file_msg", user_id=str(user_id))
        )

    async def create_flash_task(
        self,
        *,
        files: list[str] | str,
        name: str | None = None,
        thumb_path: str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "create_flash_task",
                files=files,
                name=name,
                thumb_path=thumb_path,
            )
        )

    async def get_flash_file_list(self, *, fileset_id: str) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action("get_flash_file_list", fileset_id=fileset_id)
        )

    async def get_flash_file_url(
        self,
        *,
        fileset_id: str,
        file_name: str | None = None,
        file_index: int | float | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "get_flash_file_url",
                fileset_id=fileset_id,
                file_name=file_name,
                file_index=float(file_index) if file_index is not None else None,
            )
        )

    async def receive_online_file(
        self,
        *,
        user_id: int | str,
        msg_id: str,
        element_id: str,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "receive_online_file",
                user_id=str(user_id),
                msg_id=msg_id,
                element_id=element_id,
            )
        )

    async def refuse_online_file(
        self,
        *,
        user_id: int | str,
        msg_id: str,
        element_id: str,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "refuse_online_file",
                user_id=str(user_id),
                msg_id=msg_id,
                element_id=element_id,
            )
        )

    async def cancel_online_file(
        self, *, user_id: int | str, msg_id: str
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "cancel_online_file",
                user_id=str(user_id),
                msg_id=msg_id,
            )
        )

    async def send_online_file(
        self,
        *,
        user_id: int | str,
        file_path: str,
        file_name: str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "send_online_file",
                user_id=str(user_id),
                file_path=file_path,
                file_name=file_name,
            )
        )

    async def send_online_folder(
        self,
        *,
        user_id: int | str,
        folder_path: str,
        folder_name: str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "send_online_folder",
                user_id=str(user_id),
                folder_path=folder_path,
                folder_name=folder_name,
            )
        )

    async def send_flash_message(
        self,
        *,
        fileset_id: str,
        user_id: int | str | None = None,
        group_id: int | str | None = None,
    ) -> dict[str, Any]:
        if (user_id is None) == (group_id is None):
            raise ValueError("Exactly one of user_id or group_id must be provided.")
        return self._build_action_payload(
            await self.call_action(
                "send_flash_msg",
                fileset_id=fileset_id,
                user_id=str(user_id) if user_id is not None else None,
                group_id=str(group_id) if group_id is not None else None,
            )
        )

    async def send_message(
        self,
        *,
        message: Any,
        user_id: int | str | None = None,
        group_id: int | str | None = None,
        auto_escape: bool = False,
        timeout_ms: float | None = None,
    ) -> NapCatSendMessageResult:
        if (user_id is None) == (group_id is None):
            raise ValueError("Exactly one of user_id or group_id must be provided.")
        payload = await self.call_action(
            "send_msg",
            message=self._normalize_message(message),
            message_type="private" if user_id is not None else "group",
            user_id=str(user_id) if user_id is not None else None,
            group_id=str(group_id) if group_id is not None else None,
            auto_escape=auto_escape,
            timeout=float(timeout_ms) if timeout_ms is not None else None,
        )
        return self._build_send_result("send_message", payload)

    async def send_private_message(
        self,
        *,
        user_id: int | str,
        message: Any,
        auto_escape: bool = False,
        timeout_ms: float | None = None,
    ) -> NapCatSendMessageResult:
        payload = await self.call_action(
            "send_private_msg",
            message=self._normalize_message(message),
            message_type="private",
            user_id=str(user_id),
            auto_escape=auto_escape,
            timeout=float(timeout_ms) if timeout_ms is not None else None,
        )
        return self._build_send_result("send_private_message", payload)

    async def send_private_forward_message(
        self,
        *,
        user_id: int | str,
        messages: list[object],
        source: str | None = None,
        summary: str | None = None,
        prompt: str | None = None,
        news: list[object] | None = None,
        timeout_ms: float | None = None,
    ) -> NapCatSendMessageResult:
        payload = await self.call_action(
            "send_private_forward_msg",
            message_type="private",
            user_id=str(user_id),
            message=self._normalize_message(messages),
            messages=self._normalize_message(messages),
            source=source,
            summary=summary,
            prompt=prompt,
            news=news,
            timeout=float(timeout_ms) if timeout_ms is not None else None,
        )
        return self._build_send_result("send_private_forward_message", payload)

    async def send_group_message(
        self,
        *,
        group_id: int | str,
        message: Any,
        auto_escape: bool = False,
        timeout_ms: float | None = None,
    ) -> NapCatSendMessageResult:
        payload = await self.call_action(
            "send_group_msg",
            message=self._normalize_message(message),
            message_type="group",
            group_id=str(group_id),
            auto_escape=auto_escape,
            timeout=float(timeout_ms) if timeout_ms is not None else None,
        )
        return self._build_send_result("send_group_message", payload)

    async def send_group_forward_message(
        self,
        *,
        group_id: int | str,
        messages: list[object],
        source: str | None = None,
        summary: str | None = None,
        prompt: str | None = None,
        news: list[object] | None = None,
        timeout_ms: float | None = None,
    ) -> NapCatSendMessageResult:
        payload = await self.call_action(
            "send_group_forward_msg",
            message_type="group",
            group_id=str(group_id),
            message=self._normalize_message(messages),
            messages=self._normalize_message(messages),
            source=source,
            summary=summary,
            prompt=prompt,
            news=news,
            timeout=float(timeout_ms) if timeout_ms is not None else None,
        )
        return self._build_send_result("send_group_forward_message", payload)

    async def delete_message(self, message_id: int | str) -> None:
        self._require_success_payload(
            "delete_message",
            await self.call_action("delete_msg", message_id=str(message_id)),
        )

    async def set_group_admin(
        self,
        *,
        group_id: int | str,
        user_id: int | str,
        enable: bool = True,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_group_admin",
                group_id=str(group_id),
                user_id=str(user_id),
                enable=enable,
            )
        )

    async def set_group_ban(
        self,
        *,
        group_id: int | str,
        user_id: int | str,
        duration: int | float = 0,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_group_ban",
                group_id=str(group_id),
                user_id=str(user_id),
                duration=float(duration),
            )
        )

    async def set_group_card(
        self,
        *,
        group_id: int | str,
        user_id: int | str,
        card: str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_group_card",
                group_id=str(group_id),
                user_id=str(user_id),
                card=card,
            )
        )

    async def set_group_kick(
        self,
        *,
        group_id: int | str,
        user_id: int | str,
        reject_add_request: bool | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_group_kick",
                group_id=str(group_id),
                user_id=str(user_id),
                reject_add_request=reject_add_request,
            )
        )

    async def set_group_kick_members(
        self,
        *,
        group_id: int | str,
        user_ids: list[int | str],
        reject_add_request: bool | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_group_kick_members",
                group_id=str(group_id),
                user_id=[str(user_id) for user_id in user_ids],
                reject_add_request=reject_add_request,
            )
        )

    async def set_group_leave(
        self,
        *,
        group_id: int | str,
        is_dismiss: bool | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_group_leave",
                group_id=str(group_id),
                is_dismiss=is_dismiss,
            )
        )

    async def set_group_whole_ban(
        self,
        *,
        group_id: int | str,
        enable: bool = True,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_group_whole_ban",
                group_id=str(group_id),
                enable=enable,
            )
        )

    async def set_essence_message(
        self,
        *,
        message_id: int | float | str,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action("set_essence_msg", message_id=message_id)
        )

    async def delete_essence_message(
        self,
        *,
        message_id: int | float | str | None = None,
        msg_seq: str | None = None,
        msg_random: str | None = None,
        group_id: int | str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "delete_essence_msg",
                message_id=message_id,
                msg_seq=msg_seq,
                msg_random=msg_random,
                group_id=str(group_id) if group_id is not None else None,
            )
        )

    async def send_like(
        self,
        *,
        user_id: int | str,
        times: int | float = 1,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "send_like",
                user_id=str(user_id),
                times=float(times),
            )
        )

    async def friend_poke(
        self,
        *,
        user_id: int | str,
        group_id: int | str | None = None,
        target_id: int | str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "friend_poke",
                user_id=str(user_id),
                group_id=str(group_id) if group_id is not None else None,
                target_id=str(target_id) if target_id is not None else None,
            )
        )

    async def group_poke(
        self,
        *,
        user_id: int | str,
        group_id: int | str | None = None,
        target_id: int | str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "group_poke",
                user_id=str(user_id),
                group_id=str(group_id) if group_id is not None else None,
                target_id=str(target_id) if target_id is not None else None,
            )
        )

    async def send_group_notice(
        self,
        *,
        group_id: int | str,
        content: str,
        pinned: int | float | None = None,
        type_: int | float | None = None,
        confirm_required: int | float | None = None,
        is_show_edit_card: int | float | None = None,
        tip_window_type: int | float | None = None,
        image: str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "_send_group_notice",
                group_id=str(group_id),
                content=content,
                pinned=float(pinned) if pinned is not None else 0.0,
                type=float(type_) if type_ is not None else 1.0,
                confirm_required=(
                    float(confirm_required) if confirm_required is not None else 1.0
                ),
                is_show_edit_card=(
                    float(is_show_edit_card) if is_show_edit_card is not None else 0.0
                ),
                tip_window_type=(
                    float(tip_window_type) if tip_window_type is not None else 0.0
                ),
                image=image,
            )
        )

    async def set_input_status(
        self,
        *,
        user_id: int | str,
        event_type: int | float = 1,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_input_status",
                user_id=str(user_id),
                event_type=int(event_type),
            )
        )

    async def get_group_msg_history(
        self,
        *,
        group_id: int | str,
        count: int = 20,
        message_seq: int | str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._get_message_history(
            operation="get_group_msg_history",
            base_params={"group_id": str(group_id)},
            count=count,
            message_seq=message_seq,
        )

    async def get_friend_msg_history(
        self,
        *,
        user_id: int | str,
        count: int = 20,
        message_seq: int | str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._get_message_history(
            operation="get_friend_msg_history",
            base_params={"user_id": str(user_id)},
            count=count,
            message_seq=message_seq,
        )

    async def fetch_custom_face(self, *, count: int = 48) -> list[Any]:
        payload = await self.call_action("fetch_custom_face", count=int(count))
        data = self._require_data("fetch_custom_face", payload)
        if not isinstance(data, list):
            raise NapCatTransportError(
                "fetch_custom_face",
                "successful response did not contain a custom face list",
            )
        return data

    async def get_ai_characters(
        self,
        *,
        group_id: int | str,
        chat_type: int | float = 1,
    ) -> list[Any]:
        payload = await self.call_action(
            "get_ai_characters",
            group_id=str(group_id),
            chat_type=int(chat_type),
        )
        data = self._require_data("get_ai_characters", payload)
        if not isinstance(data, list):
            raise NapCatTransportError(
                "get_ai_characters",
                "successful response did not contain an AI character list",
            )
        return data

    async def send_group_ai_record(
        self,
        *,
        group_id: int | str,
        character: str,
        text: str,
        chat_type: int | float = 1,
        timeout_seconds: float = 10.0,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "send_group_ai_record",
                group_id=str(group_id),
                character=character,
                text=text,
            )
        )

    async def set_friend_add_request(
        self,
        *,
        flag: str,
        approve: bool = True,
        remark: str | None = None,
    ) -> None:
        self._require_success_payload(
            "set_friend_add_request",
            await self.call_action(
                "set_friend_add_request",
                flag=flag,
                approve=approve,
                remark=remark,
            ),
        )

    async def set_group_add_request(
        self,
        *,
        flag: str,
        sub_type: str = "add",
        approve: bool = True,
        reason: str | None = None,
        count: float | None = None,
    ) -> None:
        self._require_success_payload(
            "set_group_add_request",
            await self.call_action(
                "set_group_add_request",
                flag=flag,
                sub_type=sub_type,
                approve=approve,
                reason=reason,
                count=float(count) if count is not None else None,
            ),
        )

    def _normalize_message(self, message: Any) -> Any:
        if isinstance(message, str):
            return message
        if isinstance(message, Sequence) and not isinstance(
            message, str | bytes | bytearray
        ):
            normalized: list[Any] = []
            for item in message:
                if isinstance(item, str):
                    normalized.append(self.text(item).to_dict())
                else:
                    to_dict = getattr(item, "to_dict", None)
                    if callable(to_dict):
                        normalized.append(to_dict())
                    else:
                        normalized.append(item)
            return normalized
        to_dict = getattr(message, "to_dict", None)
        if callable(to_dict):
            return to_dict()
        return message

    def _require_data_dict(
        self, operation: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        data = self._require_data(operation, payload)
        if not isinstance(data, dict):
            raise NapCatTransportError(
                operation,
                "successful response did not contain object data payload",
            )
        return data

    def _require_data(self, operation: str, payload: dict[str, Any]) -> Any:
        if not isinstance(payload, dict):
            raise NapCatTransportError(
                operation,
                f"action returned non-object payload: {type(payload).__name__}",
            )
        self._require_success_payload(operation, payload)
        if "data" not in payload:
            raise NapCatTransportError(
                operation,
                "successful response did not contain data payload",
            )
        return payload.get("data")

    async def _get_message_history(
        self,
        *,
        operation: str,
        base_params: dict[str, str],
        count: int,
        message_seq: int | str | None,
    ) -> list[dict[str, Any]]:
        page_size = 200
        total_needed = max(1, min(int(count), 999))

        def _build_params(
            seq: int | str | None,
            *,
            reverse_order: bool,
        ) -> dict[str, Any]:
            params: dict[str, Any] = dict(base_params)
            if seq is not None:
                params["message_seq"] = seq
            params["count"] = min(page_size, total_needed)
            params["reverse_order"] = reverse_order
            params["reverseOrder"] = reverse_order
            params["disable_get_url"] = False
            params["parse_mult_msg"] = True
            params["quick_reply"] = False
            return params

        async def _fetch_page(
            seq: int | str | None,
            *,
            reverse_order: bool,
        ) -> list[dict[str, Any]]:
            payload = await self.call_action(
                operation,
                **_build_params(seq, reverse_order=reverse_order),
            )
            return self._extract_message_history_items(operation, payload)

        if message_seq is not None:
            return await _fetch_page(message_seq, reverse_order=False)

        batch = await _fetch_page(None, reverse_order=False)
        if not batch:
            return []

        all_messages = list(batch)
        newest_id = max(self._history_message_id(item) for item in batch)

        while newest_id > 0:
            newer_batch = await _fetch_page(newest_id, reverse_order=False)
            if not newer_batch:
                break
            new_items = newer_batch
            if self._history_message_id(newer_batch[0]) == newest_id:
                new_items = newer_batch[1:]
            if not new_items:
                break
            all_messages.extend(new_items)
            newest_id = max(self._history_message_id(item) for item in new_items)

        while len(all_messages) < total_needed:
            oldest_id = self._history_message_id(all_messages[0])
            if oldest_id <= 0:
                break
            older_batch = await _fetch_page(oldest_id, reverse_order=True)
            if not older_batch:
                break
            older_items = older_batch
            if self._history_message_id(older_batch[-1]) == oldest_id:
                older_items = older_batch[:-1]
            if not older_items:
                break
            all_messages = list(reversed(older_items)) + all_messages
            if len(older_batch) < page_size:
                break

        return all_messages[-total_needed:]

    def _extract_message_history_items(
        self,
        operation: str,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        self._require_success_payload(operation, payload)

        messages = payload.get("messages")
        if isinstance(messages, list):
            return [item for item in messages if isinstance(item, dict)]

        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            nested_messages = data.get("messages")
            if isinstance(nested_messages, list):
                return [item for item in nested_messages if isinstance(item, dict)]

        raise NapCatTransportError(
            operation,
            "successful response did not contain a message history list",
        )

    def _history_message_id(self, item: Mapping[str, Any]) -> int:
        return _coerce_int(item.get("message_id")) or 0

    def _require_success_payload(self, operation: str, payload: dict[str, Any]) -> None:
        status = payload.get("status")
        retcode = _coerce_int(payload.get("retcode"))
        message = payload.get("message")
        wording = payload.get("wording")

        if status != "ok" or retcode not in (None, 0):
            raise NapCatApiError(
                operation,
                status=str(status) if status is not None else None,
                retcode=retcode,
                message=str(message) if isinstance(message, str) else None,
                wording=str(wording) if isinstance(wording, str) else None,
            )

    def _build_send_result(
        self, operation: str, payload: dict[str, Any]
    ) -> NapCatSendMessageResult:
        data = self._require_data_dict(operation, payload)
        message_id = _coerce_int(data.get("message_id"))
        if message_id is None:
            raise NapCatTransportError(
                operation,
                "successful response did not contain message_id",
            )
        return NapCatSendMessageResult(
            message_id=message_id,
            res_id=_string_or_none(data.get("res_id")),
            forward_id=_string_or_none(data.get("forward_id")),
            extra={
                key: value
                for key, value in data.items()
                if key not in {"message_id", "res_id", "forward_id"}
            },
        )

    def _build_action_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_success_payload("action", payload)
        result = {
            "status": cast(str, payload.get("status", "ok")),
            "retcode": _coerce_int(payload.get("retcode")) or 0,
            "data": payload.get("data"),
        }
        if isinstance(payload.get("message"), str):
            result["message"] = payload["message"]
        if isinstance(payload.get("wording"), str):
            result["wording"] = payload["wording"]
        return result
