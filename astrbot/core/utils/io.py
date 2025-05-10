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

import certifi

from PIL import Image
import toml
from .astrbot_path import get_astrbot_root, get_astrbot_temp_path, get_astrbot_webroot_path


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

def save_temp_img(img: Image.Image | str ) -> str:
    
    temp_dir = get_astrbot_temp_path()
    # 获得文件创建时间，清除超过 12 小时的
    try:
        for f in os.listdir(temp_dir):
            path = temp_dir / f
            if path.is_file():
                ctime = path.stat().st_ctime
                if time.time() - ctime > 3600 * 12:
                    path.unlink()
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
    url: str, post: bool = False, post_data: dict = None, path: Path | None = None
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
    except (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError):
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


async def download_file(url: str, path: Path , show_progress: bool = False):
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

async def get_dashboard_version(root : Path) -> str:
    # dist_dir = os.path.join(get_astrbot_data_path(), "dist")
    dist_dir : Path = root / "webroot" / "dist"
    if dist_dir.exists():
        version_file = dist_dir / "assets" / "version"
        if version_file.exists():
            version = version_file.read_text(encoding="utf-8").strip()
            
    version = "N/A"

    return version

async def download_dashboard(root: Path | None = None) -> str :
    """下载管理面板文件
    """

    if root is None:
        root = get_astrbot_root()

    webroot = get_astrbot_webroot_path()

    dashboard_release_url = "https://astrbot-registry.soulter.top/download/astrbot-dashboard/latest/dist.zip"
    try:
        await download_file(dashboard_release_url, root / "temp" / "dashboard.zip", show_progress=True)
    except BaseException as _:
        dashboard_release_url = (
            "https://github.com/Soulter/AstrBot/releases/latest/download/dist.zip"
        )
        await download_file(dashboard_release_url, root / "temp" / "dashboard.zip", show_progress=True)

    with zipfile.ZipFile(str(root / "temp" / "dashboard.zip"), "r") as z:
        z.extractall(webroot)

    shutil.rmtree(root / "temp")

    # 返回一个版本号 得知道下载得哪个版本吧
    version = await get_dashboard_version(root) 

    # 更新 .astrbot 文件
    metadata = toml.load(root / ".astrbot")
    metadata["dashboard_version"] = version
    with open(root / ".astrbot", "w", encoding="utf-8") as f:
        toml.dump(metadata, f)

    return version

# 和新版的AstrbotFS搭配使用

from .astrbot_path import AstrbotFS
class DashboardManager:
    astrbot_fs: AstrbotFS = AstrbotFS.getAstrbotFS()

    @classmethod
    def get_version(cls) -> str:
        """获取当前版本号"""
        version_file: Path = cls.astrbot_fs.webroot / "dist" / "assets" / "version"
        return version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "N/A"    @classmethod
    
    @classmethod
    def get_latest_version(cls) -> str:
        """获取最新版本号
        
        从GitHub获取AstrBot最新的发布版本号标签名
        例如 "v3.5.8"
        
        Returns:
            str: 最新版本号，若获取失败则返回空字符串
        """
        import requests

        try:
            api_url = "https://api.github.com/repos/AstrBotDevs/AstrBot/releases/latest"
            
            # 发送请求（带超时和用户代理）
            response = requests.get(
                api_url, 
                timeout=10
            )
            
            # 如果请求成功
            if response.status_code == 200:
                data = response.json()
                return data.get("tag_name", "")
            else:
                print(f"获取最新版本号失败: HTTP {response.status_code}")
                return ""
        except Exception as e:
            print(f"获取最新版本号过程中发生错误: {e}")
            return ""

    @classmethod
    def need_update(cls) -> bool:
        """检查是否需要更新"""
        current_version = cls.get_version()
        if current_version == "N/A" or cls.get_latest_version() != current_version:
            """直接看版本是否一致就行了，不一致肯定是有新版本了"""
            return True
        return False    
    
    @classmethod
    async def update(cls) -> None:
        """更新管理面板"""
        from rich.console import Console
        from rich.panel import Panel
        from rich.progress import Progress, TextColumn, BarColumn, TimeRemainingColumn, SpinnerColumn

        console = Console()
        
        # 显示更新开始信息
        console.print(Panel("[bold blue]管理面板更新[/bold blue]", 
                            subtitle="开始更新过程...", 
                            expand=False))

        # 检查当前版本
        current_version = cls.get_version()
        console.print(f"[yellow]当前版本[/yellow]: {current_version}")
        console.print(f"[yellow]正在获取最新版本信息...[/yellow]")
        
        latest_version = cls.get_latest_version()
        console.print(f"[yellow]目标版本[/yellow]: {latest_version or '最新版本'}")
        
        # 显示进度条
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}[/bold blue]"),
            BarColumn(bar_width=40),
            TextColumn("[bold]{task.percentage:.0f}%"),
            TimeRemainingColumn(),
            console=console,
            expand=True
        ) as progress:
            # 删除旧版本任务
            delete_task = progress.add_task("[red]删除旧版本...", total=1)
            
            # 先删除旧的
            if cls.astrbot_fs.webroot.exists():
                try:
                    shutil.rmtree(cls.astrbot_fs.webroot)
                    progress.update(delete_task, completed=1)
                except Exception as e:
                    progress.update(delete_task, completed=1)
                    console.print(f"[bold red]删除旧版本时出错: {e}[/bold red]")
            else:
                progress.update(delete_task, completed=1)
                
            # 下载新版本任务
            download_task = progress.add_task("[green]下载并安装新版本...", total=1)
            
            # 下载新的
            try:
                # 这里使用 await 调用异步方法
                version = await download_dashboard(cls.astrbot_fs.root)
                progress.update(download_task, completed=1)
                
                # 更新完成，显示结果
                console.print(Panel(f"[bold green]管理面板更新成功[/bold green]", 
                                  subtitle=f"当前版本: {version}", 
                                  expand=False))
            except Exception as e:
                progress.update(download_task, completed=1)
                console.print(f"[bold red]下载新版本时出错: {str(e)}[/bold red]")