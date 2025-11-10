import aiohttp
import certifi
import ssl
import time
from loguru import logger


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
