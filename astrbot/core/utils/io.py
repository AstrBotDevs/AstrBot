import asyncio
import base64
import logging
import os
import shutil
import socket
import ssl
import time
import uuid
import zipfile
from ipaddress import IPv4Address, IPv6Address, ip_address
from pathlib import Path

import aiohttp
import anyio
import certifi
import psutil
from PIL import Image

from .astrbot_path import get_astrbot_data_path, get_astrbot_path, get_astrbot_temp_path

logger = logging.getLogger("astrbot")


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
    if not os.path.exists(file_path):
        return True
    shutil.rmtree(file_path, onerror=on_error)
    return True


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


async def download_file(url: str, path: str, show_progress: bool = False) -> None:
    """从指定 url 下载文件到指定路径 path"""
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
            async with session.get(url, timeout=1800) as resp:
                if resp.status != 200:
                    raise Exception(f"下载文件失败: {resp.status}")
                total_size = int(resp.headers.get("content-length", 0))
                downloaded_size = 0
                start_time = time.time()
                if show_progress:
                    logger.info(
                        f"文件大小: {total_size / 1024:.2f} KB | 文件地址: {url}"
                    )
                async with await anyio.open_file(path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(8192)
                        if not chunk:
                            break
                        await f.write(chunk)
                        downloaded_size += len(chunk)
                        if show_progress:
                            elapsed_time = (
                                time.time() - start_time
                                if time.time() - start_time > 0
                                else 1
                            )
                            speed = downloaded_size / 1024 / elapsed_time  # KB/s
                            logger.info(
                                f"\r下载进度: {downloaded_size / total_size:.2%} 速度: {speed:.2f} KB/s"
                            )
    except (aiohttp.ClientConnectorSSLError, aiohttp.ClientConnectorCertificateError):
        # 关闭SSL验证(仅在证书验证失败时作为fallback)
        logger.warning(
            "SSL 证书验证失败,已关闭 SSL 验证(不安全,仅用于临时下载)｡请检查目标服务器的证书配置｡"
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
                    logger.info(
                        f"文件大小: {total_size / 1024:.2f} KB | 文件地址: {url}"
                    )
                async with await anyio.open_file(path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(8192)
                        if not chunk:
                            break
                        await f.write(chunk)
                        downloaded_size += len(chunk)
                        if show_progress:
                            elapsed_time = time.time() - start_time
                            speed = downloaded_size / 1024 / elapsed_time  # KB/s
                            logger.info(
                                f"\r下载进度: {downloaded_size / total_size:.2%} 速度: {speed:.2f} KB/s"
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
            async with session.get(url, timeout=3) as resp:
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


async def get_dashboard_version():
    # First check user data directory (manually updated / downloaded dashboard).
    dist_dir = os.path.join(get_astrbot_data_path(), "dist")
    if not await anyio.Path(dist_dir).exists():
        # Fall back to the dist bundled inside the installed wheel.
        _bundled = Path(get_astrbot_path()) / "astrbot" / "dashboard" / "dist"
        if _bundled.exists():
            dist_dir = str(_bundled)
    if await anyio.Path(dist_dir).exists():
        version_file = os.path.join(dist_dir, "assets", "version")
        if await anyio.Path(version_file).exists():
            async with await anyio.open_file(version_file, encoding="utf-8") as f:
                v = (await f.read()).strip()
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
        zip_path = anyio.Path(get_astrbot_data_path()) / "dashboard.zip"
    else:
        zip_path = anyio.Path(path)

    # 缓存机制
    cache_dir = anyio.Path(get_astrbot_data_path()) / "cache"
    if not await cache_dir.exists():
        await cache_dir.mkdir(parents=True, exist_ok=True)

    use_cache = False

    # Only use cache if not requesting "latest" (we don't know the version yet)
    if not latest and version:
        cache_name = f"dashboard_{version}.zip"
        cache_path = cache_dir / cache_name

        if await cache_path.exists():
            logger.info(f"发现本地缓存的管理面板文件: {cache_path}")
            try:
                with zipfile.ZipFile(str(cache_path), "r") as z:
                    if z.testzip() is None:
                        logger.info("缓存文件校验通过,将直接使用缓存｡")
                        if str(cache_path) != str(zip_path):
                            shutil.copy(str(cache_path), str(zip_path))
                        use_cache = True
                    else:
                        logger.warning("缓存文件损坏,将重新下载｡")
                        await cache_path.unlink()
            except zipfile.BadZipFile:
                logger.warning("缓存文件损坏 (BadZipFile),将重新下载｡")
                await cache_path.unlink()
        if not use_cache:
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
                    try:
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
                    except Exception as e:
                        if not latest:
                            logger.warning(
                                f"下载指定版本({version})失败: {e},尝试下载最新版本｡"
                            )
                            await download_dashboard(
                                path=path,
                                extract_path=extract_path,
                                latest=True,
                                proxy=proxy,
                            )
                            return
                        raise e
            else:
                url = f"https://github.com/AstrBotDevs/astrbot-release-harbour/releases/download/release-{version}/dist.zip"
                logger.info(f"准备下载指定版本的 AstrBot WebUI: {url}")
                if proxy:
                    url = f"{proxy}/{url}"
                await download_file(url, str(zip_path), show_progress=True)

            # 下载完成后存入缓存
        try:
            save_cache_name = None
            if not latest and version:
                save_cache_name = f"dashboard_{version}.zip"
            else:
                # 尝试从下载的文件中读取版本号
                try:
                    with zipfile.ZipFile(zip_path, "r") as z:
                        for v_path in ["dist/assets/version", "assets/version"]:
                            try:
                                with z.open(v_path) as f:
                                    v = f.read().decode("utf-8").strip()
                                    save_cache_name = f"dashboard_{v}.zip"
                                    break
                            except KeyError:
                                continue
                except Exception:
                    pass

            if save_cache_name:
                cache_save_path = cache_dir / save_cache_name
                if str(zip_path) != str(cache_save_path):
                    shutil.copy(zip_path, cache_save_path)
                    logger.info(f"已缓存管理面板文件至: {cache_save_path}")
        except Exception as e:
            logger.warning(f"缓存管理面板文件失败: {e}")

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_path)
