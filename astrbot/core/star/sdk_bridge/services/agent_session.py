from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from astrbot_sdk import agents as sdk
from astrbot_sdk.errors import InvalidRequest, NotFound, RateLimited
from astrbot_sdk.events import UMO, MessageType

from astrbot.core.agent import input as core_input
from astrbot.core.agent.events import OutputReady
from astrbot.core.agent.output import InlineMedia, PathMedia, URLMedia

from ..convert import to_umo_string
from .assets import _MAX_ASSET_BYTES

if TYPE_CHECKING:
    from astrbot.core.agent.runtime import InputReceipt
    from astrbot.core.agent_service import AgentRun
    from astrbot.core.platform.astr_message_event import AstrMessageEvent

    from ..bridge import SDKPluginBridge

_MAX_RUNS = 128
_MAX_STEERING_RECEIPTS = 128


class AgentSessionService:
    """Expose Core's configured Agent through connection-owned turn handles."""

    capability_id = "agent.run"

    def __init__(self, bridge: SDKPluginBridge) -> None:
        self._bridge = bridge
        self._runs: dict[str, AgentRun] = {}
        self._receipts: dict[str, dict[str, InputReceipt]] = {}
        self._admission = asyncio.Lock()
        self._media_cache: dict[str, dict[Any, Any]] = {}

    async def close(self) -> None:
        """Drop handles and cancel unfinished turns when the Runner disconnects."""
        async with self._admission:
            runs = list(self._runs.values())
            self._runs.clear()
            self._receipts.clear()
            self._media_cache.clear()
        await asyncio.gather(
            *(run.cancel() for run in runs if not run.done), return_exceptions=True
        )

    def _inputs(self, values: Any) -> list[core_input.InputComponent]:
        """Resolve portable Runner input to validated Core components.

        Args:
            values: Decoded SDK input components in presentation order.

        Returns:
            Core components with public URLs or Host-resolved asset paths.

        Raises:
            InvalidRequest: An input component is absent or unsupported.
        """
        if not isinstance(values, list) or not values:
            raise InvalidRequest("input_message must contain at least one component")
        content = []
        for value in values:
            if isinstance(value, sdk.PlainInput):
                content.append({"type": "plain", "text": value.text})
                continue
            if not isinstance(value, sdk.ImageInput | sdk.FileInput):
                raise InvalidRequest("unknown Agent input component")
            item = {"type": "image" if isinstance(value, sdk.ImageInput) else "file"}
            if isinstance(value.source, sdk.AssetRef):
                item["path"] = str(
                    self._bridge._require_asset_store().resolve(value.source)
                )
            elif isinstance(value.source, str) and value.source.startswith(
                ("http://", "https://")
            ):
                item["url"] = value.source
            else:
                raise InvalidRequest(
                    "Agent attachments require an AssetRef or HTTP(S) URL"
                )
            item["text"] = value.text or ""
            content.append(item)
        return core_input.parse_input_content(content)

    def _to_sdk(self, value: Any, media_cache: dict) -> Any:
        """Project Core values to the SDK DTOs without exposing Host paths.

        Args:
            value: Core event, result, or nested field.
            media_cache: Per-turn asset references shared by replay readers.

        Returns:
            Portable SDK value.
        """
        if isinstance(value, URLMedia):
            return value.url
        if isinstance(value, PathMedia | InlineMedia):
            key = (
                type(value),
                value.path if isinstance(value, PathMedia) else value.data,
            )
            if key not in media_cache:
                if isinstance(value, PathMedia):
                    path = Path(value.path)
                    try:
                        with path.open("rb") as file:
                            data = file.read(_MAX_ASSET_BYTES + 1)
                        asset = self._bridge._require_asset_store().put(
                            data,
                            filename=path.name,
                            media_type=value.mime_type,
                        )
                    except OSError:
                        asset = None
                else:
                    asset = self._bridge._require_asset_store().put(
                        base64.b64decode(value.data),
                        filename=None,
                        media_type=value.mime_type,
                    )
                media_cache[key] = asset
            return media_cache[key]
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, (list, tuple)):
            return tuple(self._to_sdk(item, media_cache) for item in value)
        if isinstance(value, (str, int, float, bool, dict, datetime)) or value is None:
            return value
        dto = getattr(sdk, type(value).__name__, None)
        if not is_dataclass(dto):
            raise InvalidRequest(f"unsupported Agent value: {type(value).__name__}")
        result = {
            field.name: self._to_sdk(getattr(value, field.name), media_cache)
            for field in fields(dto)
        }
        if isinstance(value, OutputReady):
            platform, kind, session = value.target_umo.split(":", 2)
            result["target_umo"] = UMO(
                platform,
                {
                    "FriendMessage": MessageType.PRIVATE,
                    "GroupMessage": MessageType.GROUP,
                }.get(kind, MessageType.OTHER),
                session,
            )
        return dto(**result)

    async def _events(
        self, run: AgentRun, media_cache: dict
    ) -> AsyncIterator[sdk.RuntimeEvent]:
        """Stream replayable runtime events to a Runner.

        Args:
            run: The authorized turn handle.
            media_cache: Shared references for media across events and results.

        Yields:
            Typed execution events in Core order.
        """
        async for event in run.events():
            yield self._to_sdk(event, media_cache)

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Dispatch one Agent RPC against handles owned by this Runner.

        Args:
            operation: Requested Agent action.
            payload: Decoded operation inputs.

        Returns:
            A turn identifier, typed result, event stream, or control receipt.

        Raises:
            InvalidRequest: Parameters are invalid.
            NotFound: The handle or operation is unknown.
            RateLimited: Too many retained turns or steering receipts.
        """
        try:
            if operation in {"run_turn", "run_turn_from_event", "follow_up"}:
                async with self._admission:
                    if len(self._runs) >= _MAX_RUNS:
                        expired = next(
                            (key for key, run in self._runs.items() if run.done), None
                        )
                        if expired is None:
                            raise RateLimited("too many active SDK Agent turns")
                        self._runs.pop(expired)
                        self._receipts.pop(expired, None)
                        self._media_cache.pop(expired, None)
                    content = self._inputs(payload.get("input_message"))
                    delivery = payload.get("send_to_user")
                    if delivery is not None and type(delivery) is not bool:
                        raise ValueError("send_to_user must be a boolean")
                    if operation != "follow_up":
                        umo = payload.get("umo")
                        if not isinstance(umo, UMO):
                            raise ValueError("run_turn requires a UMO")
                        target = to_umo_string(umo)
                        metadata = payload.get("metadata")
                        if metadata is not None:
                            if not isinstance(metadata, dict):
                                raise ValueError("Agent metadata must be a JSON object")
                            json.dumps(metadata, allow_nan=False)
                        source: AstrMessageEvent | None = (
                            self._bridge._agent_sources.get(
                                payload.get("source_event_id")
                            )
                        )
                        if operation == "run_turn_from_event" and source is None:
                            raise InvalidRequest("source event is no longer active")
                        if source is not None and source.unified_msg_origin != target:
                            raise ValueError("source event belongs to another UMO")
                        run = await self._bridge.context.agent.run_turn(
                            umo=target,
                            input_message=content,
                            send_to_user=True if delivery is None else delivery,
                            source_event=source,
                            session_id=payload.get("session_id"),
                            metadata=metadata,
                        )
                    else:
                        parent = self._runs.get(payload.get("run_id"))
                        if parent is None:
                            raise NotFound("unknown Agent turn")
                        run = await parent.follow_up(
                            input_message=content, send_to_user=delivery
                        )
                    self._runs[run.id] = run
                    self._media_cache[run.id] = {}
                    return run.id
            run = self._runs.get(payload.get("run_id"))
            if run is None:
                raise NotFound("unknown Agent turn")
            media_cache = self._media_cache[run.id]
            if operation == "events":
                return self._events(run, media_cache)
            if operation == "result":
                return self._to_sdk(await run.result(), media_cache)
            if operation == "session":
                return self._to_sdk(await run.get_session(), media_cache)
            if operation == "cancel":
                await run.cancel()
                return None
            if operation == "steer":
                receipts = self._receipts.setdefault(run.id, {})
                if len(receipts) >= _MAX_STEERING_RECEIPTS:
                    raise RateLimited("too many steering receipts for this turn")
                receipt = await run.steer(
                    input_message=self._inputs(payload.get("input_message"))
                )
                if receipt is None:
                    return None
                receipt_id = uuid4().hex
                receipts[receipt_id] = receipt
                return receipt_id
            if operation == "receipt":
                receipt = self._receipts.get(run.id, {}).get(payload.get("receipt_id"))
                if receipt is None:
                    raise NotFound("unknown steering receipt")
                return await receipt
        except (TypeError, ValueError) as exc:
            raise InvalidRequest(str(exc)) from exc
        raise NotFound(f"unknown Agent operation: {operation}")
