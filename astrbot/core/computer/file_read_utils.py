from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from asyncio import to_thread
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import mcp

from astrbot.core.agent.context.token_counter import EstimateTokenCounter
from astrbot.core.agent.message import Message
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.media_utils import (
    IMAGE_COMPRESS_DEFAULT_MAX_SIZE,
    IMAGE_COMPRESS_DEFAULT_OPTIMIZE,
    IMAGE_COMPRESS_DEFAULT_QUALITY,
    _compress_image_sync,
)

from .booters.base import ComputerBooter

_MAX_FILE_READ_BYTES = 128 * 1024
_MAX_FILE_READ_TOKENS = 25_000
_MAX_TEXT_FILE_FULL_READ_BYTES = 256 * 1024
_FILE_SNIFF_BYTES = 512
_TOKEN_COUNTER = EstimateTokenCounter()
_TEXT_ENCODINGS = (
    "utf-8-sig",
    "utf-8",
    "gb18030",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
    "utf-32",
    "utf-32-le",
    "utf-32-be",
)
_UTF_BOMS = (
    b"\xef\xbb\xbf",
    b"\xff\xfe",
    b"\xfe\xff",
    b"\xff\xfe\x00\x00",
    b"\x00\x00\xfe\xff",
)
_ZIP_MAGIC_PREFIXES = (
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"PK\x07\x08",
)
_BINARY_MAGIC_PREFIXES = (
    b"%PDF-",
    b"\x1f\x8b",
    b"7z\xbc\xaf\x27\x1c",
    b"Rar!\x1a\x07",
    b"\x7fELF",
    b"MZ",
)


@dataclass(frozen=True)
class FileProbe:
    kind: Literal["text", "image", "binary"]
    encoding: str | None
    mime_type: str | None
    size_bytes: int


@dataclass(frozen=True)
class ParsedDocument:
    kind: Literal["docx", "pdf"]
    file_bytes: bytes
    text: str


def _build_probe_script(path: str) -> str:
    return f"""
import base64
import json
from pathlib import Path

path = Path({path!r})
with path.open("rb") as file_obj:
    sample = file_obj.read({_FILE_SNIFF_BYTES})
print(
    json.dumps(
        {{
            "size_bytes": path.stat().st_size,
            "sample_b64": base64.b64encode(sample).decode("ascii"),
        }}
    )
)
""".strip()


def _build_text_read_script(
    path: str,
    *,
    encoding: str,
    offset: int | None,
    limit: int | None,
) -> str:
    start_expr = "0" if offset is None else str(offset)
    limit_expr = "None" if limit is None else str(limit)
    return f"""
import json
from pathlib import Path

path = Path({path!r})
start = {start_expr}
limit = {limit_expr}
end = None if limit is None else start + limit
lines = []
with path.open("r", encoding={encoding!r}, newline="") as file_obj:
    for index, line in enumerate(file_obj):
        if index < start:
            continue
        if end is not None and index >= end:
            break
        lines.append(line)
content = "".join(lines)
print(json.dumps({{"content": content}}, ensure_ascii=False))
""".strip()


def _build_image_read_script(path: str) -> str:
    return f"""
import base64
import json
from pathlib import Path

path = Path({path!r})
data = path.read_bytes()
print(
    json.dumps(
        {{
            "size_bytes": len(data),
            "base64": base64.b64encode(data).decode("ascii"),
        }}
    )
)
""".strip()


def _looks_like_text(decoded: str) -> bool:
    if not decoded:
        return True

    disallowed = 0
    printable = 0
    for char in decoded:
        if char in "\n\r\t\f\b":
            printable += 1
            continue
        if char.isprintable():
            printable += 1
        code = ord(char)
        if (0 <= code < 32) or (127 <= code < 160):
            disallowed += 1

    total = max(len(decoded), 1)
    return disallowed / total <= 0.02 and printable / total >= 0.85


def detect_text_encoding(sample: bytes) -> str | None:
    if not sample:
        return "utf-8"

    if b"\x00" in sample and not sample.startswith(_UTF_BOMS):
        odd_bytes = sample[1::2]
        even_bytes = sample[0::2]
        odd_zero_ratio = odd_bytes.count(0) / max(len(odd_bytes), 1)
        even_zero_ratio = even_bytes.count(0) / max(len(even_bytes), 1)
        if odd_zero_ratio < 0.8 and even_zero_ratio < 0.8:
            return None

    for encoding in _TEXT_ENCODINGS:
        try:
            decoded = sample.decode(encoding)
        except UnicodeDecodeError as exc:
            # Probe samples can end in the middle of a multibyte sequence.
            # When the decode failure only happens at the sample tail, trim a few
            # bytes and retry so UTF-8 text is not misclassified as binary.
            if exc.start >= len(sample) - 4:
                decoded = ""
                for trim_bytes in range(1, min(4, len(sample)) + 1):
                    try:
                        decoded = sample[:-trim_bytes].decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                if not decoded:
                    continue
            else:
                continue
        if _looks_like_text(decoded):
            return encoding

    return None


