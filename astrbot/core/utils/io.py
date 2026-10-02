import asyncio
import base64
import inspect
import logging
import os
import shutil
import socket
import ssl
import time
import uuid
from ipaddress import IPv4Address, IPv6Address, ip_address
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiohttp
import anyio
import certifi
import psutil
from PIL import Image

from .astrbot_path import get_astrbot_temp_path

logger = logging.getLogger("astrbot")


def _safe_url_for_log(url: str) -> str:
    """Return a URL summary that omits query strings and fragments."""
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        filename = Path(unquote(parsed.path or "")).name
        suffix = f" file={filename!r}" if filename else ""
        return f"{parsed.scheme} URL host={parsed.netloc!r}{suffix} len={len(url)}"
    return f"URL len={len(url)}"


def _get_aiohttp():
    import aiohttp

    return aiohttp


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
        img.save(p)
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
    aiohttp = _get_aiohttp()
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
                    async with await anyio.open_file(path, "wb") as f:
                        await f.write(await resp.read())
                    return path
            else:
                async with session.get(url) as resp:
                    if not path:
                        return save_temp_img(await resp.read())
                    async with await anyio.open_file(path, "wb") as f:
                        await f.write(await resp.read())
                    return path
    except (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError):
        # 关闭SSL验证(仅在证书验证失败时作为fallback)
        logger.warning(
            f"SSL certificate verification failed for {_safe_url_for_log(url)}. "
            "Disabling SSL verification (CERT_NONE) as a fallback. "
            "This is insecure and exposes the application to man-in-the-middle attacks. "
            "Please investigate and resolve certificate issues.",
        )
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        async with aiohttp.ClientSession() as session:
            if post:
                async with session.post(url, json=post_data, ssl=ssl_context) as resp:
                    if not path:
                        return save_temp_img(await resp.read())
                    async with await anyio.open_file(path, "wb") as f:
                        await f.write(await resp.read())
                    return path
            else:
                async with session.get(url, ssl=ssl_context) as resp:
                    if not path:
                        return save_temp_img(await resp.read())
                    async with await anyio.open_file(path, "wb") as f:
                        await f.write(await resp.read())
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


async def download_file(
    url: str,
    path: str,
    show_progress: bool = False,
    progress_callback=None,
    allow_insecure_ssl_fallback: bool = True,
) -> None:
    """Download a remote file to a local path."""
    aiohttp = _get_aiohttp()
    try:
        ssl_context = ssl.create_default_context(
            cafile=certifi.where(),
        )  # 使用 certifi 提供的 CA 证书
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(
            trust_env=True,
            connector=connector,
        ) as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=1800),
            ) as resp:
                _raise_for_download_status(resp, url)
                total_size = int(resp.headers.get("content-length", 0))
                downloaded_size = 0
                start_time = time.time()
                if show_progress:
                    logger.info(
                        "Downloading: %s | Size: %.2f KB",
                        _safe_url_for_log(url),
                        total_size / 1024,
                    )
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
                async with await anyio.open_file(path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(8192)
                        if not chunk:
                            break
                        await f.write(chunk)
                        downloaded_size += len(chunk)
                        elapsed_time = (
                            time.time() - start_time
                            if time.time() - start_time > 0
                            else 1
                        )
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
                            logger.info(
                                f"Progress: {percent:.2%} Speed: {speed:.2f} KB/s",
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
    except (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError):
        if not allow_insecure_ssl_fallback:
            raise
        # 关闭SSL验证(仅在证书验证失败时作为fallback)
        logger.warning(
            f"SSL certificate verification failed for {_safe_url_for_log(url)}. "
            "Falling back to unverified connection (CERT_NONE). "
            "This is insecure and exposes the application to man-in-the-middle attacks. "
            "Please investigate certificate issues with the remote server.",
        )
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                url,
                ssl=ssl_context,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp,
        ):
            _raise_for_download_status(resp, url)
            total_size = int(resp.headers.get("content-length", 0))
            downloaded_size = 0
            start_time = time.time()
            if show_progress:
                logger.info(
                    "Size: %.2f KB | URL: %s",
                    total_size / 1024,
                    _safe_url_for_log(url),
                )
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
            async with await anyio.open_file(path, "wb") as f:
                while True:
                    chunk = await resp.content.read(8192)
                    if not chunk:
                        break
                    await f.write(chunk)
                    downloaded_size += len(chunk)
                    elapsed_time = (
                        time.time() - start_time if time.time() - start_time > 0 else 1
                    )
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
                        logger.info(
                            f"Progress: {percent:.2%} Speed: {speed:.2f} KB/s",
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
    if show_progress:
        logger.info("下载完成")


def file_to_base64(file_path: str) -> str:
    with open(file_path, "rb") as f:
        data_bytes = f.read()
        base64_str = base64.b64encode(data_bytes).decode()
    return "base64://" + base64_str


def get_local_ip_addresses() -> list[IPv4Address | IPv6Address]:
    net_interfaces = psutil.net_if_addrs()
    network_ips: list[IPv4Address | IPv6Address] = []

    for _, addrs in net_interfaces.items():
        for addr in addrs:
            if addr.family == socket.AF_INET:
                network_ips.append(ip_address(addr.address))
            elif addr.family == socket.AF_INET6:
                # 过滤掉 IPv6 的 link-local 地址(fe80:...)
                ip = ip_address(addr.address.split("%")[0])  # 处理带 zone index 的情况
                if not ip.is_link_local:
                    network_ips.append(ip)

    return network_ips


async def get_public_ip_address() -> list[IPv4Address | IPv6Address]:
    urls = [
        "https://api64.ipify.org",
        "https://ident.me",
        "https://ifconfig.me",
        "https://icanhazip.com",
    ]
    found_ips: dict[int, IPv4Address | IPv6Address] = {}

    async def fetch(session: aiohttp.ClientSession, url: str):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    raw_ip = (await resp.text()).strip()
                    ip = ip_address(raw_ip)
                    if ip.version not in found_ips:
                        found_ips[ip.version] = ip
        except Exception as e:
            # Ignore errors from individual services so that a single failing
            # endpoint does not prevent discovering the public IP from others.
            logger.debug("Failed to fetch public IP from %s: %s", url, e)

    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session, url) for url in urls]
        await asyncio.gather(*tasks)

    # 返回找到的所有 IP 对象列表
    return list(found_ips.values())
