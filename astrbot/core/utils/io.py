import os
import ssl
import shutil
import socket
import time
import aiohttp
import base64
import zipfile

from PIL import Image

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
    except BaseException:
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
    return p

async def download_image_by_url(url: str, post: bool = False, post_data: dict = None) -> str:
    '''
    下载图片, 返回 path
    '''
    try:
        async with aiohttp.ClientSession() as session:
            if post:
                async with session.post(url, json=post_data) as resp:
                    return save_temp_img(await resp.read())
            else:
                async with session.get(url) as resp:
                    return save_temp_img(await resp.read())
    except aiohttp.client_exceptions.ClientConnectorSSLError:
        # 关闭SSL验证
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers('DEFAULT')
        async with aiohttp.ClientSession(trust_env=False) as session:
            if post:
                async with session.get(url, ssl=ssl_context) as resp:
                    return save_temp_img(await resp.read())
            else:
                async with session.get(url, ssl=ssl_context) as resp:
                    return save_temp_img(await resp.read())
    except Exception as e:
        raise e
    
async def download_file(url: str, path: str):
    '''
    从指定 url 下载文件到指定路径 path
    '''
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20) as resp:
                if resp.status != 200:
                    raise Exception(f"下载文件失败: {resp.status}")
                with open(path, 'wb') as f:
                    while True:
                        chunk = await resp.content.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
    except Exception as e:
        raise e

def file_to_base64(file_path: str) -> str:
    with open(file_path, "rb") as f:
        data_bytes = f.read()
        base64_str = base64.b64encode(data_bytes).decode()
    return "base64://" + base64_str

def get_local_ip_addresses():
    ip = ''
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except BaseException:
        pass
    finally:
        s.close()
    return ip

async def download_dashboard():
    '''下载管理面板文件'''
    dashboard_release_url = "https://astrbot-registry.lwl.lol/download/astrbot-dashboard/latest/dist.zip"
    await download_file(dashboard_release_url, "data/dashboard.zip")
    with zipfile.ZipFile("data/dashboard.zip", "r") as z:
        z.extractall("data")