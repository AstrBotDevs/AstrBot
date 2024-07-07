import sys, os, zipfile, shutil
import requests
import psutil
from type.config import VERSION
from SparkleLogging.utils.core import LogManager
from logging import Logger

from util.general_utils import download_file

logger: Logger = LogManager.GetLogger(log_name='astrbot-core')

ASTRBOT_RELEASE_API = "https://api.github.com/repos/Soulter/AstrBot/releases"
MIRROR_ASTRBOT_RELEASE_API = "https://api.soulter.top/releases" # 0-10 分钟的缓存时间

def get_main_path():
    ret = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    return ret

def terminate_child_processes():
    try:
        parent = psutil.Process(os.getpid())
        children = parent.children(recursive=True)
        logger.info(f"正在终止 {len(children)} 个子进程。")
        for child in children:
            logger.info(f"正在终止子进程 {child.pid}")
            child.terminate()
            try:
                child.wait(timeout=3)
            except psutil.NoSuchProcess:
                continue
            except psutil.TimeoutExpired:
                logger.info(f"子进程 {child.pid} 没有被正常终止, 正在强行杀死。")
                child.kill()
    except psutil.NoSuchProcess:
        pass

def _reboot():
    py = sys.executable
    terminate_child_processes()
    os.execl(py, py, *sys.argv)
    
def request_release_info(latest: bool = True, url: str = ASTRBOT_RELEASE_API, mirror_url: str = MIRROR_ASTRBOT_RELEASE_API) -> list:
    '''
    请求版本信息。
    返回一个列表，每个元素是一个字典，包含版本号、发布时间、更新内容、commit hash等信息。
    '''
    try:
        result = requests.get(mirror_url).json()
    except BaseException as e:
        result = requests.get(url).json()
    try:
        if not result: return []
        if latest:
            ret = github_api_release_parser([result[0]])
        else:
            ret = github_api_release_parser(result)
    except BaseException as e:
        logger.error(f"解析版本信息失败: {result}")
        raise Exception(f"解析版本信息失败: {result}")
    return ret
        
def github_api_release_parser(releases: list) -> list:
    '''
    解析 GitHub API 返回的 releases 信息。
    返回一个列表，每个元素是一个字典，包含版本号、发布时间、更新内容、commit hash等信息。
    '''
    ret = []
    for release in releases:
        version = release['name']
        commit_hash = ''
        # 规范是: v3.0.7.xxxxxx，其中xxxxxx为 commit hash
        _t = version.split(".")
        if len(_t) == 4:
            commit_hash = _t[3]
        ret.append({
            "version": release['name'],
            "published_at": release['published_at'],
            "body": release['body'],
            "commit_hash": commit_hash,
            "tag_name": release['tag_name'],
            "zipball_url": release['zipball_url']
        })
    return ret

def compare_version(v1: str, v2: str) -> int:
    '''
    比较两个版本号的大小。
    返回 1 表示 v1 > v2，返回 -1 表示 v1 < v2，返回 0 表示 v1 = v2。
    '''
    v1 = v1.replace('v', '')
    v2 = v2.replace('v', '')
    v1 = v1.split('.')
    v2 = v2.split('.')

    for i in range(3):
        if int(v1[i]) > int(v2[i]):
            return 1
        elif int(v1[i]) < int(v2[i]):
            return -1
    return 0

def check_update() -> str:
    update_data = request_release_info()
    tag_name = update_data[0]['tag_name']
    logger.debug(f"当前版本: v{VERSION}")
    logger.debug(f"最新版本: {tag_name}")

    if compare_version(VERSION, tag_name) >= 0:
        return "当前已经是最新版本。"

    update_info = f"""# 当前版本
v{VERSION}

# 最新版本
{update_data[0]['version']}

# 发布时间
{update_data[0]['published_at']}

# 更新内容
---
{update_data[0]['body']}
---"""
    return update_info
    
def update_project(reboot: bool = False, 
                   latest: bool = True,
                   version: str = ''):
    update_data = request_release_info(latest)
    if latest:
        latest_version = update_data[0]['tag_name']
        if compare_version(VERSION, latest_version) >= 0:
            raise Exception("当前已经是最新版本。")
        else:
            try:
                download_file(update_data[0]['zipball_url'], "temp.zip")
                unzip_file("temp.zip", get_main_path())
                if reboot: _reboot()
            except BaseException as e:
                raise e
    else:
        # 更新到指定版本
        flag = False
        print(f"请求更新到指定版本: {version}")
        for data in update_data:
            if data['tag_name'] == version:
                try:
                    download_file(data['zipball_url'], "temp.zip")
                    unzip_file("temp.zip", get_main_path())
                    flag = True
                    if reboot: _reboot()
                except BaseException as e:
                    raise e
        if not flag:
            raise Exception("未找到指定版本。")

def unzip_file(zip_path: str, target_dir: str):
    '''
    解压缩文件, 并将压缩包内**第一个**文件夹内的文件移动到 target_dir
    '''
    os.makedirs(target_dir, exist_ok=True)
    update_dir = ""
    logger.info(f"解压文件: {zip_path}")
    with zipfile.ZipFile(zip_path, 'r') as z:
        update_dir = z.namelist()[0]
        z.extractall(target_dir)

    avoid_dirs = ["logs", "data", "configs", "temp_plugins", update_dir]
    # copy addons/plugins to the target_dir temporarily
    if os.path.exists(os.path.join(target_dir, "addons/plugins")):
        logger.info("备份插件目录：从 addons/plugins 到 temp_plugins")
        shutil.copytree(os.path.join(target_dir, "addons/plugins"), "temp_plugins")

    files = os.listdir(os.path.join(target_dir, update_dir))
    for f in files:
        logger.info(f"移动更新文件/目录: {f}")
        if os.path.isdir(os.path.join(target_dir, update_dir, f)):
            if f in avoid_dirs: continue
            if os.path.exists(os.path.join(target_dir, f)):
                shutil.rmtree(os.path.join(target_dir, f), onerror=on_error)
        else:
            if os.path.exists(os.path.join(target_dir, f)):
                os.remove(os.path.join(target_dir, f))
        shutil.move(os.path.join(target_dir, update_dir, f), target_dir)
    
    # move back
    if os.path.exists("temp_plugins"):
        logger.info("恢复插件目录：从 temp_plugins 到 addons/plugins")
        shutil.rmtree(os.path.join(target_dir, "addons/plugins"), onerror=on_error)
        shutil.move("temp_plugins", os.path.join(target_dir, "addons/plugins"))
    
    try:
        logger.info(f"删除临时更新文件: {zip_path} 和 {os.path.join(target_dir, update_dir)}")
        shutil.rmtree(os.path.join(target_dir, update_dir), onerror=on_error)
        os.remove(zip_path)
    except:
        logger.warn(f"删除更新文件失败，可以手动删除 {zip_path} 和 {os.path.join(target_dir, update_dir)}")

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