def read_local_text_range_sync(
    path: str,
    *,
    encoding: str,
    offset: int | None,
    limit: int | None,
) -> str:
    lines: list[str] = []
    start = 0 if offset is None else offset
    end = None if limit is None else start + limit
    with open(path, encoding=encoding, newline="") as file_obj:
        for index, line in enumerate(file_obj):
            if index < start:
                continue
            if end is not None and index >= end:
                break
            lines.append(line)
    return "".join(lines)


async def read_local_text_range(
    path: str,
    *,
    encoding: str,
    offset: int | None,
    limit: int | None,
) -> str:
    return await to_thread(
        read_local_text_range_sync,
        path,
        encoding=encoding,
        offset=offset,
        limit=limit,
    )


async def _exec_python_json(
    booter: ComputerBooter,
    script: str,
    *,
    action: str,
) -> dict:
    result = await booter.python.exec(script)
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if not isinstance(data, dict):
        raise RuntimeError(f"{action} failed: invalid result format")
    output = data.get("output") if isinstance(data.get("output"), dict) else {}
    if not isinstance(output, dict):
        raise RuntimeError(f"{action} failed: invalid output format")
    error_text = str(data.get("error", "") or result.get("error", "") or "").strip()
    if error_text:
        raise RuntimeError(f"{action} failed: {error_text}")

    text = str(output.get("text", "") or "").strip()
    if not text:
        raise RuntimeError(f"{action} failed: empty output")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{action} failed: invalid JSON output") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"{action} failed: invalid JSON payload")
    return payload


async def _probe_local_file(path: str) -> dict[str, str | int]:
    def _run() -> dict[str, str | int]:
        file_path = Path(path)
        with file_path.open("rb") as file_obj:
            sample = file_obj.read(_FILE_SNIFF_BYTES)
        return {
            "size_bytes": file_path.stat().st_size,
            "sample_b64": base64.b64encode(sample).decode("ascii"),
        }

    return await to_thread(_run)


async def _read_local_image_base64(path: str) -> dict[str, str | int]:
    def _run() -> dict[str, str | int]:
        data = Path(path).read_bytes()
        return {
            "size_bytes": len(data),
            "base64": base64.b64encode(data).decode("ascii"),
        }

    return await to_thread(_run)


async def _read_local_file_bytes(path: str) -> bytes:
    return await to_thread(Path(path).read_bytes)


async def _compress_image_bytes_to_base64(data: bytes) -> dict[str, str | int]:
    def _run() -> dict[str, str | int]:
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        compressed_path = Path(
            _compress_image_sync(
                data,
                temp_dir,
                IMAGE_COMPRESS_DEFAULT_MAX_SIZE,
                IMAGE_COMPRESS_DEFAULT_QUALITY,
                IMAGE_COMPRESS_DEFAULT_OPTIMIZE,
            )
        )
        try:
            compressed_bytes = compressed_path.read_bytes()
        finally:
            compressed_path.unlink(missing_ok=True)

        return {
            "size_bytes": len(compressed_bytes),
            "base64": base64.b64encode(compressed_bytes).decode("ascii"),
            "mime_type": "image/jpeg",
        }

    return await to_thread(_run)


def _detect_image_mime(sample: bytes) -> str | None:
    if sample.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if sample.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if sample.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if sample.startswith(b"BM"):
        return "image/bmp"
    if sample.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if sample.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    if len(sample) >= 12 and sample[:4] == b"RIFF" and sample[8:12] == b"WEBP":
        return "image/webp"
    if len(sample) >= 12 and sample[4:12] in (b"ftypavif", b"ftypavis"):
        return "image/avif"
    return None


def _looks_like_known_binary(sample: bytes) -> bool:
    return any(sample.startswith(prefix) for prefix in _BINARY_MAGIC_PREFIXES)


def _looks_like_pdf(path: str, sample: bytes) -> bool:
    return Path(path).suffix.lower() == ".pdf" or sample.startswith(b"%PDF-")


def _looks_like_zip_container(sample: bytes) -> bool:
    return any(sample.startswith(prefix) for prefix in _ZIP_MAGIC_PREFIXES)


