"""Bounded JSON rewriting for legacy conversations with inline image data."""

from __future__ import annotations

import base64
import binascii
import codecs
import json
import re
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from astrbot.core.image_history_migration import (
    ImageHistoryMigrationError,
    _resolve_temp_file,
)
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

DEFAULT_MAX_OUTPUT_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_IMAGE_BYTES = 64 * 1024 * 1024
_MAX_CAPTURED_JSON_STRING_BYTES = 4096
_MAX_LOCAL_URL_BYTES = 32 * 1024
_MAX_JSON_DEPTH = 256
_CONTROL_BYTES = re.compile(rb"[\x00-\x1f]")


@dataclass(frozen=True, slots=True)
class StagedImage:
    """One recognized image part and its validated local byte source.

    Attributes:
        message_index: Zero-based position in the source message array.
        part_index: Zero-based position in the source message's content array.
        payload_path: Decoded data URI file or validated existing AstrBot temp file.
    """

    message_index: int
    part_index: int
    payload_path: Path


@dataclass(frozen=True, slots=True)
class StreamRewriteStats:
    """Bounded summary of one completed history rewrite."""

    input_bytes: int
    output_bytes: int
    images_rewritten: int


class StreamHistoryError(ValueError):
    """The source history is malformed, unsupported, or exceeds an output limit."""


class _OutputLimitError(StreamHistoryError):
    """The compact rewritten JSON exceeds the configured byte limit."""


class _Reader:
    """Buffered byte reader that tracks offsets without reading whole strings."""

    def __init__(self, source: BinaryIO, chunk_bytes: int) -> None:
        self.source = source
        self.chunk_bytes = chunk_bytes
        self.buffer = b""
        self.position = 0
        self.offset = 0

    def _fill(self) -> bool:
        if self.position < len(self.buffer):
            return True
        self.buffer = self.source.read(self.chunk_bytes)
        self.position = 0
        return bool(self.buffer)

    def peek(self) -> int | None:
        if not self._fill():
            return None
        return self.buffer[self.position]

    def read_byte(self) -> int:
        value = self.peek()
        if value is None:
            raise StreamHistoryError("Unexpected end of JSON input")
        self.position += 1
        self.offset += 1
        return value

    def read_exact(self, size: int) -> bytes:
        if size < 0:
            raise ValueError("size must not be negative")
        result = bytearray()
        while size:
            if not self._fill():
                raise StreamHistoryError("Unexpected end of JSON input")
            available = min(size, len(self.buffer) - self.position)
            result.extend(self.buffer[self.position : self.position + available])
            self.position += available
            self.offset += available
            size -= available
        return bytes(result)

    def copy_until_string_delimiter(
        self,
        writer: _Writer,
        capture: bytearray | None,
        capture_limit: int | None,
    ) -> bytes:
        """Copy an unescaped string run, stopping at quote, slash, or control byte."""
        if not self._fill():
            raise StreamHistoryError("Unterminated JSON string")
        view = self.buffer[self.position :]
        quote = view.find(b'"')
        slash = view.find(b"\\")
        control_match = _CONTROL_BYTES.search(view)
        control = control_match.start() if control_match else -1
        candidates = [index for index in (quote, slash, control) if index >= 0]
        count = min(candidates) if candidates else len(view)
        if control == count:
            raise StreamHistoryError("Unescaped control byte in JSON string")
        if count:
            chunk = bytes(view[:count])
            writer.write(chunk)
            if capture is not None:
                room = capture_limit + 3 - len(capture)
                if room > 0:
                    capture.extend(chunk[:room])
            self.position += count
            self.offset += count
            return chunk
        return b""


class _Writer:
    """Write bytes and optionally enforce a byte-level output budget."""

    def __init__(self, stream: BinaryIO, limit: int | None = None) -> None:
        self.stream = stream
        self.limit = limit
        self.bytes_written = 0

    def tell(self) -> int:
        return self.bytes_written

    def write(self, data: bytes | bytearray | memoryview) -> None:
        if not data:
            return
        size = len(data)
        if self.limit is not None and self.bytes_written + size > self.limit:
            raise _OutputLimitError("Rewritten conversation exceeds 16 MiB")
        written = self.stream.write(data)
        if written != size:
            raise OSError("Incomplete history rewrite write")
        self.bytes_written += size


