import base64
import inspect
import logging
import os
import shutil
import socket
import ssl
import stat
import tempfile
import time
import uuid
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlparse

import aiohttp
import certifi
import psutil
from PIL import Image

from .astrbot_path import get_astrbot_temp_path

logger = logging.getLogger("astrbot")


def _safe_url_for_log(url: str) -> str:
    """Return a URL summary that omits query strings and fragments.

    Args:
        url: URL that may contain signed query parameters.

    Returns:
        A short description suitable for logs.
    """

    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        filename = Path(unquote(parsed.path or "")).name
        suffix = f" file={filename!r}" if filename else ""
        return f"{parsed.scheme} URL host={parsed.netloc!r}{suffix} len={len(url)}"
    return f"URL len={len(url)}"


def on_error(func, path, exc_info) -> None:
    """A callback of the rmtree function."""
    import stat

    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise exc_info[1]


def remove_dir(file_path: str) -> bool:
    if not os.path.lexists(file_path):
        return True
    if os.path.isfile(file_path) or os.path.islink(file_path):
        os.remove(file_path)
    else:
        shutil.rmtree(file_path, onerror=on_error)
    return True


def ensure_dir(dir_path: str | Path) -> None:
    """确保目录存在。如果路径处存在非目录的文件或损坏的符号链接，则先将其删除。"""
    p = Path(dir_path)
    if (p.exists() or p.is_symlink()) and not p.is_dir():
        logger.warning(
            f"Path {p} exists but is not a directory; removing it before creating "
            "the directory."
        )
        try:
            if p.is_dir():
                shutil.rmtree(p, onerror=on_error)
            else:
                p.unlink()
        except Exception as e:
            logger.error(f"Failed to remove conflicting path {p}: {e!s}")
            raise RuntimeError(f"Could not remove conflicting path {p}: {e!s}") from e

    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create directory {p}: {e!s}")
        raise RuntimeError(f"Could not create directory {p}: {e!s}") from e


def port_checker(port: int, host: str = "localhost") -> bool:
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sk.settimeout(1)
    try:
        sk.connect((host, port))
        sk.close()
        return True
    except Exception:
        sk.close()
        return False


def save_temp_img(img: Image.Image | bytes) -> str:
    temp_dir = get_astrbot_temp_path()
    # 获得时间戳
    timestamp = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    p = os.path.join(temp_dir, f"io_temp_img_{timestamp}.jpg")

    if isinstance(img, Image.Image):
        cast(Image.Image, img).save(p)
    else:
        with open(p, "wb") as f:
            f.write(img)
    return p


async def download_image_by_url(
    url: str,
    post: bool = False,
    post_data: dict | None = None,
    path: str | None = None,
) -> str:
    """下载图片, 返回 path"""
    try:
        ssl_context = ssl.create_default_context(
            cafile=certifi.where(),
        )  # 使用 certifi 提供的 CA 证书
        connector = aiohttp.TCPConnector(ssl=ssl_context)  # 使用 certifi 的根证书
        async with aiohttp.ClientSession(
            trust_env=True,
            connector=connector,
        ) as session:
            if post:
                async with session.post(url, json=post_data) as resp:
                    if not path:
                        return save_temp_img(await resp.read())
                    with open(path, "wb") as f:
                        f.write(await resp.read())
                    return path
            else:
                async with session.get(url) as resp:
                    if not path:
                        return save_temp_img(await resp.read())
                    with open(path, "wb") as f:
                        f.write(await resp.read())
                    return path
    except (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError):
        # 关闭SSL验证（仅在证书验证失败时作为fallback）
        logger.warning(
            f"SSL certificate verification failed for {_safe_url_for_log(url)}. "
            "Disabling SSL verification (CERT_NONE) as a fallback. "
            "This is insecure and exposes the application to man-in-the-middle attacks. "
            "Please investigate and resolve certificate issues."
        )
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        async with aiohttp.ClientSession() as session:
            if post:
                async with session.post(url, json=post_data, ssl=ssl_context) as resp:
                    if not path:
                        return save_temp_img(await resp.read())
                    with open(path, "wb") as f:
                        f.write(await resp.read())
                    return path
            else:
                async with session.get(url, ssl=ssl_context) as resp:
                    if not path:
                        return save_temp_img(await resp.read())
                    with open(path, "wb") as f:
                        f.write(await resp.read())
                    return path
    except Exception as e:
        raise e


async def _emit_download_progress(progress_callback, payload: dict) -> None:
    if not progress_callback:
        return
    result = progress_callback(payload)
    if inspect.isawaitable(result):
        await result


