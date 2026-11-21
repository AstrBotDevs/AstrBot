from __future__ import annotations

import asyncio
import base64
import math
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ..assets import AssetRef
from ..message_components import (
    MediaSegment,
    Node,
    Nodes,
)
from ..messages import MessageChain

if TYPE_CHECKING:
    from ..context import PluginContext

_ASSETS_CAPABILITY = "assets.transfer"
# Chunks stay small so every protocol frame remains bounded and other RPC
# traffic on the same connection is not starved.
_CHUNK_BYTES = 256 * 1024


class AssetService:
    """Transfer media blobs between the Runner and the Host asset store."""

    def __init__(self, ctx: PluginContext) -> None:
        """Initialize the service.

        Args:
            ctx: Owning plugin context used for Host invocation.
        """
        self._ctx = ctx

    async def upload(
        self,
        source: Path | bytes,
        *,
        filename: str | None = None,
        media_type: str | None = None,
    ) -> AssetRef:
        """Upload a local blob into the Host asset store.

        Small payloads use one inline call; larger payloads are split into
        bounded chunks transparently.

        Args:
            source: Local file or in-memory bytes.
            filename: Optional display filename.
            media_type: Optional MIME type.

        Returns:
            Reference to the stored asset.
        """
        if isinstance(source, Path):
            data = await asyncio.to_thread(source.read_bytes)
            filename = filename or source.name
        else:
            data = bytes(source)

        if len(data) <= _CHUNK_BYTES:
            result = await self._ctx._invoke_capability(
                _ASSETS_CAPABILITY,
                "upload",
                {
                    "filename": filename,
                    "media_type": media_type,
                    "size": len(data),
                    "data": base64.b64encode(data).decode("ascii"),
                },
            )
            return result["asset"]

        begin = await self._ctx._invoke_capability(
            _ASSETS_CAPABILITY,
            "upload_begin",
            {"filename": filename, "media_type": media_type, "size": len(data)},
        )
        upload_id = str(begin["upload_id"])
        try:
            for seq in range(math.ceil(len(data) / _CHUNK_BYTES)):
                chunk = data[seq * _CHUNK_BYTES : (seq + 1) * _CHUNK_BYTES]
                await self._ctx._invoke_capability(
                    _ASSETS_CAPABILITY,
                    "upload_chunk",
                    {
                        "upload_id": upload_id,
                        "seq": seq,
                        "data": base64.b64encode(chunk).decode("ascii"),
                    },
                )
        except Exception:
            await self._ctx._invoke_capability(
                _ASSETS_CAPABILITY,
                "upload_abort",
                {"upload_id": upload_id},
            )
            raise
        commit = await self._ctx._invoke_capability(
            _ASSETS_CAPABILITY,
            "upload_commit",
            {"upload_id": upload_id},
        )
        return commit["asset"]

    async def download(self, asset: AssetRef) -> Path:
        """Download an asset into a Runner-local file.

        Args:
            asset: Asset reference to fetch.

        Returns:
            Path of the downloaded local file.
        """
        stat = await self._ctx._invoke_capability(
            _ASSETS_CAPABILITY,
            "stat",
            {"asset_id": asset.id},
        )
        size = int(stat.get("size", 0))
        filename = stat.get("filename") or asset.filename or "asset"
        offset = 0
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f"{asset.id}_",
            suffix=f"_{filename}",
            delete=False,
        ) as handle:
            target = Path(handle.name)
            while offset < size:
                length = min(_CHUNK_BYTES, size - offset)
                result = await self._ctx._invoke_capability(
                    _ASSETS_CAPABILITY,
                    "read",
                    {"asset_id": asset.id, "offset": offset, "length": length},
                )
                handle.write(base64.b64decode(result["data"]))
                offset += length
        return target


async def prepare_outbound_chain(
    chain: MessageChain,
    assets: AssetService,
) -> MessageChain:
    """Replace local media sources with uploaded asset references.

    Args:
        chain: Outbound chain possibly containing Path or bytes sources.
        assets: Asset service used for uploading.

    Returns:
        Chain in which every media source is an AssetRef or public URL.
    """
    segments = []
    for segment in chain:
        if isinstance(segment, MediaSegment) and isinstance(
            segment.source,
            Path | bytes,
        ):
            explicit = getattr(segment, "filename", None)
            if isinstance(segment.source, Path):
                upload_filename = explicit or segment.source.name
            else:
                upload_filename = explicit
            asset = await assets.upload(
                segment.source,
                filename=upload_filename,
                media_type=segment.media_type,
            )
            extra = {"filename": explicit} if explicit is not None else {}
            segments.append(
                type(segment)(
                    source=asset,
                    media_type=segment.media_type,
                    **extra,
                ),
            )
        elif isinstance(segment, Node):
            prepared = await prepare_outbound_chain(
                MessageChain(*segment.content),
                assets,
            )
            segments.append(
                Node(
                    sender_id=segment.sender_id,
                    content=prepared,
                    sender_name=segment.sender_name,
                ),
            )
        elif isinstance(segment, Nodes):
            prepared_nodes = []
            for node in segment.nodes:
                prepared = await prepare_outbound_chain(
                    MessageChain(*node.content),
                    assets,
                )
                prepared_nodes.append(
                    Node(
                        sender_id=node.sender_id,
                        content=prepared,
                        sender_name=node.sender_name,
                    ),
                )
            segments.append(Nodes(nodes=prepared_nodes))
        else:
            segments.append(segment)
    return MessageChain(*segments)
