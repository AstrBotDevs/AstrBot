"""Dashboard Extension Protocol v1 catalog and Action dispatch."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import tempfile
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ValidationError
from starlette.datastructures import UploadFile

from astrbot.core.star.dashboard_extension import (
    ALL_OPEN_API_SCOPES,
    DashboardActionContext,
    DashboardActionError,
    DashboardActionKind,
    DashboardCancellation,
    DashboardExtensionRegistry,
    DashboardExtensionSnapshot,
    DashboardExtensionState,
    DashboardFile,
    DashboardFileAction,
    DashboardJsonAction,
    DashboardRegisteredAction,
    DashboardUploadAction,
)
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.dashboard.responses import ApiError
from astrbot.dashboard.services.auth_service import DashboardSessionPrincipal
from astrbot.dashboard.services.plugin_file_ticket_service import (
    CreatedFileTicket,
    PluginFileTicketService,
)
from astrbot.dashboard.services.plugin_page_session_service import (
    CreatedPageSession,
    PluginPageSessionService,
)

logger = logging.getLogger("astrbot")

MAX_JSON_REQUEST_BYTES = 1024 * 1024
MAX_JSON_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_UPLOAD_FILE_BYTES = 16 * 1024 * 1024
MAX_UPLOAD_METADATA_BYTES = 64 * 1024
MAX_UPLOAD_FILENAME_BYTES = 255
RATE_BUCKET_MAX_ENTRIES = 4096
RATE_BUCKET_IDLE_SECONDS = 600.0


class PluginDashboardRateLimitError(ApiError):
    """Rate/concurrency rejection carrying the HTTP Retry-After value."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many requests", status_code=429)
        self.retry_after = max(1, retry_after)


@dataclass
class _RateBucket:
    tokens: float
    last_refill: float
    last_accessed: float


class _Cancellation(DashboardCancellation):
    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()

    def cancel(self) -> None:
        self._event.set()


class _UploadedFile:
    def __init__(
        self,
        path: Path,
        filename: str,
        content_type: str,
        size: int,
    ) -> None:
        self._path = path
        self.filename = filename
        self.content_type = content_type
        self.size = size

    def iter_chunks(self, chunk_size: int = 64 * 1024) -> AsyncIterator[bytes]:
        async def iterator() -> AsyncIterator[bytes]:
            with self._path.open("rb") as handle:
                while chunk := await asyncio.to_thread(handle.read, chunk_size):
                    yield chunk

        return iterator()


def _json_size(value: Any) -> int:
    try:
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise ApiError("Invalid request payload", status_code=422) from exc


def _detected_image_type(sample: bytes) -> str | None:
    if sample.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if sample.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if sample.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if sample.startswith(b"RIFF") and sample[8:12] == b"WEBP":
        return "image/webp"
    if sample.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    return None