@dataclass(slots=True)
class _ValueInfo:
    kind: str
    start: int
    end: int
    scalar: Any = None
    fields: dict[str, _ValueInfo] | None = None


class _JsonParser:
    """Small strict JSON copier with selective field spans for image parts."""

    def __init__(self, reader: _Reader, chunk_bytes: int) -> None:
        self.reader = reader
        self.chunk_bytes = chunk_bytes

    def _skip_whitespace(self) -> None:
        while self.reader.peek() in (0x20, 0x09, 0x0A, 0x0D):
            self.reader.read_byte()

    def _expect(self, expected: int) -> None:
        self._skip_whitespace()
        if self.reader.read_byte() != expected:
            raise StreamHistoryError("Invalid JSON structure")

    def _parse_string(
        self, writer: _Writer, *, capture_limit: int | None = None
    ) -> tuple[int, int, str | None]:
        start = writer.tell()
        self._expect(0x22)
        writer.write(b'"')
        capture = bytearray(b'"') if capture_limit is not None else None
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        while True:
            raw = self.reader.copy_until_string_delimiter(
                writer, capture, capture_limit
            )
            if raw:
                decoder.decode(raw, final=False)
            if capture is not None and len(capture) > capture_limit + 2:
                capture = None
            marker = self.reader.peek()
            if marker is None:
                raise StreamHistoryError("Unterminated JSON string")
            if marker == 0x22:
                decoder.decode(b"", final=True)
                self.reader.read_byte()
                writer.write(b'"')
                if capture is not None:
                    capture.extend(b'"')
                break
            if marker != 0x5C:
                continue

            decoder.decode(b"", final=True)
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            escape = bytearray(self.reader.read_exact(2))
            if escape[0] != 0x5C or escape[1] not in b'"\\/bfnrtu':
                raise StreamHistoryError("Invalid JSON escape")
            if escape[1] == ord("u"):
                digits = self.reader.read_exact(4)
                if any(item not in b"0123456789abcdefABCDEF" for item in digits):
                    raise StreamHistoryError("Invalid JSON Unicode escape")
                escape.extend(digits)
            writer.write(escape)
            if capture is not None:
                capture.extend(escape)
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            if capture is not None and len(capture) > capture_limit + 2:
                capture = None

        end = writer.tell()
        decoded: str | None = None
        if capture is not None:
            try:
                decoded = json.loads(capture.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise StreamHistoryError("Invalid JSON string") from None
        return start, end, decoded

    def _parse_number(self, writer: _Writer) -> _ValueInfo:
        start = writer.tell()
        state = "start"
        while True:
            value = self.reader.peek()
            if value is None or value in b" \t\r\n,]}":
                break
            if value == ord("-") and state == "start":
                state = "minus"
            elif value == ord("0") and state in {"start", "minus"}:
                state = "zero"
            elif value in b"123456789" and state in {"start", "minus", "integer"}:
                state = "integer"
            elif value == ord("0") and state == "integer":
                pass
            elif value == ord(".") and state in {"zero", "integer"}:
                state = "dot"
            elif value in b"0123456789" and state in {"dot", "fraction"}:
                state = "fraction"
            elif value in b"eE" and state in {"zero", "integer", "fraction"}:
                state = "exponent"
            elif value in b"+-" and state == "exponent":
                state = "exponent_sign"
            elif value in b"0123456789" and state in {
                "exponent",
                "exponent_sign",
                "exponent_digits",
            }:
                state = "exponent_digits"
            else:
                raise StreamHistoryError("Invalid JSON number")
            writer.write(bytes((self.reader.read_byte(),)))
        if state not in {"zero", "integer", "fraction", "exponent_digits"}:
            raise StreamHistoryError("Invalid JSON number")
        return _ValueInfo("number", start, writer.tell(), scalar=None)

    def parse_value(
        self,
        writer: _Writer,
        *,
        depth: int = 0,
        track_fields: set[str] | None = None,
    ) -> _ValueInfo:
        if depth > _MAX_JSON_DEPTH:
            raise StreamHistoryError("JSON nesting exceeds the supported limit")
        self._skip_whitespace()
        start = writer.tell()
        value = self.reader.peek()
        if value is None:
            raise StreamHistoryError("Unexpected end of JSON input")
        if value == ord('"'):
            _, end, scalar = self._parse_string(
                writer,
                capture_limit=(
                    _MAX_CAPTURED_JSON_STRING_BYTES
                    if track_fields is not None
                    else None
                ),
            )
            return _ValueInfo("string", start, end, scalar=scalar)
        if value == ord("{"):
            return self._parse_object(
                writer, depth=depth + 1, track_fields=track_fields
            )
        if value == ord("["):
            self._parse_array(writer, depth=depth + 1)
            return _ValueInfo("array", start, writer.tell())
        if value in b"-0123456789":
            return self._parse_number(writer)
        for literal, kind, scalar in (
            (b"true", "boolean", True),
            (b"false", "boolean", False),
            (b"null", "null", None),
        ):
            if value == literal[0]:
                if self.reader.read_exact(len(literal)) != literal:
                    raise StreamHistoryError("Invalid JSON value")
                writer.write(literal)
                return _ValueInfo(kind, start, writer.tell(), scalar=scalar)
        raise StreamHistoryError("Invalid JSON value")

    def _parse_array(self, writer: _Writer, *, depth: int) -> None:
        self._expect(ord("["))
        writer.write(b"[")
        self._skip_whitespace()
        if self.reader.peek() == ord("]"):
            self.reader.read_byte()
            writer.write(b"]")
            return
        first = True
        while True:
            if not first:
                self._expect(ord(","))
                writer.write(b",")
            first = False
            self.parse_value(writer, depth=depth)
            self._skip_whitespace()
            if self.reader.peek() == ord("]"):
                self.reader.read_byte()
                writer.write(b"]")
                return
            if self.reader.peek() != ord(","):
                raise StreamHistoryError("Invalid JSON array")

    def _parse_object(
        self,
        writer: _Writer,
        *,
        depth: int,
        track_fields: set[str] | None = None,
    ) -> _ValueInfo:
        start = writer.tell()
        self._expect(ord("{"))
        writer.write(b"{")
        fields: dict[str, _ValueInfo] = {}
        self._skip_whitespace()
        if self.reader.peek() == ord("}"):
            self.reader.read_byte()
            writer.write(b"}")
            return _ValueInfo("object", start, writer.tell(), fields=fields)

        first = True
        while True:
            if not first:
                self._expect(ord(","))
                writer.write(b",")
            first = False
            self._skip_whitespace()
            key_start, key_end, key = self._parse_string(
                writer, capture_limit=_MAX_CAPTURED_JSON_STRING_BYTES
            )
            if key is None:
                key = ""
            self._expect(ord(":"))
            writer.write(b":")
            value_start = writer.tell()
            nested = (
                {"url"}
                if track_fields is not None
                and "image_url" in track_fields
                and key == "image_url"
                else None
            )
            item = self.parse_value(
                writer,
                depth=depth,
                track_fields=(
                    nested if nested is not None else set() if key == "type" else None
                ),
            )
            item.start = value_start
            if track_fields is not None and key in track_fields:
                fields[key] = item
            self._skip_whitespace()
            if self.reader.peek() == ord("}"):
                self.reader.read_byte()
                writer.write(b"}")
                return _ValueInfo("object", start, writer.tell(), fields=fields)
            if self.reader.peek() != ord(","):
                raise StreamHistoryError("Invalid JSON object")


def _copy_stream(source: BinaryIO, destination: _Writer, chunk_bytes: int) -> None:
    """Copy a seekable spool to a writer in bounded chunks."""
    source.seek(0)
    while chunk := source.read(chunk_bytes):
        destination.write(chunk)


def _decode_json_string_chunks(
    source: BinaryIO, start: int, end: int, chunk_bytes: int
):
    """Yield decoded text chunks for a JSON string's content, without joining it."""
    cursor = start + 1
    stop = end - 1
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    while cursor < stop:
        source.seek(cursor)
        chunk = source.read(min(chunk_bytes, stop - cursor))
        if not chunk:
            raise StreamHistoryError("Unexpected end of staged JSON string")
        escape_at = chunk.find(b"\\")
        if escape_at < 0:
            text = decoder.decode(chunk, final=False)
            if text:
                yield text
            cursor += len(chunk)
            continue

        text = decoder.decode(chunk[:escape_at], final=True)
        if text:
            yield text
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        cursor += escape_at
        source.seek(cursor)
        escape = source.read(2)
        if len(escape) != 2 or escape[0] != 0x5C:
            raise StreamHistoryError("Invalid JSON escape in image URL")
        cursor += 2
        simple = {
            ord('"'): '"',
            ord("\\"): "\\",
            ord("/"): "/",
            ord("b"): "\b",
            ord("f"): "\f",
            ord("n"): "\n",
            ord("r"): "\r",
            ord("t"): "\t",
        }
        if escape[1] in simple:
            yield simple[escape[1]]
        elif escape[1] == ord("u"):
            digits = source.read(4)
            if len(digits) != 4:
                raise StreamHistoryError("Invalid JSON Unicode escape")
            cursor += 4
            try:
                codepoint = int(digits, 16)
            except ValueError:
                raise StreamHistoryError("Invalid JSON Unicode escape") from None
            if 0xD800 <= codepoint <= 0xDBFF:
                pair = source.read(6)
                if len(pair) != 6 or pair[:2] != b"\\u":
                    raise StreamHistoryError("Unpaired JSON surrogate")
                cursor += 6
                try:
                    low = int(pair[2:], 16)
                except ValueError:
                    raise StreamHistoryError("Invalid JSON Unicode escape") from None
                if not 0xDC00 <= low <= 0xDFFF:
                    raise StreamHistoryError("Unpaired JSON surrogate")
                codepoint = 0x10000 + ((codepoint - 0xD800) << 10) + low - 0xDC00
            elif 0xDC00 <= codepoint <= 0xDFFF:
                raise StreamHistoryError("Unpaired JSON surrogate")
            yield chr(codepoint)
        else:
            raise StreamHistoryError("Invalid JSON escape in image URL")
    final = decoder.decode(b"", final=True)
    if final:
        yield final


def _write_base64_chunk(output: BinaryIO, data: bytes, current_size: int) -> int:
    """Decode one non-final block of strict base64 into the staged image."""
    if b"=" in data:
        raise ImageHistoryMigrationError("invalid_image")
    try:
        decoded = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise ImageHistoryMigrationError("invalid_image") from None
    size = current_size + len(decoded)
    if size > DEFAULT_MAX_IMAGE_BYTES:
        raise ImageHistoryMigrationError("invalid_image")
    if output.write(decoded) != len(decoded):
        raise OSError("Incomplete image staging write")
    return size


def _resolve_image_string(
    spool: BinaryIO,
    span: _ValueInfo,
    staging_dir: Path,
    chunk_bytes: int,
) -> tuple[Path, bool]:
    """Resolve one JSON string as a bounded data URI or an AstrBot temp file."""
    prefix = bytearray()
    url_bytes = bytearray()
    mode: str | None = None
    staged: Path | None = None
    output: BinaryIO | None = None
    base64_pending = bytearray()
    decoded_size = 0
    temp_root = Path(get_astrbot_temp_path()).resolve()

    def feed_base64(data: bytes) -> None:
        nonlocal decoded_size
        base64_pending.extend(data)
        process_length = max(0, ((len(base64_pending) - 4) // 4) * 4)
        if process_length:
            decoded_size = _write_base64_chunk(
                output,
                bytes(base64_pending[:process_length]),
                decoded_size,
            )
            del base64_pending[:process_length]

    try:
        for text in _decode_json_string_chunks(
            spool, span.start, span.end, chunk_bytes
        ):
            if not text.isascii() and (
                mode == "data" or prefix[:5].lower() == b"data:"
            ):
                raise ImageHistoryMigrationError("invalid_image")
            encoded = text.encode("utf-8")
            if mode == "path":
                url_bytes.extend(encoded)
                if len(url_bytes) > _MAX_LOCAL_URL_BYTES:
                    raise ImageHistoryMigrationError("unavailable")
                continue
            if mode == "data":
                feed_base64(encoded)
                continue

            comma = encoded.find(b",")
            if comma < 0:
                prefix.extend(encoded)
                if len(prefix) > _MAX_CAPTURED_JSON_STRING_BYTES:
                    if prefix[:5].lower() == b"data:":
                        raise ImageHistoryMigrationError("invalid_image")
                    mode = "path"
                    url_bytes.extend(prefix)
                    prefix.clear()
                    if len(url_bytes) > _MAX_LOCAL_URL_BYTES:
                        raise ImageHistoryMigrationError("unavailable")
                elif len(prefix) >= 5 and prefix[:5].lower() != b"data:":
                    mode = "path"
                    url_bytes.extend(prefix)
                    prefix.clear()
                continue

            prefix.extend(encoded[:comma])
            if prefix[:5].lower() != b"data:":
                mode = "path"
                url_bytes.extend(prefix)
                url_bytes.extend(b",")
                url_bytes.extend(encoded[comma + 1 :])
                if len(url_bytes) > _MAX_LOCAL_URL_BYTES:
                    raise ImageHistoryMigrationError("unavailable")
                continue

            parameters = bytes(prefix)[5:].split(b";")
            if (
                not parameters
                or not parameters[0].lower().startswith(b"image/")
                or not any(item.lower() == b"base64" for item in parameters[1:])
            ):
                raise ImageHistoryMigrationError("invalid_image")
            staging_dir.mkdir(parents=True, exist_ok=True)
            staged = staging_dir / f"m7-image-{uuid.uuid4()}.img"
            output = staged.open("xb")
            mode = "data"
            feed_base64(encoded[comma + 1 :])

        if mode != "data" or output is None or staged is None:
            if mode is None:
                url_bytes.extend(prefix)
            try:
                url = bytes(url_bytes).decode("utf-8")
            except UnicodeDecodeError:
                raise ImageHistoryMigrationError("unavailable") from None
            return _resolve_temp_file(url, temp_root), False
        try:
            final = base64.b64decode(bytes(base64_pending), validate=True)
        except (binascii.Error, ValueError):
            raise ImageHistoryMigrationError("invalid_image") from None
        if (
            not final
            or decoded_size + len(final) > DEFAULT_MAX_IMAGE_BYTES
            or b"=" in base64_pending[:-2]
        ):
            raise ImageHistoryMigrationError("invalid_image")
        if output.write(final) != len(final):
            raise OSError("Incomplete image staging write")
        decoded_size += len(final)
        output.flush()
        return staged, True
    except BaseException:
        if output is not None:
            output.close()
            output = None
        if staged is not None:
            staged.unlink(missing_ok=True)
        raise
    finally:
        if output is not None:
            output.close()


def _extract_image_url(part: _ValueInfo) -> _ValueInfo | None:
    """Select the legacy image URL field using the M6 field precedence."""
    fields = part.fields or {}
    image_url = fields.get("image_url")
    if image_url is not None and image_url.kind == "string":
        return image_url
    if image_url is not None and image_url.kind == "object":
        nested_url = (image_url.fields or {}).get("url")
        return nested_url if nested_url and nested_url.kind == "string" else None
    fallback = fields.get("url")
    return fallback if fallback and fallback.kind == "string" else None


def _encode_replacement(part: dict[str, Any]) -> bytes:
    """Serialize a callback-produced reference as compact UTF-8 JSON."""
    try:
        return json.dumps(
            part,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise StreamHistoryError("Image callback returned invalid JSON data") from None


async def rewrite_legacy_history_stream(
    source: BinaryIO,
    output: BinaryIO,
    *,
    staging_dir: Path,
    import_image: Callable[[StagedImage], Awaitable[dict[str, Any]]],
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    chunk_bytes: int = 64 * 1024,
) -> StreamRewriteStats:
    """Rewrite legacy image blocks without materializing a message or long string.

    Args:
        source: Seekable binary snapshot containing the serialized message array.
        output: Binary destination that receives compact JSON on success.
        staging_dir: Temporary directory for decoded data URI files.
        import_image: Async callback that stores a local image and returns its
            complete persisted ``image_ref`` mapping.
        max_output_bytes: Maximum compact JSON output size in bytes.
        chunk_bytes: Bounded read size used for source, output, and payload streams.

    Returns:
        Input and output byte counts and the number of replaced image blocks.

    Raises:
        StreamHistoryError: JSON is malformed or rewritten output exceeds the limit.
        ImageHistoryMigrationError: A recognized image source is unsafe or invalid.
        OSError: A storage or filesystem operation fails.
    """
    if not all(hasattr(source, method) for method in ("read", "seek", "tell")):
        raise ValueError("History source must support read, seek, and tell")
    if not all(
        hasattr(output, method) for method in ("write", "seek", "tell", "truncate")
    ):
        raise ValueError("History output must support write, seek, tell, and truncate")
    if chunk_bytes < 4 or max_output_bytes < 1:
        raise ValueError("Invalid stream rewrite limits")
    staging_dir.mkdir(parents=True, exist_ok=True)
    source.seek(0, 2)
    input_bytes = source.tell()
    source.seek(0)
    output.seek(0)
    output.truncate(0)
    reader = _Reader(source, chunk_bytes)
    parser = _JsonParser(reader, chunk_bytes)
    final_writer = _Writer(output, max_output_bytes)
    message_index = 0
    images_rewritten = 0
    try:
        parser._expect(ord("["))
        final_writer.write(b"[")
        parser._skip_whitespace()
        if reader.peek() != ord("]"):
            while True:
                if message_index:
                    parser._expect(ord(","))
                    final_writer.write(b",")
                parser._skip_whitespace()
                if reader.peek() != ord("{"):
                    raise StreamHistoryError(
                        "Conversation messages must be JSON objects"
                    )
                with tempfile.SpooledTemporaryFile(
                    max_size=max(chunk_bytes, 1024 * 1024),
                    mode="w+b",
                    dir=staging_dir,
                ) as message_spool:
                    message_writer = _Writer(message_spool)
                    message_info = parser.parse_value(
                        message_writer, track_fields={"content"}
                    )
                    content_span = (message_info.fields or {}).get("content")
                    message_spool.seek(0)
                    message_reader = _Reader(message_spool, chunk_bytes)
                    message_parser = _JsonParser(message_reader, chunk_bytes)
                    await _rewrite_message(
                        message_parser,
                        final_writer,
                        content_span,
                        message_index,
                        import_image,
                        staging_dir,
                        chunk_bytes,
                    )
                    images_rewritten += getattr(message_parser, "images_rewritten", 0)
                message_index += 1
                parser._skip_whitespace()
                if reader.peek() == ord("]"):
                    break
                if reader.peek() != ord(","):
                    raise StreamHistoryError("Invalid conversation message array")
        parser._expect(ord("]"))
        final_writer.write(b"]")
        parser._skip_whitespace()
        if reader.peek() is not None:
            raise StreamHistoryError("Trailing data after conversation JSON")
        output.flush()
        return StreamRewriteStats(
            input_bytes, final_writer.bytes_written, images_rewritten
        )
    except BaseException:
        output.seek(0)
        output.truncate(0)
        raise


async def _rewrite_message(
    parser: _JsonParser,
    writer: _Writer,
    content_span: _ValueInfo | None,
    message_index: int,
    import_image: Callable[[StagedImage], Awaitable[dict[str, Any]]],
    staging_dir: Path,
    chunk_bytes: int,
) -> None:
    """Copy one disk-spooled message and rewrite only its last content field."""
    parser._expect(ord("{"))
    writer.write(b"{")
    parser._skip_whitespace()
    first = True
    while parser.reader.peek() != ord("}"):
        if not first:
            parser._expect(ord(","))
            writer.write(b",")
        first = False
        parser._skip_whitespace()
        _, _, key = parser._parse_string(
            writer, capture_limit=_MAX_CAPTURED_JSON_STRING_BYTES
        )
        parser._expect(ord(":"))
        writer.write(b":")
        source_value_start = parser.reader.offset
        if key == "content" and content_span is not None:
            value_writer = writer
            parser._skip_whitespace()
            if source_value_start == content_span.start and parser.reader.peek() == ord(
                "["
            ):
                images = await _rewrite_content_array(
                    parser,
                    value_writer,
                    message_index,
                    import_image,
                    staging_dir,
                    chunk_bytes,
                )
                parser.images_rewritten = (
                    getattr(parser, "images_rewritten", 0) + images
                )
            else:
                parser.parse_value(writer, depth=1)
        else:
            parser.parse_value(writer, depth=1)
        parser._skip_whitespace()
        if parser.reader.peek() == ord("}"):
            break
    parser._expect(ord("}"))
    writer.write(b"}")
    parser._skip_whitespace()
    if parser.reader.peek() is not None:
        raise StreamHistoryError("Invalid message JSON")


async def _rewrite_content_array(
    parser: _JsonParser,
    writer: _Writer,
    message_index: int,
    import_image: Callable[[StagedImage], Awaitable[dict[str, Any]]],
    staging_dir: Path,
    chunk_bytes: int,
) -> int:
    """Rewrite image objects in one content array while streaming other values."""
    parser._expect(ord("["))
    writer.write(b"[")
    parser._skip_whitespace()
    part_index = 0
    image_count = 0
    if parser.reader.peek() != ord("]"):
        while True:
            if part_index:
                parser._expect(ord(","))
                writer.write(b",")
            parser._skip_whitespace()
            if parser.reader.peek() == ord("{"):
                image_count += await _rewrite_part(
                    parser,
                    writer,
                    message_index,
                    part_index,
                    import_image,
                    staging_dir,
                    chunk_bytes,
                )
            else:
                parser.parse_value(writer, depth=2)
            part_index += 1
            parser._skip_whitespace()
            if parser.reader.peek() == ord("]"):
                break
            if parser.reader.peek() != ord(","):
                raise StreamHistoryError("Invalid message content array")
    parser._expect(ord("]"))
    writer.write(b"]")
    return image_count


async def _rewrite_part(
    parser: _JsonParser,
    writer: _Writer,
    message_index: int,
    part_index: int,
    import_image: Callable[[StagedImage], Awaitable[dict[str, Any]]],
    staging_dir: Path,
    chunk_bytes: int,
) -> int:
    """Spool one part to disk so its type may appear after its URL field."""
    with tempfile.SpooledTemporaryFile(
        max_size=max(chunk_bytes, 1024 * 1024), mode="w+b", dir=staging_dir
    ) as part_spool:
        part_writer = _Writer(part_spool)
        part = parser.parse_value(
            part_writer, track_fields={"type", "image_url", "url"}
        )
        fields = part.fields or {}
        part_type = fields.get("type")
        if (
            part_type is None
            or part_type.kind != "string"
            or part_type.scalar != "image_url"
        ):
            part_spool.seek(0)
            _copy_stream(part_spool, writer, chunk_bytes)
            return 0
        url_info = _extract_image_url(part)
        if url_info is None:
            raise ImageHistoryMigrationError("invalid_history")
        payload_path, temporary = _resolve_image_string(
            part_spool, url_info, staging_dir, chunk_bytes
        )
        try:
            result = await import_image(
                StagedImage(message_index, part_index, payload_path)
            )
            if not isinstance(result, dict) or result.get("type") != "image_ref":
                raise StreamHistoryError(
                    "Image callback must return an image_ref mapping"
                )
            writer.write(_encode_replacement(result))
        finally:
            if temporary:
                payload_path.unlink(missing_ok=True)
        return 1
