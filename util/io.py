import os
import ssl
import shutil
import socket
import time
import aiohttp
import requests

from PIL import Image
from SparkleLogging.utils.core import LogManager
from logging import Logger

logger: Logger = LogManager.GetLogger(log_name='astrbot')


def on_error(func, path, exc_info):
    '''
    a callback of the rmtree function.
    '''
    print(f"remove {path} failed.")
    import stat
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise
    
def remove_dir(file_path) -> bool:
    if not os.path.exists(file_path): return True
    try:
        shutil.rmtree(file_path, onerror=on_error)
        return True
    except BaseException as e:
        logger.error(f"删除文件/文件夹 {file_path} 失败: {str(e)}")
        return False
    
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
    

def save_temp_img(img: Image) -> str:
    os.makedirs("data/temp", exist_ok=True)
    # 获得文件创建时间，清除超过1小时的
    try:
        for f in os.listdir("data/temp"):
            path = os.path.join("data/temp", f)
            if os.path.isfile(path):
                ctime = os.path.getctime(path)
                if time.time() - ctime > 3600:
                    os.remove(path)
    except Exception as e:
        print(f"清除临时文件失败: {e}")

    # 获得时间戳
    timestamp = int(time.time())
    p = f"data/temp/{timestamp}.jpg"

    if isinstance(img, Image.Image):
        img.save(p)
    else:
        with open(p, "wb") as f:
            f.write(img)
    logger.info(f"保存临时图片: {p}")
    return p

async def download_image_by_url(url: str, post: bool = False, post_data: dict = None) -> str:
    '''
    下载图片, 返回 path
    '''
    try:
        logger.info(f"下载图片: {url}")
        async with aiohttp.ClientSession() as session:
            if post:
                async with session.post(url, json=post_data) as resp:
                    return save_temp_img(await resp.read())
            else:
                async with session.get(url) as resp:
                    return save_temp_img(await resp.read())
    except aiohttp.client_exceptions.ClientConnectorSSLError as e:
        # 关闭SSL验证
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        async with aiohttp.ClientSession(trust_env=False) as session:
            if post:
                async with session.get(url, ssl=ssl_context) as resp:
                    return save_temp_img(await resp.read())
            else:
                async with session.get(url, ssl=ssl_context) as resp:
                    return save_temp_img(await resp.read())
    except Exception as e:
        raise e
    
def download_file(url: str, path: str):
    '''
    从指定 url 下载文件到指定路径 path
    '''
    try:
        logger.info(f"下载文件: {url}")
        with requests.get(url, stream=True) as r:
            with open(path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        raise e


def get_local_ip_addresses():
    ip = ''
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except BaseException as e:
        pass
    finally:
        s.close()
    return ip