class DownloadFileHTTPError(RuntimeError):
    """Raised when a file download returns an unsuccessful HTTP status."""


def _raise_for_download_status(resp, url: str) -> None:
    if resp.status == 200:
        return
    logger.error(
        "Failed to download file from %s. HTTP status code: %s",
        _safe_url_for_log(url),
        resp.status,
    )
    raise DownloadFileHTTPError(
        "Failed to download file from "
        f"{_safe_url_for_log(url)}. HTTP status code: {resp.status}"
    )


async def _download_response_to_file(
    resp,
    file_obj,
    url: str,
    show_progress: bool,
    progress_callback,
    show_downloading_label: bool = True,
) -> None:
    """Write a successful download response to a local file.

    Args:
        resp: aiohttp response object to read from.
        file_obj: Open writable binary file object.
        url: Source URL used for progress events and sanitized errors.
        show_progress: Whether to print progress to stdout.
        progress_callback: Optional callback for progress payloads.
        show_downloading_label: Whether to use the standard download heading.

    """

    total_size = int(resp.headers.get("content-length", 0))
    downloaded_size = 0
    start_time = time.time()
    if show_progress:
        if show_downloading_label:
            print(
                f"Downloading: {_safe_url_for_log(url)} | "
                f"Size: {total_size / 1024:.2f} KB"
            )
        else:
            print(f"Size: {total_size / 1024:.2f} KB | URL: {_safe_url_for_log(url)}")
    await _emit_download_progress(
        progress_callback,
        {
            "url": url,
            "downloaded": 0,
            "total": total_size,
            "percent": 0,
            "speed": 0,
        },
    )
    while True:
        chunk = await resp.content.read(8192)
        if not chunk:
            break
        file_obj.write(chunk)
        downloaded_size += len(chunk)
        elapsed_time = time.time() - start_time if time.time() - start_time > 0 else 1
        speed = downloaded_size / 1024 / elapsed_time  # KB/s
        percent = downloaded_size / total_size if total_size > 0 else 0
        await _emit_download_progress(
            progress_callback,
            {
                "url": url,
                "downloaded": downloaded_size,
                "total": total_size,
                "percent": percent,
                "speed": speed,
            },
        )
        if show_progress:
            print(
                f"\rProgress: {percent:.2%} Speed: {speed:.2f} KB/s",
                end="",
            )
    await _emit_download_progress(
        progress_callback,
        {
            "url": url,
            "downloaded": downloaded_size,
            "total": total_size,
            "percent": 1,
            "speed": 0,
        },
    )


