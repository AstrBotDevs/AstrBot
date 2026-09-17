"""Durable, content-addressed storage for conversation image bytes."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True, slots=True)
class ImageMediaRef:
    """A versioned reference persisted in a conversation message.

    Args:
        media_id: SHA-256 digest of the exact stored bytes.
        mime_type: MIME type sent to a provider.
        width: Pixel width, if the bytes are a readable image.
        height: Pixel height, if the bytes are a readable image.
        byte_size: Exact stored byte count.
        detail: Provider image-detail metadata.
    """

    media_id: str
    mime_type: str
    width: int | None
    height: int | None
    byte_size: int
    detail: str | None = None
    version: int = 1
    image_id: str | None = None

    def __post_init__(self) -> None:
        if (
            self.version != 1
            or len(self.media_id) != 64
            or any(char not in "0123456789abcdef" for char in self.media_id)
            or self.byte_size < 0
            or not self.mime_type.startswith("image/")
            or (self.image_id is not None and not isinstance(self.image_id, str))
        ):
            raise ValueError("Invalid durable image reference")

    @property
    def uri(self) -> str:
        """Return the internal URI; this URI is never sent to a provider."""
        return f"astrbot-media:v{self.version}:{self.media_id}"

    def model_dump(self) -> dict[str, object]:
        """Return a stable JSON-compatible history representation."""
        return {"type": "image_media_ref", **asdict(self)}


class ImageMediaStore:
    """Store immutable image bytes outside the temporary directory."""

    def __init__(self, root: Path) -> None:
        """Create a store rooted under the configured data directory.

        Args:
            root: Dedicated durable media directory, not a client path.
        """
        self.root = root

    def put(
        self,
        data: bytes,
        mime_type: str | None = None,
        detail: str | None = None,
        image_id: str | None = None,
    ) -> ImageMediaRef:
        """Atomically persist bytes and return their deduplicated reference.

        Args:
            data: Exact prepared image bytes.
            mime_type: Optional MIME type; Pillow detection is preferred.
            detail: Provider image-detail metadata.

        Returns:
            A reference whose object and metadata have both been verified.

        Raises:
            OSError: The object or metadata cannot be committed atomically.
            ValueError: The stored bytes are not a readable image.
        """
        media_id = hashlib.sha256(data).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise OSError("invalid durable media root")
        object_path = self.root / f"{media_id}.bin"
        metadata_path = self.root / f"{media_id}.json"
        detected_mime = "application/octet-stream"
        width: int | None = None
        height: int | None = None
        try:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                detected_mime = Image.MIME.get(image.format, detected_mime)
        except MemoryError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ValueError("media bytes are not a readable image") from exc
        ref = ImageMediaRef(
            media_id,
            mime_type or detected_mime,
            width,
            height,
            len(data),
            detail,
            image_id=image_id,
        )
        canonical = {
            "media_id": ref.media_id,
            "mime_type": detected_mime,
            "width": ref.width,
            "height": ref.height,
            "byte_size": ref.byte_size,
            "version": ref.version,
        }
        if object_path.exists() or metadata_path.exists():
            # Verify shared bytes first. An interrupted metadata write can then
            # be completed through the same atomic path as a new object.
            if object_path.is_symlink() or not object_path.is_file():
                raise OSError("incomplete durable media object")
            if hashlib.sha256(object_path.read_bytes()).hexdigest() != media_id:
                raise OSError("media hash verification failed")
            if metadata_path.is_symlink():
                raise OSError("incomplete durable media object")
            if metadata_path.exists():
                if not metadata_path.is_file():
                    raise OSError("incomplete durable media object")
                try:
                    persisted = json.loads(metadata_path.read_text())
                except (OSError, json.JSONDecodeError) as exc:
                    raise OSError("durable media metadata verification failed") from exc
                if persisted != canonical:
                    raise OSError("durable media metadata verification failed")
                self.read(ref, {media_id})
                return ref
        temporary_paths: list[Path] = []
        try:
            with tempfile.NamedTemporaryFile(dir=self.root, delete=False) as output:
                object_tmp = Path(output.name)
                temporary_paths.append(object_tmp)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary_paths[0], object_path)
            except FileExistsError:
                pass
            if hashlib.sha256(object_path.read_bytes()).hexdigest() != media_id:
                raise OSError("media hash verification failed")
            with tempfile.NamedTemporaryFile(
                dir=self.root,
                prefix=f"{media_id}.",
                suffix=".json",
                mode="w",
                delete=False,
            ) as metadata_file:
                metadata_path_tmp = Path(metadata_file.name)
                temporary_paths.append(metadata_path_tmp)
                metadata_file.write(json.dumps(canonical, sort_keys=True) + "\n")
                metadata_file.flush()
                os.fsync(metadata_file.fileno())
            try:
                os.link(metadata_path_tmp, metadata_path)
            except FileExistsError:
                pass
            if json.loads(metadata_path.read_text()) != canonical:
                raise OSError("durable media metadata verification failed")
        finally:
            for path in temporary_paths:
                path.unlink(missing_ok=True)
        return ref

    def read(self, ref: ImageMediaRef, allowed_media_ids: set[str]) -> bytes:
        """Read a reference only when the caller already proved access.

        Args:
            ref: Persisted reference, not a client-supplied filesystem path.
            allowed_media_ids: IDs belonging to the authorized conversation.

        Returns:
            The exact bytes committed for the reference.

        Raises:
            PermissionError: The reference is outside the authorized history.
            FileNotFoundError: The durable object is missing.
            OSError: The object hash no longer matches its reference.
        """
        if ref.media_id not in allowed_media_ids:
            raise PermissionError("media reference is not authorized")
        if self.root.is_symlink() or not self.root.is_dir():
            raise OSError("invalid durable media root")
        path = self.root / f"{ref.media_id}.bin"
        if path.is_symlink():
            raise OSError("invalid durable media object")
        if not path.exists():
            raise FileNotFoundError("durable media object is unavailable")
        if not path.is_file():
            raise OSError("invalid durable media object")
        metadata_path = self.root / f"{ref.media_id}.json"
        if metadata_path.is_symlink() or not metadata_path.exists():
            raise OSError("incomplete durable media object")
        try:
            metadata = json.loads(metadata_path.read_text())
            metadata.pop("type", None)
            persisted_ref = ImageMediaRef(**metadata)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise OSError("durable media metadata verification failed") from exc
        if (
            persisted_ref.media_id,
            persisted_ref.width,
            persisted_ref.height,
            persisted_ref.byte_size,
            persisted_ref.version,
        ) != (
            ref.media_id,
            ref.width,
            ref.height,
            ref.byte_size,
            ref.version,
        ):
            raise OSError("durable media metadata verification failed")
        data = path.read_bytes()
        if (
            len(data) != ref.byte_size
            or hashlib.sha256(data).hexdigest() != ref.media_id
        ):
            raise OSError("media hash verification failed")
        return data


def persist_inline_image_refs(
    history: list[dict],
    store: ImageMediaStore,
) -> list[dict]:
    """Replace newly created data URIs with durable references before saving.

    Args:
        history: Serialized messages about to be persisted.
        store: Durable store for this application data root.

    Returns:
        A new history list. Non-inline URLs remain unchanged for compatibility.
    """
    import copy

    result = copy.deepcopy(history)
    for message in result:
        parts = message.get("content") if isinstance(message, dict) else None
        if not isinstance(parts, list):
            continue
        for index, part in enumerate(parts):
            if not isinstance(part, dict) or part.get("type") != "image_url":
                continue
            if part.get("_no_save"):
                continue
            image_url = part.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else None
            if not isinstance(url, str) or not url.startswith("data:image/"):
                continue
            header, payload = url.split(",", 1)
            mime_type = header[5:].split(";", 1)[0]
            data = base64.b64decode(payload, validate=True)
            ref = store.put(
                data,
                mime_type,
                image_url.get("detail") if isinstance(image_url, dict) else None,
                image_url.get("id") if isinstance(image_url, dict) else None,
            )
            parts[index] = ref.model_dump()
    return result


async def materialize_image_media_refs(
    contexts: list,
    store: ImageMediaStore,
    *,
    strict: bool = False,
) -> list:
    """Resolve only the selected references into a request-local view.

    Args:
        contexts: Messages selected by the context manager.
        store: Store for the application's configured data root.
        strict: Fail on missing media when preparing a rollback export.

    Returns:
        Request-local messages with images, or the original list if no refs exist.

    Raises:
        ValueError: A reference has invalid metadata.
        MemoryError: Image materialization exhausts process resources.
    """
    import asyncio

    from astrbot import logger
    from astrbot.core.agent.message import ContentPart, Message

    output = []
    for message in contexts:
        serialized = message.model_dump() if isinstance(message, Message) else message
        parts = serialized.get("content")
        if not isinstance(parts, list) or not any(
            isinstance(part, dict) and part.get("type") == "image_media_ref"
            for part in parts
        ):
            output.append(message)
            continue
        resolved = []
        for part in parts:
            if not isinstance(part, dict) or part.get("type") != "image_media_ref":
                resolved.append(part)
                continue
            try:
                ref = ImageMediaRef(
                    part["media_id"],
                    part["mime_type"],
                    part.get("width"),
                    part.get("height"),
                    part["byte_size"],
                    part.get("detail"),
                    part.get("version", 1),
                    part.get("image_id"),
                )
                payload = await asyncio.to_thread(store.read, ref, {ref.media_id})
                image_url = {
                    "url": f"data:{ref.mime_type};base64,{base64.b64encode(payload).decode('ascii')}",
                }
                del payload
                if ref.detail is not None:
                    image_url["detail"] = ref.detail
                if ref.image_id is not None:
                    image_url["id"] = ref.image_id
                resolved.append({"type": "image_url", "image_url": image_url})
            except (KeyError, TypeError, ValueError, OSError):
                if strict:
                    raise
                logger.warning("A selected conversation image is unavailable")
                resolved.append({"type": "text", "text": "[Image unavailable]"})
        if isinstance(message, Message):
            provider_message = message.model_copy()
            provider_message.content = [
                ContentPart.model_validate(part) for part in resolved
            ]
        else:
            provider_message = {**message, "content": resolved}
        output.append(provider_message)
    return output