class PluginDashboardService:
    """Expose one fixed HTTP dispatcher over the committed extension Registry."""

    _RATE_LIMITS = {
        "session": (5, 20 / 60),
        "json": (30, 120 / 60),
        "upload": (5, 20 / 60),
        "file": (15, 60 / 60),
    }

    def __init__(
        self,
        registry: DashboardExtensionRegistry,
        page_sessions: PluginPageSessionService,
        file_tickets: PluginFileTicketService,
    ) -> None:
        self.registry = registry
        self.page_sessions = page_sessions
        self.file_tickets = file_tickets
        self._rate_buckets: dict[tuple[str, str, str], _RateBucket] = {}
        self._rate_lock = asyncio.Lock()
        self._concurrency_lock = asyncio.Lock()
        self._user_extension_inflight: dict[tuple[str, str], int] = {}
        self._extension_inflight: dict[str, int] = {}

    def _snapshot(self, extension_id: str) -> DashboardExtensionSnapshot:
        record = self.registry.get_record(extension_id)
        if record is None:
            raise ApiError("Not found", status_code=404)
        state, snapshot = record
        if state is DashboardExtensionState.DRAINING:
            raise ApiError("Plugin temporarily unavailable", status_code=503)
        if state is not DashboardExtensionState.ACTIVE:
            raise ApiError("Not found", status_code=404)
        return snapshot

    @staticmethod
    def _action_catalog(action: DashboardRegisteredAction) -> dict[str, Any]:
        spec = action.spec
        payload: dict[str, Any] = {
            "id": action.id,
            "kind": action.kind.value,
            "required_scope": spec.required_scope,
            "description": spec.description,
        }
        if isinstance(spec, DashboardJsonAction):
            payload.update(
                input_schema=spec.input_model.model_json_schema(),
                output_schema=spec.output_model.model_json_schema(),
            )
        elif isinstance(spec, DashboardUploadAction):
            payload.update(
                input_schema=spec.fields_model.model_json_schema(),
                output_schema=spec.output_model.model_json_schema(),
                max_file_bytes=min(spec.max_file_bytes, MAX_UPLOAD_FILE_BYTES),
                allowed_content_types=sorted(spec.allowed_content_types),
                allowed_extensions=sorted(spec.allowed_extensions),
            )
        elif isinstance(spec, DashboardFileAction):
            payload.update(
                input_schema=spec.input_model.model_json_schema(),
                disposition=spec.disposition,
                max_file_bytes=spec.max_file_bytes,
                allowed_content_types=sorted(spec.allowed_content_types),
            )
        return payload

    def catalog(
        self,
        extension_id: str,
        _principal: DashboardSessionPrincipal,
    ) -> dict[str, Any]:
        snapshot = self._snapshot(extension_id)
        actions = {
            action_id: action
            for action_id, action in snapshot.actions.items()
            if action.spec.required_scope in ALL_OPEN_API_SCOPES
        }
        return {
            "protocol_version": 1,
            "extension_id": snapshot.extension_id,
            "plugin_name": snapshot.plugin_name,
            "plugin_generation": snapshot.generation,
            "pages": [
                {
                    "id": page.id,
                    "title": page.title,
                    "icon": page.icon,
                    "actions": [item for item in page.actions if item in actions],
                }
                for page in snapshot.pages
            ],
            "actions": [
                self._action_catalog(action)
                for action in sorted(actions.values(), key=lambda item: item.id)
            ],
        }

    def action_required_scope(self, extension_id: str, action_id: str) -> str:
        """Return one registered Action's declared authorization scope.

        This lookup happens before request-body processing, so a Dashboard
        principal is authorized before it can invoke a plugin handler. The
        invocation path validates the page capability and Action kind again.
        """

        snapshot = self._snapshot(extension_id)
        action = snapshot.actions.get(action_id)
        if action is None:
            raise ApiError("Not found", status_code=404)
        return action.spec.required_scope

    async def create_page_session(
        self,
        extension_id: str,
        page_id: str,
        expected_generation: str,
        principal: DashboardSessionPrincipal,
    ) -> CreatedPageSession:
        await self._consume_rate(principal.username, extension_id, "session")
        return await self.page_sessions.create_session(
            extension_id,
            page_id,
            expected_generation,
            principal,
        )

    async def invoke_json(
        self,
        extension_id: str,
        action_id: str,
        instance_id: str,
        expected_generation: str,
        payload: Any,
        principal: DashboardSessionPrincipal,
    ) -> dict[str, Any]:
        instance, snapshot, action = await self._resolve_action(
            extension_id,
            action_id,
            instance_id,
            expected_generation,
            DashboardActionKind.JSON,
            principal,
        )
        if _json_size(payload) > MAX_JSON_REQUEST_BYTES:
            raise ApiError("Request body is too large", status_code=413)
        await self._consume_rate(principal.username, extension_id, "json")
        spec = action.spec
        assert isinstance(spec, DashboardJsonAction)
        model = self._validate_input(spec.input_model, payload)
        result = await self._invoke_handler(
            snapshot,
            instance.page.id,
            action,
            principal,
            request_bytes=_json_size(payload),
            arguments=(model,),
        )
        try:
            output = spec.output_model.model_validate(result)
            data = output.model_dump(mode="json")
        except ValidationError as exc:
            logger.error(
                "Plugin Dashboard Action output validation failed",
                extra=self._log_fields(snapshot, instance.page.id, action, principal),
            )
            raise ApiError("Plugin operation failed", status_code=500) from exc
        if _json_size(data) > MAX_JSON_RESPONSE_BYTES:
            raise ApiError("Plugin operation failed", status_code=500)
        return data

    async def invoke_upload(
        self,
        extension_id: str,
        action_id: str,
        instance_id: str,
        expected_generation: str,
        fields: Any,
        upload: UploadFile,
        principal: DashboardSessionPrincipal,
    ) -> dict[str, Any]:
        instance, snapshot, action = await self._resolve_action(
            extension_id,
            action_id,
            instance_id,
            expected_generation,
            DashboardActionKind.UPLOAD,
            principal,
        )
        if _json_size(fields) > MAX_UPLOAD_METADATA_BYTES:
            raise ApiError("Upload metadata is too large", status_code=413)
        await self._consume_rate(principal.username, extension_id, "upload")
        spec = action.spec
        assert isinstance(spec, DashboardUploadAction)
        model = self._validate_input(spec.fields_model, fields)
        filename = (upload.filename or "").strip()
        if (
            not filename
            or len(filename.encode("utf-8")) > MAX_UPLOAD_FILENAME_BYTES
            or any(
                character in filename for character in ("\x00", "\r", "\n", "/", "\\")
            )
        ):
            raise ApiError("Invalid upload filename", status_code=422)
        extension = Path(filename).suffix.lower()
        if spec.allowed_extensions and extension not in spec.allowed_extensions:
            raise ApiError("Upload file type is not allowed", status_code=415)
        content_type = (
            (upload.content_type or "application/octet-stream")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        if (
            spec.allowed_content_types
            and content_type not in spec.allowed_content_types
        ):
            raise ApiError("Upload media type is not allowed", status_code=415)
        limit = min(spec.max_file_bytes, MAX_UPLOAD_FILE_BYTES)
        temp_root = Path(get_astrbot_temp_path()) / "plugin_dashboard_uploads"
        temp_root.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix="upload_", dir=temp_root)
        os.close(descriptor)
        temp_path = Path(temp_name)
        size = 0
        sample = bytearray()
        try:
            with temp_path.open("wb") as destination:
                while chunk := await upload.read(64 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise ApiError("Upload is too large", status_code=413)
                    if len(sample) < 32:
                        sample.extend(chunk[: 32 - len(sample)])
                    await asyncio.to_thread(destination.write, chunk)
            if size == 0:
                raise ApiError("Empty uploads are not supported", status_code=422)
            detected = _detected_image_type(bytes(sample))
            if content_type.startswith("image/") and detected != content_type:
                raise ApiError(
                    "Upload media type does not match content", status_code=415
                )
            uploaded = _UploadedFile(temp_path, filename, content_type, size)
            result = await self._invoke_handler(
                snapshot,
                instance.page.id,
                action,
                principal,
                request_bytes=size + _json_size(fields),
                arguments=(uploaded, model),
            )
            try:
                output = spec.output_model.model_validate(result)
                data = output.model_dump(mode="json")
            except ValidationError as exc:
                raise ApiError("Plugin operation failed", status_code=500) from exc
            if _json_size(data) > MAX_JSON_RESPONSE_BYTES:
                raise ApiError("Plugin operation failed", status_code=500)
            return data
        finally:
            await upload.close()
            temp_path.unlink(missing_ok=True)

    async def invoke_file(
        self,
        extension_id: str,
        action_id: str,
        instance_id: str,
        expected_generation: str,
        expected_disposition: str,
        payload: Any,
        principal: DashboardSessionPrincipal,
    ) -> CreatedFileTicket:
        instance, snapshot, action = await self._resolve_action(
            extension_id,
            action_id,
            instance_id,
            expected_generation,
            DashboardActionKind.FILE,
            principal,
        )
        spec = action.spec
        assert isinstance(spec, DashboardFileAction)
        if spec.disposition != expected_disposition:
            raise ApiError("File disposition mismatch", status_code=409)
        if _json_size(payload) > MAX_JSON_REQUEST_BYTES:
            raise ApiError("Request body is too large", status_code=413)
        await self._consume_rate(principal.username, extension_id, "file")
        model = self._validate_input(spec.input_model, payload)
        result = await self._invoke_handler(
            snapshot,
            instance.page.id,
            action,
            principal,
            request_bytes=_json_size(payload),
            arguments=(model,),
        )
        if not isinstance(result, DashboardFile):
            raise ApiError("Plugin operation failed", status_code=500)
        return await self.file_tickets.create_ticket(
            snapshot,
            action_id,
            spec,
            result,
            principal,
        )

    async def _resolve_action(
        self,
        extension_id: str,
        action_id: str,
        instance_id: str,
        expected_generation: str,
        expected_kind: DashboardActionKind,
        principal: DashboardSessionPrincipal,
    ):
        instance = await self.page_sessions.get_instance(
            instance_id,
            extension_id,
            expected_generation,
            principal,
        )
        if action_id not in instance.page.actions:
            raise ApiError("Not found", status_code=404)
        snapshot = self._snapshot(extension_id)
        action = snapshot.actions.get(action_id)
        if action is None:
            raise ApiError("Not found", status_code=404)
        if action.kind is not expected_kind:
            raise ApiError("Action kind mismatch", status_code=409)
        if action.spec.required_scope not in ALL_OPEN_API_SCOPES:
            raise ApiError("Insufficient scope", status_code=403)
        return instance, snapshot, action

    @staticmethod
    def _validate_input(model_type: type[BaseModel], payload: Any) -> BaseModel:
        try:
            return model_type.model_validate(payload)
        except ValidationError as exc:
            raise ApiError("Invalid request payload", status_code=422) from exc

    @asynccontextmanager
    async def _concurrency_slot(self, username: str, extension_id: str):
        user_key = (username, extension_id)
        async with self._concurrency_lock:
            user_count = self._user_extension_inflight.get(user_key, 0)
            extension_count = self._extension_inflight.get(extension_id, 0)
            if user_count >= 4 or extension_count >= 16:
                raise PluginDashboardRateLimitError(1)
            self._user_extension_inflight[user_key] = user_count + 1
            self._extension_inflight[extension_id] = extension_count + 1
        try:
            yield
        finally:
            async with self._concurrency_lock:
                next_user = self._user_extension_inflight.get(user_key, 1) - 1
                next_extension = self._extension_inflight.get(extension_id, 1) - 1
                if next_user:
                    self._user_extension_inflight[user_key] = next_user
                else:
                    self._user_extension_inflight.pop(user_key, None)
                if next_extension:
                    self._extension_inflight[extension_id] = next_extension
                else:
                    self._extension_inflight.pop(extension_id, None)

    async def _invoke_handler(
        self,
        snapshot: DashboardExtensionSnapshot,
        page_id: str,
        action: DashboardRegisteredAction,
        principal: DashboardSessionPrincipal,
        *,
        request_bytes: int,
        arguments: tuple[Any, ...],
    ) -> Any:
        request_id = str(uuid.uuid4())
        cancellation = _Cancellation()
        context = DashboardActionContext(
            request_id=request_id,
            username=principal.username,
            # The route has already authorized this exact Action.  Do not
            # hand a plugin a fabricated wildcard capability set: a handler
            # may safely observe only the scope that admitted this call.
            scopes=frozenset({action.spec.required_scope}),
            extension_id=snapshot.extension_id,
            plugin_name=snapshot.plugin_name,
            cancellation=cancellation,
        )
        task = asyncio.current_task()
        if task is None:
            raise ApiError("Plugin operation failed", status_code=500)
        started = time.monotonic()
        fields = self._log_fields(snapshot, page_id, action, principal, request_id)
        outcome = "error"
        async with self._concurrency_slot(principal.username, snapshot.extension_id):
            try:
                self.registry.register_inflight(
                    snapshot.extension_id,
                    snapshot.generation,
                    task,
                )
            except ValueError as exc:
                raise ApiError(
                    "Plugin temporarily unavailable", status_code=503
                ) from exc
            try:
                handler = cast(Callable[..., Awaitable[Any]], action.handler)
                result = await asyncio.wait_for(
                    handler(*arguments, context),
                    timeout=action.spec.timeout_seconds,
                )
                outcome = "ok"
                return result
            except TimeoutError as exc:
                cancellation.cancel()
                outcome = "timeout"
                raise ApiError("Plugin operation timed out", status_code=504) from exc
            except DashboardActionError as exc:
                outcome = "plugin_error"
                raise ApiError(
                    exc.public_message,
                    status_code=400,
                    data={
                        "code": exc.code,
                        "request_id": request_id,
                        "retryable": False,
                    },
                ) from exc
            except asyncio.CancelledError:
                cancellation.cancel()
                outcome = "cancelled"
                raise
            except ApiError:
                raise
            except Exception as exc:
                stack: list[str] = []
                traceback_cursor = exc.__traceback__
                while traceback_cursor is not None:
                    frame = traceback_cursor.tb_frame
                    stack.append(
                        f"{Path(frame.f_code.co_filename).name}:"
                        f"{traceback_cursor.tb_lineno}:{frame.f_code.co_name}"
                    )
                    traceback_cursor = traceback_cursor.tb_next
                logger.error(
                    "Plugin Dashboard Action failed (%s) at %s",
                    type(exc).__name__,
                    stack,
                    extra=fields,
                )
                raise ApiError(
                    "Plugin operation failed",
                    status_code=500,
                    data={
                        "code": "plugin_action_failed",
                        "request_id": request_id,
                        "retryable": False,
                    },
                ) from exc
            finally:
                self.registry.unregister_inflight(
                    snapshot.extension_id,
                    snapshot.generation,
                    task,
                )
                logger.info(
                    "Plugin Dashboard Action completed",
                    extra={
                        **fields,
                        "duration_ms": round((time.monotonic() - started) * 1000),
                        "request_bytes": request_bytes,
                        "response_bytes": None,
                        "outcome": outcome,
                    },
                )

    @staticmethod
    def _log_fields(
        snapshot: DashboardExtensionSnapshot,
        page_id: str,
        action: DashboardRegisteredAction,
        principal: DashboardSessionPrincipal,
        request_id: str | None = None,
    ) -> dict[str, object]:
        return {
            "request_id": request_id,
            "plugin_name": snapshot.plugin_name,
            "extension_id": snapshot.extension_id,
            "plugin_generation": snapshot.generation,
            "page_id": page_id,
            "action_id": action.id,
            "action_kind": action.kind.value,
            "username": principal.username,
            "auth_session_hash": hashlib.sha256(principal.sid.encode()).hexdigest()[
                :16
            ],
        }

    async def _consume_rate(
        self,
        username: str,
        extension_id: str,
        operation: str,
    ) -> None:
        capacity, refill_rate = self._RATE_LIMITS[operation]
        key = (username, extension_id, operation)
        async with self._rate_lock:
            now = time.monotonic()
            stale = [
                item
                for item, bucket in self._rate_buckets.items()
                if now - bucket.last_accessed >= RATE_BUCKET_IDLE_SECONDS
            ]
            for item in stale:
                self._rate_buckets.pop(item, None)
            bucket = self._rate_buckets.get(key)
            if bucket is None:
                if len(self._rate_buckets) >= RATE_BUCKET_MAX_ENTRIES:
                    raise PluginDashboardRateLimitError(1)
                bucket = _RateBucket(float(capacity), now, now)
                self._rate_buckets[key] = bucket
            elapsed = now - bucket.last_refill
            bucket.tokens = min(float(capacity), bucket.tokens + elapsed * refill_rate)
            bucket.last_refill = now
            bucket.last_accessed = now
            if bucket.tokens < 1:
                raise PluginDashboardRateLimitError(
                    math.ceil((1 - bucket.tokens) / refill_rate)
                )
            bucket.tokens -= 1
