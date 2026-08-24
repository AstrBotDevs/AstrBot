import asyncio
import inspect
import json
from typing import Any

from aiocqhttp import CQHttp
from aiocqhttp.api_impl import ResultStore
from quart import websocket

from astrbot.api import logger


class GuardedCQHttp(CQHttp):
    """CQHttp server with stale reverse-WebSocket eviction."""

    def __init__(
        self,
        *args: Any,
        ws_receive_timeout_sec: float = 60.0,
        connection_label: str = "aiocqhttp",
        **kwargs: Any,
    ) -> None:
        self.ws_receive_timeout_sec = max(float(ws_receive_timeout_sec), 0.0)
        self.connection_label = connection_label
        super().__init__(*args, **kwargs)

    async def _receive_payload(self, ws: Any) -> tuple[bool, dict | None]:
        """Receive and decode one reverse-WebSocket payload.

        Args:
            ws: Active Quart-compatible WebSocket connection.

        Returns:
            A tuple containing the connection state and a decoded JSON object.
        """
        try:
            receive = ws.receive()
            if self.ws_receive_timeout_sec > 0:
                raw_payload = await asyncio.wait_for(
                    receive,
                    timeout=self.ws_receive_timeout_sec,
                )
            else:
                raw_payload = await receive
        except TimeoutError:
            logger.warning(
                "aiocqhttp reverse WebSocket timed out after %.0f seconds "
                "without an inbound frame; closing stale connection for adapter %s.",
                self.ws_receive_timeout_sec,
                self.connection_label,
            )
            await self._close_ws(ws, code=1011, reason="Inbound frame timeout")
            return False, None

        try:
            payload = json.loads(raw_payload)
        except (TypeError, ValueError):
            payload = None
        return True, payload if isinstance(payload, dict) else None

    async def _close_ws(self, ws: Any, *, code: int, reason: str) -> None:
        """Close a WebSocket without assuming a specific close signature.

        Args:
            ws: WebSocket connection to close.
            code: WebSocket close code.
            reason: Human-readable close reason.
        """
        close = getattr(ws, "close", None)
        if not callable(close):
            return
        try:
            close_result = close(code=code, reason=reason)
        except TypeError:
            try:
                close_result = close()
            except Exception:
                logger.debug(
                    "Failed to close aiocqhttp reverse WebSocket for adapter %s.",
                    self.connection_label,
                    exc_info=True,
                )
                return
        except Exception:
            logger.debug(
                "Failed to close aiocqhttp reverse WebSocket for adapter %s.",
                self.connection_label,
                exc_info=True,
            )
            return

        if not inspect.isawaitable(close_result):
            return
        try:
            await asyncio.wait_for(close_result, timeout=5.0)
        except Exception:
            logger.debug(
                "Failed to close aiocqhttp reverse WebSocket for adapter %s.",
                self.connection_label,
                exc_info=True,
            )

    async def _register_api_client(self, self_id: str, ws: Any) -> None:
        """Register an API client and evict an older same-account connection.

        Args:
            self_id: OneBot self identifier supplied by the connection.
            ws: Newly connected WebSocket.
        """
        previous = self._wsr_api_clients.get(self_id)
        self._wsr_api_clients[self_id] = ws
        if previous is None or previous is ws:
            return

        logger.warning(
            "Replacing an existing aiocqhttp reverse WebSocket connection for "
            "adapter %s.",
            self.connection_label,
        )
        await self._close_ws(previous, code=1000, reason="Replaced by new connection")

    def _remove_api_client(self, self_id: str, ws: Any) -> None:
        """Remove a client only when it still owns the account mapping.

        Args:
            self_id: OneBot self identifier supplied by the connection.
            ws: WebSocket completing its cleanup path.
        """
        if self._wsr_api_clients.get(self_id) is ws:
            del self._wsr_api_clients[self_id]

    async def _handle_wsr_event(self) -> None:
        ws = websocket._get_current_object()
        self._wsr_event_clients.add(ws)
        try:
            while True:
                connected, payload = await self._receive_payload(ws)
                if not connected:
                    return
                if payload is not None:
                    asyncio.create_task(self._handle_event_with_response(payload))
        finally:
            self._wsr_event_clients.discard(ws)

    async def _handle_wsr_api(self) -> None:
        ws = websocket._get_current_object()
        self_id = ws.headers["X-Self-ID"]
        await self._register_api_client(self_id, ws)
        try:
            while True:
                connected, payload = await self._receive_payload(ws)
                if not connected:
                    return
                if payload is not None:
                    ResultStore.add(payload)
        finally:
            self._remove_api_client(self_id, ws)

    async def _handle_wsr_universal(self) -> None:
        ws = websocket._get_current_object()
        self_id = ws.headers["X-Self-ID"]
        await self._register_api_client(self_id, ws)
        self._wsr_event_clients.add(ws)
        try:
            while True:
                connected, payload = await self._receive_payload(ws)
                if not connected:
                    return
                if payload is None:
                    continue
                if "post_type" in payload:
                    asyncio.create_task(self._handle_event_with_response(payload))
                else:
                    ResultStore.add(payload)
        finally:
            self._wsr_event_clients.discard(ws)
            self._remove_api_client(self_id, ws)