def _publish_download(
    staging_path: Path, target_path: Path, original_stat: os.stat_result | None
) -> None:
    """Publish a completed download without silently changing destination access.

    Args:
        staging_path: Complete file on the destination filesystem.
        target_path: Resolved destination path.
        original_stat: Destination metadata observed before downloading, if present.

    Raises:
        FileExistsError: Another writer changed the destination during the download.
        OSError: Authorization, metadata preservation or replacement failed.
    """
    try:
        current_stat = target_path.stat()
    except FileNotFoundError:
        current_stat = None
    # Ignore atime: another reader must not invalidate this download. The publish
    # section has no awaits, so concurrent tasks cannot race the check and replace.
    if (original_stat is None) != (current_stat is None) or (
        original_stat is not None
        and current_stat is not None
        and any(
            getattr(original_stat, field) != getattr(current_stat, field)
            for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        )
    ):
        raise FileExistsError("Download destination changed while downloading")
    if current_stat is not None:
        # Unlike rename, opening without truncation enforces file-level write
        # authorization, including ACLs. Close before replacing on Windows.
        descriptor = os.open(target_path, os.O_WRONLY)
        os.close(descriptor)
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            # ReplaceFileW preserves the destination DACL and alternate streams.
            # Do not use the flags that ignore ACL/attribute merge failures.
            replace_file = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
            replace_file.argtypes = (
                wintypes.LPCWSTR,
                wintypes.LPCWSTR,
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.LPVOID,
                wintypes.LPVOID,
            )
            replace_file.restype = wintypes.BOOL
            if not replace_file(
                str(target_path), str(staging_path), None, 0, None, None
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            return

        staged_stat = staging_path.stat()
        if (staged_stat.st_uid, staged_stat.st_gid) != (
            current_stat.st_uid,
            current_stat.st_gid,
        ):
            os.chown(staging_path, current_stat.st_uid, current_stat.st_gid)
        if hasattr(os, "listxattr"):
            # Preserve ACLs and other xattrs strictly; capability and integrity
            # attributes authenticate the old bytes and must never be inherited.
            attributes = set(os.listxattr(target_path)) - {
                "security.capability",
                "security.ima",
                "security.evm",
            }
            for attribute in set(os.listxattr(staging_path)) - attributes:
                os.removexattr(staging_path, attribute)
            for attribute in attributes:
                os.setxattr(
                    staging_path, attribute, os.getxattr(target_path, attribute)
                )
        staging_path.chmod(
            stat.S_IMODE(current_stat.st_mode) & ~(stat.S_ISUID | stat.S_ISGID)
        )
    staging_path.replace(target_path)


async def download_file(
    url: str,
    path: str,
    show_progress: bool = False,
    progress_callback=None,
    allow_insecure_ssl_fallback: bool = True,
) -> None:
    """Download a remote file and replace the destination on success.

    Keep the destination intact until the response and progress callbacks have
    completed. Failed or cancelled downloads leave no partial file behind.
    Atomic publication requires write access to the parent directory. A changed
    destination is rejected rather than overwriting a concurrent writer's result.
    Existing ownership and available extended attributes are preserved; POSIX
    privilege/integrity attributes are not transferred to downloaded bytes.

    Args:
        url: Remote URL to download.
        path: Local destination path.
        show_progress: Whether to print progress to stdout.
        progress_callback: Optional callback for progress payloads.
        allow_insecure_ssl_fallback: Whether certificate failures may retry with
            TLS certificate verification disabled.

    Returns:
        None.

    Raises:
        OSError: The destination changed or cannot be safely replaced. Native
            metadata not exposed by the platform APIs is outside this contract.
    """

    # Resolve symlinks as open(path, "wb") does, and stage on the same filesystem
    # so replacement is atomic. Each call owns its own temporary directory.
    target_path = Path(path).resolve()
    try:
        original_stat = target_path.stat()
    except FileNotFoundError:
        original_stat = None
    if original_stat is not None:
        if not stat.S_ISREG(original_stat.st_mode):
            raise ValueError("Download destination must be a regular file")
        descriptor = os.open(target_path, os.O_WRONLY)
        os.close(descriptor)
    with tempfile.TemporaryDirectory(
        prefix=".astrbot-download-", dir=target_path.parent
    ) as staging_dir:
        staging_path = Path(staging_dir) / "download.part"
        try:
            ssl_context = ssl.create_default_context(
                cafile=certifi.where(),
            )  # Use certifi's CA certificates.
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with aiohttp.ClientSession(
                trust_env=True,
                connector=connector,
            ) as session:
                async with session.get(url, timeout=1800) as resp:
                    _raise_for_download_status(resp, url)
                    with staging_path.open("wb") as f:
                        await _download_response_to_file(
                            resp,
                            f,
                            url,
                            show_progress,
                            progress_callback,
                        )
        except (
            aiohttp.ClientConnectorSSLError,
            aiohttp.ClientConnectorCertificateError,
        ):
            if not allow_insecure_ssl_fallback:
                raise
            # Retry without verification only after certificate failures.
            logger.warning(
                f"SSL certificate verification failed for {_safe_url_for_log(url)}. "
                "Falling back to unverified connection (CERT_NONE). "
            )
            logger.warning(
                f"SSL certificate verification failed for {_safe_url_for_log(url)}. "
                "Falling back to unverified connection (CERT_NONE). "
                "This is insecure and exposes the application to man-in-the-middle attacks. "
                "Please investigate certificate issues with the remote server."
            )
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            async with aiohttp.ClientSession() as session:
                async with session.get(url, ssl=ssl_context, timeout=120) as resp:
                    _raise_for_download_status(resp, url)
                    with staging_path.open("wb") as f:
                        await _download_response_to_file(
                            resp,
                            f,
                            url,
                            show_progress,
                            progress_callback,
                            show_downloading_label=False,
                        )
        _publish_download(staging_path, target_path, original_stat)
    if show_progress:
        print()


def file_to_base64(file_path: str) -> str:
    with open(file_path, "rb") as f:
        data_bytes = f.read()
        base64_str = base64.b64encode(data_bytes).decode()
    return "base64://" + base64_str


def get_local_ip_addresses():
    net_interfaces = psutil.net_if_addrs()
    network_ips = []

    for interface, addrs in net_interfaces.items():
        for addr in addrs:
            if addr.family == socket.AF_INET:  # 使用 socket.AF_INET 代替 psutil.AF_INET
                network_ips.append(addr.address)

    return network_ips
