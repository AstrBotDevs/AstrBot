"""Media file utilities.

Provides shared media reference materialization, format conversion, duration
probing, and image compression helpers.
"""

import asyncio
import base64
import binascii
import errno
import io
import math
import mimetypes
import os
import shutil
import struct
import subprocess
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias
from urllib.parse import unquote, urlparse, urlsplit
from urllib.request import url2pathname

from aiohttp import ClientError
from PIL import Image as PILImage
from PIL import ImageOps

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.datetime_utils import generate_timestamp_id
from astrbot.core.utils.io import DownloadFileHTTPError, download_file
from astrbot.core.utils.tencent_record_helper import (
    tencent_silk_to_wav,
    wav_to_tencent_silk,
)

IMAGE_COMPRESS_DEFAULT_MAX_SIZE = 1280
IMAGE_COMPRESS_DEFAULT_QUALITY = 95
IMAGE_COMPRESS_DEFAULT_OPTIMIZE = True
IMAGE_COMPRESS_DEFAULT_MIN_FILE_SIZE_MB = 1.0
# Model image inputs larger than this are skipped before decoding.
MODEL_IMAGE_MAX_INPUT_BYTES = 64 * 1024 * 1024


class ImagePayloadTooLargeError(ValueError):
    """Raised when an image exceeds a safe input or output byte budget."""


@dataclass(slots=True)
class ImagePreparationOptions:
    """Options for the shared provider-facing image preparation boundary.

    Args:
        max_size: Longest edge of the prepared image in pixels.
    """

    max_size: int = IMAGE_COMPRESS_DEFAULT_MAX_SIZE


def get_image_preparation_options(
    provider_settings: dict | None,
) -> ImagePreparationOptions:
    """Build preparation options from the current provider settings.

    Args:
        provider_settings: Provider-level settings. Only the mainline image
            dimension option is read; removed legacy byte-budget settings are
            intentionally ignored.

    Returns:
        Validated options for the shared image preparation path.
    """
    raw_options = (
        provider_settings.get("image_compress_options", {})
        if isinstance(provider_settings, dict)
        else {}
    )
    max_size = raw_options.get("max_size") if isinstance(raw_options, dict) else None
    return ImagePreparationOptions(max_size=normalize_model_image_max_size(max_size))


MEDIA_MIME_EXTENSIONS = {
    "audio/wav": ".wav",
    "audio/wave": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/flac": ".flac",
    "audio/aac": ".aac",
    "audio/amr": ".amr",
    "audio/silk": ".silk",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/avif": ".avif",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}

# Magic-byte prefixes for O(1) image MIME sniffing; unknown headers fall
# back to the caller-provided default instead of decoding the file.
_IMAGE_MAGIC_MIME_TYPES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
)

ANIMATED_MONTAGE_GRID = 3
"""Animated images become a grid x grid frame montage (contact sheet)."""

ANIMATED_MONTAGE_FRAME_COUNT = ANIMATED_MONTAGE_GRID * ANIMATED_MONTAGE_GRID

AUDIO_FORMAT_MIME_TYPES = {
    "aac": "audio/aac",
    "amr": "audio/amr",
    "flac": "audio/flac",
    "mp3": "audio/mp3",
    "ogg": "audio/ogg",
    "opus": "audio/opus",
    "silk": "audio/silk",
    "tencent_silk": "audio/silk",
    "wav": "audio/wav",
}

DEFAULT_MEDIA_SUFFIXES = {
    "audio": ".wav",
    "image": ".bin",
    "video": ".mp4",
    "file": ".bin",
}


MediaRefStr: TypeAlias = str
"""
A media reference string accepted by MediaResolver: local path, file URI, HTTP(S),
base64://, data URI, or legacy bare base64.

Examples:
    Local path: ``/tmp/image.png``
    File URI: ``file:///tmp/image.png``
    HTTP(S) URL: ``https://example.com/image.png``
    base64:// payload: ``base64://iVBORw0KGgo...``
    Data URI: ``data:image/png;base64,iVBORw0KGgo...``
    Legacy bare base64: ``iVBORw0KGgo...``
"""


@dataclass(frozen=True, slots=True)
class ImagePreparationInput:
    """Describe an image entering the shared preparation boundary.

    Args:
        value: Image path, URL, data URI, base64 reference, or raw bytes.
        source_kind: Logical producer name used for diagnostics.
        cleanup_paths: Temporary paths owned by the caller.
    """

    value: MediaRefStr | bytes
    source_kind: str = "unknown"
    cleanup_paths: tuple[Path, ...] = ()


@dataclass(slots=True)
class ResolvedMediaData:
    """Base64 media bytes plus the metadata needed by provider payloads.

    Attributes:
        base64_data: Raw base64 payload without a ``data:`` URI prefix.
        mime_type: MIME type to send with provider payloads.
        format: Optional normalized media format, such as ``wav`` for audio.
    """

    base64_data: str
    mime_type: str
    format: str | None = None
    byte_size: int | None = None

    def to_bytes(self) -> bytes:
        """Decode the base64 payload, accepting missing padding."""
        return _decode_base64_payload(
            self.base64_data,
            error_message="invalid resolved media base64 data",
        )

    def to_data_url(self) -> str:
        """Return a ``data:<mime>;base64,...`` URL for multimodal providers."""
        return f"data:{self.mime_type};base64,{self.base64_data}"


@dataclass(slots=True)
class _LocalMediaFile:
    path: Path
    mime_type: str | None = None
    cleanup_paths: list[Path] = field(default_factory=list)


@dataclass(slots=True)
class ResolvedMediaFile:
    """A media reference resolved to a local path.

    ``cleanup_paths`` contains temporary files owned by the resolver. Callers that
    use ``MediaResolver.as_path()`` get automatic cleanup; callers that need to
    keep a path after the resolver returns should use ``MediaResolver.to_path()``.
    """

    source_ref: MediaRefStr
    media_type: str
    path: Path
    mime_type: str | None = None
    format: str | None = None
    cleanup_paths: list[Path] = field(default_factory=list)

    def read_bytes(self) -> bytes:
        """Read the resolved local file."""
        return self.path.read_bytes()

    def to_base64(self) -> str:
        """Read the resolved local file and return raw base64 data."""
        return base64.b64encode(self.read_bytes()).decode("utf-8")

    def to_data_url(self) -> str:
        """Read the resolved local file and return a data URL."""
        mime_type = self.mime_type or "application/octet-stream"
        return f"data:{mime_type};base64,{self.to_base64()}"

    def open(self, mode: str = "rb"):
        """Open the resolved local file."""
        return self.path.open(mode)

    def detach(self) -> None:
        """Keep temporary files alive after resolver cleanup would normally run."""

        self.cleanup_paths.clear()

    def cleanup(self) -> None:
        _cleanup_paths(self.cleanup_paths)


def is_file_uri(value: object) -> bool:
    """Return whether a value is a ``file:`` URI.

    Args:
        value: Candidate media reference or local path.

    Returns:
        ``True`` only for string values whose parsed URI scheme is ``file``.
    """

    if not isinstance(value, str):
        return False
    try:
        return urlsplit(value).scheme.lower() == "file"
    except ValueError:
        return False


def file_uri_to_path(file_uri: MediaRefStr) -> str:
    """Normalize file URIs to local filesystem paths.

    Args:
        file_uri: A ``file:`` URI or a plain filesystem path.

    Returns:
        The local filesystem path decoded with standard-library URL path rules.
        Non-``file:`` inputs are returned unchanged for convenience.
    """

    if not is_file_uri(file_uri):
        return file_uri

    parsed = urlparse(file_uri)
    netloc = parsed.netloc or ""
    path = parsed.path or ""
    if netloc and netloc.lower() != "localhost":
        if len(netloc) == 2 and netloc[1] == ":" and netloc[0].isalpha():
            return str(Path(url2pathname(f"{netloc}{path}")))
        return str(Path(url2pathname(f"//{netloc}{path}")))

    path = url2pathname(path)
    # url2pathname keeps "/" on POSIX but converts it to "\" on Windows, so
    # accept both prefixes before the drive colon.
    if (
        len(path) >= 4
        and path[0] in ("/", "\\")
        and path[2] == ":"
        and path[1].isalpha()
    ):
        path = path[1:]
    elif os.name != "nt" and path.startswith("//"):
        # Older AstrBot builds generated file:////path for POSIX absolute paths.
        path = "/" + path.lstrip("/")
    return str(Path(path))


