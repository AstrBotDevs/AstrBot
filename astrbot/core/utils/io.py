import base64
import logging
import os
import shutil
import socket
import ssl
import time
import uuid
import zipfile
from pathlib import Path

import aiohttp
import certifi
import psutil
from PIL import Image

from .astrbot_path import get_astrbot_data_path, get_astrbot_path, get_astrbot_temp_path

logger = logging.getLogger("astrbot")


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
            f"SSL certificate verification failed for {url}. "
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


async def download_file(url: str, path: str, show_progress: bool = False) -> None:
    """从指定 url 下载文件到指定路径 path"""
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
                if resp.status != 200:
                    logger.error(
                        f"Failed to download file from {url}. HTTP status code: {resp.status}"
                    )
                total_size = int(resp.headers.get("content-length", 0))
                downloaded_size = 0
                start_time = time.time()
                if show_progress:
                    print(f"Downloading: {url} | Size: {total_size / 1024:.2f} KB")
                with open(path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if show_progress:
                            elapsed_time = (
                                time.time() - start_time
                                if time.time() - start_time > 0
                                else 1
                            )
                            speed = downloaded_size / 1024 / elapsed_time  # KB/s
                            print(
                                f"\rProgress: {downloaded_size / total_size:.2%} Speed: {speed:.2f} KB/s",
                                end="",
                            )
    except (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError):
        # 关闭SSL验证（仅在证书验证失败时作为fallback）
        logger.warning(
            f"SSL certificate verification failed for {url}. "
            "Falling back to unverified connection (CERT_NONE). "
        )
        logger.warning(
            f"SSL certificate verification failed for {url}. "
            "Falling back to unverified connection (CERT_NONE). "
            "This is insecure and exposes the application to man-in-the-middle attacks. "
            "Please investigate certificate issues with the remote server."
        )
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        async with aiohttp.ClientSession() as session:
            async with session.get(url, ssl=ssl_context, timeout=120) as resp:
                total_size = int(resp.headers.get("content-length", 0))
                downloaded_size = 0
                start_time = time.time()
                if show_progress:
                    print(f"Size: {total_size / 1024:.2f} KB | URL: {url}")
                with open(path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if show_progress:
                            elapsed_time = time.time() - start_time
                            speed = downloaded_size / 1024 / elapsed_time  # KB/s
                            print(
                                f"\rProgress: {downloaded_size / total_size:.2%} Speed: {speed:.2f} KB/s",
                                end="",
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


async def get_dashboard_version():
    # First check user data directory (manually updated / downloaded dashboard).
    dist_dir = os.path.join(get_astrbot_data_path(), "dist")
    if not os.path.exists(dist_dir):
        # Fall back to the dist bundled inside the installed wheel.
        _bundled = Path(get_astrbot_path()) / "astrbot" / "dashboard" / "dist"
        if _bundled.exists():
            dist_dir = str(_bundled)
    if os.path.exists(dist_dir):
        version_file = os.path.join(dist_dir, "assets", "version")
        if os.path.exists(version_file):
            with open(version_file, encoding="utf-8") as f:
                v = f.read().strip()
                return v
    return None


async def download_dashboard(
    path: str | None = None,
    extract_path: str = "data",
    latest: bool = True,
    version: str | None = None,
    proxy: str | None = None,
) -> None:
    """下载管理面板文件"""
    if path is None:
        zip_path = Path(get_astrbot_data_path()).absolute() / "dashboard.zip"
    else:
        zip_path = Path(path).absolute()

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
            )
    else:
        url = f"https://github.com/AstrBotDevs/astrbot-release-harbour/releases/download/release-{version}/dist.zip"
        logger.info(f"Downloading AstrBot WebUI from {url}")
        if proxy:
            url = f"{proxy}/{url}"
        await download_file(url, str(zip_path), show_progress=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_path)
