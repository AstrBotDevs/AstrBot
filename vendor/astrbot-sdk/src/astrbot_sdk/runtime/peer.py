from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from ..errors import (
    AstrBotSDKError,
    HostUnavailable,
    InvalidRequest,
    RemoteError,
)
from ..protocol import (
    CancelFrame,
    ErrorFrame,
    ProtocolFrame,
    RequestFrame,
    ResponseFrame,
)

FrameSender = Callable[[ProtocolFrame], Awaitable[None]]
RequestHandler = Callable[[RequestFrame], Awaitable[Any]]
RemoteErrorFactory = Callable[[str, str], RemoteError]


class Peer:
    """Correlate bidirectional requests over one framed transport."""

    def __init__(
        self,
        *,
        send: FrameSender,
        request_handler: RequestHandler,
        request_id_prefix: str,
        remote_error_factory: RemoteErrorFactory,
        internal_error_code: str = "INTERNAL_ERROR",
    ) -> None:
        """Initialize a protocol peer.

        Args:
            send: Coroutine that writes one frame to the transport.
            request_handler: Coroutine that handles requests from the remote peer.
            request_id_prefix: Prefix for locally generated request IDs.
            remote_error_factory: Factory for errors returned by the remote peer.
            internal_error_code: Error code for unexpected request handler failures.
        """
        self._send = send
        self._request_handler = request_handler
        self._request_id_prefix = request_id_prefix
        self._remote_error_factory = remote_error_factory
        self._internal_error_code = internal_error_code
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._inbound: dict[str, asyncio.Task[None]] = {}
        self._closed_error: Exception | None = None

    async def request(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> Any:
        """Call one method exposed by the remote peer.

        Args:
            method: Remote method name.
            params: JSON-compatible request parameters.
            timeout_seconds: Optional timeout in seconds.

        Returns:
            The remote response result.

        Raises:
            HostUnavailable: The peer is closed.
            RemoteError: The remote method returns an error.
            TimeoutError: The request exceeds the supplied timeout.
        """
        if self._closed_error is not None:
            raise HostUnavailable("protocol peer is closed") from self._closed_error
        if not method:
            raise InvalidRequest("request method must be a non-empty string")

        request_id = f"{self._request_id_prefix}{uuid.uuid4().hex}"
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._send(RequestFrame(id=request_id, method=method, params=params))
            if timeout_seconds is None:
                return await future
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        except (TimeoutError, asyncio.CancelledError):
            with contextlib.suppress(Exception):
                await self._send(CancelFrame(id=request_id))
            raise
        except Exception:
            if not future.done():
                future.cancel()
            raise
        finally:
            self._pending.pop(request_id, None)

    def has_pending(self, request_id: str) -> bool:
        """Return whether an outbound request ID is still active."""
        return request_id in self._pending

    async def receive(self, frame: ProtocolFrame) -> bool:
        """Process a generic bidirectional RPC frame when applicable.

        Args:
            frame: Decoded frame received from the remote peer.

        Returns:
            Whether the frame was consumed by the generic RPC layer.

        Raises:
            InvalidRequest: A duplicate inbound request ID is received.
        """
        if isinstance(frame, ResponseFrame):
            future = self._pending.pop(frame.id, None)
            if future is None:
                return False
            if not future.done():
                future.set_result(frame.result)
            return True

        if isinstance(frame, ErrorFrame):
            future = self._pending.pop(frame.id, None)
            if future is None:
                return False
            if not future.done():
                future.set_exception(
                    self._remote_error_factory(frame.code, frame.message)
                )
            return True

        if isinstance(frame, RequestFrame):
            if frame.id in self._inbound:
                raise InvalidRequest(f"duplicate inbound request id: {frame.id}")
            task = asyncio.create_task(self._run_inbound_request(frame))
            self._inbound[frame.id] = task
            return True

        if isinstance(frame, CancelFrame):
            task = self._inbound.get(frame.id)
            if task is None:
                return False
            task.cancel()
            return True

        return False

    async def close(self, error: Exception | None = None) -> None:
        """Fail pending calls and cancel inbound work.

        Args:
            error: Connection failure reported to pending callers.
        """
        if self._closed_error is not None:
            return
        self._closed_error = error or HostUnavailable("protocol peer closed")
        for future in tuple(self._pending.values()):
            if not future.done():
                future.set_exception(self._closed_error)
        self._pending.clear()

        current = asyncio.current_task()
        tasks = [
            task
            for task in self._inbound.values()
            if task is not current and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._inbound.clear()

    async def _run_inbound_request(self, frame: RequestFrame) -> None:
        """Execute one request and return its terminal frame.

        Args:
            frame: Inbound request to execute.
        """
        try:
            result = await self._request_handler(frame)
            await self._send(ResponseFrame(id=frame.id, result=result))
        except asyncio.CancelledError:
            if self._closed_error is None:
                with contextlib.suppress(Exception):
                    await self._send(
                        ErrorFrame(
                            id=frame.id,
                            code="CANCELLED",
                            message="request was cancelled",
                        )
                    )
        except BaseException as exc:  # noqa: BLE001 - plugin code may raise SystemExit
            code = (
                exc.code
                if isinstance(exc, AstrBotSDKError)
                else self._internal_error_code
            )
            with contextlib.suppress(Exception):
                await self._send(ErrorFrame(id=frame.id, code=code, message=str(exc)))
        finally:
            self._inbound.pop(frame.id, None)
