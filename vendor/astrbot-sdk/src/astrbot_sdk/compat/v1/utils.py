"""Legacy astrbot.core.utils shims that are safe inside an isolated Runner.

Only pure local helpers live here (HTTP download, temp files, path
derivations, asyncio locks). Utilities that touch Host state keep failing
loudly through the core-import blocker.
"""

from __future__ import annotations

import asyncio
import base64
import os
import shutil
import socket
import ssl
import time
import urllib.request
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, urlsplit


def _temp_dir() -> Path:
    """Return the Runner-local AstrBot temp directory, creating it."""
    path = Path(os.environ.get("ASTRBOT_DATA_PATH", ".")) / "temp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_dir(dir_path: str | Path) -> None:
    """Ensure the directory exists (legacy astrbot.core.utils.io parity)."""
    Path(dir_path).mkdir(parents=True, exist_ok=True)


def remove_dir(file_path: str) -> bool:
    """Remove one file or directory tree; legacy io parity."""
    if not os.path.lexists(file_path):
        return True
    if os.path.isfile(file_path) or os.path.islink(file_path):
        os.remove(file_path)
    else:
        shutil.rmtree(file_path, ignore_errors=True)
    return True


def port_checker(port: int, host: str = "localhost") -> bool:
    """Return whether a TCP connection to host:port succeeds."""
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sk.settimeout(1)
    try:
        sk.connect((host, port))
        sk.close()
        return True
    except Exception:
        sk.close()
        return False


def file_to_base64(file_path: str) -> str:
    """Read one local file and return its base64 encoding."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def get_local_ip_addresses() -> list[str]:
    """Return the host's local IPv4 addresses."""
    addresses: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            if info[0] == socket.AF_INET:
                addr = info[4][0]
                if addr not in addresses:
                    addresses.append(addr)
    except socket.gaierror:
        pass
    if "127.0.0.1" not in addresses:
        addresses.append("127.0.0.1")
    return addresses


def save_temp_img(img: Any) -> str:
    """Save a PIL image or raw bytes to a temp file; return the path."""
    timestamp = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    target = _temp_dir() / f"io_temp_img_{timestamp}.jpg"
    if hasattr(img, "save"):
        img.save(str(target))
    else:
        target.write_bytes(bytes(img))
    return str(target)


def _urlopen_request(url: str, post_data: dict | None) -> urllib.request.Request:
    # urllib honors http_proxy/https_proxy environment variables by default,
    # matching the old core's trust_env behavior.
    if post_data is not None:
        import json

        return urllib.request.Request(
            url,
            data=json.dumps(post_data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    return urllib.request.Request(url, headers={"User-Agent": "astrbot"})


async def download_image_by_url(
    url: str,
    post: bool = False,
    post_data: dict | None = None,
    path: str | None = None,
) -> str:
    """Download an image and return the local path (legacy io parity)."""

    def _download() -> str:
        request = _urlopen_request(url, post_data if post else None)
        with urllib.request.urlopen(
            request,
            timeout=30,
            context=ssl.create_default_context(),
        ) as resp:
            data = resp.read()
        if path:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            target = _temp_dir() / f"io_temp_img_{uuid.uuid4().hex[:8]}.jpg"
        target.write_bytes(data)
        return str(target)

    return await asyncio.to_thread(_download)


async def download_file(
    url: str,
    path: str,
    show_progress: bool = False,
    progress_callback: Any = None,
    allow_insecure_ssl_fallback: bool = True,
) -> None:
    """Download a remote file to a local path (legacy io parity)."""

    def _download() -> None:
        request = _urlopen_request(url, None)
        context = ssl.create_default_context()
        try:
            response = urllib.request.urlopen(request, timeout=60, context=context)
        except ssl.SSLError:
            if not allow_insecure_ssl_fallback:
                raise
            insecure = ssl.create_default_context()
            insecure.check_hostname = False
            insecure.verify_mode = ssl.CERT_NONE
            response = urllib.request.urlopen(request, timeout=60, context=insecure)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with response, open(target, "wb") as handle:
            shutil.copyfileobj(response, handle)

    await asyncio.to_thread(_download)


class SessionLockManager:
    """Per-session asyncio lock manager (legacy session_lock parity)."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @asynccontextmanager
    async def acquire_lock(self, session_id: str):
        """Hold the lock for one session id inside the context."""
        lock = self._locks[session_id]
        async with lock:
            yield


session_lock_manager = SessionLockManager()


def coerce_int_config(
    value: object,
    *,
    default: int,
    min_value: int | None = None,
    field_name: str | None = None,
    source: str = "config",
    warn: bool = True,
) -> int:
    """Coerce a config value to int, mirroring the Host helper.

    Args:
        value: Raw config value.
        default: Fallback when coercion fails.
        min_value: Optional lower bound; values below fall back to default.
        field_name: Field label used in warnings.
        source: Source label used in warnings.
        warn: Whether to log a warning on fallback.

    Returns:
        The coerced int, or default on failure.
    """
    import logging

    label = f"'{field_name}'" if field_name else "value"
    parsed: int
    ok = True
    if isinstance(value, bool):
        parsed = default
        ok = False
    elif isinstance(value, int):
        parsed = value
    else:
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            parsed = default
            ok = False
    if ok and min_value is not None and parsed < min_value:
        parsed = default
        ok = False
    if not ok and warn:
        logging.getLogger("astrbot_sdk.compat").warning(
            "%s %s should be numeric, got %r. Fallback to %s.",
            source,
            label,
            value,
            default,
        )
    return parsed


def is_file_uri(value: object) -> bool:
    """Return whether a value is a ``file:`` URI."""
    if not isinstance(value, str):
        return False
    try:
        return urlsplit(value).scheme.lower() == "file"
    except ValueError:
        return False


def file_uri_to_path(file_uri: str) -> str:
    """Normalize file URIs to local filesystem paths."""
    from urllib.request import url2pathname

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
    if (
        len(path) >= 4
        and path[0] in ("/", "\\")
        and path[2] == ":"
        and path[1].isalpha()
    ):
        path = path[1:]
    elif os.name != "nt" and path.startswith("//"):
        path = "/" + path.lstrip("/")
    return str(Path(path))


def describe_media_ref(media_ref: object | None) -> str:
    """Return a log-safe description of a media reference."""
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

    return f"local path or payload len={ref_len}"