def _is_docx_bytes(file_bytes: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False

    if "[Content_Types].xml" not in names:
        return False

    return any(name.startswith("word/") for name in names)


async def _parse_local_docx_text(file_bytes: bytes, file_name: str) -> str:
    from astrbot.core.knowledge_base.parsers.markitdown_parser import (
        MarkitdownParser,
    )

    result = await MarkitdownParser().parse(file_bytes, file_name)
    return result.text


async def _parse_local_pdf_text(file_bytes: bytes, file_name: str) -> str:
    from astrbot.core.knowledge_base.parsers.pdf_parser import PDFParser

    result = await PDFParser().parse(file_bytes, file_name)
    return result.text


async def _parse_local_supported_document(
    path: str,
    sample: bytes,
) -> ParsedDocument | None:
    file_name = Path(path).name
    if _looks_like_pdf(path, sample):
        file_bytes = await _read_local_file_bytes(path)
        text = await _parse_local_pdf_text(file_bytes, file_name)
        return ParsedDocument(kind="pdf", file_bytes=file_bytes, text=text)

    if Path(path).suffix.lower() == ".docx" or _looks_like_zip_container(sample):
        file_bytes = await _read_local_file_bytes(path)
        if not _is_docx_bytes(file_bytes):
            return None
        text = await _parse_local_docx_text(file_bytes, file_name)
        return ParsedDocument(kind="docx", file_bytes=file_bytes, text=text)

    return None


def _probe_file(sample: bytes, *, size_bytes: int) -> FileProbe:
    if image_mime := _detect_image_mime(sample):
        return FileProbe(
            kind="image",
            encoding=None,
            mime_type=image_mime,
            size_bytes=size_bytes,
        )

    if _looks_like_known_binary(sample):
        return FileProbe(
            kind="binary",
            encoding=None,
            mime_type=None,
            size_bytes=size_bytes,
        )

    if encoding := detect_text_encoding(sample):
        return FileProbe(
            kind="text",
            encoding=encoding,
            mime_type="text/plain",
            size_bytes=size_bytes,
        )

    return FileProbe(
        kind="binary",
        encoding=None,
        mime_type=None,
        size_bytes=size_bytes,
    )


def _validate_text_output(content: str) -> str | None:
    content_bytes = len(content.encode("utf-8"))
    if content_bytes > _MAX_FILE_READ_BYTES:
        return (
            "Error reading file: "
            f"output exceeds {_MAX_FILE_READ_BYTES} bytes "
            f"({content_bytes} bytes). Use `offset`, `limit` to narrow the read window."
        )

    content_tokens = _TOKEN_COUNTER.count_tokens(
        [Message(role="user", content=content)]
    )
    if content_tokens > _MAX_FILE_READ_TOKENS:
        return (
            "Error reading file: "
            f"output exceeds {_MAX_FILE_READ_TOKENS} tokens "
            f"({content_tokens} tokens). Use `offset`, `limit` to narrow the read window."
        )

    return None


def _text_exceeds_read_thresholds(content: str) -> bool:
    return _validate_text_output(content) is not None


def _validate_full_text_read_request(probe: FileProbe) -> str | None:
    if probe.size_bytes > _MAX_TEXT_FILE_FULL_READ_BYTES:
        return (
            "Error reading file: "
            f"text file exceeds {_MAX_TEXT_FILE_FULL_READ_BYTES} bytes "
            f"({probe.size_bytes} bytes). Use `offset` and `limit` to narrow the read window."
        )
    return None


def _slice_text_by_lines(
    content: str,
    *,
    offset: int | None,
    limit: int | None,
) -> str:
    if offset is None and limit is None:
        return content

    lines = content.splitlines(keepends=True)
    start = 0 if offset is None else offset
    end = None if limit is None else start + limit
    return "".join(lines[start:end])


async def _store_converted_text_for_workspace(
    *,
    workspace_dir: str,
    original_path: str,
    original_bytes: bytes,
    content: str,
) -> str:
    def _run() -> str:
        original_name = Path(original_path).name
        digest_suffix = hashlib.md5(original_bytes).hexdigest()[-6:]
        target_dir = (
            Path(workspace_dir) / "converted_files" / f"{original_name}_{digest_suffix}"
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "text.txt"
        target_path.write_text(content, encoding="utf-8")
        return str(target_path)

    return await to_thread(_run)


def _build_converted_text_notice(
    converted_text_path: str,
    *,
    selection_returned: bool,
    selection_too_large: bool = False,
) -> str:
    if selection_too_large:
        return (
            "Converted text was saved to "
            f"`{converted_text_path}`. The requested output is still too large to "
            "return directly. Read or grep that file with a narrower window."
        )

    if selection_returned:
        return (
            "Full converted text is also available at "
            f"`{converted_text_path}`. Read or grep that file with a narrow "
            "window for additional reads."
        )

    return (
        "Converted text was saved to "
        f"`{converted_text_path}` because the parsed document is too large to "
        "return directly. Read or grep that file with a narrow window."
    )


async def _read_local_supported_document_result(
    *,
    path: str,
    parsed_document: ParsedDocument,
    workspace_dir: str | None,
    offset: int | None,
    limit: int | None,
) -> ToolExecResult:
    content = parsed_document.text
    if not content:
        return "No content found at the requested line offset."

    if not _text_exceeds_read_thresholds(content):
        selected_content = _slice_text_by_lines(content, offset=offset, limit=limit)
        if not selected_content:
            return "No content found at the requested line offset."
        if validation_error := _validate_text_output(selected_content):
            return validation_error
        return selected_content

    if not workspace_dir:
        return (
            "Error reading file: parsed document exceeds the read output limit and "
            "no workspace is available for storing converted text."
        )

    converted_text_path = await _store_converted_text_for_workspace(
        workspace_dir=workspace_dir,
        original_path=path,
        original_bytes=parsed_document.file_bytes,
        content=content,
    )

    if offset is None and limit is None:
        return _build_converted_text_notice(
            converted_text_path,
            selection_returned=False,
        )

    selected_content = _slice_text_by_lines(content, offset=offset, limit=limit)
    if not selected_content:
        return (
            "No content found at the requested line offset. "
            + _build_converted_text_notice(
                converted_text_path,
                selection_returned=False,
            )
        )

    notice = _build_converted_text_notice(
        converted_text_path,
        selection_returned=True,
    )
    combined_output = f"{selected_content}\n\n[{notice}]"
    if _validate_text_output(combined_output):
        if _validate_text_output(selected_content):
            return _build_converted_text_notice(
                converted_text_path,
                selection_returned=False,
                selection_too_large=True,
            )
        return selected_content

    return combined_output


async def read_file_tool_result(
    booter: ComputerBooter,
    *,
    local_mode: bool,
    path: str,
    offset: int | None,
    limit: int | None,
    workspace_dir: str | None = None,
) -> ToolExecResult:
    if local_mode:
        probe_payload = await _probe_local_file(path)
    else:
        probe_payload = await _exec_python_json(
            booter,
            _build_probe_script(path),
            action="file probe",
        )
    sample_b64 = str(probe_payload.get("sample_b64", "") or "")
    sample = base64.b64decode(sample_b64) if sample_b64 else b""
    size_bytes = int(probe_payload.get("size_bytes", 0) or 0)
    probe = _probe_file(sample, size_bytes=size_bytes)

    if local_mode:
        try:
            parsed_document = await _parse_local_supported_document(path, sample)
        except Exception as exc:
            return f"Error reading file: failed to parse document: {exc}"

        if parsed_document is not None:
            return await _read_local_supported_document_result(
                path=path,
                parsed_document=parsed_document,
                workspace_dir=workspace_dir,
                offset=offset,
                limit=limit,
            )

    if probe.kind == "binary":
        return "Error reading file: binary files are not supported by this tool."

    if probe.kind == "image":
        if local_mode:
            image_payload = await _read_local_image_base64(path)
        else:
            image_payload = await _exec_python_json(
                booter,
                _build_image_read_script(path),
                action="image read",
            )
        raw_base64_data = str(image_payload.get("base64", "") or "")
        if not raw_base64_data:
            return "Error reading file: image payload is empty."
        raw_bytes = base64.b64decode(raw_base64_data)
        compressed_payload = await _compress_image_bytes_to_base64(raw_bytes)
        base64_data = str(compressed_payload.get("base64", "") or "")
        if not base64_data:
            return "Error reading file: compressed image payload is empty."
        return mcp.types.CallToolResult(
            content=[
                mcp.types.ImageContent(
                    type="image",
                    data=base64_data,
                    mimeType=str(
                        compressed_payload.get("mime_type", "") or "image/jpeg"
                    ),
                )
            ]
        )

    if offset is None and limit is None:
        if validation_error := _validate_full_text_read_request(probe):
            return validation_error

    if local_mode:
        content = await read_local_text_range(
            path,
            encoding=probe.encoding or "utf-8",
            offset=offset,
            limit=limit,
        )
    else:
        text_payload = await _exec_python_json(
            booter,
            _build_text_read_script(
                path,
                encoding=probe.encoding or "utf-8",
                offset=offset,
                limit=limit,
            ),
            action="text read",
        )
        content = str(text_payload.get("content", "") or "")

    if not content:
        return "No content found at the requested line offset."

    if validation_error := _validate_text_output(content):
        return validation_error

    return content
