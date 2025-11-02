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

from .astrbot_path import get_astrbot_data_path

logger = logging.getLogger("astrbot")


def on_error(func, path, exc_info):
    """A callback of the rmtree function."""
    import stat

    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise exc_info[1]


def remove_dir(file_path: str) -> bool:
    if not os.path.exists(file_path):
        return True
    shutil.rmtree(file_path, onerror=on_error)
    return True


def port_checker(port: int, host: str = "localhost"):
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sk.settimeout(1)
    try:
        sk.connect((host, port))
        sk.close()
        return True
    except Exception:
        sk.close()
        return False


def save_temp_img(img: Image.Image | str) -> str:
    temp_dir = os.path.join(get_astrbot_data_path(), "temp")
    # 获得文件创建时间，清除超过 12 小时的
    try:
        for f in os.listdir(temp_dir):
            path = os.path.join(temp_dir, f)
            if os.path.isfile(path):
                ctime = os.path.getctime(path)
                if time.time() - ctime > 3600 * 12:
                    os.remove(path)
    except Exception as e:
        print(f"清除临时文件失败: {e}")

    # 获得时间戳
    timestamp = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    p = os.path.join(temp_dir, f"{timestamp}.jpg")

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


async def download_file(url: str, path: str, show_progress: bool = False):
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
                    raise Exception(f"下载文件失败: {resp.status}")
                total_size = int(resp.headers.get("content-length", 0))
                downloaded_size = 0
                start_time = time.time()
                if show_progress:
                    print(f"文件大小: {total_size / 1024:.2f} KB | 文件地址: {url}")
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
                                f"\r下载进度: {downloaded_size / total_size:.2%} 速度: {speed:.2f} KB/s",
                                end="",
                            )
    except (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError):
        # 关闭SSL验证（仅在证书验证失败时作为fallback）
        logger.warning(
            "SSL 证书验证失败，已关闭 SSL 验证（不安全，仅用于临时下载）。请检查目标服务器的证书配置。"
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
                    print(f"文件大小: {total_size / 1024:.2f} KB | 文件地址: {url}")
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
                                f"\r下载进度: {downloaded_size / total_size:.2%} 速度: {speed:.2f} KB/s",
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
    dist_dir = os.path.join(get_astrbot_data_path(), "dist")
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
            f"准备下载指定发行版本的 AstrBot WebUI 文件: {dashboard_release_url}",
        )
        try:
            await download_file(
                dashboard_release_url,
                str(zip_path),
                show_progress=True,
            )
        except BaseException as _:
            if latest:
                dashboard_release_url = "https://github.com/AstrBotDevs/AstrBot/releases/latest/download/dist.zip"
            else:
                dashboard_release_url = f"https://github.com/AstrBotDevs/AstrBot/releases/download/{version}/dist.zip"
            if proxy:
                dashboard_release_url = f"{proxy}/{dashboard_release_url}"
            await download_file(
                dashboard_release_url,
                str(zip_path),
                show_progress=True,
            )
    else:
        url = f"https://github.com/AstrBotDevs/astrbot-release-harbour/releases/download/release-{version}/dist.zip"
        logger.info(f"准备下载指定版本的 AstrBot WebUI: {url}")
        if proxy:
            url = f"{proxy}/{url}"
        await download_file(url, str(zip_path), show_progress=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_path)