def _extension_from_mime_type(mime_type: str | None) -> str | None:
    """Return a filesystem suffix for a MIME type, if one is known."""
    if not mime_type:
        return None
    normalized = mime_type.split(";", 1)[0].strip().lower()
    if not normalized:
        return None
    return MEDIA_MIME_EXTENSIONS.get(normalized) or mimetypes.guess_extension(
        normalized
    )


def _temp_media_path(media_type: str, suffix: str) -> Path:
    """Create a unique path under AstrBot's temp directory for materialized media."""
    temp_dir = Path(get_astrbot_temp_path())
    temp_dir.mkdir(parents=True, exist_ok=True)
    safe_media_type = "".join(
        char if char.isalnum() or char in {"_", "-"} else "_" for char in media_type
    )
    return temp_dir / f"media_{safe_media_type}_{generate_timestamp_id()}{suffix}"


def _parse_base64_data_uri(data_uri: str) -> tuple[str | None, bytes]:
    """Parse a base64 data URI and return ``(mime_type, decoded_bytes)``."""
    header, separator, payload = data_uri.partition(",")
    if not separator or not header.lower().startswith("data:"):
        raise ValueError("invalid data URI")

    header_body = header[5:]
    header_parts = header_body.split(";") if header_body else []
    mime_type = header_parts[0].strip() if header_parts and header_parts[0] else None
    if not any(part.lower() == "base64" for part in header_parts[1:]):
        raise ValueError("data URI is not base64 encoded")

    return mime_type, _decode_base64_payload(
        payload,
        error_message="invalid base64 data URI payload",
    )


def _decode_base64_payload(
    payload: str,
    *,
    error_message: str,
    validate: bool = False,
) -> bytes:
    """Decode a base64 payload while tolerating omitted padding.

    Args:
        payload: Base64 payload without a data URI header.
        error_message: Message to use when decoding fails.
        validate: Whether to ask ``base64.b64decode`` to reject non-base64
            characters.

    Returns:
        Decoded bytes.

    Raises:
        ValueError: Raised when the payload cannot be decoded.
    """
    payload = "".join(payload.split())
    missing_padding = len(payload) % 4
    if missing_padding:
        payload += "=" * (4 - missing_padding)

    try:
        return base64.b64decode(payload, validate=validate)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(error_message) from exc


