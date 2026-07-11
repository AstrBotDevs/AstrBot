import base64
import inspect
import logging
import os
import re
import shutil
import socket
import ssl
import time
import uuid
import zipfile
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlparse

import aiohttp
import certifi
import psutil
from PIL import Image

from .astrbot_path import get_astrbot_data_path, get_astrbot_path, get_astrbot_temp_path
from .version_comparator import VersionComparator

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
        logger.warning(f"路径 {p} 已存在但不是目录，正在清理以创建目录。")
        try:
            if p.is_dir():
                shutil.rmtree(p, onerror=on_error)
            else:
                p.unlink()
        except Exception as e:
            logger.error(f"清理冲突路径 {p} 失败: {e!s}")
            raise RuntimeError(f"无法清理冲突路径 {p}：{e!s}") from e

    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"创建目录 {p} 失败: {e!s}")
        raise RuntimeError(f"无法创建目录 {p}：{e!s}") from e


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


async def download_file(
    url: str,
    path: str,
    show_progress: bool = False,
    progress_callback=None,
    allow_insecure_ssl_fallback: bool = True,
) -> None:
    """Download a remote file to a local path.

    Args:
        url: Remote URL to download.
        path: Local destination path.
        show_progress: Whether to print progress to stdout.
        progress_callback: Optional callback for progress payloads.
        allow_insecure_ssl_fallback: Whether certificate failures may retry with
            TLS certificate verification disabled.

    Returns:
        None.
    """

    try:
        ssl_context = ssl.create_default_context(
            cafile=certifi.where(),
        )  # 使用 certifi 提供的 CA 证书
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(
            trust_env=True,
            connector=connector,
        ) as session:
            async with session.get(url, timeout=1800) as resp:
                _raise_for_download_status(resp, url)
                with open(path, "wb") as f:
                    await _download_response_to_file(
                        resp,
                        f,
                        url,
                        show_progress,
                        progress_callback,
                    )
    except (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError):
        if not allow_insecure_ssl_fallback:
            raise
        # 关闭SSL验证（仅在证书验证失败时作为fallback）
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
                with open(path, "wb") as f:
                    await _download_response_to_file(
                        resp,
                        f,
                        url,
                        show_progress,
                        progress_callback,
                        show_downloading_label=False,
                    )
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


def get_dashboard_dist_version(dist_dir: str | Path) -> str | None:
    """Read the WebUI version from a dashboard dist directory.

    Args:
        dist_dir: Dashboard dist directory path.

    Returns:
        The version string from assets/version, or None when unavailable.
    """

    version_file = Path(dist_dir) / "assets" / "version"
    try:
        if version_file.exists():
            return version_file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read WebUI version from %s: %s", version_file, exc)
    return None


def get_bundled_dashboard_dist_path() -> Path:
    return Path(get_astrbot_path()) / "astrbot" / "dashboard" / "dist"


def _normalize_dashboard_version(version: str) -> str:
    version = version.strip()
    if version[:1].lower() == "v":
        version = version[1:]
    if not re.match(
        r"^[0-9]+(?:\.[0-9]+)*"
        r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
        r"(?:\+.+)?$",
        version,
    ):
        raise ValueError(f"invalid dashboard version: {version!r}")
    return version


def is_dashboard_version_compatible(
    dashboard_version: str | None, current_version: str
) -> bool:
    """Check whether a WebUI version matches the current core version.

    Args:
        dashboard_version: Version read from the WebUI assets/version file.
        current_version: Current AstrBot core version.

    Returns:
        True when both versions are valid SemVer values and compare equal.
    """

    if dashboard_version is None:
        return False
    try:
        return (
            VersionComparator.compare_version(
                _normalize_dashboard_version(dashboard_version),
                _normalize_dashboard_version(current_version),
            )
            == 0
        )
    except (TypeError, ValueError):
        return False


def is_dashboard_dist_compatible(dist_dir: str | Path, current_version: str) -> bool:
    """Check whether a WebUI dist is complete and matches the core version.

    Args:
        dist_dir: Dashboard dist directory path.
        current_version: Current AstrBot core version.

    Returns:
        True when the dist has an index file and a compatible assets/version.
    """

    dist_path = Path(dist_dir)
    return (dist_path / "index.html").is_file() and is_dashboard_version_compatible(
        get_dashboard_dist_version(dist_path),
        current_version,
    )


def should_use_bundled_dashboard_dist(
    user_dist: str | Path, current_version: str
) -> bool:
    """Decide whether bundled WebUI should replace a user data dist.

    Args:
        user_dist: Runtime dashboard dist directory under data/.
        current_version: Current AstrBot core version.

    Returns:
        True when user_dist exists but is missing or mismatched against the
        current core version, and bundled WebUI matches the current core version.
    """

    user_dist = Path(user_dist)
    user_version = get_dashboard_dist_version(user_dist)
    bundled_dist = get_bundled_dashboard_dist_path()
    if not user_dist.exists() or not is_dashboard_dist_compatible(
        bundled_dist,
        current_version,
    ):
        return False
    if user_version is None or not (user_dist / "index.html").is_file():
        return True
    try:
        return not is_dashboard_version_compatible(user_version, current_version)
    except (TypeError, ValueError):
        return False


