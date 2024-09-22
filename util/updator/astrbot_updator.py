import os, psutil, sys, time
from util.updator.zip_updator import ReleaseInfo, RepoZipUpdator
from util.log import LogManager
from logging import Logger
from type.config import VERSION
from util.io import on_error, download_file

logger: Logger = LogManager.GetLogger(log_name='astrbot')

class AstrBotUpdator(RepoZipUpdator):
    def __init__(self):
        self.MAIN_PATH = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../"))
        self.ASTRBOT_RELEASE_API = "https://api.github.com/repos/Soulter/AstrBot/releases"

    def terminate_child_processes(self):
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
    
    def _reboot(self, delay: int = None, context = None):
        if os.environ.get('TEST_MODE', 'off') == 'on':
            logger.info("测试模式下不会重启。")
            return
        # if delay: time.sleep(delay)
        py = sys.executable
        context.running = False
        time.sleep(3)
        self.terminate_child_processes()
        py = py.replace(" ", "\\ ")
        try:
            os.execl(py, py, *sys.argv)
        except Exception as e:
            logger.error(f"重启失败（{py}, {e}），请尝试手动重启。")
            raise e
        
    async def check_update(self, url: str, current_version: str) -> ReleaseInfo:
        return await super().check_update(self.ASTRBOT_RELEASE_API, VERSION)
        
    async def update(self, reboot = False, latest = True, version = None):
        update_data = await self.fetch_release_info(self.ASTRBOT_RELEASE_API, latest)
        file_url = None
        
        if latest:
            latest_version = update_data[0]['tag_name']
            if self.compare_version(VERSION, latest_version) >= 0:
                raise Exception("当前已经是最新版本。")
            file_url = update_data[0]['zipball_url']
        else:
            # 更新到指定版本
            print(f"请求更新到指定版本: {version}")
            for data in update_data:
                if data['tag_name'] == version:
                    file_url = data['zipball_url']
            if not file_url:
                raise Exception(f"未找到版本号为 {version} 的更新文件。")
            
        try:
            await download_file(file_url, "temp.zip")
            self.unzip_file("temp.zip", self.MAIN_PATH)
        except BaseException as e:
            raise e
        
        if reboot:
            self._reboot()
