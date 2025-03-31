import os
import ssl
import shutil
import socket
import time
import aiohttp
import base64
import zipfile
import uuid
from pathlib import Path
import psutil
from rich.progress import TimeRemainingColumn, BarColumn, Progress, TextColumn, TransferSpeedColumn, DownloadColumn
import certifi
import asyncio

from typing import Union

from PIL import Image

download_progress_bar = Progress(
    TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
    BarColumn(bar_width=None),
    "[progress.percentage]{task.percentage:>3.1f}%",
    "•",
    DownloadColumn(),
    "•",
    TransferSpeedColumn(),
    "•",
    TimeRemainingColumn(),
    transient=False,
)

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


def remove_dir(file_path) -> bool:
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


def save_temp_img(img: Union[Image.Image, str]) -> str:
    os.makedirs("data/temp", exist_ok=True)
    # 获得文件创建时间，清除超过 12 小时的
    try:
        for f in os.listdir("data/temp"):
            path = os.path.join("data/temp", f)
            if os.path.isfile(path):
                ctime = os.path.getctime(path)
                if time.time() - ctime > 3600 * 12:
                    os.remove(path)
    except Exception as e:
        print(f"清除临时文件失败: {e}")

    # 获得时间戳
    timestamp = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    p = f"data/temp/{timestamp}.jpg"

    if isinstance(img, Image.Image):
        img.save(p)
    else:
        with open(p, "wb") as f:
            f.write(img)
    return p


async def download_image_by_url(
    url: str, post: bool = False, post_data: dict = None, path=None
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
                        return save_temp_img(await resp.read())
                    else:
                        with open(path, "wb") as f:
                            f.write(await resp.read())
                        return path
            else:
                async with session.get(url) as resp:
                    if not path:
                        return save_temp_img(await resp.read())
                    else:
                        with open(path, "wb") as f:
                            f.write(await resp.read())
                        return path
    except aiohttp.client.ClientConnectorSSLError:
        # 关闭SSL验证
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers("DEFAULT")
        async with aiohttp.ClientSession() as session:
            if post:
                async with session.get(url, ssl=ssl_context) as resp:
                    return save_temp_img(await resp.read())
            else:
                async with session.get(url, ssl=ssl_context) as resp:
                    return save_temp_img(await resp.read())
    except Exception as e:
        raise e

async def download_file(url: str, path: str, show_progress: bool = False):
    """
    从指定 url 下载文件到指定路径 path
    """
    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(trust_env=True, connector=connector) as session:
            async with session.get(url, timeout=1800) as resp:
                if resp.status != 200:
                    raise Exception(f"下载文件失败: {resp.status}")
                total_size = int(resp.headers.get("content-length", 0))
                if show_progress:
                    with download_progress_bar as progress:
                        task = progress.add_task(f"[cyan]下载 {url}", total=total_size, filename=Path(path).name)
                        with open(path, "wb") as f:
                            while True:
                                chunk = await resp.content.read(8192)
                                if not chunk:
                                    break
                                f.write(chunk)
                                progress.update(task, advance=len(chunk))
                else:
                    with open(path, "wb") as f:
                        while True:
                            chunk = await resp.content.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
    except aiohttp.client.ClientConnectorSSLError:
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers("DEFAULT")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, ssl=ssl_context, timeout=120) as resp:
                total_size = int(resp.headers.get("content-length", 0))
                if show_progress:
                    with download_progress_bar as progress:
                        task = progress.add_task(f"[cyan]下载 {url}", total=total_size)
                        with open(path, "wb") as f:
                            while True:
                                chunk = await resp.content.read(8192)
                                if not chunk:
                                    break
                                f.write(chunk)
                                progress.update(task, advance=len(chunk))
                else:
                    with open(path, "wb") as f:
                        while True:
                            chunk = await resp.content.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
    if show_progress:
        print("[green]下载完成！")

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
    if os.path.exists("data/dist"):
        if os.path.exists("data/dist/assets/version"):
            with open("data/dist/assets/version", "r") as f:
                v = f.read().strip()
                return v
    return None


async def download_dashboard(retry_times: int = 3, show_progress: bool = True):
    """下载管理面板文件"""
    dashboard_release_url = "https://astrobot-registry.soulter.top/download/astrobot-dashboard/latest/dist.zip"
    github_dashboard_release_url = "https://github.com/Soulter/AstrBot/releases/latest/download/dist.zip"

    for i in range(retry_times):
        try:
            print(f"尝试下载管理面板文件（尝试 {i+1}）")
            await download_file(dashboard_release_url, "data/dashboard.zip", show_progress=show_progress)
            print("下载管理面板文件成功。")
            return
        except Exception as e:
            print(f"下载管理面板文件失败：{type(e).__name__}, {e}")
            print(f"正在尝试第 {i+1} 次下载...")
            if i >= retry_times - 1:
                print(f"下载管理面板文件失败：超过最大重试次数 {retry_times} 次，尝试备用路线...")
                await download_file(github_dashboard_release_url, "data/dashboard.zip", show_progress=show_progress)
                break
            else:
                await asyncio.sleep(2)  # 增加延迟时间
                continue
    else:
        print(f"下载管理面板文件失败：超过最大重试次数 {retry_times} 次")
        raise Exception("下载管理面板文件失败")

    print("下载管理面板文件完成！")
    print("解压管理面板文件中...")
    with zipfile.ZipFile("data/dashboard.zip", "r") as z:
        z.extractall("data")