async def get_dashboard_version():
    """Return the effective WebUI version for the current runtime.

    Returns:
        The matching data/dist version, matching bundled version, or the raw
        data/dist version when no compatible bundled WebUI is available.
    """

    from astrbot.core.config.default import VERSION

    # First check user data directory (manually updated / downloaded dashboard).
    dist_dir = os.path.join(get_astrbot_data_path(), "dist")
    if os.path.exists(dist_dir):
        user_version = get_dashboard_dist_version(dist_dir)
        if is_dashboard_dist_compatible(dist_dir, VERSION):
            return user_version

        bundled = get_bundled_dashboard_dist_path()
        if is_dashboard_dist_compatible(bundled, VERSION):
            return get_dashboard_dist_version(bundled)
        return user_version

    bundled = get_bundled_dashboard_dist_path()
    if is_dashboard_dist_compatible(bundled, VERSION):
        return get_dashboard_dist_version(bundled)
    return None


async def download_dashboard(
    path: str | None = None,
    extract_path: str = "data",
    latest: bool = True,
    version: str | None = None,
    proxy: str | None = None,
    progress_callback=None,
    extract: bool = True,
    allow_insecure_ssl_fallback: bool = True,
) -> None:
    """Download dashboard assets and optionally extract them.

    Args:
        path: Destination zip path. Defaults to the AstrBot data directory.
        extract_path: Directory where assets should be extracted.
        latest: Whether to download the latest dashboard build.
        version: Specific release tag or commit hash to download.
        proxy: Optional download proxy prefix.
        progress_callback: Optional callback for download progress payloads.
        extract: Whether to extract the archive after download.
        allow_insecure_ssl_fallback: Whether certificate failures may retry with
            TLS certificate verification disabled.

    Returns:
        None.
    """
    if path is None:
        zip_path = Path(get_astrbot_data_path()).absolute() / "dashboard.zip"
    else:
        zip_path = Path(path).absolute()
    ensure_dir(zip_path.parent)

    if latest or len(str(version)) != 40:
        ver_name = "latest" if latest else version
        dashboard_release_url = f"https://astrbot-registry.soulter.top/download/astrbot-dashboard/{ver_name}/dist.zip"
        logger.info(
            f"Downloading AstrBot WebUI from {dashboard_release_url}",
        )
        try:
            await download_file(
                dashboard_release_url,
                str(zip_path),
                show_progress=True,
                progress_callback=progress_callback,
                allow_insecure_ssl_fallback=allow_insecure_ssl_fallback,
            )
            if not zipfile.is_zipfile(zip_path):
                raise RuntimeError(
                    "Downloaded dashboard package is not a valid ZIP file"
                )
        except BaseException as _:
            if latest:
                # Resolve latest release tag from GitHub API to construct correct asset URL
                ssl_context = ssl.create_default_context(cafile=certifi.where())
                async with aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(ssl=ssl_context),
                    trust_env=True,
                ) as session:
                    async with session.get(
                        "https://api.github.com/repos/AstrBotDevs/AstrBot/releases/latest",
                        timeout=30,
                        headers={"Accept": "application/vnd.github+json"},
                    ) as api_resp:
                        api_resp.raise_for_status()
                        release_data = await api_resp.json()
                        tag = release_data["tag_name"]
            else:
                tag = version
            dashboard_release_url = f"https://github.com/AstrBotDevs/AstrBot/releases/download/{tag}/AstrBot-{tag}-dashboard.zip"
            if proxy:
                dashboard_release_url = f"{proxy}/{dashboard_release_url}"
            await download_file(
                dashboard_release_url,
                str(zip_path),
                show_progress=True,
                progress_callback=progress_callback,
                allow_insecure_ssl_fallback=allow_insecure_ssl_fallback,
            )
            if not zipfile.is_zipfile(zip_path):
                raise RuntimeError(
                    "Downloaded dashboard package is not a valid ZIP file"
                )
    else:
        url = f"https://github.com/AstrBotDevs/astrbot-release-harbour/releases/download/release-{version}/dist.zip"
        logger.info(f"Downloading AstrBot WebUI from {url}")
        if proxy:
            url = f"{proxy}/{url}"
        await download_file(
            url,
            str(zip_path),
            show_progress=True,
            progress_callback=progress_callback,
            allow_insecure_ssl_fallback=allow_insecure_ssl_fallback,
        )
        if not zipfile.is_zipfile(zip_path):
            raise RuntimeError("Downloaded dashboard package is not a valid ZIP file")
    if extract:
        extract_dashboard(zip_path, extract_path)


def extract_dashboard(zip_path: str | Path, extract_path: str | Path = "data") -> None:
    """Extract a downloaded dashboard archive.

    Args:
        zip_path: Dashboard zip archive path.
        extract_path: Directory where the archive contents should be extracted.

    Returns:
        None.
    """

    extract_root = Path(extract_path).resolve()
    ensure_dir(extract_root)
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.infolist():
            target_path = (extract_root / member.filename).resolve()
            if not target_path.is_relative_to(extract_root):
                raise ValueError(
                    f"Unsafe dashboard archive path: {member.filename}",
                )
            z.extract(member, extract_root)
