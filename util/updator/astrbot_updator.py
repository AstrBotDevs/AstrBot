import os, psutil, sys, zipfile, shutil, time
from util.updator.zip_updator import ReleaseInfo, RepoZipUpdator
from SparkleLogging.utils.core import LogManager
from logging import Logger
from type.config import VERSION
from util.io import on_error, download_file

logger: Logger = LogManager.GetLogger(log_name='astrbot')

class AstrBotUpdator(RepoZipUpdator):
    def __init__(self):
        self.MAIN_PATH = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
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
    
    def _reboot(self, delay: int = None):
        if delay: time.sleep(delay)
        py = sys.executable
        self.terminate_child_processes()
        py = py.replace(" ", "\\ ")
        os.execl(py, py, *sys.argv)
        
    def check_update(self, url: str, current_version: str) -> ReleaseInfo:
        return super().check_update(self.ASTRBOT_RELEASE_API, VERSION)
        
    def update(self, reboot = False, latest = True, version = None):
        update_data = self.fetch_release_info(self.ASTRBOT_RELEASE_API, latest)
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
            # self.download_from_repo_url("temp", file_url)
            download_file(file_url, "temp.zip")
            self.unzip_file("temp.zip", self.MAIN_PATH)
        except BaseException as e:
            raise e
        
        if reboot:
            self._reboot()
            
    def unzip_file(self, zip_path: str, target_dir: str):
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