def _estimate_base64_decoded_size(
    payload: str,
    *,
    start: int = 0,
    require_valid_chars: bool = False,
) -> int | None:
    """Estimate decoded bytes without creating a compact payload copy.

    Args:
        payload: Base64 text, possibly containing whitespace.
        start: Index at which the payload begins.
        require_valid_chars: Whether to reject non-base64 characters.

    Returns:
        Estimated decoded byte count, or ``None`` when the payload is not a
        complete standard Base64 string.
    """
    encoded_size = 0
    padding_size = 0
    for index, char in enumerate(payload):
        if index < start or char.isspace():
            continue
        if require_valid_chars and char not in (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
        ):
            return None
        encoded_size += 1
        if char == "=":
            padding_size += 1
    if encoded_size % 4 == 1:
        return None
    return max(0, encoded_size * 3 // 4 - padding_size)


def validate_image_input_size(image_source: bytes | str | Path | int) -> int | None:
    """Reject known oversized image inputs before decoding them.

    Args:
        image_source: Raw bytes, a local path, a media reference, or a known
            byte count. Remote URLs return ``None`` until downloaded.

    Returns:
        Known encoded byte count, or ``None`` when it cannot be determined
        without reading the source.

    Raises:
        ImagePayloadTooLargeError: The known source exceeds the 64 MiB input cap.
        TypeError: The source type is unsupported.
        ValueError: The source size is negative.
    """
    source_size: int | None = None
    if isinstance(image_source, bool):
        raise TypeError("Image source size must not be a boolean")
    if isinstance(image_source, int):
        source_size = image_source
    elif isinstance(image_source, bytes):
        source_size = len(image_source)
    elif isinstance(image_source, Path):
        try:
            source_size = image_source.stat().st_size
        except FileNotFoundError:
            return None
    elif isinstance(image_source, str):
        if image_source.startswith(("http://", "https://")):
            return None
        if image_source.startswith("data:"):
            comma_index = image_source.find(",")
            if comma_index < 0:
                return None
            header_parts = image_source[5:comma_index].split(";")
            if any(part.lower() == "base64" for part in header_parts[1:]):
                source_size = _estimate_base64_decoded_size(
                    image_source,
                    start=comma_index + 1,
                )
        elif image_source.startswith("base64://"):
            source_size = _estimate_base64_decoded_size(
                image_source,
                start=len("base64://"),
            )
        else:
            is_uri = is_file_uri(image_source)
            path = (
                Path(file_uri_to_path(image_source)) if is_uri else Path(image_source)
            )
            try:
                source_size = path.stat().st_size
            except (FileNotFoundError, OSError, ValueError):
                source_size = None
            if source_size is None and not is_uri:
                source_size = _estimate_base64_decoded_size(
                    image_source,
                    require_valid_chars=True,
                )
    else:
        raise TypeError(f"Unsupported image source type: {type(image_source).__name__}")

    if source_size is None:
        return None
    if source_size < 0:
        raise ValueError("Image source size must not be negative")
    if source_size > MODEL_IMAGE_MAX_INPUT_BYTES:
        if isinstance(image_source, Path):
            raise ImageInputTooLargeError(str(image_source))
        raise ImageInputTooLargeError(
            "Image input exceeds the "
            f"{MODEL_IMAGE_MAX_INPUT_BYTES}-byte limit ({source_size} bytes)"
        )
    return source_size


def _encode_file_to_base64(path: Path) -> str:
    """Encode a local file in chunks without retaining raw and encoded copies."""
    encoded = io.StringIO()
    remainder = b""
    with path.open("rb") as source:
        while chunk := source.read(1023 * 1024):
            block = remainder + chunk if remainder else chunk
            complete_size = len(block) - len(block) % 3
            if complete_size:
                encoded.write(base64.b64encode(block[:complete_size]).decode("ascii"))
            remainder = block[complete_size:]
    if remainder:
        encoded.write(base64.b64encode(remainder).decode("ascii"))
    return encoded.getvalue()


def describe_media_ref(media_ref: object | None) -> str:
    """Return a log-safe description of a media reference.

    Args:
        media_ref: Original media reference from a platform, plugin, or provider
            request. It may contain a signed URL or a large base64 payload.

    Returns:
        A short description that avoids logging query strings, tokens, and base64
        payload contents.
    """

    if not media_ref:
        return "<empty media ref>"
    if not isinstance(media_ref, str):
        return f"media ref type={type(media_ref).__name__}"

    ref_len = len(media_ref)
    if media_ref.startswith("data:"):
        header, _, payload = media_ref.partition(",")
        mime_type = header[5:].split(";", 1)[0] or "unknown"
        return f"data URI mime={mime_type!r} payload_len={len(payload)}"

    if media_ref.startswith("base64://"):
        return f"base64 media payload_len={len(media_ref.removeprefix('base64://'))}"

    parsed = urlparse(media_ref)
    if parsed.scheme in {"http", "https"}:
        filename = Path(unquote(parsed.path or "")).name
        suffix = f" file={filename!r}" if filename else ""
        return f"{parsed.scheme} URL host={parsed.netloc!r}{suffix} len={ref_len}"

    if is_file_uri(media_ref):
        filename = Path(file_uri_to_path(media_ref)).name
        return f"file URI name={filename!r} len={ref_len}"

    media_path_exists = False
    try:
        media_path_exists = Path(media_ref).exists()
    except OSError:
        pass
    if not media_path_exists:
        compact = "".join(media_ref.split())
        if compact:
            try:
                _decode_base64_payload(
                    compact,
                    error_message="invalid bare base64 media payload",
                    validate=True,
                )
            except ValueError:
                pass
            else:
                return f"bare base64 media payload_len={len(compact)}"

    return f"local media path name={Path(media_ref).name!r} len={ref_len}"


def detect_image_mime_type(
    image_source: bytes | str | Path,
    *,
    default_mime_type: str | None = "image/jpeg",
) -> str | None:
    """Detect an image MIME type by sniffing the file header.

    Only the first bytes of the input are read, so detection cost and memory
    stay constant regardless of file size.

    Args:
        image_source: Encoded image bytes or a local image path to inspect.
        default_mime_type: MIME type to return when detection fails.

    Returns:
        The detected MIME type, or ``default_mime_type`` when the header does
        not match a known image format.
    """

    try:
        if isinstance(image_source, bytes):
            header = image_source[:32]
        else:
            with open(image_source, "rb") as image_file:
                header = image_file.read(32)
    except OSError:
        return default_mime_type

    if len(header) >= 12:
        if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
            return "image/webp"
        if header[4:8] == b"ftyp" and (b"avif" in header[8:] or b"avis" in header[8:]):
            return "image/avif"
    for magic, mime_type in _IMAGE_MAGIC_MIME_TYPES:
        if header.startswith(magic):
            return mime_type
    return default_mime_type


async def detect_image_mime_type_async(
    image_source: bytes | str | Path,
    *,
    default_mime_type: str | None = "image/jpeg",
) -> str | None:
    """Detect an image MIME type without blocking the event loop.

    Args:
        image_source: Encoded image bytes or a local image path to inspect.
        default_mime_type: MIME type to return when detection fails.

    Returns:
        The detected MIME type, or ``default_mime_type`` when detection fails or
        the format is unknown.
    """

    return await asyncio.to_thread(
        detect_image_mime_type,
        image_source,
        default_mime_type=default_mime_type,
    )


def _guess_mime_type(path: Path, fallback: str | None = None) -> str | None:
    """Guess a MIME type from a filename, with an optional fallback."""
    return mimetypes.guess_type(path.name)[0] or fallback


def _cleanup_paths(cleanup_paths: list[Path] | None) -> None:
    """Best-effort cleanup for temporary files created by the resolver."""
    for cleanup_path in cleanup_paths or []:
        try:
            cleanup_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Failed to cleanup %s: %s", cleanup_path, exc)


async def _materialize_media_ref(
    media_ref: MediaRefStr,
    *,
    media_type: str = "file",
    default_suffix: str | None = None,
) -> _LocalMediaFile:
    """Resolve a plugin-facing media reference to a local file.

    Supported references: local paths, file:// URIs, http(s) URLs, base64://,
    data:*;base64,... URIs, and legacy bare base64 payloads.

    Args:
        media_ref: Original media reference from a platform, plugin, or history.
        media_type: Logical media family used for temp filenames and defaults.
        default_suffix: Suffix to use when the reference does not carry one.
    """

    cleanup_paths: list[Path] = []
    suffix = default_suffix or DEFAULT_MEDIA_SUFFIXES.get(media_type, ".bin")

    if media_ref.startswith(("http://", "https://")):
        if media_type == "image":
            target_path = _temp_media_path("image", ".bin")
        else:
            parsed = urlparse(media_ref)
            target_suffix = Path(parsed.path).suffix or suffix
            target_path = _temp_media_path(media_type, target_suffix)
        cleanup_paths.append(target_path)
        try:
            await download_file(media_ref, str(target_path))
            if media_type == "image":
                validate_image_input_size(target_path)
        except ImageInputTooLargeError as exc:
            exc.path = str(target_path)
            raise
        except Exception:
            _cleanup_paths(cleanup_paths)
            raise
        mime_type = _guess_mime_type(target_path)
        if media_type == "image":
            detected_mime_type = await detect_image_mime_type_async(
                target_path,
                default_mime_type=None,
            )
            if detected_mime_type:
                mime_type = detected_mime_type
                detected_suffix = _extension_from_mime_type(detected_mime_type)
                if detected_suffix and target_path.suffix.lower() != detected_suffix:
                    detected_path = _temp_media_path("image", detected_suffix)
                    await asyncio.to_thread(target_path.rename, detected_path)
                    cleanup_paths[-1] = detected_path
                    target_path = detected_path
        return _LocalMediaFile(
            path=target_path,
            mime_type=mime_type,
            cleanup_paths=cleanup_paths,
        )

    if is_file_uri(media_ref):
        path = Path(file_uri_to_path(media_ref))
        return _LocalMediaFile(path=path, mime_type=_guess_mime_type(path))

    if media_ref.startswith("data:"):
        if media_type == "image":
            validate_image_input_size(media_ref)
        mime_type, media_bytes = _parse_base64_data_uri(media_ref)
        target_suffix = _extension_from_mime_type(mime_type) or suffix
        if media_type == "image" and target_suffix == suffix:
            detected_mime_type = await detect_image_mime_type_async(
                media_bytes,
                default_mime_type=None,
            )
            if detected_mime_type:
                mime_type = detected_mime_type
                target_suffix = _extension_from_mime_type(detected_mime_type) or suffix
        target_path = _temp_media_path(media_type, target_suffix)
        cleanup_paths.append(target_path)
        try:
            await asyncio.to_thread(target_path.write_bytes, media_bytes)
        except Exception:
            _cleanup_paths(cleanup_paths)
            raise
        return _LocalMediaFile(
            path=target_path,
            mime_type=mime_type,
            cleanup_paths=cleanup_paths,
        )

    if media_ref.startswith("base64://"):
        if media_type == "image":
            validate_image_input_size(media_ref)
        media_bytes = _decode_base64_payload(
            media_ref.removeprefix("base64://"),
            error_message="invalid base64 media payload",
        )
        mime_type = None
        target_suffix = suffix
        if media_type == "image":
            mime_type = await detect_image_mime_type_async(
                media_bytes,
                default_mime_type=None,
            )
            target_suffix = _extension_from_mime_type(mime_type) or suffix
        target_path = _temp_media_path(media_type, target_suffix)
        cleanup_paths.append(target_path)
        try:
            await asyncio.to_thread(target_path.write_bytes, media_bytes)
        except Exception:
            _cleanup_paths(cleanup_paths)
            raise
        return _LocalMediaFile(
            path=target_path,
            mime_type=mime_type,
            cleanup_paths=cleanup_paths,
        )

    path = Path(media_ref)
    path_exists = False
    try:
        path_exists = path.exists()
    except OSError:
        pass
    if path_exists:
        return _LocalMediaFile(path=path, mime_type=_guess_mime_type(path))

    if media_type == "image":
        validate_image_input_size(media_ref)
    compact_media_ref = "".join(media_ref.split())
    if compact_media_ref:
        try:
            media_bytes = _decode_base64_payload(
                compact_media_ref,
                error_message="invalid bare base64 media payload",
                validate=True,
            )
        except ValueError:
            pass
        else:
            mime_type = None
            target_suffix = suffix
            if media_type == "image":
                mime_type = await detect_image_mime_type_async(
                    media_bytes,
                    default_mime_type=None,
                )
                target_suffix = _extension_from_mime_type(mime_type) or suffix
            target_path = _temp_media_path(media_type, target_suffix)
            cleanup_paths.append(target_path)
            try:
                await asyncio.to_thread(target_path.write_bytes, media_bytes)
            except Exception:
                _cleanup_paths(cleanup_paths)
                raise
            return _LocalMediaFile(
                path=target_path,
                mime_type=mime_type,
                cleanup_paths=cleanup_paths,
            )

    return _LocalMediaFile(path=path, mime_type=_guess_mime_type(path))


class MediaResolver:
    """Resolve, convert, and export media references.

    The resolver accepts local paths, file:// URIs, http(s) URLs, base64:// payloads,
    data:*;base64,... URIs, and legacy bare base64 payloads. Temporary paths are
    cleaned when using as_path(), while to_path() intentionally leaves returned
    paths alive for callers that need to hand them to platform SDKs.

    Args:
        media_ref: Source media reference. It may be a local path, ``file://`` URI,
            HTTP(S) URL, ``base64://`` payload, base64 data URI, or legacy bare
            base64 payload.
        media_type: Logical media family. ``audio`` enables format conversion and
            defaults to WAV output; ``image`` enables image MIME detection.
        default_suffix: Fallback suffix for temporary files when the source does
            not expose one.
    """

    def __init__(
        self,
        media_ref: MediaRefStr,
        *,
        media_type: str = "file",
        default_suffix: str | None = None,
    ) -> None:
        self.media_ref = media_ref
        self.media_type = media_type
        self.default_suffix = default_suffix

    async def _resolve_path(
        self,
        *,
        target_format: str | None = None,
        preserve_mp3: bool = False,
    ) -> ResolvedMediaFile:
        """Materialize the source and apply media-type-specific conversion.

        For audio, ``target_format`` controls the output format, including the
        QQ / Wechat / Wecom ``tencent_silk`` upload format. When it is not set, audio
        resolves to WAV unless ``preserve_mp3`` is true and the source already
        appears to be MP3.
        """
        local_file = await _materialize_media_ref(
            self.media_ref,
            media_type=self.media_type,
            default_suffix=self.default_suffix,
        )
        cleanup_paths = list(local_file.cleanup_paths)
        resolved_path = local_file.path
        mime_type = local_file.mime_type or _guess_mime_type(resolved_path)
        resolved_format = resolved_path.suffix.lower().lstrip(".") or None

        try:
            if self.media_type == "audio":
                audio_format = target_format
                if not audio_format:
                    audio_format = (
                        "mp3" if preserve_mp3 and resolved_format == "mp3" else "wav"
                    )

                if audio_format == "tencent_silk":
                    intermediate_cleanup_paths = list(cleanup_paths)
                    silk_path = _temp_media_path("audio", ".silk")
                    try:
                        wav_path = Path(await ensure_wav(str(resolved_path)))
                        if wav_path != resolved_path:
                            intermediate_cleanup_paths.append(wav_path)
                        duration = await wav_to_tencent_silk(
                            str(wav_path), str(silk_path)
                        )
                        if duration <= 0:
                            raise ValueError(
                                "Tencent Silk conversion returned empty duration"
                            )
                    except Exception:
                        _cleanup_paths([*intermediate_cleanup_paths, silk_path])
                        raise

                    _cleanup_paths(intermediate_cleanup_paths)
                    cleanup_paths = [silk_path]
                    resolved_path = silk_path
                    resolved_format = audio_format
                    mime_type = AUDIO_FORMAT_MIME_TYPES[resolved_format]
                else:
                    if audio_format == "wav":
                        converted_audio_path = Path(
                            await ensure_wav(str(resolved_path))
                        )
                    elif resolved_format == audio_format:
                        converted_audio_path = resolved_path
                    else:
                        converted_audio_path = Path(
                            await convert_audio_format(
                                str(resolved_path),
                                output_format=audio_format,
                            )
                        )

                    if converted_audio_path != resolved_path:
                        cleanup_paths.append(converted_audio_path)
                    resolved_path = converted_audio_path
                    resolved_format = audio_format
                    mime_type = AUDIO_FORMAT_MIME_TYPES.get(
                        resolved_format, "audio/wav"
                    )
        except Exception:
            _cleanup_paths(cleanup_paths)
            raise

        return ResolvedMediaFile(
            source_ref=self.media_ref,
            media_type=self.media_type,
            path=resolved_path,
            mime_type=mime_type,
            format=resolved_format,
            cleanup_paths=cleanup_paths,
        )

    @asynccontextmanager
    async def as_path(
        self,
        *,
        target_format: str | None = None,
        preserve_mp3: bool = False,
    ) -> AsyncIterator[ResolvedMediaFile]:
        """Yield a resolved local file and clean resolver-owned temp files on exit.

        Use this when the consumer only needs the file during the context manager.
        For audio, pass ``target_format`` to force a format such as ``wav`` or
        ``tencent_silk``.
        """
        resolved = await self._resolve_path(
            target_format=target_format,
            preserve_mp3=preserve_mp3,
        )
        try:
            yield resolved
        finally:
            resolved.cleanup()

    async def to_path(
        self,
        *,
        target_format: str | None = None,
        preserve_mp3: bool = False,
    ) -> str:
        """Return a resolved local path and keep temporary files alive.

        This is for message components and platform SDK calls that need a path
        after the resolver method returns. Callers or event cleanup should remove
        the returned temp file later.
        """
        resolved = await self._resolve_path(
            target_format=target_format,
            preserve_mp3=preserve_mp3,
        )
        resolved.detach()
        return str(resolved.path.resolve())

    async def to_bytes(
        self,
        *,
        target_format: str | None = None,
        preserve_mp3: bool = False,
    ) -> bytes:
        """Resolve media, read bytes, and clean resolver-owned temp files."""
        async with self.as_path(
            target_format=target_format,
            preserve_mp3=preserve_mp3,
        ) as resolved:
            return resolved.read_bytes()

    async def to_base64(
        self,
        *,
        target_format: str | None = None,
        preserve_mp3: bool = False,
    ) -> str:
        """Resolve media to raw base64 data without a data URI prefix."""
        return base64.b64encode(
            await self.to_bytes(
                target_format=target_format,
                preserve_mp3=preserve_mp3,
            )
        ).decode("utf-8")

    async def to_base64_data(
        self,
        *,
        strict: bool = False,
        target_format: str | None = None,
        preserve_mp3: bool = False,
        default_mime_type: str | None = "image/jpeg",
    ) -> ResolvedMediaData | None:
        """Resolve media to base64 data plus MIME metadata.

        Args:
            strict: Raise on invalid or unreadable media instead of returning
                ``None`` where the resolver can safely ignore the reference.
            target_format: Optional output format for audio conversion.
            preserve_mp3: Keep existing MP3 audio as MP3 when no target format is
                provided; otherwise audio defaults to WAV.
            default_mime_type: Fallback MIME type for legacy image base64 payloads
                whose bytes cannot be identified.
        """
        if self.media_type == "image":
            async with self.as_path(target_format=target_format) as resolved:
                try:
                    media_bytes = await asyncio.to_thread(resolved.read_bytes)
                except OSError as exc:
                    if strict or not is_recoverable_image_error(exc):
                        raise
                    return None

                mime_type = await detect_image_mime_type_async(
                    media_bytes,
                    default_mime_type=None,
                )
                if (
                    not mime_type
                    and resolved.mime_type
                    and resolved.mime_type.startswith("image/")
                ):
                    mime_type = resolved.mime_type
                is_legacy_base64_ref = self.media_ref.startswith("base64://")
                is_remote_or_data_ref = self.media_ref.startswith(
                    ("http://", "https://", "data:")
                ) or is_file_uri(self.media_ref)
                if not is_legacy_base64_ref and not is_remote_or_data_ref:
                    try:
                        _decode_base64_payload(
                            "".join(self.media_ref.split()),
                            error_message="invalid bare base64 media payload",
                            validate=True,
                        )
                    except ValueError:
                        is_legacy_base64_ref = False
                    else:
                        is_legacy_base64_ref = True
                if not mime_type and is_legacy_base64_ref:
                    mime_type = default_mime_type
                if not mime_type:
                    if strict:
                        raise ValueError(
                            f"Invalid image file: {describe_media_ref(self.media_ref)}"
                        )
                    return None

                return ResolvedMediaData(
                    base64_data=base64.b64encode(media_bytes).decode("utf-8"),
                    mime_type=mime_type,
                    byte_size=len(media_bytes),
                )

        async with self.as_path(
            target_format=target_format,
            preserve_mp3=preserve_mp3,
        ) as resolved:
            try:
                media_bytes = resolved.read_bytes()
            except OSError:
                if strict:
                    raise
                return None

            mime_type = resolved.mime_type or "application/octet-stream"
            return ResolvedMediaData(
                base64_data=base64.b64encode(media_bytes).decode("utf-8"),
                mime_type=mime_type,
                format=resolved.format,
            )

    async def to_data_url(
        self,
        *,
        strict: bool = False,
        target_format: str | None = None,
        preserve_mp3: bool = False,
        default_mime_type: str | None = "image/jpeg",
    ) -> str | None:
        """Resolve media directly to a provider-ready data URL."""
        resolved = await self.to_base64_data(
            strict=strict,
            target_format=target_format,
            preserve_mp3=preserve_mp3,
            default_mime_type=default_mime_type,
        )
        return resolved.to_data_url() if resolved else None

    @asynccontextmanager
    async def open(
        self,
        mode: str = "rb",
        *,
        target_format: str | None = None,
        preserve_mp3: bool = False,
    ):
        """Open resolved media as a file object inside a cleanup context."""
        async with self.as_path(
            target_format=target_format,
            preserve_mp3=preserve_mp3,
        ) as resolved:
            with resolved.open(mode) as file_obj:
                yield file_obj


async def resolve_image_ref_to_base64_data(
    image_ref: MediaRefStr | bytes,
    *,
    strict: bool = False,
    default_mime_type: str | None = "image/jpeg",
    options: ImagePreparationOptions | None = None,
) -> ResolvedMediaData | None:
    """Resolve and prepare an image reference for a provider request.

    When ``options`` is provided, the mainline preparation path bounds a
    model-facing image while keeping historical media references outside the
    in-memory request until selected. Without options, preserve the resolver's
    original byte-for-byte behavior for platform and compatibility callers.

    ``strict=False`` returns ``None`` for invalid images so payload
    assembly can skip bad image refs without failing the whole request.
    """
    try:
        if options is None:
            return await MediaResolver(
                image_ref,
                media_type="image",
                default_suffix=".bin",
            ).to_base64_data(
                strict=strict,
                default_mime_type=default_mime_type,
            )
        return await prepare_image_source(
            image_ref,
            options=options,
            default_mime_type=default_mime_type,
        )
    except (ImagePayloadTooLargeError, MemoryError):
        raise
    except Exception:
        if strict:
            raise
        return None


def is_recoverable_image_error(error: Exception) -> bool:
    """Identify ordinary input, decoder, network and cache failures.

    Args:
        error: Exception raised while processing an image.

    Returns:
        Whether the image may be skipped. Resource exhaustion, Pillow's image
        safety limit and programming errors must propagate to the caller.
    """
    if isinstance(error, OSError) and error.errno in {
        errno.ENOMEM,
        errno.EMFILE,
        errno.ENFILE,
    }:
        return False
    return isinstance(
        error,
        (
            OSError,
            ValueError,
            SyntaxError,
            EOFError,
            struct.error,
            ClientError,
            DownloadFileHTTPError,
        ),
    )


MODEL_IMAGE_MAX_BYTES = 512 * 1024
"""Model input image files must be strictly smaller than this limit."""


def normalize_model_image_max_size(value: object) -> int:
    """Normalize the model image longest-edge cap.

    Accepts ints, integer-like floats, and integer strings. Booleans,
    non-finite numbers, unparseable values, and values below the smallest
    usable montage edge (the grid size) fall back to the default with a
    warning, so every entry shares one effective-size semantic and a
    configured cap is actually honored by the produced montage.

    Args:
        value: Raw configured cap. ``None`` means unset and silently uses
            the default.

    Returns:
        The effective longest-edge cap in pixels.
    """
    normalized: int | None = None
    if isinstance(value, bool):
        normalized = None
    elif value is None:
        normalized = None
    elif isinstance(value, int):
        normalized = value
    elif isinstance(value, float):
        normalized = int(value) if math.isfinite(value) and value.is_integer() else None
    elif isinstance(value, str):
        try:
            normalized = int(value.strip())
        except ValueError:
            normalized = None
    if normalized is None or normalized < ANIMATED_MONTAGE_GRID:
        if value is not None:
            logger.warning(
                "Invalid model image max size %r; falling back to %d.",
                value,
                IMAGE_COMPRESS_DEFAULT_MAX_SIZE,
            )
        return IMAGE_COMPRESS_DEFAULT_MAX_SIZE
    return normalized


def _encode_image_frame_bytes(
    image: PILImage.Image,
    max_size: int | None = None,
) -> bytes:
    """Encode an owned frame below the byte limit while preserving transparency.

    Args:
        image: Decoded frame owned by the caller; its pixels and metadata may change.
        max_size: Optional longest-edge limit; smaller images are not enlarged.

    Returns:
        JPEG or transparent PNG bytes strictly below MODEL_IMAGE_MAX_BYTES.

    Raises:
        ValueError: The image cannot fit the byte limit even at one pixel.
    """
    ImageOps.exif_transpose(image, in_place=True)
    has_alpha = "A" in image.getbands() or "transparency" in image.info
    icc_profile = image.info.get("icc_profile")
    if image.mode not in {"RGB", "RGBA", "L", "LA", "P", "1", "I", "I;16"}:
        # A source profile is invalid after a color-space conversion such as CMYK.
        icc_profile = None
    prepared = image
    try:
        if has_alpha:
            if image.mode != "RGBA":
                prepared = image.convert("RGBA")
        elif image.mode not in {"RGB", "L", "I", "I;16"}:
            prepared = image.convert("L" if image.mode == "1" else "RGB")
        if max_size is not None:
            prepared.thumbnail(
                (max_size, max_size),
                PILImage.Resampling.LANCZOS,
                reducing_gap=None if prepared.mode == "I;16" else 2.0,
            )
        if prepared.mode in {"I", "I;16"}:
            # Normalize high-bit-depth pixels instead of clipping them to 255.
            low, high = prepared.getextrema()
            if high > low:
                with prepared.point(
                    lambda v: (v - low) * (255.0 / (high - low))
                ) as scaled:
                    prepared = scaled.convert("L")
            else:
                prepared = prepared.convert("L")
        # Do not carry EXIF, text chunks, or other unbounded metadata into previews.
        prepared.info.clear()
        save_kwargs = {"icc_profile": icc_profile} if icc_profile else {}
        while True:
            with io.BytesIO() as buffer:
                if has_alpha:
                    prepared.save(buffer, "PNG", **save_kwargs)
                else:
                    prepared.save(
                        buffer, "JPEG", quality=85, optimize=True, **save_kwargs
                    )
                data = buffer.getvalue()
            if len(data) < MODEL_IMAGE_MAX_BYTES:
                return data
            if save_kwargs:
                # Oversized profiles must not defeat the byte limit.
                save_kwargs.clear()
                continue
            if prepared.size == (1, 1):
                raise ValueError("Image cannot fit the model input byte limit")
            scale = min(0.85, math.sqrt((MODEL_IMAGE_MAX_BYTES - 1) / len(data)) * 0.95)
            prepared.thumbnail(
                (
                    max(1, int(prepared.width * scale)),
                    max(1, int(prepared.height * scale)),
                ),
                PILImage.Resampling.LANCZOS,
            )
    finally:
        if prepared is not image:
            prepared.close()


def _prepare_model_image_sync(source_bytes: bytes, max_size: int) -> tuple[bytes, bool]:
    """Prepare a preview using a single opened source image.

    Args:
        source_bytes: Original encoded image content.
        max_size: Longest-edge limit for still images and animation montages.

    Returns:
        Encoded image bytes and whether they represent an animation montage.
    """
    with PILImage.open(io.BytesIO(source_bytes)) as image:
        if getattr(image, "n_frames", 1) > 1:
            return _extract_animation_montage_sync(image, max_size), True
        if (
            image.format in {"PNG", "JPEG"}
            and len(source_bytes) < MODEL_IMAGE_MAX_BYTES
            and max(image.size) <= max_size
            and image.getexif().get(274, 1) == 1
        ):
            # Validate even byte-identical passthroughs without decoding twice.
            image.load()
            return source_bytes, False
        return _encode_image_frame_bytes(image, max_size), False


def _even_frame_indices(total_frames: int, max_frames: int) -> list[int]:
    """Pick evenly spaced animation frames, including both endpoints.

    Args:
        total_frames: Number of animation frames, excluding an independent cover.
        max_frames: Maximum number of frames to select.

    Returns:
        Ascending, unique frame indices.
    """
    count = min(max_frames, total_frames)
    if count <= 1:
        return [0]
    return sorted({round(i * (total_frames - 1) / (count - 1)) for i in range(count)})


def _extract_animation_montage_sync(image: PILImage.Image, max_size: int) -> bytes:
    """Tile evenly spaced animation frames into one white 3x3 preview.

    Args:
        image: Opened animation owned by the caller.
        max_size: Longest-edge limit of the montage, without upscaling.

    Returns:
        JPEG bytes below the byte limit, with unused cells left white.
    """
    total_frames = getattr(image, "n_frames", 1)
    # APNG's independent default image is a cover, not an animation frame.
    first_frame = 1 if image.info.get("default_image", False) else 0
    frame_indices = [
        first_frame + index
        for index in _even_frame_indices(
            total_frames - first_frame, ANIMATED_MONTAGE_FRAME_COUNT
        )
    ]
    image.seek(first_frame)
    with ImageOps.exif_transpose(image) as oriented:
        display_size = oriented.size
    # Floor the per-cell scale so the montage never exceeds max_size.
    longest_edge = max(display_size) * ANIMATED_MONTAGE_GRID
    scale = min(1.0, max(max_size, 1) / longest_edge)
    cell_size = (
        max(1, int(display_size[0] * scale)),
        max(1, int(display_size[1] * scale)),
    )
    canvas = PILImage.new(
        "RGB",
        (
            cell_size[0] * ANIMATED_MONTAGE_GRID,
            cell_size[1] * ANIMATED_MONTAGE_GRID,
        ),
        (255, 255, 255),
    )
    try:
        for out_index, frame_index in enumerate(frame_indices):
            image.seek(frame_index)
            with (
                ImageOps.exif_transpose(image) as oriented,
                oriented.convert("RGBA") as frame,
            ):
                resized = frame
                try:
                    if frame.size != cell_size:
                        resized = frame.resize(cell_size, PILImage.Resampling.LANCZOS)
                    # Alpha shows the white canvas through transparent pixels.
                    canvas.paste(
                        resized,
                        (
                            (out_index % ANIMATED_MONTAGE_GRID) * cell_size[0],
                            (out_index // ANIMATED_MONTAGE_GRID) * cell_size[1],
                        ),
                        resized,
                    )
                finally:
                    if resized is not frame:
                        resized.close()
        encoded = _encode_image_frame_bytes(canvas)
    finally:
        canvas.close()
    return encoded


class ImageInputTooLargeError(ImagePayloadTooLargeError):
    """Raised with the retained source path when an image exceeds the input cap."""

    def __init__(self, path: str) -> None:
        """Keep the source path for the file-reading fallback."""
        super().__init__(path)
        self.path = path


async def prepare_model_image(
    image_ref: str,
    *,
    max_size: int,
    output_dir: Path,
) -> tuple[str, bool, bool, str] | None:
    """Prepare an image, reusing compliant local files without copying them.

    Args:
        image_ref: Source reference accepted by MediaResolver.
        max_size: Longest-edge limit for both still images and montages.
        output_dir: Directory for event-owned working files.

    Returns:
        The image path, whether it is an animation montage, whether the caller must
        delete the preview after use, and the retained original path. Compliant
        originals are reused directly. Returns None for a recoverable failure.

    Raises:
        ImageInputTooLargeError: The input exceeds the size cap. Its original path
            is retained for file-tool access and returned as the error message.
    """
    try:
        async with MediaResolver(image_ref, media_type="image").as_path() as source:
            input_size = source.path.stat().st_size
            if input_size > MODEL_IMAGE_MAX_INPUT_BYTES:
                logger.warning(
                    "Skipping oversized image input (%d bytes): %s",
                    input_size,
                    source.path,
                )
                original_path = str(source.path)
                source.detach()
                raise ImageInputTooLargeError(original_path)
            image_bytes = await asyncio.to_thread(source.read_bytes)
            converted_bytes, is_montage = await asyncio.to_thread(
                _prepare_model_image_sync, image_bytes, max_size
            )
            original_path = str(source.path)
            needs_cleanup = bool(source.cleanup_paths)
            # Final image labels expose this original for later file-tool access.
            source.detach()
            if converted_bytes is image_bytes:
                return original_path, is_montage, needs_cleanup, original_path
        # Publish the working file synchronously after encoding, so cancellation
        # cannot leave an untracked background write alive after this call.
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".jpg" if converted_bytes.startswith(b"\xff\xd8") else ".png"
        fd, name = tempfile.mkstemp(
            prefix="model_image_", suffix=suffix, dir=output_dir
        )
        output_path = Path(name)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(converted_bytes)
        except BaseException:
            output_path.unlink(missing_ok=True)
            raise
        return str(output_path), is_montage, True, original_path
    except (ImageInputTooLargeError, ImagePayloadTooLargeError):
        raise
    except Exception as exc:
        if not is_recoverable_image_error(exc):
            raise
        logger.warning(
            "Model image preparation failed; skipping image (%s).", type(exc).__name__
        )
        return None


async def resolve_audio_ref_to_base64_data(
    audio_ref: MediaRefStr,
    *,
    preserve_mp3: bool = False,
    target_format: str | None = None,
) -> ResolvedMediaData:
    """Resolve an audio reference to base64 data.

    Audio is converted to WAV by default. Pass preserve_mp3=True for legacy
    provider payloads that intentionally keep MP3 input unchanged.
    ``target_format`` overrides both defaults when provided.
    """

    audio_data = await MediaResolver(
        audio_ref,
        media_type="audio",
        default_suffix=".wav",
    ).to_base64_data(
        target_format=target_format,
        preserve_mp3=preserve_mp3,
        strict=True,
    )
    if audio_data is None:
        raise ValueError(f"Invalid audio data: {describe_media_ref(audio_ref)}")
    return audio_data


async def get_media_duration(file_path: str) -> int | None:
    """Probe media duration with ffprobe.

    Args:
        file_path: Local media file path.

    Returns:
        Duration in milliseconds, or ``None`` when probing fails.
    """
    try:
        # Probe duration with ffprobe.
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0 and stdout:
            duration_seconds = float(stdout.decode().strip())
            duration_ms = int(duration_seconds * 1000)
            logger.debug("Media duration detected: %sms", duration_ms)
            return duration_ms
        else:
            logger.warning("Failed to get media duration: %s", file_path)
            return None

    except FileNotFoundError:
        logger.warning(
            "ffprobe is not installed or not in PATH. "
            "Install ffmpeg: https://ffmpeg.org/"
        )
        return None
    except Exception as e:
        logger.warning("Error while probing media duration: %s", e)
        return None


async def convert_audio_to_opus(audio_path: str, output_path: str | None = None) -> str:
    """Convert an audio file to Opus format.

    Args:
        audio_path: Source audio file path.
        output_path: Optional output file path. When omitted, a temporary path is
            created under AstrBot's temp directory.

    Returns:
        The converted Opus file path.
    """
    return await convert_audio_format(
        audio_path=audio_path,
        output_format="opus",
        output_path=output_path,
    )


async def convert_video_format(
    video_path: str, output_format: str = "mp4", output_path: str | None = None
) -> str:
    """Convert a video file with ffmpeg.

    Args:
        video_path: Source video file path.
        output_format: Target format, such as ``mp4``.
        output_path: Optional output file path. When omitted, a temporary path is
            created under AstrBot's temp directory.

    Returns:
        The converted video file path.

    Raises:
        Exception: Raised when ffmpeg is unavailable or conversion fails.
    """
    # Return early when the source already appears to be in the target format.
    if video_path.lower().endswith(f".{output_format}"):
        return video_path

    # Create an output path when the caller does not provide one.
    if output_path is None:
        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
        output_path = os.path.join(
            temp_dir,
            f"media_video_{generate_timestamp_id()}.{output_format}",
        )

    try:
        # Convert the video with ffmpeg.
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            output_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            # Remove a partial output file created by a failed ffmpeg run.
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                    logger.debug(
                        "Removed failed %s output file: %s",
                        output_format,
                        output_path,
                    )
                except OSError as e:
                    logger.warning(
                        "Failed to remove failed %s output file: %s",
                        output_format,
                        e,
                    )

            error_msg = stderr.decode() if stderr else "unknown error"
            logger.error("ffmpeg video conversion failed: %s", error_msg)
            raise Exception(f"ffmpeg conversion failed: {error_msg}")

        logger.debug(
            "Video converted successfully: %s -> %s",
            video_path,
            output_path,
        )
        return output_path

    except FileNotFoundError:
        logger.error(
            "ffmpeg is not installed or not in PATH. "
            "Install ffmpeg: https://ffmpeg.org/"
        )
        raise Exception("ffmpeg not found")
    except Exception as e:
        logger.error("Error while converting video format: %s", e)
        raise


async def convert_audio_format(
    audio_path: str,
    output_format: str = "amr",
    output_path: str | None = None,
) -> str:
    """Convert an audio file to the requested format with ffmpeg.

    Args:
        audio_path: Source audio file path.
        output_format: Target format, such as ``amr``, ``ogg``, ``opus``, or
            ``wav``.
        output_path: Optional output file path. When omitted, a temporary path is
            created under AstrBot's temp directory.

    Returns:
        The converted audio file path.

    Raises:
        Exception: Raised when ffmpeg is unavailable or conversion fails.
    """
    source_path = Path(audio_path)
    if source_path.suffix.lower() == f".{output_format}" and (
        not source_path.exists() or _get_audio_magic_type(audio_path) == output_format
    ):
        return audio_path

    if output_path is None:
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(
            temp_dir / f"media_audio_{generate_timestamp_id()}.{output_format}"
        )

    args = ["ffmpeg", "-y", "-i", audio_path]
    if output_format == "amr":
        args.extend(
            [
                "-ac",
                "1",
                "-ar",
                "8000",
                "-ab",
                "12.2k",
                "-af",
                (
                    "highpass=f=310:poles=2,"
                    "lowpass=f=3720:poles=2,"
                    "equalizer=f=3150:width_type=h:width=1000:g=7.5,"
                    "loudnorm=I=-18.5:TP=-1.5:LRA=6,"
                    "aresample=8000"
                ),
            ]
        )
    elif output_format == "ogg":
        args.extend(["-acodec", "libopus", "-ac", "1", "-ar", "16000"])
    elif output_format == "opus":
        args.extend(["-acodec", "libopus", "-ac", "1", "-ar", "16000"])
    args.append(output_path)

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError as e:
                    logger.warning(
                        "Failed to remove failed audio output file: %s",
                        e,
                    )
            error_msg = stderr.decode() if stderr else "unknown error"
            raise Exception(f"ffmpeg conversion failed: {error_msg}")
        logger.debug(
            "Audio converted successfully: %s -> %s",
            audio_path,
            output_path,
        )
        return output_path
    except FileNotFoundError:
        raise Exception("ffmpeg not found")


async def convert_audio_to_amr(audio_path: str, output_path: str | None = None) -> str:
    """Convert an audio file to AMR format.

    Args:
        audio_path: Source audio file path.
        output_path: Optional output file path. When omitted, a temporary path is
            created under AstrBot's temp directory.

    Returns:
        The converted AMR file path.
    """
    return await convert_audio_format(
        audio_path=audio_path,
        output_format="amr",
        output_path=output_path,
    )


async def convert_audio_to_wav(audio_path: str, output_path: str | None = None) -> str:
    """Convert an audio file to WAV format.

    Args:
        audio_path: Source audio file path.
        output_path: Optional output file path. When omitted, a temporary path is
            created under AstrBot's temp directory.

    Returns:
        The converted WAV file path.
    """
    return await convert_audio_format(
        audio_path=audio_path,
        output_format="wav",
        output_path=output_path,
    )


async def ensure_wav(audio_path: str, output_path: str | None = None) -> str:
    """Ensure the audio path points to wav format by extension/guess and convert when needed.

    If the file appears to already be WAV, return it directly to avoid extra
    conversion. If the file does not exist yet, return the original path so
    upstream retry logic can handle platform races.

    Args:
        audio_path: Local audio path to inspect and convert when needed.
        output_path: Optional destination path. When omitted, conversion helpers
            create a temporary file under AstrBot's temp directory.

    Returns:
        The original path when it is already WAV or unavailable; otherwise the
        converted WAV path.

    Raises:
        Exception: Raised by the underlying conversion helper when conversion
            fails.
    """

    if not audio_path:
        return audio_path

    if not os.path.exists(audio_path):
        # File not available yet (e.g. napcat race condition);
        # return the path as-is so upstream retry logic can handle it later.
        return audio_path

    audio_type = _get_audio_magic_type(audio_path)
    if audio_type == "wav":
        return audio_path

    if audio_type == "silk":
        if output_path is None:
            temp_dir = get_astrbot_temp_path()
            os.makedirs(temp_dir, exist_ok=True)
            output_path = os.path.join(
                temp_dir, f"media_audio_{generate_timestamp_id()}.wav"
            )
        return await tencent_silk_to_wav(audio_path, output_path)

    return await convert_audio_to_wav(audio_path, output_path)


async def ensure_jpeg(image_path: str, output_path: str | None = None) -> str:
    """Ensure JPEG-compatible still images point to a JPEG file.

    Args:
        image_path: Local image path to inspect and convert when needed.
        output_path: Optional destination path. When omitted, a temporary file under
            AstrBot's temp directory is created for converted JPEG output.

    Returns:
        The original path when the source is already a JPEG file with a jpg/jpeg
        suffix, cannot be found, has alpha transparency, or is animated. JPEG
        files with another suffix are copied without re-encoding; other still
        images are converted to JPEG.

    Raises:
        Exception: Raised by Pillow when the source file cannot be opened or saved as
            an image.
    """

    if not image_path:
        return image_path

    source_path = Path(image_path)
    if not source_path.exists():
        return image_path

    with PILImage.open(source_path) as opened_img:
        image_format = str(opened_img.format or "").upper()
        image_has_alpha = opened_img.mode in {"RGBA", "LA"} or (
            opened_img.mode == "P" and "transparency" in opened_img.info
        )
        image_is_animated = (
            getattr(opened_img, "is_animated", False)
            or getattr(
                opened_img,
                "n_frames",
                1,
            )
            > 1
        )

    if image_format == "JPEG" and source_path.suffix.lower() in {".jpg", ".jpeg"}:
        return image_path

    if image_has_alpha or image_is_animated:
        return image_path

    if output_path is None:
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(temp_dir / f"media_image_{generate_timestamp_id()}.jpg")
    jpeg_output_path = output_path

    try:
        if image_format == "JPEG":
            await asyncio.to_thread(shutil.copyfile, source_path, jpeg_output_path)
            return jpeg_output_path
    except Exception:
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as e:
                logger.warning(
                    "Failed to remove failed image output file: %s",
                    e,
                )
        raise

    def convert_image_to_jpeg() -> str:
        converted_img: PILImage.Image | None = None

        with PILImage.open(image_path) as opened_img:
            try:
                working_img: PILImage.Image = opened_img
                if opened_img.mode != "RGB":
                    converted_img = opened_img.convert("RGB")
                    working_img = converted_img

                working_img.save(
                    jpeg_output_path,
                    "JPEG",
                    quality=IMAGE_COMPRESS_DEFAULT_QUALITY,
                    subsampling=0,
                )
                return jpeg_output_path
            finally:
                if converted_img is not None:
                    converted_img.close()

    try:
        return await asyncio.to_thread(convert_image_to_jpeg)
    except Exception:
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as e:
                logger.warning(
                    "Failed to remove failed image output file: %s",
                    e,
                )
        raise


def _get_audio_magic_type(audio_path: str) -> str:
    """Detect common audio formats from magic bytes.

    Args:
        audio_path: Local audio path to inspect.

    Returns:
        A normalized format name such as ``wav``, ``mp3``, ``opus``, ``silk``, or
        an empty string when the type cannot be detected.
    """
    try:
        with open(audio_path, "rb") as f:
            header = f.read(64)
    except FileNotFoundError:
        logger.warning("WAV probe file not found: %s", audio_path)
        return ""
    except Exception as e:
        logger.warning(
            "WAV probe failed: %s, error: %s",
            audio_path,
            e,
        )
        return ""

    if len(header) < 12:
        return ""

    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return "wav"

    if header[:4] == b"#!AM":
        return "amr"

    if header[:4] == b"OggS":
        if b"OpusHead" in header:
            return "opus"
        return "ogg"

    if header[:3] == b"fLa":
        return "flac"

    if header[:3] == b"ID3" or header[:2] == b"\xff\xfb":
        return "mp3"

    if header[:4] == b"ftyp" and b"mp4" in header[:8]:
        return "mp4"

    if header.startswith(b"#!SILK_V3"):
        return "silk"

    # Tencent SILK: leading \x02 byte before #!SILK_V3
    if header.startswith(b"\x02#!SILK_V3"):
        return "silk"

    return ""


async def extract_video_cover(
    video_path: str,
    output_path: str | None = None,
) -> str:
    """Extract a JPEG cover frame from a video.

    Args:
        video_path: Source video file path.
        output_path: Optional output image path. When omitted, a temporary JPEG
            path is created under AstrBot's temp directory.

    Returns:
        The extracted JPEG cover path.

    Raises:
        Exception: Raised when ffmpeg is unavailable or cover extraction fails.
    """
    if output_path is None:
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(temp_dir / f"media_cover_{generate_timestamp_id()}.jpg")

    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-ss",
            "00:00:00",
            "-frames:v",
            "1",
            output_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError as e:
                    logger.warning(
                        "Failed to remove failed video cover file: %s",
                        e,
                    )
            error_msg = stderr.decode() if stderr else "unknown error"
            raise Exception(f"ffmpeg extract cover failed: {error_msg}")
        return output_path
    except FileNotFoundError:
        raise Exception("ffmpeg not found")


def _compress_image_sync(
    source: bytes | Path,
    temp_dir: Path,
    max_size: int,
    quality: int,
    optimize: bool,
) -> str | None:
    """Run image compression synchronously via ``asyncio.to_thread``.

    Args:
        source: Encoded image bytes or a local path to open inside the worker.
        temp_dir: Directory where the compressed image should be written.
        max_size: Longest edge of the compressed image in pixels.
        quality: JPEG output quality in the range 1-100.
        optimize: Whether Pillow should optimize the saved image.

    Returns:
        The compressed image path, or ``None`` when the image should be kept as-is.
    """
    fp = io.BytesIO(source) if isinstance(source, bytes) else source
    with PILImage.open(fp) as opened_img:
        converted_img: PILImage.Image | None = None

        try:
            if (
                getattr(opened_img, "is_animated", False)
                or getattr(opened_img, "n_frames", 1) > 1
            ):
                return None

            working_img = opened_img
            image_has_alpha = opened_img.mode in {"RGBA", "LA"} or (
                opened_img.mode == "P" and "transparency" in opened_img.info
            )
            output_format = "PNG" if image_has_alpha else "JPEG"
            output_suffix = ".png" if image_has_alpha else ".jpg"

            if image_has_alpha and opened_img.mode != "RGBA":
                converted_img = opened_img.convert("RGBA")
                working_img = converted_img
            elif not image_has_alpha and opened_img.mode != "RGB":
                converted_img = opened_img.convert("RGB")
                working_img = converted_img
            assert working_img is not None

            if max(working_img.size) > max_size:
                working_img.thumbnail((max_size, max_size), PILImage.Resampling.LANCZOS)

            save_path = (
                temp_dir / f"compressed_{generate_timestamp_id()}{output_suffix}"
            )
            save_kwargs: dict[str, int | bool] = {"optimize": optimize}
            if output_format == "JPEG":
                save_kwargs["quality"] = quality
            working_img.save(save_path, output_format, **save_kwargs)
            logger.debug(f"Image compressed successfully: {save_path}")
            return str(save_path)
        finally:
            if converted_img is not None:
                converted_img.close()


async def compress_image(
    url_or_path: str,
    max_size: int = IMAGE_COMPRESS_DEFAULT_MAX_SIZE,
    quality: int = IMAGE_COMPRESS_DEFAULT_QUALITY,
    *,
    optimize: bool = IMAGE_COMPRESS_DEFAULT_OPTIMIZE,
) -> str:
    """Compress large user-uploaded images.

    Args:
        url_or_path: Image path or URL.
        max_size: Longest edge of the compressed image in pixels.
        quality: JPEG output quality in the range 1-100.
        optimize: Whether Pillow should optimize the encoded output.

    Returns:
        The compressed image path. Returns the original path if compression
        fails or the source does not need compression.
    """
    max_size = max(int(max_size), 1)
    quality = min(max(int(quality), 1), 100)
    min_file_size_bytes = int(IMAGE_COMPRESS_DEFAULT_MIN_FILE_SIZE_MB * 1024 * 1024)
    image_source: bytes | Path | None = None

    def _exceeds_max_size(source: bytes | Path) -> bool:
        try:
            fp = io.BytesIO(source) if isinstance(source, bytes) else source
            with PILImage.open(fp) as opened_img:
                return max(opened_img.size) > max_size
        except Exception:  # noqa: BLE001
            return False

    # Skip compression for remote images and return the original value.
    if url_or_path.startswith("http"):
        return url_or_path
    elif url_or_path.startswith("data:image"):
        validate_image_input_size(url_or_path)
        _header, encoded = url_or_path.split(",", 1)
        image_source = _decode_base64_payload(
            encoded,
            error_message="invalid image data URI payload",
        )
        if len(image_source) < min_file_size_bytes and not _exceeds_max_size(
            image_source
        ):
            return url_or_path
    else:
        local_path = Path(url_or_path)
        if not local_path.exists():
            return url_or_path
        validate_image_input_size(local_path)
        source_size = local_path.stat().st_size
        if source_size < min_file_size_bytes and not _exceeds_max_size(local_path):
            return url_or_path
        image_source = local_path

    if image_source is None:
        return url_or_path

    temp_dir = Path(get_astrbot_temp_path())
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Offload the blocking image processing task to a thread.
    compressed_path = await asyncio.to_thread(
        _compress_image_sync,
        image_source,
        temp_dir,
        max_size,
        quality,
        optimize,
    )
    return compressed_path or url_or_path


async def prepare_image_source(
    image_ref: MediaRefStr | bytes | ImagePreparationInput,
    *,
    options: ImagePreparationOptions | None = None,
    default_mime_type: str | None = "image/jpeg",
) -> ResolvedMediaData:
    """Prepare one image through the mainline model-image pipeline.

    Args:
        image_ref: Local path, URL, data URI, base64 reference, or raw bytes.
        options: Optional dimension settings for the request.
        default_mime_type: Fallback MIME type when detection is unavailable.

    Returns:
        Provider-ready Base64 data and its MIME type.

    Raises:
        ImagePayloadTooLargeError: The input or prepared image exceeds a safe
            byte budget.
        ValueError: The source is not a readable image.
    """
    selected = options or ImagePreparationOptions()
    preparation_input = (
        image_ref
        if isinstance(image_ref, ImagePreparationInput)
        else ImagePreparationInput(image_ref)
    )
    source_ref = preparation_input.value
    try:
        if isinstance(source_ref, bytes):
            validate_image_input_size(source_ref)
            prepared_bytes, _ = await asyncio.to_thread(
                _prepare_model_image_sync,
                source_ref,
                max(selected.max_size, 1),
            )
            mime_type = detect_image_mime_type(
                prepared_bytes,
                default_mime_type=default_mime_type,
            )
            if not mime_type:
                raise ValueError("image content could not be identified")
            return ResolvedMediaData(
                base64_data=base64.b64encode(prepared_bytes).decode("ascii"),
                mime_type=mime_type,
                byte_size=len(prepared_bytes),
            )

        if not isinstance(source_ref, str):
            raise TypeError("image reference must be a string or bytes")

        prepared = await prepare_model_image(
            source_ref,
            max_size=max(selected.max_size, 1),
            output_dir=Path(get_astrbot_temp_path()),
        )
        if prepared is None:
            # Preserve the historical opaque-base64 fallback for callers that
            # intentionally pass bytes Pillow cannot identify as an image.
            resolved = await MediaResolver(
                source_ref,
                media_type="image",
                default_suffix=".bin",
            ).to_base64_data(
                strict=True,
                default_mime_type=default_mime_type,
            )
            if resolved is not None:
                if (
                    resolved.byte_size is not None
                    and resolved.byte_size >= MODEL_IMAGE_MAX_BYTES
                ):
                    raise ImagePayloadTooLargeError(
                        "Prepared image exceeds the model input byte limit"
                    )
                return resolved
            raise ValueError(f"Invalid image file: {describe_media_ref(source_ref)}")
        prepared_path, _is_montage, needs_cleanup, _original_path = prepared
        path = Path(prepared_path)
        try:
            mime_type = await detect_image_mime_type_async(
                path,
                default_mime_type=default_mime_type,
            )
            if not mime_type:
                raise ValueError("image content could not be identified")
            encoded_data = await asyncio.to_thread(_encode_file_to_base64, path)
            byte_size = path.stat().st_size
            return ResolvedMediaData(
                base64_data=encoded_data,
                mime_type=mime_type,
                byte_size=byte_size,
            )
        finally:
            if needs_cleanup:
                path.unlink(missing_ok=True)
    finally:
        for cleanup_path in preparation_input.cleanup_paths:
            cleanup_path.unlink(missing_ok=True)


async def resolve_media_ref_to_base64_data(
    media_ref: MediaRefStr | bytes,
    *,
    media_type: str,
    strict: bool = False,
    image_options: ImagePreparationOptions | None = None,
    default_mime_type: str | None = "image/jpeg",
) -> ResolvedMediaData | None:
    """Resolve a media reference through the shared provider boundary.

    Args:
        media_ref: Media path, URL, data URI, Base64 reference, or raw bytes.
        media_type: Logical media family.
        strict: Whether ordinary resolution failures should propagate.
        image_options: Optional image preparation settings.
        default_mime_type: MIME fallback for image data.

    Returns:
        Resolved media data, or ``None`` for a recoverable non-strict failure.
    """
    if media_type == "image":
        return await resolve_image_ref_to_base64_data(
            media_ref,
            strict=strict,
            default_mime_type=default_mime_type,
            options=image_options,
        )
    return await MediaResolver(
        media_ref,
        media_type=media_type,
    ).to_base64_data(strict=strict, default_mime_type=default_mime_type)
