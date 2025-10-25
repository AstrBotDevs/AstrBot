import os
import ssl
import shutil
import socket
import time
import aiohttp
import base64
import zipfile
import uuid
import psutil
import logging

import certifi

from typing import Union

from PIL import Image
from .astrbot_path import get_astrbot_data_path

logger = logging.getLogger("astrbot")


def on_error(func, path, exc_info):
    """
    a callback of the rmtree function.
    """
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


def save_temp_img(img: Union[Image.Image, bytes], save_name: str | None = None) -> str:
    """
    保存临时图片：
    - 自动清理超过 12 小时的临时文件
    - 如果提供了 save_name（含扩展名），直接用作文件名；否则按规则自动生成
    - 根据图片模式自动选择保存格式（RGBA -> PNG，其余 -> JPG）
    """
    temp_dir = Path(get_astrbot_data_path()) / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # 清理超过 12 小时的旧文件
    now = time.time()
    try:
        for f in temp_dir.iterdir():
            if f.is_file() and now - f.stat().st_ctime > 3600 * 12:
                f.unlink(missing_ok=True)
    except Exception as e:
        print(f"清除临时文件失败: {e}")

    # 决定文件名
    if save_name:  # 外部指定了名字
        file_name = save_name
        path = temp_dir / file_name
    else:  # 自动生成
        timestamp = f"{int(now)}_{uuid.uuid4().hex[:8]}"
        if isinstance(img, Image.Image) and img.mode in ("RGBA", "LA"):
            file_name = f"{timestamp}.png"
        else:
            file_name = f"{timestamp}.jpg"
        path = temp_dir / file_name

    # 保存文件
    if isinstance(img, Image.Image):
        if path.suffix.lower() == ".png" or img.mode in ("RGBA", "LA"):
            img.save(path, format="PNG")
        else:
            img.convert("RGB").save(path, format="JPEG", quality=95)
    else:  # bytes
        path.write_bytes(img)

    return str(path)


async def download_image_by_url(
    url: str, post: bool = False, post_data: dict = None, path=None, save_name=None
) -> str:
    """
    下载图片, 返回 path
    """
    try:
        ssl_context = ssl.create_default_context(
            cafile=certifi.where()
        )  # 使用 certifi 提供的 CA 证书
        connector = aiohttp.TCPConnector(ssl=ssl_context)  # 使用 certifi 的根证书
        async with aiohttp.ClientSession(
            trust_env=True, connector=connector
        ) as session:
            if post:
                async with session.post(url, json=post_data) as resp:
                    if not path:
                        return save_temp_img(await resp.read(), save_name)
                    else:
                        with open(path, "wb") as f:
                            f.write(await resp.read())
                        return path
            else:
                async with session.get(url) as resp:
                    if not path:
                        return save_temp_img(await resp.read(), save_name)
                    else:
                        with open(path, "wb") as f:
                            f.write(await resp.read())
                        return path
    except (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError):
        # 关闭SSL验证
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers("DEFAULT")
        async with aiohttp.ClientSession() as session:
            if post:
                async with session.get(url, ssl=ssl_context) as resp:
                    return save_temp_img(await resp.read(), save_name)
            else:
                async with session.get(url, ssl=ssl_context) as resp:
                    return save_temp_img(await resp.read(), save_name)
    except Exception as e:
        raise e

async def download_file(url: str, path: str, show_progress: bool = False):
    """
    从指定 url 下载文件到指定路径 path
    """
    try:
        ssl_context = ssl.create_default_context(
            cafile=certifi.where()
        )  # 使用 certifi 提供的 CA 证书
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(
            trust_env=True, connector=connector
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
                            elapsed_time = time.time() - start_time
                            speed = downloaded_size / 1024 / elapsed_time  # KB/s
                            print(
                                f"\r下载进度: {downloaded_size / total_size:.2%} 速度: {speed:.2f} KB/s",
                                end="",
                            )
    except (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError):
        # 关闭SSL验证
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers("DEFAULT")
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
            with open(version_file, "r") as f:
                v = f.read().strip()
                return v
    return None


async def download_dashboard(
    path: str | None = None,
    extract_path: str = "data",
    latest: bool = True,
    version: str | None = None,
    proxy: str | None = None,
):
    """下载管理面板文件"""
    if path is None:
        path = os.path.join(get_astrbot_data_path(), "dashboard.zip")

    if latest or len(str(version)) != 40:
        ver_name = "latest" if latest else version
        dashboard_release_url = f"https://astrbot-registry.soulter.top/download/astrbot-dashboard/{ver_name}/dist.zip"
        logger.info(
            f"准备下载指定发行版本的 AstrBot WebUI 文件: {dashboard_release_url}"
        )
        try:
            await download_file(dashboard_release_url, path, show_progress=True)
        except BaseException as _:
            if latest:
                dashboard_release_url = "https://github.com/Soulter/AstrBot/releases/latest/download/dist.zip"
            else:
                dashboard_release_url = f"https://github.com/Soulter/AstrBot/releases/download/{version}/dist.zip"
            if proxy:
                dashboard_release_url = f"{proxy}/{dashboard_release_url}"
            await download_file(dashboard_release_url, path, show_progress=True)
    else:
        url = f"https://github.com/AstrBotDevs/astrbot-release-harbour/releases/download/release-{version}/dist.zip"
        logger.info(f"准备下载指定版本的 AstrBot WebUI: {url}")
        if proxy:
            url = f"{proxy}/{url}"
        await download_file(url, path, show_progress=True)
    with zipfile.ZipFile(path, "r") as z:
        z.extractall(extract_path)
