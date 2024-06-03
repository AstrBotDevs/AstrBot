has_git = True
try:
    import git.exc
    from git.repo import Repo
except BaseException as e:
    has_git = False
import sys, os
import requests
import psutil
from type.config import VERSION
from SparkleLogging.utils.core import LogManager
from logging import Logger

logger: Logger = LogManager.GetLogger(log_name='astrbot-core')


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
    
def find_repo() -> Repo:
    if not has_git:
        raise Exception("未安装 GitPython 库，无法进行更新。")
    repo = None
    
    # 由于项目更名过，因此这里需要多次尝试。
    try:
        repo = Repo()
    except git.exc.InvalidGitRepositoryError:
        try:
            repo = Repo(path="QQChannelChatGPT")  
        except git.exc.InvalidGitRepositoryError:
            repo = Repo(path="AstrBot")
    if not repo:
        raise Exception("在已知的目录下未找到项目位置。请联系项目维护者。")
    return repo
    
def request_release_info(latest: bool = True) -> list:
    '''
    请求版本信息。
    返回一个列表，每个元素是一个字典，包含版本号、发布时间、更新内容、commit hash等信息。
    '''
    api_url1 = "https://api.github.com/repos/Soulter/AstrBot/releases"
    api_url2 = "https://api.soulter.top/releases" # 0-10 分钟的缓存时间
    try:
        result = requests.get(api_url2).json()
    except BaseException as e:
        result = requests.get(api_url1).json()
    try:
        if latest:
            ret = github_api_release_parser([result[0]])
        else:
            ret = github_api_release_parser(result)
    except BaseException as e:
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
            "tag_name": release['tag_name']
        })
    return ret

def check_update() -> str:
    repo = find_repo()
    curr_commit = repo.commit().hexsha
    update_data = request_release_info()
    new_commit = update_data[0]['commit_hash']
    print(f"当前版本: {curr_commit}")
    print(f"最新版本: {new_commit}")
    if curr_commit.startswith(new_commit):
        return f"当前已经是最新版本: v{VERSION}"
    else:
        update_info = f"""> 有新版本可用，请及时更新。
# 当前版本
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
    
def update_project(update_data: list,
                   reboot: bool = False, 
                   latest: bool = True,
                   version: str = ''):
    repo = find_repo()
    # update_data = request_release_info(latest)
    if latest:
        # 检查本地commit和最新commit是否一致
        curr_commit = repo.head.commit.hexsha
        new_commit = update_data[0]['commit_hash']
        if curr_commit == '':
            raise Exception("无法获取当前版本号对应的版本位置。请联系项目维护者。")
        if curr_commit.startswith(new_commit):
            raise Exception("当前已经是最新版本。")
        else:
            # 更新到最新版本对应的commit
            try:
                repo.git.fetch()
                repo.git.checkout(update_data[0]['tag_name'], "-f")
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
                    repo.git.fetch()
                    repo.git.checkout(data['tag_name'], "-f")
                    flag = True
                    if reboot: _reboot()
                except BaseException as e:
                    raise e
        if not flag:
            raise Exception("未找到指定版本。")
    
def checkout_branch(branch_name: str):
    repo = find_repo()
    try:
        repo.git.fetch()
        repo.git.checkout(branch_name, "-f")
        repo.git.pull("origin", branch_name, "-f")
        return True
    except BaseException as e:
        raise e